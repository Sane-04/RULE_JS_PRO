from __future__ import annotations

import csv
import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.constants import START
from langgraph.graph import END, StateGraph
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat_history import ChatHistory
from app.models.workflow_log import WorkflowLog
from app.prompts.intent_prompts import INTENT_SYSTEM_PROMPT_FULL, build_intent_user_prompt
from app.prompts.result_summary_prompts import RESULT_SUMMARY_SYSTEM_PROMPT, build_result_summary_user_prompt
from app.prompts.sql_generation_prompts import SQL_GENERATION_SYSTEM_PROMPT, build_sql_generation_user_prompt
from app.prompts.task_parse_prompts import TASK_PARSE_SYSTEM_PROMPT, build_task_parse_user_prompt
from app.schemas.chat import ChatIntentRequest


class UnifiedChatGraphState(TypedDict):
    message: str
    history_user_messages: list[str]
    threshold: float
    model_name: str
    intent_result: dict[str, Any] | None
    parse_result: dict[str, Any] | None
    sql_result: dict[str, Any] | None
    sql_validate_result: dict[str, Any] | None
    hidden_context_result: dict[str, Any] | None
    hidden_context_retry_count: int
    result_return_result: dict[str, Any] | None


def execute_chat_workflow(
        db: Session,
        admin_id: int,
        payload: ChatIntentRequest,
        on_step_event: Callable[[str, str, str | None, dict[str, Any] | None], None] | None = None,
) -> dict[str, Any]:
    """作用：执行统一聊天工作流。
    
    输入参数：
    - db: Session。
    - admin_id: int。
    - payload: ChatIntentRequest。
    
    输出参数：
    - 返回值类型: dict[str, Any]。
    """

    ALLOWED_INTENTS = {"chat", "business_query"}
    ALLOWED_OPERATIONS = {"detail", "aggregate", "ranking", "trend"}
    ALLOWED_FILTER_OPS = {"=", "!=", ">", "<", ">=", "<=", "like", "in", "not in", "between"}
    HIDDEN_CONTEXT_MAX_RETRY = 2

    def _helper_emit_step_event(
            step_name: str,
            status: str,
            error_message: str | None = None,
            step_payload: dict[str, Any] | None = None,
    ) -> None:
        if not on_step_event:
            return
        try:
            on_step_event(step_name, status, error_message, step_payload)
        except Exception:
            return

    def _helper_to_json_safe(value: Any) -> Any:
        """作用：递归转换为 JSON 安全类型，避免 date/datetime 序列化失败。"""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): _helper_to_json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [_helper_to_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [_helper_to_json_safe(item) for item in value]
        return value

    def _helper_get_recent_user_messages(session_id: str, limit: int = 4) -> list[str]:
        """作用：读取同一会话最近的用户消息。
        
        输入参数：
        - session_id: str。
        - limit: int。
        
        输出参数：
        - 返回值类型: list[str]。
        """

        rows = (
            db.query(ChatHistory)
            .filter(
                ChatHistory.session_id == session_id,
                ChatHistory.message_role == "user",
                ChatHistory.is_deleted == False,
            )
            .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
            .limit(limit)
            .all()
        )
        return [row.message_content for row in reversed(rows)]

    def _helper_extract_json_object(text_value: str) -> dict[str, Any] | None:
        """作用：从模型输出文本中提取 JSON。
        
        输入参数：
        - text_value: str。
        
        输出参数：
        - 返回值类型: dict[str, Any] | None。
        """

        match = re.search(r"\{.*\}", text_value, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None

    def _helper_safe_float(value: Any, default: float = 0.0) -> float:
        """作用：安全转换浮点并裁剪到 [0,1]。
        
        输入参数：
        - value: Any。
        - default: float。
        
        输出参数：
        - 返回值类型: float。
        """

        try:
            number = float(value)
        except Exception:
            number = default
        return max(0.0, min(1.0, number))

    def _helper_to_unique_str_list(value: Any) -> list[str]:
        """作用：标准化字符串数组并去重。
        
        输入参数：
        - value: Any。
        
        输出参数：
        - 返回值类型: list[str]。
        """

        if not isinstance(value, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            text_value = str(item).strip()
            if not text_value:
                continue
            key = text_value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(text_value)
        return result

    def _helper_normalize_entities(value: Any) -> list[dict[str, str]]:
        """作用：标准化实体列表。
        
        输入参数：
        - value: Any。
        
        输出参数：
        - 返回值类型: list[dict[str, str]]。
        """

        if not isinstance(value, list):
            return []
        entities: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            entity_type = str(item.get("type", "")).strip()
            entity_value = str(item.get("value", "")).strip()
            if not entity_type or not entity_value:
                continue
            entities.append({"type": entity_type, "value": entity_value})
        return entities

    def _helper_normalize_filters(value: Any, whitelist: set[str]) -> list[dict[str, Any]]:
        """作用：标准化过滤条件并校验字段白名单。
        
        输入参数：
        - value: Any。
        - whitelist: set[str]。
        
        输出参数：
        - 返回值类型: list[dict[str, Any]]。
        """

        def _helper_normalize_filter_value(raw_value: Any) -> Any:
            """作用：标准化单个过滤值，清理字符串两端空格并兼容字符串列表值。
            
            输入参数：
            - raw_value: Any。
            
            输出参数：
            - 返回值类型: Any。
            """
            if isinstance(raw_value, str):
                return raw_value.strip()
            if isinstance(raw_value, list):
                return [item.strip() if isinstance(item, str) else item for item in raw_value]
            return raw_value

        if not isinstance(value, list):
            return []
        filters: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field", "")).strip()
            if field not in whitelist:
                continue
            op = str(item.get("op", "=")).strip().lower() or "="
            if op not in ALLOWED_FILTER_OPS:
                continue
            filters.append({"field": field, "op": op, "value": _helper_normalize_filter_value(item.get("value"))})
        return filters

    def _helper_trim_sql_fields_and_values(sql: str) -> str:
        """作用：清理 SQL 字段与字符串字面值两端空格。
        
        输入参数：
        - sql: str。
        
        输出参数：
        - 返回值类型: str。
        """

        normalized_sql = re.sub(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\.\s*([a-zA-Z_][a-zA-Z0-9_]*)\b",
            r"\1.\2",
            sql,
        )

        def _helper_trim_quoted_value(match: re.Match[str]) -> str:
            """作用：清理 SQL 单引号字符串字面值的两端空格并保持引号结构。
            
            输入参数：
            - match: re.Match[str]。
            
            输出参数：
            - 返回值类型: str。
            """
            raw_value = match.group(1)
            return f"'{raw_value.strip()}'"

        normalized_sql = re.sub(r"'((?:''|[^'])*)'", _helper_trim_quoted_value, normalized_sql)
        return normalized_sql

    def _helper_extract_sql_fields(sql: str) -> list[str]:
        """作用：提取 SQL 中的表字段引用并去重。
        
        输入参数：
        - sql: str。
        
        输出参数：
        - 返回值类型: list[str]。
        """

        matches = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b", sql)
        result: list[str] = []
        seen: set[str] = set()
        for table_name, column_name in matches:
            field = f"{table_name}.{column_name}"
            key = field.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(field)
        return result

    def _helper_extract_cte_names(sql: str) -> set[str]:
        """作用：提取 WITH 子句中定义的 CTE 名称。
        
        输入参数：
        - sql: str。
        
        输出参数：
        - 返回值类型: set[str]。
        """

        names = re.findall(r"(?is)(?:\bwith\b|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", sql)
        return {name.lower() for name in names}

    def _helper_normalize_entity_mappings(value: Any, whitelist: set[str]) -> list[dict[str, str]]:
        """作用：标准化实体映射并校验字段白名单。
        
        输入参数：
        - value: Any。
        - whitelist: set[str]。
        
        输出参数：
        - 返回值类型: list[dict[str, str]]。
        """

        if not isinstance(value, list):
            return []
        mappings: list[dict[str, str]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            entity_type = str(item.get("type", "")).strip()
            entity_value = str(item.get("value", "")).strip()
            field = str(item.get("field", "")).strip()
            reason = str(item.get("reason", "")).strip()
            if not entity_type or not entity_value or not field:
                continue
            if field not in whitelist:
                continue
            mappings.append(
                {
                    "type": entity_type,
                    "value": entity_value,
                    "field": field,
                    "reason": reason,
                }
            )
        return mappings

    def _helper_is_readonly_sql(sql: str) -> bool:
        """作用：仅允许查询 SQL。
        
        输入参数：
        - sql: str。
        
        输出参数：
        - 返回值类型: bool。
        """

        stripped = sql.strip().lower()
        if not stripped:
            return False
        if not (stripped.startswith("select") or stripped.startswith("with")):
            return False
        forbidden_tokens = [
            "insert",
            "update",
            "delete",
            "replace",
            "alter",
            "drop",
            "truncate",
            "create",
            "grant",
            "revoke",
        ]
        for token in forbidden_tokens:
            if re.search(rf"\b{token}\b", stripped):
                return False
        return True

    def _helper_build_kb_hints() -> tuple[list[str], list[dict[str, list[str]]], list[dict[str, Any]]]:
        """作用：构建字段白名单、字段别名提示与结构化描述提示。
        
        输入参数：
        - 无。
        
        输出参数：
        - 返回值类型: tuple[list[str], list[dict[str, list[str]]], list[dict[str, Any]]]。
        """

        kb_path = Path(__file__).resolve().parents[1] / "knowledge" / "schema_kb_core.json"
        kb = json.loads(kb_path.read_text(encoding="utf-8"))
        fields: list[str] = []
        alias_pairs: list[dict[str, list[str]]] = []
        schema_hints: list[dict[str, Any]] = []

        for table in kb.get("tables", []):
            table_name = str(table.get("name", "")).strip()
            if not table_name:
                continue
            table_description = str(table.get("description", "")).strip()
            table_columns: list[dict[str, Any]] = []
            for column in table.get("columns", []):
                column_name = str(column.get("name", "")).strip()
                if not column_name:
                    continue
                field = f"{table_name}.{column_name}"
                fields.append(field)

                raw_aliases = column.get("aliases", []) or []
                aliases = [str(item).strip() for item in raw_aliases if str(item).strip()]
                aliases.extend([column_name, field])

                dedup_aliases: list[str] = []
                seen: set[str] = set()
                for alias in aliases:
                    key = alias.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    dedup_aliases.append(alias)
                alias_pairs.append({field: dedup_aliases})
                table_columns.append(
                    {
                        "field": field,
                        "field_description": str(column.get("description", "")).strip(),
                        "aliases": dedup_aliases,
                    }
                )

            schema_hints.append(
                {
                    "table": table_name,
                    "table_description": table_description,
                    "columns": table_columns,
                }
            )

        return fields, alias_pairs, schema_hints

    def _helper_call_llm(
            system_prompt: str,
            user_prompt: str,
            model_name: str,
            timeout: float,
            response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：调用大模型并解析 JSON。
        
        输入参数：
        - system_prompt: str。
        - user_prompt: str。
        - model_name: str。
        - timeout: float。
        
        输出参数：
        - 返回值类型: dict[str, Any]。
        """

        import httpx
        from openai import OpenAI

        if not settings.llm_api_key:
            raise RuntimeError("未配置 LLM_API_KEY，无法执行工作流")
        if not model_name:
            raise RuntimeError("未配置模型名，无法执行工作流")

        try:
            kwargs: dict[str, Any] = {"api_key": settings.llm_api_key}
            if settings.llm_base_url:
                kwargs["base_url"] = settings.llm_base_url
            with httpx.Client(trust_env=False, timeout=timeout) as http_client:
                client = OpenAI(**kwargs, http_client=http_client)
                completion_payload: dict[str, Any] = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                }
                if response_format:
                    completion_payload["response_format"] = response_format
                response = client.chat.completions.create(**completion_payload)
        except Exception as exc:
            raise RuntimeError(f"大模型调用失败: {exc}") from exc

        output_text = ""
        if response.choices and response.choices[0].message:
            output_text = response.choices[0].message.content or ""
        output_data = _helper_extract_json_object(output_text)
        if not output_data:
            raise ValueError("模型输出不是有效 JSON")
        return output_data

    def _helper_intent_node_logic(
            message: str,
            history_user_messages: list[str],
            threshold: float,
            model_name: str,
    ) -> dict[str, Any]:
        """作用：意图识别节点业务逻辑。
        
        输入参数：
        - message: str。
        - history_user_messages: list[str]。
        - threshold: float。
        - model_name: str。
        
        输出参数：
        - 返回值类型: dict[str, Any]。
        """

        llm_data = _helper_call_llm(
            system_prompt=INTENT_SYSTEM_PROMPT_FULL,
            user_prompt=build_intent_user_prompt(message, history_user_messages),
            model_name=model_name,
            timeout=20.0,
        )

        intent = str(llm_data.get("intent", "")).strip().lower()
        if intent not in ALLOWED_INTENTS:
            raise ValueError(f"意图识别输出了非法 intent: {intent}")

        confidence = _helper_safe_float(llm_data.get("confidence", None), default=-1.0)
        if confidence < 0.0:
            raise ValueError("意图识别缺少有效 confidence 字段")

        merged_query = str(llm_data.get("merged_query", "")).strip()
        rewritten_query = str(llm_data.get("rewritten_query", merged_query)).strip()
        if not merged_query or not rewritten_query:
            raise ValueError("意图识别缺少 merged_query 或 rewritten_query")

        if confidence < threshold:
            intent = "chat"
        result = {
            "intent": intent,
            "is_followup": bool(llm_data.get("is_followup", False)),
            "confidence": confidence,
            "merged_query": merged_query,
            "rewritten_query": rewritten_query,
            "threshold": threshold,
        }
        print("意图识别节点输出:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return result

    def _helper_task_parse_node_logic(intent_result: dict[str, Any], model_name: str) -> dict[str, Any]:
        """作用：任务解析节点业务逻辑。
        
        输入参数：
        - intent_result: dict[str, Any]。
        - model_name: str。
        
        输出参数：
        - 返回值类型: dict[str, Any]。
        """

        query = str(
            intent_result.get("rewritten_query")
            or intent_result.get("merged_query")
            or intent_result.get("message")
            or ""
        ).strip()
        if not query:
            raise ValueError("任务解析缺少 query")

        field_whitelist, alias_pairs, _ = _helper_build_kb_hints()
        whitelist_set = set(field_whitelist)

        llm_output = _helper_call_llm(
            system_prompt=TASK_PARSE_SYSTEM_PROMPT,
            user_prompt=build_task_parse_user_prompt(
                query=query,
                field_whitelist=field_whitelist,
                alias_pairs=alias_pairs,
            ),
            model_name=model_name,
            timeout=25.0,
        )

        intent = str(llm_output.get("intent", "")).strip().lower()
        if intent not in ALLOWED_INTENTS:
            raise ValueError(f"任务解析输出了非法 intent: {intent}")

        operation = str(llm_output.get("operation", "")).strip().lower()
        if operation not in ALLOWED_OPERATIONS:
            raise ValueError(f"任务解析输出了非法 operation: {operation}")

        time_range_raw = llm_output.get("time_range")
        if not isinstance(time_range_raw, dict):
            raise ValueError("任务解析缺少有效 time_range")

        confidence = _helper_safe_float(llm_output.get("confidence", None), default=-1.0)
        if confidence < 0.0:
            raise ValueError("任务解析缺少有效 confidence 字段")

        result = {
            "intent": "business_query",
            "entities": _helper_normalize_entities(llm_output.get("entities")),
            "dimensions": _helper_to_unique_str_list(llm_output.get("dimensions")),
            "metrics": _helper_to_unique_str_list(llm_output.get("metrics")),
            "filters": _helper_normalize_filters(llm_output.get("filters"), whitelist_set),
            "time_range": {
                "start": str(time_range_raw.get("start")).strip() if time_range_raw.get("start") not in (
                None, "") else None,
                "end": str(time_range_raw.get("end")).strip() if time_range_raw.get("end") not in (None, "") else None,
            },
            "operation": operation,
            "confidence": confidence,
        }
        print("任务解析节点输出:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return result

    def _helper_sql_generation_node_logic(
            rewritten_query: str,
            parse_result: dict[str, Any],
            hidden_context_result: dict[str, Any] | None,
            model_name: str,
    ) -> dict[str, Any]:
        """作用：SQL 生成节点业务逻辑。
        
        输入参数：
        - rewritten_query: str。
        - parse_result: dict[str, Any]。
        - hidden_context_result: dict[str, Any] | None。
        - model_name: str。
        
        输出参数：
        - 返回值类型: dict[str, Any]。
        """

        if not isinstance(parse_result, dict):
            raise ValueError("SQL 生成缺少有效任务解析结果")
        if str(parse_result.get("intent", "")).strip().lower() != "business_query":
            raise ValueError("SQL 生成仅支持 business_query")

        field_whitelist, alias_pairs, schema_hints = _helper_build_kb_hints()
        whitelist_set = set(field_whitelist)

        sql_response_format = {"type": "json_object"} if settings.llm_response_format_sql == "json_object" else None

        llm_output = _helper_call_llm(
            system_prompt=SQL_GENERATION_SYSTEM_PROMPT,
            user_prompt=build_sql_generation_user_prompt(
                rewritten_query=rewritten_query,
                task=parse_result,
                field_whitelist=field_whitelist,
                alias_pairs=alias_pairs,
                schema_hints=schema_hints,
                hidden_context=hidden_context_result,
            ),
            model_name=model_name,
            timeout=30.0,
            response_format=sql_response_format,
        )

        sql = str(llm_output.get("sql", "")).strip()
        sql = _helper_trim_sql_fields_and_values(sql)
        if not sql:
            raise ValueError("SQL 生成缺少 sql 字段")
        if not re.search(r"^\s*with\b", sql, flags=re.I):
            raise ValueError("SQL 生成未使用 WITH（CTE）")

        sql_fields = _helper_extract_sql_fields(sql)
        if not sql_fields:
            raise ValueError("SQL 中未识别到 table.field 字段")
        cte_names = _helper_extract_cte_names(sql)
        invalid_fields: list[str] = []
        for field in sql_fields:
            table_name = field.split(".", 1)[0].lower()
            if table_name in cte_names:
                continue
            if field not in whitelist_set:
                invalid_fields.append(field)
        applied_field_replacements: list[dict[str, str]] = []
        if invalid_fields and isinstance(hidden_context_result, dict):
            raw_field_candidates = hidden_context_result.get("field_candidates")
            candidate_map: dict[str, list[str]] = {}
            if isinstance(raw_field_candidates, list):
                for item in raw_field_candidates:
                    if not isinstance(item, dict):
                        continue
                    missing_field = str(item.get("missing", "")).strip()
                    if not missing_field:
                        continue
                    candidates_raw = item.get("candidates")
                    if not isinstance(candidates_raw, list):
                        continue
                    normalized_candidates: list[str] = []
                    seen_candidates: set[str] = set()
                    for candidate in candidates_raw:
                        candidate_text = str(candidate).strip()
                        if not candidate_text:
                            continue
                        if candidate_text not in whitelist_set:
                            continue
                        candidate_key = candidate_text.lower()
                        if candidate_key in seen_candidates:
                            continue
                        seen_candidates.add(candidate_key)
                        normalized_candidates.append(candidate_text)
                    if normalized_candidates:
                        candidate_map[missing_field.lower()] = normalized_candidates

            replacement_sql = sql
            for invalid_field in invalid_fields:
                replacement_candidates = candidate_map.get(invalid_field.lower(), [])
                if not replacement_candidates:
                    continue
                invalid_table = invalid_field.split(".", 1)[0].lower() if "." in invalid_field else ""
                invalid_suffix = invalid_field.split(".", 1)[1].lower() if "." in invalid_field else invalid_field.lower()
                target_field = ""
                if invalid_suffix.endswith("_id"):
                    for candidate in replacement_candidates:
                        candidate_lower = candidate.lower()
                        if candidate_lower.endswith("_id") and (not candidate_lower.endswith(".id")):
                            if invalid_table and (not candidate_lower.startswith(f"{invalid_table}.")):
                                continue
                            target_field = candidate
                            break
                for candidate in replacement_candidates:
                    if target_field:
                        break
                    if invalid_table and candidate.lower().startswith(f"{invalid_table}."):
                        target_field = candidate
                        break
                if not target_field:
                    target_field = replacement_candidates[0]

                replace_pattern = re.compile(rf"\b{re.escape(invalid_field)}\b", flags=re.I)
                if not replace_pattern.search(replacement_sql):
                    continue
                replacement_sql = replace_pattern.sub(target_field, replacement_sql)
                applied_field_replacements.append({"from": invalid_field, "to": target_field})

            if applied_field_replacements:
                sql = _helper_trim_sql_fields_and_values(replacement_sql)
                sql_fields = _helper_extract_sql_fields(sql)
                cte_names = _helper_extract_cte_names(sql)
                invalid_fields = []
                for field in sql_fields:
                    table_name = field.split(".", 1)[0].lower()
                    if table_name in cte_names:
                        continue
                    if field not in whitelist_set:
                        invalid_fields.append(field)

        if invalid_fields:
            raise ValueError(f"SQL 包含非白名单字段: {invalid_fields}")

        entity_mappings = _helper_normalize_entity_mappings(llm_output.get("entity_mappings"), whitelist_set)
        entities = _helper_normalize_entities(parse_result.get("entities"))
        for entity in entities:
            entity_type = entity["type"]
            entity_value = entity["value"]
            target_mapping = next(
                (
                    mapping
                    for mapping in entity_mappings
                    if mapping["type"] == entity_type and mapping["value"] == entity_value
                ),
                None,
            )
            if not target_mapping:
                raise ValueError(f"关键实体映射失败: type={entity_type}, value={entity_value}")
            if target_mapping["field"] not in sql_fields:
                raise ValueError(
                    f"关键实体映射字段未出现在 SQL 中: type={entity_type}, value={entity_value}, field={target_mapping['field']}"
                )

        result = {
            "sql": sql,
            "entity_mappings": entity_mappings,
            "sql_fields": sql_fields,
            "applied_field_replacements": applied_field_replacements,
        }
        print("SQL 生成节点输出:")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return result

    def _helper_sql_validate_node_logic(sql_result: dict[str, Any] | None) -> dict[str, Any]:
        """作用：SQL 校验节点业务逻辑：执行 SQL 并返回结果或错误信息。
        
        输入参数：
        - sql_result: dict[str, Any] | None。
        
        输出参数：
        - 返回值类型: dict[str, Any]。
        """

        def _helper_extract_metric_aliases(sql_text: str) -> list[str]:
            """作用：从 SQL 中提取指标型别名（如 count/sum/avg）用于后续零值判断。
            
            输入参数：
            - sql_text: str。
            
            输出参数：
            - 返回值类型: list[str]。
            """
            aliases = re.findall(r"(?is)\bas\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql_text)
            keywords = (
                "count", "sum", "avg", "total", "num", "cnt",
                "ren_shu", "shu_liang", "zong_shu", "he_ji", "ping_jun", "jun_zhi",
                "ratio", "rate", "percent",
            )
            result: list[str] = []
            seen: set[str] = set()
            for alias in aliases:
                alias_text = alias.strip()
                alias_key = alias_text.lower()
                if not alias_key or alias_key in seen:
                    continue
                if any(keyword in alias_key for keyword in keywords):
                    seen.add(alias_key)
                    result.append(alias_text)
            return result

        def _helper_has_zero_metric(result_rows: list[dict[str, Any]], metric_aliases: list[str]) -> bool:
            """作用：根据指标别名检查查询结果首行是否存在数值型指标等于0的情况。
            
            输入参数：
            - result_rows: list[dict[str, Any]]。
            - metric_aliases: list[str]。
            
            输出参数：
            - 返回值类型: bool。
            """
            if not result_rows or not metric_aliases:
                return False
            first_row = result_rows[0] if isinstance(result_rows[0], dict) else {}
            for alias in metric_aliases:
                if alias not in first_row:
                    continue
                value = first_row.get(alias)
                try:
                    if float(value) == 0.0:
                        return True
                except Exception:
                    continue
            return False

        sql = str((sql_result or {}).get("sql", "")).strip()
        sql = _helper_trim_sql_fields_and_values(sql)
        if not sql:
            v_result = {
                "is_valid": False,
                "error": "sql_validate_missing_sql",
                "rows": 0,
                "result": [],
                "executed_sql": "",
                "empty_result": False,
                "zero_metric_result": False,
            }
            print("SQL验证节点输出:")
            print(json.dumps(v_result, indent=2, ensure_ascii=False, default=str))
            return v_result

        if not _helper_is_readonly_sql(sql):
            v_result = {
                "is_valid": False,
                "error": "sql_validate_readonly_violation",
                "rows": 0,
                "result": [],
                "executed_sql": sql,
                "empty_result": False,
                "zero_metric_result": False,
            }
            print("SQL验证节点输出:")
            print(json.dumps(v_result, indent=2, ensure_ascii=False, default=str))
            return v_result

        try:
            rows = db.execute(text(sql)).mappings().all()
            result_rows = _helper_to_json_safe([dict(row) for row in rows])
            metric_aliases = _helper_extract_metric_aliases(sql)
            empty_result = len(result_rows) == 0
            zero_metric_result = _helper_has_zero_metric(result_rows, metric_aliases)
            v_result = {
                "is_valid": True,
                "error": None,
                "rows": len(result_rows),
                "result": result_rows,
                "executed_sql": sql,
                "empty_result": empty_result,
                "zero_metric_result": zero_metric_result,
            }
            print("SQL验证节点输出:")
            print(json.dumps(v_result, indent=2, ensure_ascii=False, default=str))
            return v_result
        except Exception as exc:
            v_result = {
                "is_valid": False,
                "error": str(exc),
                "rows": 0,
                "result": [],
                "executed_sql": sql,
                "empty_result": False,
                "zero_metric_result": False,
            }
            print("SQL验证节点输出:")
            print(json.dumps(v_result, indent=2, ensure_ascii=False, default=str))
            return v_result

    def _helper_hidden_context_node_logic(
            rewritten_query: str,
            parse_result: dict[str, Any] | None,
            sql_result: dict[str, Any] | None,
            sql_validate_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """作用：隐藏上下文探索节点：基于 SQL 报错做只读探测并产出补充上下文。
        
        输入参数：
        - rewritten_query: str。
        - parse_result: dict[str, Any] | None。
        - sql_result: dict[str, Any] | None。
        - sql_validate_result: dict[str, Any] | None。
        
        输出参数：
        - 返回值类型: dict[str, Any]。
        """

        error_text = str((sql_validate_result or {}).get("error") or "").strip()
        validate_result = sql_validate_result if isinstance(sql_validate_result, dict) else {}
        is_valid = bool(validate_result.get("is_valid"))
        empty_result = bool(validate_result.get("empty_result"))
        zero_metric_result = bool(validate_result.get("zero_metric_result"))
        failed_sql = str((sql_result or {}).get("sql") or "").strip()
        error_lower = error_text.lower()
        retry_reason = "sql_error"
        if is_valid and empty_result:
            retry_reason = "empty_result"
        elif is_valid and zero_metric_result:
            retry_reason = "zero_metric_result"

        error_type = "execution_error"
        if "unknown column" in error_lower:
            error_type = "unknown_column"
        elif "unknown table" in error_lower:
            error_type = "unknown_table"
        elif "syntax" in error_lower:
            error_type = "syntax_error"
        elif "doesn't exist" in error_lower:
            error_type = "object_not_found"

        field_whitelist, alias_pairs, schema_hints = _helper_build_kb_hints()
        whitelist_set = set(field_whitelist)

        sql_fields = (sql_result or {}).get("sql_fields") if isinstance(sql_result, dict) else []
        candidate_fields: list[str] = []
        if isinstance(sql_fields, list):
            for field in sql_fields:
                field_text = str(field).strip()
                if not field_text:
                    continue
                if field_text in whitelist_set:
                    candidate_fields.append(field_text)
        # 当 SQL 生成失败且 sql_fields 为空时，回退到任务解析字段作为探测候选，帮助下一轮重试修复。
        if isinstance(parse_result, dict):
            dimensions_raw = parse_result.get("dimensions")
            if isinstance(dimensions_raw, list):
                for field in dimensions_raw:
                    field_text = str(field).strip()
                    if field_text in whitelist_set:
                        candidate_fields.append(field_text)

            filters_raw = parse_result.get("filters")
            if isinstance(filters_raw, list):
                for item in filters_raw:
                    if not isinstance(item, dict):
                        continue
                    field_text = str(item.get("field", "")).strip()
                    if field_text in whitelist_set:
                        candidate_fields.append(field_text)

            metrics_raw = parse_result.get("metrics")
            if isinstance(metrics_raw, list):
                for metric in metrics_raw:
                    metric_text = str(metric).strip()
                    if not metric_text:
                        continue
                    metric_fields = re.findall(
                        r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b",
                        metric_text,
                    )
                    for metric_field in metric_fields:
                        if metric_field in whitelist_set:
                            candidate_fields.append(metric_field)

        dedup_fields: list[str] = []
        seen_fields: set[str] = set()
        for field in candidate_fields:
            key = field.lower()
            if key in seen_fields:
                continue
            seen_fields.add(key)
            dedup_fields.append(field)

        missing_tokens: list[str] = []
        match_single = re.search(r"Unknown column '([^']+)'", error_text, flags=re.I)
        match_tick = re.search(r"Unknown column `([^`]+)`", error_text, flags=re.I)
        if match_single:
            missing_tokens.append(match_single.group(1).strip())
        elif match_tick:
            missing_tokens.append(match_tick.group(1).strip())
        seen_missing_tokens = {item.lower() for item in missing_tokens}
        extra_field_tokens = re.findall(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b",
            error_text,
        )
        for token in extra_field_tokens:
            token_text = token.strip()
            if not token_text:
                continue
            token_key = token_text.lower()
            if token_key in seen_missing_tokens:
                continue
            seen_missing_tokens.add(token_key)
            missing_tokens.append(token_text)

        alias_lookup: dict[str, list[str]] = {}
        for alias_item in alias_pairs:
            if isinstance(alias_item, dict):
                for field, aliases in alias_item.items():
                    alias_lookup[field] = [str(alias).strip().lower() for alias in aliases if str(alias).strip()]

        field_candidates: list[dict[str, Any]] = []
        for missing_token in missing_tokens:
            missing_suffix = missing_token.split(".")[-1].strip().lower()
            missing_table = missing_token.split(".", 1)[0].strip().lower() if "." in missing_token else ""
            candidates: list[str] = []
            for field in field_whitelist:
                field_lower = field.lower()
                if field_lower.endswith(f".{missing_suffix}"):
                    candidates.append(field)
                    continue
                aliases = alias_lookup.get(field, [])
                if missing_suffix in aliases:
                    candidates.append(field)
            if not candidates and missing_table:
                for field in field_whitelist:
                    if field.lower().startswith(f"{missing_table}."):
                        candidates.append(field)
            field_candidates.append(
                {
                    "missing": missing_token,
                    "candidates": candidates[:12],
                }
            )

        probe_target_fields = list(dedup_fields)
        seen_probe_fields = {item.lower() for item in probe_target_fields}
        for item in field_candidates:
            candidates = item.get("candidates")
            if not isinstance(candidates, list):
                continue
            for candidate in candidates[:6]:
                candidate_text = str(candidate).strip()
                if not candidate_text:
                    continue
                candidate_key = candidate_text.lower()
                if candidate_key in seen_probe_fields:
                    continue
                if candidate_text not in whitelist_set:
                    continue
                seen_probe_fields.add(candidate_key)
                probe_target_fields.append(candidate_text)

        probe_samples: list[dict[str, Any]] = []
        for field in probe_target_fields[:24]:
            table_name, column_name = field.split(".", 1)
            probe_sql = (
                f"SELECT DISTINCT {table_name}.{column_name} AS value "
                f"FROM {table_name} "
                f"WHERE {table_name}.{column_name} IS NOT NULL AND {table_name}.is_deleted = 0"
            )
            if table_name != "class":
                probe_sql = f"{probe_sql} LIMIT 20"
            try:
                rows = db.execute(text(probe_sql)).mappings().all()
                values = [str(row.get("value")) for row in rows if row.get("value") is not None]
                probe_samples.append(
                    {
                        "field": field,
                        "probe_sql": probe_sql,
                        "values": values,
                    }
                )
            except Exception as exc:
                probe_samples.append(
                    {
                        "field": field,
                        "probe_sql": probe_sql,
                        "values": [],
                        "error": str(exc),
                    }
                )

        probe_value_map: dict[str, list[str]] = {}
        for sample in probe_samples:
            if not isinstance(sample, dict):
                continue
            field_text = str(sample.get("field", "")).strip()
            values_raw = sample.get("values")
            if not field_text or not isinstance(values_raw, list):
                continue
            normalized_values: list[str] = []
            seen_values: set[str] = set()
            for value in values_raw:
                value_text = str(value).strip()
                if not value_text:
                    continue
                value_key = value_text.lower()
                if value_key in seen_values:
                    continue
                seen_values.add(value_key)
                normalized_values.append(value_text)
            if normalized_values:
                probe_value_map[field_text] = normalized_values

        value_candidates: list[dict[str, Any]] = []
        filters_raw = parse_result.get("filters") if isinstance(parse_result, dict) else []
        if isinstance(filters_raw, list):
            for filter_item in filters_raw:
                if not isinstance(filter_item, dict):
                    continue
                field_text = str(filter_item.get("field", "")).strip()
                if not field_text:
                    continue
                probe_values = probe_value_map.get(field_text, [])
                if not probe_values:
                    continue
                original_value_text = str(filter_item.get("value", "")).strip()
                if not original_value_text:
                    continue

                exact_matches: list[str] = []
                normalized_matches: list[str] = []
                fuzzy_matches: list[str] = []
                original_value_normalized = re.sub(r"\s+", "", original_value_text).lower()
                for probe_value in probe_values:
                    probe_key = probe_value.lower()
                    if probe_key == original_value_text.lower():
                        exact_matches.append(probe_value)
                        continue

                    probe_normalized = re.sub(r"\s+", "", probe_value).lower()
                    if probe_normalized == original_value_normalized:
                        normalized_matches.append(probe_value)
                        continue
                    if (
                            original_value_normalized
                            and (
                            original_value_normalized in probe_normalized
                            or probe_normalized in original_value_normalized
                    )
                    ):
                        fuzzy_matches.append(probe_value)

                candidate_values = exact_matches or normalized_matches or fuzzy_matches or probe_values[:5]
                dedup_candidate_values: list[str] = []
                seen_candidate_values: set[str] = set()
                for candidate_value in candidate_values:
                    candidate_text = str(candidate_value).strip()
                    if not candidate_text:
                        continue
                    candidate_key = candidate_text.lower()
                    if candidate_key in seen_candidate_values:
                        continue
                    seen_candidate_values.add(candidate_key)
                    dedup_candidate_values.append(candidate_text)
                    if len(dedup_candidate_values) >= 8:
                        break
                if not dedup_candidate_values:
                    continue

                match_strategy = "fallback_probe_topn"
                if exact_matches:
                    match_strategy = "exact"
                elif normalized_matches:
                    match_strategy = "normalized"
                elif fuzzy_matches:
                    match_strategy = "fuzzy"

                value_candidates.append(
                    {
                        "field": field_text,
                        "original_value": original_value_text,
                        "candidates": dedup_candidate_values,
                        "match_strategy": match_strategy,
                    }
                )

        hints: list[str] = [f"error_type={error_type}"]
        if missing_tokens:
            hints.append(f"missing_tokens={','.join(missing_tokens[:3])}")
        if field_candidates:
            hints.append("enforce_field_replacements_from_field_candidates")
        if probe_samples:
            hints.append("use_probe_samples_to_rewrite_filters_or_entities")
        if retry_reason == "empty_result" and value_candidates:
            hints.append("prioritize_value_candidates_for_empty_result")
        hints.append("retry_sql_generation_with_hidden_context")

        hc_result = {
            "retry_reason": retry_reason,
            "error_type": error_type,
            "error": error_text,
            "failed_sql": failed_sql,
            "rewritten_query": rewritten_query,
            "field_candidates": field_candidates,
            "probe_samples": probe_samples,
            "value_candidates": value_candidates,
            "hints": hints,
            "kb_summary": {
                "table_count": len(schema_hints),
                "field_count": len(field_whitelist),
            },
        }
        print("隐藏上下文探索节点输出:")
        print(json.dumps(hc_result, indent=2, ensure_ascii=False, default=str))
        return hc_result

    def _helper_insert_workflow_log(
            session_id: str,
            step_name: str,
            input_json: dict[str, Any],
            output_json: dict[str, Any] | None,
            status: str,
            error_message: str | None,
    ) -> None:
        """作用：插入工作流日志。
        
        输入参数：
        - session_id: str。
        - step_name: str。
        - input_json: dict[str, Any]。
        - output_json: dict[str, Any] | None。
        - status: str。
        - error_message: str | None。
        
        输出参数：
        - 返回值类型: None。
        """

        db.add(
            WorkflowLog(
                session_id=session_id,
                step_name=step_name,
                input_json=_helper_to_json_safe(input_json),
                output_json=_helper_to_json_safe(output_json),
                status=status,
                error_message=error_message,
                risk_level="low",
                created_by=admin_id,
                updated_by=admin_id,
                is_deleted=False,
            )
        )

    def _helper_insert_chat_history(
            session_id: str,
            user_message: str,
            assistant_message: str,
            model_name: str,
    ) -> None:
        """作用：插入一轮用户与助手会话。
        
        输入参数：
        - session_id: str。
        - user_message: str。
        - assistant_message: str。
        - model_name: str。
        
        输出参数：
        - 返回值类型: None。
        """

        db.add(
            ChatHistory(
                admin_id=admin_id,
                session_id=session_id,
                message_role="user",
                message_content=user_message,
                model_name=model_name,
                created_by=admin_id,
                updated_by=admin_id,
                is_deleted=False,
            )
        )
        db.add(
            ChatHistory(
                admin_id=admin_id,
                session_id=session_id,
                message_role="assistant",
                message_content=assistant_message,
                model_name=model_name,
                created_by=admin_id,
                updated_by=admin_id,
                is_deleted=False,
            )
        )

    def _helper_save_node_io_local(
            session_id: str,
            step_name: str,
            node_input: dict[str, Any],
            node_output: dict[str, Any] | None,
            status: str,
            error_message: str | None,
    ) -> None:
        """作用：保存节点输入输出到本地。
        
        输入参数：
        - session_id: str。
        - step_name: str。
        - node_input: dict[str, Any]。
        - node_output: dict[str, Any] | None。
        - status: str。
        - error_message: str | None。
        
        输出参数：
        - 返回值类型: None。
        """

        root = Path(settings.node_io_log_dir)
        step_dir = root / session_id / step_name
        step_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H-%M-%S-%f")
        file_path = step_dir / f"{ts}-{status}.json"
        payload_data = {
            "session_id": session_id,
            "admin_id": admin_id,
            "step_name": step_name,
            "status": status,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "input": node_input,
            "output": node_output,
        }
        file_path.write_text(
            json.dumps(_helper_to_json_safe(payload_data), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _helper_node_logger(
            step_name: str,
            node_input: dict[str, Any],
            node_output: dict[str, Any] | None,
            status: str,
            error_message: str | None,
    ) -> None:
        """作用：节点日志包装。
        
        输入参数：
        - step_name: str。
        - node_input: dict[str, Any]。
        - node_output: dict[str, Any] | None。
        - status: str。
        - error_message: str | None。
        
        输出参数：
        - 返回值类型: None。
        """

        _helper_save_node_io_local(
            session_id=session_id,
            step_name=step_name,
            node_input=node_input,
            node_output=node_output,
            status=status,
            error_message=error_message,
        )

    def _helper_intent_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """作用：图中的意图识别节点。
        
        输入参数：
        - state: UnifiedChatGraphState。
        
        输出参数：
        - 返回值类型: UnifiedChatGraphState。
        """

        node_input = {
            "message": state["message"],
            "history_user_messages": state["history_user_messages"],
            "threshold": state["threshold"],
            "model_name": state["model_name"],
        }
        _helper_emit_step_event("intent_recognition", "start", None)
        try:
            intent_result = _helper_intent_node_logic(
                message=state["message"],
                history_user_messages=state["history_user_messages"],
                threshold=state["threshold"],
                model_name=state["model_name"],
            )
            _helper_node_logger("intent_recognition", node_input, intent_result, "success", None)
            _helper_emit_step_event("intent_recognition", "end", None)
            return {**state, "intent_result": intent_result}
        except Exception as exc:
            _helper_node_logger("intent_recognition", node_input, None, "failed", str(exc))
            _helper_emit_step_event("intent_recognition", "error", str(exc))
            raise

    def _helper_task_parse_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """作用：图中的任务解析节点。
        
        输入参数：
        - state: UnifiedChatGraphState。
        
        输出参数：
        - 返回值类型: UnifiedChatGraphState。
        """

        intent_result = state.get("intent_result") or {}
        node_input = {"intent_result": intent_result}
        _helper_emit_step_event("task_parse", "start", None)
        try:
            parse_result = _helper_task_parse_node_logic(intent_result=intent_result, model_name=state["model_name"])
            _helper_node_logger("task_parse", node_input, parse_result, "success", None)
            _helper_emit_step_event("task_parse", "end", None)
            return {**state, "parse_result": parse_result}
        except Exception as exc:
            _helper_node_logger("task_parse", node_input, None, "failed", str(exc))
            _helper_emit_step_event("task_parse", "error", str(exc))
            raise

    def _helper_sql_generation_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """作用：图中的 SQL 生成节点。
        
        输入参数：
        - state: UnifiedChatGraphState。
        
        输出参数：
        - 返回值类型: UnifiedChatGraphState。
        """

        parse_result = state.get("parse_result") or {}
        hidden_context_result = state.get("hidden_context_result")
        rewritten_query = str((state.get("intent_result") or {}).get("rewritten_query", state["message"])).strip()
        sql_generation_model_name = settings.llm_model_sql_generation or state["model_name"]
        node_input = {
            "rewritten_query": rewritten_query,
            "parse_result": parse_result,
            "hidden_context_result": hidden_context_result,
            "model_name": sql_generation_model_name,
        }
        _helper_emit_step_event("sql_generation", "start", None)
        try:
            sql_result = _helper_sql_generation_node_logic(
                rewritten_query=rewritten_query,
                parse_result=parse_result,
                hidden_context_result=hidden_context_result,
                model_name=sql_generation_model_name,
            )
            _helper_node_logger("sql_generation", node_input, sql_result, "success", None)
            sql_preview = str(sql_result.get("sql") or "").strip()
            step_payload = {"sql": sql_preview} if sql_preview else None
            _helper_emit_step_event("sql_generation", "end", None, step_payload)
            return {**state, "sql_result": sql_result}
        except Exception as exc:
            error_text = str(exc)
            fallback_sql_result = {
                "sql": "",
                "entity_mappings": [],
                "sql_fields": [],
                "generation_failed": True,
                "generation_error": error_text,
            }
            fallback_validate_result = {
                "is_valid": False,
                "error": error_text,
                "rows": 0,
                "result": [],
                "executed_sql": "",
                "empty_result": False,
                "zero_metric_result": False,
            }
            _helper_node_logger("sql_generation", node_input, fallback_sql_result, "failed", error_text)
            # SQL 生成失败不再中断工作流，交由 hidden_context 继续修复。
            _helper_emit_step_event("sql_generation", "end", None)
            return {
                **state,
                "sql_result": fallback_sql_result,
                "sql_validate_result": fallback_validate_result,
            }

    def _helper_sql_validate_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """作用：图中的 SQL 验证节点。
        
        输入参数：
        - state: UnifiedChatGraphState。
        
        输出参数：
        - 返回值类型: UnifiedChatGraphState。
        """

        node_input = {"sql_result": state.get("sql_result")}
        _helper_emit_step_event("sql_validate", "start", None)
        try:
            validate_result = _helper_sql_validate_node_logic(sql_result=state.get("sql_result"))
            status = "success" if validate_result.get("is_valid") else "failed"
            _helper_node_logger("sql_validate", node_input, validate_result, status, validate_result.get("error"))
            _helper_emit_step_event("sql_validate", "end", None)
            return {**state, "sql_validate_result": validate_result}
        except Exception as exc:
            _helper_emit_step_event("sql_validate", "error", str(exc))
            raise

    def _helper_hidden_context_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """作用：图中的 隐藏上下文 探索节点。
        
        输入参数：
        - state: UnifiedChatGraphState。
        
        输出参数：
        - 返回值类型: UnifiedChatGraphState。
        """

        current_retry_count = int(state.get("hidden_context_retry_count") or 0)
        rewritten_query = str((state.get("intent_result") or {}).get("rewritten_query", state["message"])).strip()
        parse_result = state.get("parse_result")
        sql_result = state.get("sql_result")
        sql_validate_result = state.get("sql_validate_result")
        node_input = {
            "rewritten_query": rewritten_query,
            "parse_result": parse_result,
            "sql_result": sql_result,
            "sql_validate_result": sql_validate_result,
            "hidden_context_retry_count": current_retry_count,
        }
        _helper_emit_step_event("hidden_context", "start", None)
        try:
            hidden_context_result = _helper_hidden_context_node_logic(
                rewritten_query=rewritten_query,
                parse_result=parse_result,
                sql_result=sql_result,
                sql_validate_result=sql_validate_result,
            )
            next_retry_count = current_retry_count + 1
            hidden_context_result["retry_count"] = next_retry_count
            _helper_node_logger("hidden_context", node_input, hidden_context_result, "success", None)
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="hidden_context",
                input_json=node_input,
                output_json=hidden_context_result,
                status="success",
                error_message=None,
            )
            _helper_emit_step_event("hidden_context", "end", None)
            return {
                **state,
                "hidden_context_result": hidden_context_result,
                "hidden_context_retry_count": next_retry_count,
            }
        except Exception as exc:
            _helper_node_logger("hidden_context", node_input, None, "failed", str(exc))
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="hidden_context",
                input_json=node_input,
                output_json=None,
                status="failed",
                error_message=str(exc),
            )
            _helper_emit_step_event("hidden_context", "error", str(exc))
            raise

    def _helper_result_return_node_logic(
            message: str,
            intent_result: dict[str, Any] | None,
            parse_result: dict[str, Any] | None,
            sql_result: dict[str, Any] | None,
            sql_validate_result: dict[str, Any] | None,
            hidden_context_result: dict[str, Any] | None,
            hidden_context_retry_count: int,
            model_name: str,
    ) -> dict[str, Any]:
        """作用：收敛整条图执行结果，判定最终状态并生成面向用户的总结描述。
        
        输入参数：
        - message: str。
        - intent_result: dict[str, Any] | None。
        - parse_result: dict[str, Any] | None。
        - sql_result: dict[str, Any] | None。
        - sql_validate_result: dict[str, Any] | None。
        - hidden_context_result: dict[str, Any] | None。
        - hidden_context_retry_count: int。
        - model_name: str。
        
        输出参数：
        - 返回值类型: dict[str, Any]。
        """
        intent_payload = intent_result or {}
        intent = str(intent_payload.get("intent", "chat")).strip().lower()
        is_followup = bool(intent_payload.get("is_followup", False))
        merged_query = str(intent_payload.get("merged_query", message)).strip()
        rewritten_query = str(intent_payload.get("rewritten_query", message)).strip()
        skipped = parse_result is None
        operation = str((parse_result or {}).get("operation") or "").strip().lower()
        deduplicated_row_count = 0

        # Guardrail: de-duplicate list-style rows to avoid one student appearing many times due to joins.
        if isinstance(sql_validate_result, dict):
            payload_rows = sql_validate_result.get("result")
            if isinstance(payload_rows, list) and payload_rows and operation in {"detail", "ranking"}:
                unique_rows: list[Any] = []
                seen_keys: set[str] = set()
                seen_indexes: dict[str, int] = {}
                for row in payload_rows:
                    if isinstance(row, dict) and row.get("student_no") is not None:
                        row_key = (
                            f"student::{str(row.get('student_no', ''))}::"
                            f"{str(row.get('real_name', ''))}"
                        )
                    else:
                        try:
                            row_key = f"row::{json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)}"
                        except Exception:
                            row_key = f"row::{str(row)}"
                    if row_key in seen_keys:
                        row_index = seen_indexes.get(row_key)
                        if (
                                row_index is not None
                                and isinstance(row, dict)
                                and isinstance(unique_rows[row_index], dict)
                        ):
                            incoming_reason = str(row.get("reason") or "").strip()
                            if incoming_reason:
                                existing_reason = str(unique_rows[row_index].get("reason") or "").strip()
                                if incoming_reason not in existing_reason:
                                    if existing_reason:
                                        unique_rows[row_index]["reason"] = f"{existing_reason}；{incoming_reason}"
                                    else:
                                        unique_rows[row_index]["reason"] = incoming_reason
                        continue
                    seen_keys.add(row_key)
                    seen_indexes[row_key] = len(unique_rows)
                    unique_rows.append(row)
                deduplicated_row_count = len(payload_rows) - len(unique_rows)
                if deduplicated_row_count > 0:
                    normalized_validate = dict(sql_validate_result)
                    normalized_validate["result"] = unique_rows
                    normalized_validate["rows"] = len(unique_rows)
                    normalized_validate["empty_result"] = len(unique_rows) == 0
                    sql_validate_result = normalized_validate

        final_status = "failed"
        reason_code: str | None = None
        if intent == "chat":
            final_status = "success"
            reason_code = "intent_is_chat"
        elif parse_result is None:
            final_status = "failed"
            reason_code = "task_parse_missing"
        elif sql_validate_result is None:
            final_status = "failed"
            reason_code = "sql_validate_missing"
        else:
            is_valid = bool(sql_validate_result.get("is_valid"))
            empty_result = bool(sql_validate_result.get("empty_result"))
            zero_metric_result = bool(sql_validate_result.get("zero_metric_result"))
            if is_valid and (not empty_result) and (not zero_metric_result):
                final_status = "success"
                reason_code = None
            elif empty_result:
                final_status = "partial_success"
                reason_code = "empty_result_after_retry"
            elif zero_metric_result:
                final_status = "partial_success"
                reason_code = "zero_metric_after_retry"
            else:
                final_status = "failed"
                reason_code = "sql_invalid_after_retry"

        summary = ""
        try:
            summary_data = _helper_call_llm(
                system_prompt=RESULT_SUMMARY_SYSTEM_PROMPT,
                user_prompt=build_result_summary_user_prompt(
                    user_query=message,
                    rewritten_query=rewritten_query,
                    final_status=final_status,
                    reason_code=reason_code,
                    task=parse_result if isinstance(parse_result, dict) else None,
                    sql_validate_result=sql_validate_result if isinstance(sql_validate_result, dict) else None,
                    hidden_context_retry_count=hidden_context_retry_count,
                ),
                model_name=model_name,
                timeout=12.0,
            )
            summary = str(summary_data.get("summary", "")).strip()
        except Exception:
            summary = ""

        if not summary:
            if final_status == "success":
                if intent == "chat":
                    summary = "当前问题被识别为闲聊，已跳过数据查询流程。"
                else:
                    rows = int((sql_validate_result or {}).get("rows") or 0)
                    summary = f"查询执行成功，已返回结果，共{rows}行。"
            elif reason_code == "zero_metric_after_retry":
                summary = "查询流程已完成，但统计指标结果为0，建议检查筛选条件或换用更明确的实体名称。"
            elif reason_code == "empty_result_after_retry":
                summary = "查询流程已完成，但未命中符合条件的数据，建议放宽筛选条件后重试。"
            elif reason_code == "sql_invalid_after_retry":
                summary = "查询流程执行失败，SQL在重试后仍未通过校验，请调整问题描述后重试。"
            elif reason_code == "task_parse_missing":
                summary = "任务解析结果缺失，当前无法生成有效查询，请补充更明确的问题描述。"
            elif reason_code == "sql_validate_missing":
                summary = "SQL校验结果缺失，当前无法确认查询结果，请稍后重试。"
            else:
                summary = "查询未成功完成，请稍后重试。"
        assistant_reply = summary
        download_url: str | None = None
        if final_status == "success" and intent == "business_query":
            result_rows: list[Any] = []
            if isinstance(sql_validate_result, dict):
                payload_rows = sql_validate_result.get("result")
                if isinstance(payload_rows, list):
                    result_rows = payload_rows
            if result_rows:
                max_detail_rows = 10
                detail_lines: list[str] = [summary, "", "详细信息："]
                for index, row in enumerate(result_rows[:max_detail_rows], start=1):
                    if not isinstance(row, dict):
                        detail_lines.append(f"{index}. {row}")
                        continue
                    row_pairs: list[str] = []
                    for field_name, field_value in row.items():
                        row_pairs.append(f"{field_name}={field_value}")
                    detail_lines.append(f"{index}. {'，'.join(row_pairs)}")
                if len(result_rows) > max_detail_rows:
                    try:
                        export_dir = Path(settings.chat_export_dir)
                        export_dir.mkdir(parents=True, exist_ok=True)
                        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                        export_name = f"admin_{admin_id}_session_{session_id}_{timestamp}_{uuid.uuid4().hex[:8]}.csv"
                        export_path = export_dir / export_name
                        normalized_rows: list[dict[str, Any]] = []
                        for item in result_rows:
                            if isinstance(item, dict):
                                normalized_rows.append(item)
                            else:
                                normalized_rows.append({"value": item})
                        fieldnames: list[str] = []
                        seen_fields: set[str] = set()
                        for row in normalized_rows:
                            for key in row.keys():
                                if key not in seen_fields:
                                    seen_fields.add(key)
                                    fieldnames.append(key)
                        if not fieldnames:
                            fieldnames = ["value"]
                        with export_path.open("w", encoding="utf-8-sig", newline="") as fp:
                            writer = csv.DictWriter(fp, fieldnames=fieldnames)
                            writer.writeheader()
                            for row in normalized_rows:
                                writer.writerow({field: row.get(field, "") for field in fieldnames})
                        download_url = f"/api/chat/downloads/{export_name}"
                    except Exception:
                        download_url = None
                    detail_lines.append(
                        f"数据共 {len(result_rows)} 行，当前仅展示前 {max_detail_rows} 行。"
                    )
                    if deduplicated_row_count > 0:
                        detail_lines.append(f"已自动去重 {deduplicated_row_count} 条重复记录。")
                    if download_url:
                        detail_lines.append("数据量过多，请下载完整 CSV 查看：")
                        detail_lines.append(download_url)
                    else:
                        detail_lines.append("数据量过多，CSV 导出失败，请稍后重试。")
                elif deduplicated_row_count > 0:
                    detail_lines.append(f"已自动去重 {deduplicated_row_count} 条重复记录。")
                assistant_reply = "\n".join(detail_lines)
        result = {
            "session_id": session_id,
            "intent": intent,
            "is_followup": is_followup,
            "merged_query": merged_query,
            "rewritten_query": rewritten_query,
            "skipped": skipped,
            "reason": reason_code,
            "final_status": final_status,
            "reason_code": reason_code,
            "summary": summary,
            "assistant_reply": assistant_reply,
            "download_url": download_url,
            "task": parse_result,
            "sql_result": sql_result,
            "sql_validate_result": sql_validate_result,
            "hidden_context_result": hidden_context_result,
            "hidden_context_retry_count": hidden_context_retry_count,
        }
        print("结果返回节点输出：")
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return result

    def _helper_result_return_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """作用：图中的结果返回节点，负责调用结果收敛逻辑并写回状态。
        
        输入参数：
        - state: UnifiedChatGraphState。
        
        输出参数：
        - 返回值类型: UnifiedChatGraphState。
        """
        node_input = {
            "message": state["message"],
            "intent_result": state.get("intent_result"),
            "parse_result": state.get("parse_result"),
            "sql_result": state.get("sql_result"),
            "sql_validate_result": state.get("sql_validate_result"),
            "hidden_context_result": state.get("hidden_context_result"),
            "hidden_context_retry_count": int(state.get("hidden_context_retry_count") or 0),
        }
        _helper_emit_step_event("result_return", "start", None)
        try:
            result_return_result = _helper_result_return_node_logic(
                message=state["message"],
                intent_result=state.get("intent_result"),
                parse_result=state.get("parse_result"),
                sql_result=state.get("sql_result"),
                sql_validate_result=state.get("sql_validate_result"),
                hidden_context_result=state.get("hidden_context_result"),
                hidden_context_retry_count=int(state.get("hidden_context_retry_count") or 0),
                model_name=state["model_name"],
            )
            _helper_node_logger("result_return", node_input, result_return_result, "success", None)
            _helper_emit_step_event("result_return", "end", None)
            return {**state, "result_return_result": result_return_result}
        except Exception as exc:
            _helper_node_logger("result_return", node_input, None, "failed", str(exc))
            _helper_emit_step_event("result_return", "error", str(exc))
            raise

    def _helper_build_graph():
        """作用：构建统一工作流图。
        
        输入参数：
        - 无。
        
        输出参数：
        - 返回值类型: Any。
        """

        def _helper_route_after_intent(state: UnifiedChatGraphState) -> str:
            """作用：意图识别后的路由决策，业务查询进入任务解析，闲聊直接返回结果节点。
            
            输入参数：
            - state: UnifiedChatGraphState。
            
            输出参数：
            - 返回值类型: str。
            """
            intent_result = state.get("intent_result") or {}
            intent = str(intent_result.get("intent", "chat")).strip().lower()
            if intent == "business_query":
                return "task_parse"
            return "result_return"

        def _helper_route_after_sql_generation(state: UnifiedChatGraphState) -> str:
            """作用：SQL 生成后的路由决策，生成失败时优先进入隐藏上下文重试。"""
            intent = str((state.get("intent_result") or {}).get("intent", "chat")).strip().lower()
            retry_count = int(state.get("hidden_context_retry_count") or 0)
            sql_result = state.get("sql_result") or {}
            generation_failed = bool(sql_result.get("generation_failed"))

            if intent != "business_query":
                return "result_return"
            if (not generation_failed):
                return "sql_validate"
            if retry_count >= HIDDEN_CONTEXT_MAX_RETRY:
                return "result_return"
            return "hidden_context"

        def _helper_route_after_sql_validate(state: UnifiedChatGraphState) -> str:
            """作用：SQL 校验后的路由决策，失败/空结果/零指标时进入隐藏上下文重试，否则直接返回结果节点。
            
            输入参数：
            - state: UnifiedChatGraphState。
            
            输出参数：
            - 返回值类型: str。
            """
            intent = str((state.get("intent_result") or {}).get("intent", "chat")).strip().lower()
            validate_result = state.get("sql_validate_result") or {}
            retry_count = int(state.get("hidden_context_retry_count") or 0)

            if intent != "business_query":
                return "result_return"
            if retry_count >= HIDDEN_CONTEXT_MAX_RETRY:
                return "result_return"

            is_valid = bool(validate_result.get("is_valid"))
            empty_result = bool(validate_result.get("empty_result"))
            zero_metric_result = bool(validate_result.get("zero_metric_result"))
            if (not is_valid) or empty_result or zero_metric_result:
                return "hidden_context"
            return "result_return"

        def _helper_route_after_hidden_context(state: UnifiedChatGraphState) -> str:
            """作用：隐藏上下文节点后的路由决策，未超重试上限则回到 SQL 生成，超限则返回结果节点。
            
            输入参数：
            - state: UnifiedChatGraphState。
            
            输出参数：
            - 返回值类型: str。
            """
            retry_count = int(state.get("hidden_context_retry_count") or 0)
            if retry_count > HIDDEN_CONTEXT_MAX_RETRY:
                return "result_return"
            return "sql_generation"

        graph = StateGraph(UnifiedChatGraphState)
        graph.add_node("intent_recognition", _helper_intent_node)
        graph.add_node("task_parse", _helper_task_parse_node)
        graph.add_node("sql_generation", _helper_sql_generation_node)
        graph.add_node("sql_validate", _helper_sql_validate_node)
        graph.add_node("hidden_context", _helper_hidden_context_node)
        graph.add_node("result_return", _helper_result_return_node)
        graph.add_edge(START, "intent_recognition")
        graph.add_conditional_edges(
            "intent_recognition",
            _helper_route_after_intent,
            {"task_parse": "task_parse", "result_return": "result_return"},
        )
        graph.add_edge("task_parse", "sql_generation")
        graph.add_conditional_edges(
            "sql_generation",
            _helper_route_after_sql_generation,
            {"sql_validate": "sql_validate", "hidden_context": "hidden_context", "result_return": "result_return"},
        )
        graph.add_conditional_edges(
            "sql_validate",
            _helper_route_after_sql_validate,
            {"hidden_context": "hidden_context", "result_return": "result_return"},
        )
        graph.add_conditional_edges(
            "hidden_context",
            _helper_route_after_hidden_context,
            {"sql_generation": "sql_generation", "result_return": "result_return"},
        )
        graph.add_edge("result_return", END)
        return graph.compile()

    session_id = payload.session_id or uuid.uuid4().hex[:16]
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY，无法执行工作流")
    model_name = payload.model_name or settings.llm_model_intent
    if not model_name:
        raise RuntimeError("未配置 llm_model_intent，无法执行工作流")

    threshold = settings.intent_confidence_threshold
    history_user_messages = _helper_get_recent_user_messages(session_id=session_id, limit=4)[-4:]

    graph_state: UnifiedChatGraphState = {
        "message": payload.message,
        "history_user_messages": history_user_messages,
        "threshold": threshold,
        "model_name": model_name,
        "intent_result": None,
        "parse_result": None,
        "sql_result": None,
        "sql_validate_result": None,
        "hidden_context_result": None,
        "hidden_context_retry_count": 0,
        "result_return_result": None,
    }
    input_json = {
        "message": payload.message,
        "history_user_messages": history_user_messages,
        "threshold": threshold,
    }

    try:
        graph_app = _helper_build_graph()
        graph_output = graph_app.invoke(graph_state)
        intent_result = graph_output.get("intent_result") or {}
        parse_result = graph_output.get("parse_result")
        sql_result = graph_output.get("sql_result")
        sql_validate_result = graph_output.get("sql_validate_result")
        result = graph_output.get("result_return_result")
        if not isinstance(result, dict):
            raise ValueError("结果返回节点未产出有效结果")
        skipped = bool(result.get("skipped"))

        _helper_insert_chat_history(
            session_id=session_id,
            user_message=payload.message,
            assistant_message=str(result.get("assistant_reply") or result.get("summary") or ""),
            model_name=model_name,
        )
        _helper_insert_workflow_log(
            session_id=session_id,
            step_name="intent_recognition",
            input_json=input_json,
            output_json=intent_result,
            status="success",
            error_message=None,
        )
        if not skipped:
            sql_generation_failed = bool((sql_result or {}).get("generation_failed"))
            sql_generation_error = str((sql_result or {}).get("generation_error") or "").strip() or None
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="task_parse",
                input_json={"intent_result": intent_result},
                output_json=parse_result,
                status="success",
                error_message=None,
            )
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="sql_generation",
                input_json={"rewritten_query": result["rewritten_query"], "task": parse_result},
                output_json=sql_result,
                status="failed" if sql_generation_failed else "success",
                error_message=sql_generation_error,
            )
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="sql_validate",
                input_json={"sql_result": sql_result},
                output_json=sql_validate_result,
                status="success" if (sql_validate_result or {}).get("is_valid") else "failed",
                error_message=(sql_validate_result or {}).get("error"),
            )
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        try:
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="intent_recognition",
                input_json=input_json,
                output_json=None,
                status="failed",
                error_message=str(exc),
            )
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="task_parse",
                input_json={"message": payload.message},
                output_json=None,
                status="failed",
                error_message=str(exc),
            )
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="sql_generation",
                input_json={"message": payload.message},
                output_json=None,
                status="failed",
                error_message=str(exc),
            )
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="sql_validate",
                input_json={"message": payload.message},
                output_json=None,
                status="failed",
                error_message=str(exc),
            )
            _helper_insert_workflow_log(
                session_id=session_id,
                step_name="hidden_context",
                input_json={"message": payload.message},
                output_json=None,
                status="failed",
                error_message=str(exc),
            )
            db.commit()
        except Exception:
            db.rollback()
        raise
