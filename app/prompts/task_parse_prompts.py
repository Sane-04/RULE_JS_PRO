from __future__ import annotations

import json
from typing import Any

TASK_PARSE_SYSTEM_PROMPT = """
你是教务查询任务解析助手。
请将用户问题解析为结构化任务对象，供后续 SQL 生成阶段使用。

强约束：
1) 只输出一个 JSON 对象，不要输出 markdown、解释、前后缀文本。
2) JSON 字段必须包含：
   - intent: "chat" | "business_query"
   - entities: [{type, value}]
   - dimensions: [string]
   - metrics: [string]
   - filters: [{field, op, value}]
   - time_range: {start, end}
   - operation: "detail" | "aggregate" | "ranking" | "trend"
   - confidence: 0~1
3) 所有字段名必须使用 table.field 形式。
4) filters.field 与 dimensions 中的字段必须来自 kb_field_whitelist。
5) 如果问题是闲聊，intent=chat，其余字段尽量置空（空数组或 null）。

关于 alias_hints（重点）：
1) alias_hints 的结构是：[{ "table.field": ["别名1", "别名2", ...] }, ...]
2) 先做“用户词 -> 别名 -> 标准字段(table.field)”映射，再输出 filters/dimensions。
3) 输出时只能使用标准字段名（table.field），不能输出别名原文。
4) 若一个用户词可映射到多个字段，按语义最贴近当前问题的字段选择一个。
5) 若无法可靠映射，则不要臆造字段；宁可少填，也不要填错字段。

完整输出示例（必须严格输出 JSON，不要附加解释）：
{
  "intent": "business_query",
  "entities": [
    {"type": "grade", "value": "22级"},
    {"type": "major", "value": "软件工程"},
    {"type": "gender", "value": "男生"}
  ],
  "dimensions": ["major.major_name"],
  "metrics": ["count"],
  "filters": [
    {"field": "student.enroll_year", "op": "=", "value": 2022},
    {"field": "student.gender", "op": "=", "value": "男"},
    {"field": "major.major_name", "op": "=", "value": "软件工程"}
  ],
  "time_range": {"start": null, "end": null},
  "operation": "aggregate",
  "confidence": 0.92
}
""".strip()


def build_task_parse_user_prompt(
    query: str,
    field_whitelist: list[str],
    alias_pairs: list[dict[str, list[str]]],
) -> str:
    payload: dict[str, Any] = {
        "query": query,
        "kb_field_whitelist": field_whitelist,
        "alias_hints": alias_pairs,
        "output_schema": {
            "intent": "chat|business_query",
            "entities": [{"type": "string", "value": "string"}],
            "dimensions": ["string"],
            "metrics": ["string"],
            "filters": [{"field": "table.field", "op": "=", "value": "string|number|boolean"}],
            "time_range": {"start": "YYYY-MM-DD|null", "end": "YYYY-MM-DD|null"},
            "operation": "detail|aggregate|ranking|trend",
            "confidence": "0~1",
        },
    }
    return json.dumps(payload, ensure_ascii=False)