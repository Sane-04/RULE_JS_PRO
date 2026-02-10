from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatIntentRequest(BaseModel):
    session_id: str | None = Field(default=None, description="会话ID，首次可为空")
    message: str = Field(..., min_length=1, description="当前用户问题")
    model_name: str | None = Field(default=None, description="可选模型名覆盖")


class ChatIntentData(BaseModel):
    session_id: str = Field(..., description="会话ID")
    intent: str = Field(..., description="意图：chat/business_query")
    is_followup: bool = Field(..., description="是否追问")
    confidence: float = Field(..., ge=0.0, le=1.0, description="意图置信度")
    merged_query: str = Field(..., description="合并后的查询文本")
    rewritten_query: str = Field(..., description="最终查询文本")
    threshold: float = Field(..., description="意图阈值")


class ChatIntentResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: ChatIntentData


class TaskEntity(BaseModel):
    type: str = Field(..., description="实体类型")
    value: str = Field(..., description="实体值")


class TaskFilter(BaseModel):
    field: str = Field(..., description="过滤字段，必须是 table.field")
    op: str = Field(..., description="操作符，例如 =, >, <, like")
    value: Any = Field(..., description="过滤值")


class TaskTimeRange(BaseModel):
    start: str | None = Field(default=None, description="开始日期（YYYY-MM-DD）")
    end: str | None = Field(default=None, description="结束日期（YYYY-MM-DD）")


class TaskParseResult(BaseModel):
    intent: Literal["chat", "business_query"] = Field(..., description="解析后意图")
    entities: list[TaskEntity] = Field(default_factory=list, description="实体集合")
    dimensions: list[str] = Field(default_factory=list, description="维度集合")
    metrics: list[str] = Field(default_factory=list, description="指标集合")
    filters: list[TaskFilter] = Field(default_factory=list, description="过滤条件集合")
    time_range: TaskTimeRange = Field(default_factory=TaskTimeRange, description="时间范围")
    operation: Literal["detail", "aggregate", "ranking", "trend"] = Field(default="detail", description="操作类型")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="解析置信度")


class ChatParseData(BaseModel):
    session_id: str = Field(..., description="会话ID")
    intent: str = Field(..., description="意图：chat/business_query")
    is_followup: bool = Field(..., description="是否追问")
    merged_query: str = Field(..., description="合并后的查询")
    rewritten_query: str = Field(..., description="改写后的查询")
    skipped: bool = Field(..., description="是否跳过任务解析（intent=chat 时为 true）")
    reason: str | None = Field(default=None, description="跳过原因")
    task: TaskParseResult | None = Field(default=None, description="结构化任务结果")
    sql_result: dict[str, Any] | None = Field(default=None, description="SQL 生成节点输出（含 SQL 与映射详情）")


class ChatParseResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: ChatParseData
