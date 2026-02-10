from __future__ import annotations

import json
from typing import Any

RESULT_SUMMARY_SYSTEM_PROMPT = """
你是教务查询结果总结助手。
请根据输入的用户问题与查询结果，生成简洁、准确、可直接展示给用户的总结。

强约束：
1) 只输出一个 JSON 对象，不要输出 markdown、解释或多余文本。
2) JSON 必须包含字段：
   - summary: string
3) summary 使用中文，不超过120字。
4) 若 final_status=success，summary 要直接回答问题。
5) 若 final_status=partial_success 或 failed，summary 要说明当前结果与原因码（reason_code）的含义，并给出简短建议。
6) 不要虚构不存在的数据；只基于输入结果描述。
""".strip()


def build_result_summary_user_prompt(
    user_query: str,
    rewritten_query: str,
    final_status: str,
    reason_code: str | None,
    task: dict[str, Any] | None,
    sql_validate_result: dict[str, Any] | None,
    hidden_context_retry_count: int,
) -> str:
    payload: dict[str, Any] = {
        "user_query": user_query,
        "rewritten_query": rewritten_query,
        "final_status": final_status,
        "reason_code": reason_code,
        "task": task,
        "sql_validate_result": sql_validate_result,
        "hidden_context_retry_count": hidden_context_retry_count,
        "output_schema": {
            "summary": "string",
        },
    }
    return json.dumps(payload, ensure_ascii=False)
