from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.constants import START
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.chat_history import ChatHistory
from app.models.workflow_log import WorkflowLog
from app.prompts.intent_prompts import INTENT_SYSTEM_PROMPT_FULL, build_intent_user_prompt
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


def execute_chat_workflow(
    db: Session,
    admin_id: int,
    payload: ChatIntentRequest,
) -> dict[str, Any]:
    """执行统一聊天工作流。"""

    ALLOWED_INTENTS = {"chat", "business_query"}
    ALLOWED_OPERATIONS = {"detail", "aggregate", "ranking", "trend"}
    ALLOWED_FILTER_OPS = {"=", "!=", ">", "<", ">=", "<=", "like", "in", "not in", "between"}

    def _helper_get_recent_user_messages(session_id: str, limit: int = 4) -> list[str]:
        """读取同一会话最近的 user 消息。"""

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

    def _helper_extract_json_object(text: str) -> dict[str, Any] | None:
        """从文本中提取第一个 JSON 对象。"""

        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except Exception:
            return None

    def _helper_safe_float(value: Any, default: float = 0.0) -> float:
        """安全转换浮点并裁剪到 [0, 1]。"""

        try:
            number = float(value)
        except Exception:
            number = default
        return max(0.0, min(1.0, number))

    def _helper_to_unique_str_list(value: Any) -> list[str]:
        """标准化字符串数组并去重。"""

        if not isinstance(value, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    def _helper_normalize_entities(value: Any) -> list[dict[str, str]]:
        """标准化 entities。"""

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
        """标准化 filters 并校验字段白名单。"""

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
            filters.append({"field": field, "op": op, "value": item.get("value")})
        return filters

    def _helper_extract_sql_fields(sql: str) -> list[str]:
        """提取 SQL 中所有 table.field 字段并去重。"""

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
        """提取 WITH 子句中定义的 CTE 名称。"""

        names = re.findall(r"(?is)(?:\bwith\b|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s*\(", sql)
        return {name.lower() for name in names}

    def _helper_normalize_entity_mappings(value: Any, whitelist: set[str]) -> list[dict[str, str]]:
        """标准化 entity_mappings 并校验字段白名单。"""

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

    def _helper_build_kb_hints() -> tuple[list[str], list[dict[str, list[str]]], list[dict[str, Any]]]:
        """构建字段白名单、字段别名提示与结构化描述提示。"""

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

    def _helper_call_llm(system_prompt: str, user_prompt: str, model_name: str, timeout: float) -> dict[str, Any]:
        """调用大模型并解析 JSON。"""

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
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                )
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
        """意图识别节点业务逻辑。"""

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
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    def _helper_task_parse_node_logic(intent_result: dict[str, Any], model_name: str) -> dict[str, Any]:
        """任务解析节点业务逻辑。"""

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
                "start": str(time_range_raw.get("start")).strip() if time_range_raw.get("start") not in (None, "") else None,
                "end": str(time_range_raw.get("end")).strip() if time_range_raw.get("end") not in (None, "") else None,
            },
            "operation": operation,
            "confidence": confidence,
        }
        print("任务解析节点输出:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    def _helper_sql_generation_node_logic(
        rewritten_query: str,
        parse_result: dict[str, Any],
        model_name: str,
    ) -> dict[str, Any]:
        """SQL 生成节点业务逻辑。"""

        if not isinstance(parse_result, dict):
            raise ValueError("SQL 生成缺少有效任务解析结果")
        if str(parse_result.get("intent", "")).strip().lower() != "business_query":
            raise ValueError("SQL 生成仅支持 business_query")

        field_whitelist, alias_pairs, schema_hints = _helper_build_kb_hints()
        whitelist_set = set(field_whitelist)

        llm_output = _helper_call_llm(
            system_prompt=SQL_GENERATION_SYSTEM_PROMPT,
            user_prompt=build_sql_generation_user_prompt(
                rewritten_query=rewritten_query,
                task=parse_result,
                field_whitelist=field_whitelist,
                alias_pairs=alias_pairs,
                schema_hints=schema_hints,
            ),
            model_name=model_name,
            timeout=30.0,
        )

        sql = str(llm_output.get("sql", "")).strip()
        if not sql:
            raise ValueError("SQL 生成缺少 sql 字段")
        if not re.search(r"^\s*with\b", sql, flags=re.I):
            raise ValueError("SQL 生成未使用 WITH（CTE）")

        sql_fields = _helper_extract_sql_fields(sql)
        if not sql_fields:
            raise ValueError("SQL 中未识别到 table.field 字段")
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
        }
        print("SQL 生成节点输出:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return result

    def _helper_insert_workflow_log(
        session_id: str,
        step_name: str,
        input_json: dict[str, Any],
        output_json: dict[str, Any] | None,
        status: str,
        error_message: str | None,
    ) -> None:
        """插入工作流日志。"""

        db.add(
            WorkflowLog(
                session_id=session_id,
                step_name=step_name,
                input_json=input_json,
                output_json=output_json,
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
        rewritten_query: str,
        model_name: str,
    ) -> None:
        """插入一轮 user + assistant 会话。"""

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
                message_content=rewritten_query,
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
        """保存节点输入输出到本地。"""

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
        file_path.write_text(json.dumps(payload_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _helper_node_logger(
        step_name: str,
        node_input: dict[str, Any],
        node_output: dict[str, Any] | None,
        status: str,
        error_message: str | None,
    ) -> None:
        """节点日志包装。"""

        _helper_save_node_io_local(
            session_id=session_id,
            step_name=step_name,
            node_input=node_input,
            node_output=node_output,
            status=status,
            error_message=error_message,
        )

    def _helper_intent_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """图中的意图识别节点。"""

        node_input = {
            "message": state["message"],
            "history_user_messages": state["history_user_messages"],
            "threshold": state["threshold"],
            "model_name": state["model_name"],
        }
        try:
            intent_result = _helper_intent_node_logic(
                message=state["message"],
                history_user_messages=state["history_user_messages"],
                threshold=state["threshold"],
                model_name=state["model_name"],
            )
            _helper_node_logger("intent_recognition", node_input, intent_result, "success", None)
            return {**state, "intent_result": intent_result}
        except Exception as exc:
            _helper_node_logger("intent_recognition", node_input, None, "failed", str(exc))
            raise

    def _helper_task_parse_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """图中的任务解析节点。"""

        intent_result = state.get("intent_result") or {}
        node_input = {"intent_result": intent_result}
        try:
            parse_result = _helper_task_parse_node_logic(intent_result=intent_result, model_name=state["model_name"])
            _helper_node_logger("task_parse", node_input, parse_result, "success", None)
            return {**state, "parse_result": parse_result}
        except Exception as exc:
            _helper_node_logger("task_parse", node_input, None, "failed", str(exc))
            raise

    def _helper_sql_generation_node(state: UnifiedChatGraphState) -> UnifiedChatGraphState:
        """图中的 SQL 生成节点。"""

        parse_result = state.get("parse_result") or {}
        rewritten_query = str((state.get("intent_result") or {}).get("rewritten_query", state["message"])).strip()
        node_input = {
            "rewritten_query": rewritten_query,
            "parse_result": parse_result,
        }
        try:
            sql_result = _helper_sql_generation_node_logic(
                rewritten_query=rewritten_query,
                parse_result=parse_result,
                model_name=state["model_name"],
            )
            _helper_node_logger("sql_generation", node_input, sql_result, "success", None)
            return {**state, "sql_result": sql_result}
        except Exception as exc:
            _helper_node_logger("sql_generation", node_input, None, "failed", str(exc))
            raise

    def _helper_build_graph():
        """构建统一工作流图。"""

        def _helper_route_after_intent(state: UnifiedChatGraphState) -> str:
            intent_result = state.get("intent_result") or {}
            intent = str(intent_result.get("intent", "chat")).strip().lower()
            if intent == "business_query":
                return "task_parse"
            return "end"

        graph = StateGraph(UnifiedChatGraphState)
        graph.add_node("intent_recognition", _helper_intent_node)
        graph.add_node("task_parse", _helper_task_parse_node)
        graph.add_node("sql_generation", _helper_sql_generation_node)
        graph.add_edge(START, "intent_recognition")
        graph.add_conditional_edges(
            "intent_recognition",
            _helper_route_after_intent,
            {"task_parse": "task_parse", "end": END},
        )
        graph.add_edge("task_parse", "sql_generation")
        graph.add_edge("sql_generation", END)
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

        skipped = parse_result is None
        result = {
            "session_id": session_id,
            "intent": intent_result.get("intent", "chat"),
            "is_followup": bool(intent_result.get("is_followup", False)),
            "merged_query": str(intent_result.get("merged_query", payload.message)).strip(),
            "rewritten_query": str(intent_result.get("rewritten_query", payload.message)).strip(),
            "skipped": skipped,
            "reason": "intent_is_chat" if skipped else None,
            "task": parse_result,
            "sql_result": sql_result,
        }

        _helper_insert_chat_history(
            session_id=session_id,
            user_message=payload.message,
            rewritten_query=result["rewritten_query"],
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
                status="success",
                error_message=None,
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
            db.commit()
        except Exception:
            db.rollback()
        raise
