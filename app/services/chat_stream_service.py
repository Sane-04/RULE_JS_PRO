from __future__ import annotations

import json
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas.chat import ChatIntentRequest
from app.services.chat_graph import execute_chat_workflow

STEP_DISPLAY_NAMES: dict[str, str] = {
    "intent_recognition": "intent_recognition",
    "task_parse": "task_parse",
    "sql_generation": "sql_generation",
    "sql_validate": "sql_validate",
    "hidden_context": "hidden_context",
    "result_return": "result_return",
}

WORKFLOW_ERROR_MESSAGE = "工作流执行失败，请稍后重试。"
STEP_ERROR_MESSAGE_TEMPLATE = "{step}步骤执行异常，系统已终止本次处理。"
SSE_HEARTBEAT_INTERVAL_SECONDS = 0.8
SSE_PRELUDE_PADDING_CHARS = 2048


def generate_chat_stream(admin_id: int, payload: ChatIntentRequest) -> Iterator[str]:
    """作用：执行聊天工作流并持续输出 SSE 事件流。

    输入参数：
    - admin_id: int，当前管理员 ID。
    - payload: ChatIntentRequest，聊天请求体。

    输出参数：
    - Iterator[str]：SSE 文本片段迭代器。
    """

    def _helper_get_step_message(step_name: str, status: str) -> str:
        """作用：根据步骤名与状态获取占位文案。

        输入参数：
        - step_name: str，步骤名称。
        - status: str，步骤状态（start/end）。

        输出参数：
        - str：占位文案。
        """
        mapping = settings.chat_stream_step_message_placeholders.get(step_name, {})
        return mapping.get(status, f"__STEP_{step_name.upper()}_{status.upper()}__")

    def _helper_format_sse_chunk(event_name: str, event_payload: dict[str, Any]) -> str:
        """作用：把事件对象编码为 SSE 文本块。

        输入参数：
        - event_name: str，事件名称。
        - event_payload: dict[str, Any]，事件数据。

        输出参数：
        - str：SSE 格式文本（event/data + 空行）。
        """
        data_text = json.dumps(event_payload, ensure_ascii=False)
        return f"event: {event_name}\ndata: {data_text}\n\n"

    stream_session_id = payload.session_id or uuid.uuid4().hex[:16]
    run_payload = ChatIntentRequest(
        session_id=stream_session_id,
        message=payload.message,
        model_name=payload.model_name,
    )
    event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def _helper_worker() -> None:
        """作用：后台执行工作流并把事件写入队列。

        输入参数：
        - 无

        输出参数：
        - None
        """
        def _helper_emit_event(
            event_name: str,
            step: str,
            status: str,
            message: str,
            result: dict[str, Any] | None = None,
            step_payload: dict[str, Any] | None = None,
        ) -> None:
            """作用：构建统一事件 payload 并入队。

            输入参数：
            - event_name: str，事件名称。
            - step: str，步骤名。
            - status: str，状态（start/end/error）。
            - message: str，状态文案。
            - result: dict[str, Any] | None，可选最终结果。
            - step_payload: dict[str, Any] | None，可选步骤附加数据。

            输出参数：
            - None
            """
            nonlocal seq
            seq += 1
            payload_data: dict[str, Any] = {
                "session_id": stream_session_id,
                "step": step,
                "status": status,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "seq": seq,
            }
            if result is not None:
                payload_data["result"] = result
            if step_payload is not None:
                payload_data["step_payload"] = step_payload
            event_queue.put({"event": event_name, "data": payload_data})

        def _helper_step_callback(
                step_name: str,
                status: str,
                _error_message: str | None,
                step_payload: dict[str, Any] | None,
        ) -> None:
            """作用：接收节点回调并转换为 SSE 事件。

            输入参数：
            - step_name: str，节点名。
            - status: str，节点状态（start/end/error）。
            - _error_message: str | None，预留错误信息字段。
            - step_payload: dict[str, Any] | None，步骤附加信息。

            输出参数：
            - None
            """
            if status == "start":
                _helper_emit_event("step_start", step_name, "start", _helper_get_step_message(step_name, "start"))
                return
            if status == "end":
                _helper_emit_event(
                    "step_end",
                    step_name,
                    "end",
                    _helper_get_step_message(step_name, "end"),
                    step_payload=step_payload,
                )
                return
            step_label = STEP_DISPLAY_NAMES.get(step_name, step_name)
            _helper_emit_event(
                "step_end",
                step_name,
                "error",
                STEP_ERROR_MESSAGE_TEMPLATE.format(step=step_label),
            )

        db = SessionLocal()
        seq = 0

        try:
            _helper_emit_event("workflow_start", "workflow", "start", settings.chat_stream_workflow_start_message)
            result = execute_chat_workflow(
                db=db,
                admin_id=admin_id,
                payload=run_payload,
                on_step_event=_helper_step_callback,
            )
            _helper_emit_event(
                "workflow_end",
                "workflow",
                "end",
                settings.chat_stream_workflow_end_message,
                result=result,
            )
        except Exception:
            _helper_emit_event("workflow_error", "workflow", "error", WORKFLOW_ERROR_MESSAGE)
        finally:
            db.close()
            event_queue.put(None)

    worker_thread = threading.Thread(target=_helper_worker, daemon=True)
    worker_thread.start()

    # 预热注释块：用于穿透部分代理/中间层的小包缓冲阈值。
    yield f": {' ' * SSE_PRELUDE_PADDING_CHARS}\n\n"

    while True:
        try:
            item = event_queue.get(timeout=SSE_HEARTBEAT_INTERVAL_SECONDS)
        except queue.Empty:
            # 心跳注释行：保持连接活跃并持续触发流式刷新。
            yield ": heartbeat\n\n"
            continue
        if item is None:
            break
        yield _helper_format_sse_chunk(item["event"], item["data"])
