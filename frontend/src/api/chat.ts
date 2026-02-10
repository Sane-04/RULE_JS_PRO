import api from "./client";

export type ChatRequest = {
  session_id?: string;
  message: string;
  model_name?: string;
};

export type TaskEntity = {
  type: string;
  value: string;
};

export type TaskFilter = {
  field: string;
  op: string;
  value: unknown;
};

export type TaskTimeRange = {
  start: string | null;
  end: string | null;
};

export type TaskParseResult = {
  intent: "chat" | "business_query";
  entities: TaskEntity[];
  dimensions: string[];
  metrics: string[];
  filters: TaskFilter[];
  time_range: TaskTimeRange;
  operation: "detail" | "aggregate" | "ranking" | "trend";
  confidence: number;
};

export type ChatData = {
  session_id: string;
  intent: "chat" | "business_query";
  is_followup: boolean;
  merged_query: string;
  rewritten_query: string;
  skipped: boolean;
  reason: string | null;
  final_status: "success" | "partial_success" | "failed";
  reason_code: string | null;
  summary: string;
  task: TaskParseResult | null;
  sql_result: {
    sql: string;
    entity_mappings: Array<{
      type: string;
      value: string;
      field: string;
      reason: string;
    }>;
    sql_fields: string[];
  } | null;
  sql_validate_result: {
    is_valid: boolean;
    error: string | null;
    rows: number;
    result: Array<Record<string, unknown>>;
    executed_sql: string;
    empty_result: boolean;
    zero_metric_result: boolean;
  } | null;
  hidden_context_result: {
    error_type: string;
    error: string;
    failed_sql: string;
    rewritten_query: string;
    field_candidates: Array<Record<string, unknown>>;
    probe_samples: Array<Record<string, unknown>>;
    hints: string[];
    kb_summary: Record<string, unknown>;
    retry_count: number;
  } | null;
  hidden_context_retry_count: number;
};

export type ChatResponse = {
  code: number;
  message: string;
  data: ChatData;
};

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>("/chat", payload);
  return response.data;
}
