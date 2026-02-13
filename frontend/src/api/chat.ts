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
  assistant_reply?: string | null;
  download_url?: string | null;
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

export type ChatStreamEventName =
  | "workflow_start"
  | "step_start"
  | "step_end"
  | "workflow_error"
  | "workflow_end";

export type ChatStreamEventData = {
  session_id: string;
  step: string;
  status: "start" | "end" | "error";
  message: string;
  timestamp: string;
  seq: number;
  result?: ChatData;
  step_payload?: Record<string, unknown>;
};

export type PostChatStreamOptions = {
  onEvent?: (event: ChatStreamEventName, data: ChatStreamEventData) => void;
};

export type ChatListMeta = {
  offset: number;
  limit: number;
  total: number;
};

export type ChatSessionItem = {
  session_id: string;
  preview: string;
  last_active_at: string;
};

export type ChatSessionMessageItem = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type ChatSessionListResponse = {
  code: number;
  message: string;
  data: ChatSessionItem[];
  meta: ChatListMeta;
};

export type ChatSessionMessageListResponse = {
  code: number;
  message: string;
  data: ChatSessionMessageItem[];
  meta: ChatListMeta;
};

export type ChatSessionMutationResponse = {
  code: number;
  message: string;
  data: {
    deleted: number;
    session_id?: string;
  };
};

function buildFallbackChatResponse(sessionId: string, summary: string): ChatResponse {
  return {
    code: 0,
    message: "ok",
    data: {
      session_id: sessionId,
      intent: "chat",
      is_followup: false,
      merged_query: "",
      rewritten_query: "",
      skipped: false,
      reason: null,
      final_status: "success",
      reason_code: null,
      summary,
      assistant_reply: summary,
      download_url: null,
      task: null,
      sql_result: null,
      sql_validate_result: null,
      hidden_context_result: null,
      hidden_context_retry_count: 0,
    },
  };
}

async function fetchLatestAssistantSummary(sessionId: string, token: string | null): Promise<string | null> {
  const headers: Record<string, string> = {};
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const probeResp = await fetch(`/api/chat/sessions/${sessionId}/messages?offset=0&limit=1`, { headers });
  if (!probeResp.ok) {
    return null;
  }
  const probeJson = (await probeResp.json()) as ChatSessionMessageListResponse;
  const total = Number(probeJson?.meta?.total ?? 0);
  if (total <= 0) {
    return null;
  }

  const lastOffset = Math.max(total - 1, 0);
  const lastResp = await fetch(`/api/chat/sessions/${sessionId}/messages?offset=${lastOffset}&limit=1`, { headers });
  if (!lastResp.ok) {
    return null;
  }
  const lastJson = (await lastResp.json()) as ChatSessionMessageListResponse;
  const row = lastJson?.data?.[0];
  if (!row || row.role !== "assistant") {
    return null;
  }
  return row.content || "";
}

export async function postChat(payload: ChatRequest): Promise<ChatResponse> {
  const response = await api.post<ChatResponse>("/chat", payload);
  return response.data;
}

export async function postChatStream(
  payload: ChatRequest,
  options: PostChatStreamOptions = {}
): Promise<ChatResponse> {
  const token = localStorage.getItem("edu_token");
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const errorJson = await response.json();
      message = errorJson?.message ?? message;
    } catch {
      // ignore json parse error and keep fallback message
    }
    throw new Error(message);
  }

  const contentType = String(response.headers.get("content-type") || "").toLowerCase();
  if (!contentType.includes("text/event-stream")) {
    const json = (await response.json()) as ChatResponse;
    return json;
  }

  if (!response.body) {
    throw new Error("Empty stream response");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let currentEvent = "";
  let dataLines: string[] = [];
  let finalResult: ChatData | null = null;
  let workflowErrorMessage = "";
  let streamParseError = "";
  let lastSessionId = "";
  let sawWorkflowEnd = false;

  const flushEvent = () => {
    if (!currentEvent || !dataLines.length) {
      currentEvent = "";
      dataLines = [];
      return;
    }
    const rawData = dataLines.join("\n");
    dataLines = [];
    try {
      const parsed = JSON.parse(rawData) as ChatStreamEventData;
      const eventName = currentEvent as ChatStreamEventName;
      options.onEvent?.(eventName, parsed);
      if (parsed.session_id) {
        lastSessionId = parsed.session_id;
      }
      if (eventName === "workflow_end") {
        sawWorkflowEnd = true;
      }
      if (eventName === "workflow_error" && parsed.message) {
        workflowErrorMessage = parsed.message;
      }
      if (eventName === "workflow_end" && parsed.result) {
        finalResult = parsed.result;
      }
    } catch {
      // 记录解析失败，避免静默吞掉最终事件导致误判
      streamParseError = "Malformed SSE event payload";
    } finally {
      currentEvent = "";
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    while (true) {
      const newlineIndex = buffer.indexOf("\n");
      if (newlineIndex < 0) {
        break;
      }
      const line = buffer.slice(0, newlineIndex).replace(/\r$/, "");
      buffer = buffer.slice(newlineIndex + 1);
      if (!line) {
        flushEvent();
        continue;
      }
      if (line.startsWith("event:")) {
        currentEvent = line.slice("event:".length).trim();
        continue;
      }
      if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trim());
      }
    }
  }
  // flush decoder internal bytes to avoid truncating the last UTF-8 event
  buffer += decoder.decode();
  while (true) {
    const newlineIndex = buffer.indexOf("\n");
    if (newlineIndex < 0) {
      break;
    }
    const line = buffer.slice(0, newlineIndex).replace(/\r$/, "");
    buffer = buffer.slice(newlineIndex + 1);
    if (!line) {
      flushEvent();
      continue;
    }
    if (line.startsWith("event:")) {
      currentEvent = line.slice("event:".length).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim());
    }
  }
  flushEvent();

  if (workflowErrorMessage) {
    throw new Error(workflowErrorMessage);
  }
  if (streamParseError) {
    throw new Error(streamParseError);
  }
  if (!finalResult) {
    if (sawWorkflowEnd && lastSessionId) {
      const summary = await fetchLatestAssistantSummary(lastSessionId, token);
      if (summary !== null) {
        return buildFallbackChatResponse(lastSessionId, summary);
      }
    }
    throw new Error("Missing final result from stream");
  }
  return { code: 0, message: "ok", data: finalResult };
}

export async function getChatSessions(params: {
  offset: number;
  limit: number;
}): Promise<ChatSessionListResponse> {
  const response = await api.get<ChatSessionListResponse>("/chat/sessions", { params });
  return response.data;
}

export async function getChatSessionMessages(
  sessionId: string,
  params: { offset: number; limit: number }
): Promise<ChatSessionMessageListResponse> {
  const response = await api.get<ChatSessionMessageListResponse>(`/chat/sessions/${sessionId}/messages`, { params });
  return response.data;
}

export async function deleteChatSession(sessionId: string): Promise<ChatSessionMutationResponse> {
  const response = await api.delete<ChatSessionMutationResponse>(`/chat/sessions/${encodeURIComponent(sessionId)}`);
  return response.data;
}

export async function clearChatSessions(): Promise<ChatSessionMutationResponse> {
  const response = await api.delete<ChatSessionMutationResponse>("/chat/sessions");
  return response.data;
}
