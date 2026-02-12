from __future__ import annotations

import json
from typing import Any

SQL_GENERATION_SYSTEM_PROMPT = """
你是教务系统 SQL 生成助手。
请基于任务解析结果生成 MySQL 8 可执行 SQL，并严格遵守以下约束：
1) 只输出一个 JSON 对象，不要输出 markdown、解释或多余文本。
2) JSON 必须包含：
   - sql: string
   - entity_mappings: [{type, value, field, reason}]
   - sql_fields: [table.field]
3) sql 必须使用 WITH（CTE）开头。
4) SQL 中字段引用必须使用 table.field；当字段来自 CTE（如 base）时，允许使用 cte_name.field（如 base.course_name）。
5) 原表字段必须来自 kb_field_whitelist；不允许凭空构造字段。
6) 生成时必须参考 kb_schema_hints 中的表描述与字段描述做语义对齐。
7) entity_mappings 必须覆盖输入 entities 的每个实体，并映射到具体 table.field。
8) 若无法可靠映射，不要臆造字段，保持空并由调用方报错。
9) 外层查询如果 FROM base，不得引用 CTE 内部原表名（如 course.xxx），只能引用 base.xxx。
10) 当 hidden_context.probe_samples 提供候选值时，优先用候选值对过滤值做归一化。
11) 文本值归一化顺序：精确匹配 -> 规范化匹配（大小写/空白/常见简称）-> 语义近似匹配。
12) 候选值不唯一时可用 LIKE，但必须叠加其他可确定条件缩小范围，并在 reason 说明原因。
13) entity_mappings.reason 需要说明“原始实体值 -> SQL 实际过滤值”的依据；若依据来自 probe_samples 必须明确注明。
14) 若 hidden_context.hints 含 retry_sql_generation_with_hidden_context 且已有候选值，本轮 SQL 相比 failed_sql 必须体现过滤值修正。
15) SQL 中 table.field 引用与字符串过滤值都必须去除两端空格。
16) 学生名单类查询（detail/ranking）必须保证“一名学生最多一行”。
17) 禁止使用 `SELECT DISTINCT student_no, real_name, score_value ...` 作为去重手段；score_value 不同仍会导致同一学生重复。
18) 名单去重优先模式：
    - 使用 `GROUP BY student.student_no, student.real_name`；或
    - 使用 `EXISTS` 子查询判定 score/attendance 条件，再从 student 主表输出名单。
19) 若需要“原因”字段，必须按学生聚合为一行（例如 `GROUP_CONCAT(DISTINCT ...)`），不要返回同一学生多行固定文案。
20) 若存在 retry_constraints.forbidden_fields，SQL 与 sql_fields 中严禁出现这些字段。
21) 若存在 retry_constraints.field_replacements，必须把 from 字段替换为 to_candidates 中的合法字段，且优先选择语义最贴近字段。
22) 若无法完成替换修复，不要使用非法字段，返回空 SQL 字符串并保持 json 格式有效。

完整输出示例（必须严格输出 JSON，不要附加解释）：
{
  "sql": "WITH base AS (SELECT student.enroll_year, student.gender, class.class_name FROM student JOIN class ON student.class_id = class.id WHERE student.enroll_year = 2022 AND student.gender = '男' AND student.is_deleted = 0 AND class.is_deleted = 0) SELECT base.class_name, COUNT(*) AS student_count FROM base GROUP BY base.class_name ORDER BY student_count DESC",
  "entity_mappings": [
    {"type": "grade", "value": "22级", "field": "student.enroll_year", "reason": "根据字段描述“入学年份（常见问法：22级）”映射"},
    {"type": "gender", "value": "男生", "field": "student.gender", "reason": "根据字段描述“性别（男/女等）”映射"}
  ],
  "sql_fields": [
    "student.enroll_year",
    "student.gender",
    "class.class_name",
    "student.class_id",
    "class.id",
    "student.is_deleted",
    "class.is_deleted"
  ]
}
""".strip()


def _helper_build_retry_constraints(hidden_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """作用：从隐藏上下文提炼可执行的字段修复约束，降低重试阶段字段幻觉。"""
    if not isinstance(hidden_context, dict):
        return None

    field_candidates_raw = hidden_context.get("field_candidates")
    if not isinstance(field_candidates_raw, list):
        return None

    field_replacements: list[dict[str, Any]] = []
    forbidden_fields: list[str] = []
    seen_forbidden: set[str] = set()
    for item in field_candidates_raw:
        if not isinstance(item, dict):
            continue
        missing_field = str(item.get("missing", "")).strip()
        if not missing_field:
            continue
        missing_key = missing_field.lower()
        if missing_key not in seen_forbidden:
            seen_forbidden.add(missing_key)
            forbidden_fields.append(missing_field)

        candidates_raw = item.get("candidates")
        if not isinstance(candidates_raw, list):
            continue
        candidates: list[str] = []
        seen_candidates: set[str] = set()
        for candidate in candidates_raw:
            candidate_text = str(candidate).strip()
            if not candidate_text:
                continue
            candidate_key = candidate_text.lower()
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            candidates.append(candidate_text)
        if candidates:
            field_replacements.append({"from": missing_field, "to_candidates": candidates[:8]})

    hints = hidden_context.get("hints")
    retry_hint = False
    if isinstance(hints, list):
        retry_hint = any(str(item).strip() == "retry_sql_generation_with_hidden_context" for item in hints)

    failed_sql = str(hidden_context.get("failed_sql", "")).strip() if isinstance(hidden_context, dict) else ""
    constraints = {
        "enabled": True,
        "retry_hint": retry_hint,
        "forbidden_fields": forbidden_fields,
        "field_replacements": field_replacements,
        "failed_sql": failed_sql,
    }
    return constraints


def build_sql_generation_user_prompt(
    rewritten_query: str,
    task: dict[str, Any],
    field_whitelist: list[str],
    alias_pairs: list[dict[str, list[str]]],
    schema_hints: list[dict[str, Any]],
    hidden_context: dict[str, Any] | None = None,
) -> str:
    retry_constraints = _helper_build_retry_constraints(hidden_context)
    payload: dict[str, Any] = {
        "rewritten_query": rewritten_query,
        "task": task,
        "kb_field_whitelist": field_whitelist,
        "alias_hints": alias_pairs,
        "kb_schema_hints": schema_hints,
        "hidden_context": hidden_context,
        "retry_constraints": retry_constraints,
        "output_schema": {
            "sql": "WITH ... SELECT ...",
            "entity_mappings": [
                {
                    "type": "string",
                    "value": "string",
                    "field": "table.field",
                    "reason": "映射依据（可引用字段描述）",
                }
            ],
            "sql_fields": ["table.field"],
        },
    }
    return json.dumps(payload, ensure_ascii=False)
