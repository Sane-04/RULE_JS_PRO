# 工作流节点输入输出完整结构说明

本文档基于 `app/services/chat_graph.py` 当前实现整理，覆盖工作流每个节点的输入/输出结构（含内层结构、成功/失败分支）。

## 1. 顶层入口与状态

### 1.1 `execute_chat_workflow` 输入

```ts
type ChatIntentRequest = {
  session_id: string | null
  message: string
  model_name: string | null
}

type ExecuteChatWorkflowInput = {
  db: Session
  admin_id: number
  payload: ChatIntentRequest
  on_step_event?: (
    step_name: "intent_recognition" | "task_parse" | "sql_generation" | "sql_validate" | "hidden_context" | "result_return",
    status: "start" | "end" | "error",
    error_message?: string | null
  ) => void
}
```

### 1.2 图状态 `UnifiedChatGraphState`

```ts
type UnifiedChatGraphState = {
  message: string
  history_user_messages: string[]
  threshold: number
  model_name: string
  intent_result: IntentResult | null
  parse_result: ParseResult | null
  sql_result: SqlGenerationResult | null
  sql_validate_result: SqlValidateResult | null
  hidden_context_result: HiddenContextResult | null
  hidden_context_retry_count: number
  result_return_result: ResultReturnResult | null
}
```

### 1.3 最终返回值

`execute_chat_workflow` 正常返回 `ResultReturnResult`。

## 2. 公共内层结构定义

### 2.1 意图识别结果

```ts
type IntentResult = {
  intent: "chat" | "business_query"
  is_followup: boolean
  confidence: number // [0,1]
  merged_query: string
  rewritten_query: string
  threshold: number
}
```

### 2.2 任务解析结果

```ts
type TaskEntity = {
  type: string
  value: string
}

type TaskFilter = {
  field: string // 必须在 schema 白名单中，格式 table.field
  op: "=" | "!=" | ">" | "<" | ">=" | "<=" | "like" | "in" | "not in" | "between"
  value: any // string | number | boolean | null | array
}

type TaskTimeRange = {
  start: string | null
  end: string | null
}

type ParseResult = {
  intent: "business_query"
  entities: TaskEntity[]
  dimensions: string[]
  metrics: string[]
  filters: TaskFilter[]
  time_range: TaskTimeRange
  operation: "detail" | "aggregate" | "ranking" | "trend"
  confidence: number // [0,1]
}
```

### 2.3 SQL 生成结果

```ts
type EntityMapping = {
  type: string
  value: string
  field: string // table.field
  reason: string
}

type AppliedFieldReplacement = {
  from: string
  to: string
}

type SqlGenerationSuccess = {
  sql: string
  entity_mappings: EntityMapping[]
  sql_fields: string[]
  applied_field_replacements: AppliedFieldReplacement[]
}

type SqlGenerationFailed = {
  sql: ""
  entity_mappings: []
  sql_fields: []
  generation_failed: true
  generation_error: string
}

type SqlGenerationResult = SqlGenerationSuccess | SqlGenerationFailed
```

### 2.4 SQL 校验结果

```ts
type SqlValidateResult = {
  is_valid: boolean
  error: string | null
  rows: number
  result: Array<Record<string, any>>
  executed_sql: string
  empty_result: boolean
  zero_metric_result: boolean
}
```

### 2.5 隐藏上下文结果

```ts
type HiddenContextFieldCandidate = {
  missing: string
  candidates: string[]
}

type HiddenContextProbeSample = {
  field: string
  probe_sql: string
  values: string[]
  error?: string
}

type HiddenContextResult = {
  error_type: "execution_error" | "unknown_column" | "unknown_table" | "syntax_error" | "object_not_found"
  error: string
  failed_sql: string
  rewritten_query: string
  field_candidates: HiddenContextFieldCandidate[]
  probe_samples: HiddenContextProbeSample[]
  hints: string[]
  kb_summary: {
    table_count: number
    field_count: number
  }
  retry_count: number // 在 hidden_context 节点包装器中追加
}
```

### 2.6 结果返回结果（最终响应）

```ts
type ResultReturnResult = {
  session_id: string
  intent: "chat" | "business_query"
  is_followup: boolean
  merged_query: string
  rewritten_query: string
  skipped: boolean
  reason: string | null
  final_status: "success" | "partial_success" | "failed"
  reason_code:
    | "intent_is_chat"
    | "task_parse_missing"
    | "sql_validate_missing"
    | "empty_result_after_retry"
    | "zero_metric_after_retry"
    | "sql_invalid_after_retry"
    | null
  summary: string
  assistant_reply: string
  download_url: string | null
  task: ParseResult | null
  sql_result: SqlGenerationResult | null
  sql_validate_result: SqlValidateResult | null
  hidden_context_result: HiddenContextResult | null
  hidden_context_retry_count: number
}
```

## 3. 每个节点的输入输出

## 3.1 `intent_recognition`

### 输入（`node_input`）

```ts
type IntentNodeInput = {
  message: string
  history_user_messages: string[]
  threshold: number
  model_name: string
}
```

### 输出（成功）

```ts
type IntentNodeOutputSuccess = IntentResult
```

### 输出（失败）

```ts
type IntentNodeOutputFailed = null
// 错误文本写入 node_io.error_message
```

### 状态写回

```ts
state.intent_result = IntentNodeOutputSuccess
```

## 3.2 `task_parse`

### 输入（`node_input`）

```ts
type TaskParseNodeInput = {
  intent_result: IntentResult | {}
}
```

### 输出（成功）

```ts
type TaskParseNodeOutputSuccess = ParseResult
```

### 输出（失败）

```ts
type TaskParseNodeOutputFailed = null
```

### 状态写回

```ts
state.parse_result = TaskParseNodeOutputSuccess
```

## 3.3 `sql_generation`

### 输入（`node_input`）

```ts
type SqlGenerationNodeInput = {
  rewritten_query: string
  parse_result: ParseResult | {}
  hidden_context_result: HiddenContextResult | null
  model_name: string // settings.llm_model_sql_generation 或 state.model_name
}
```

### 输出（成功）

```ts
type SqlGenerationNodeOutputSuccess = SqlGenerationSuccess
```

### 输出（失败，节点内部降级，不抛出）

```ts
type SqlGenerationNodeOutputFailed = SqlGenerationFailed
```

### 状态写回

```ts
// 成功
state.sql_result = SqlGenerationNodeOutputSuccess

// 失败
state.sql_result = SqlGenerationNodeOutputFailed
state.sql_validate_result = {
  is_valid: false,
  error: string, // generation_error
  rows: 0,
  result: [],
  executed_sql: "",
  empty_result: false,
  zero_metric_result: false
}
```

## 3.4 `sql_validate`

### 输入（`node_input`）

```ts
type SqlValidateNodeInput = {
  sql_result: SqlGenerationResult | null
}
```

### 输出

```ts
type SqlValidateNodeOutput = SqlValidateResult
```

### 状态写回

```ts
state.sql_validate_result = SqlValidateNodeOutput
```

## 3.5 `hidden_context`

### 输入（`node_input`）

```ts
type HiddenContextNodeInput = {
  rewritten_query: string
  parse_result: ParseResult | null
  sql_result: SqlGenerationResult | null
  sql_validate_result: SqlValidateResult | null
  hidden_context_retry_count: number
}
```

### 输出（成功）

```ts
type HiddenContextNodeOutputSuccess = HiddenContextResult
```

### 输出（失败）

```ts
type HiddenContextNodeOutputFailed = null
```

### 状态写回

```ts
const next_retry_count = state.hidden_context_retry_count + 1
state.hidden_context_result = { ...HiddenContextNodeOutputSuccess, retry_count: next_retry_count }
state.hidden_context_retry_count = next_retry_count
```

## 3.6 `result_return`

### 输入（`node_input`）

```ts
type ResultReturnNodeInput = {
  message: string
  intent_result: IntentResult | null
  parse_result: ParseResult | null
  sql_result: SqlGenerationResult | null
  sql_validate_result: SqlValidateResult | null
  hidden_context_result: HiddenContextResult | null
  hidden_context_retry_count: number
}
```

### 输出（成功）

```ts
type ResultReturnNodeOutputSuccess = ResultReturnResult
```

### 输出（失败）

```ts
type ResultReturnNodeOutputFailed = null
```

### 状态写回

```ts
state.result_return_result = ResultReturnNodeOutputSuccess
```

## 4. 节点本地日志文件结构（`local_logs/node_io/...`）

每个节点都会按以下结构落盘：

```ts
type NodeIoLogFile<TInput, TOutput> = {
  session_id: string
  admin_id: number
  step_name: "intent_recognition" | "task_parse" | "sql_generation" | "sql_validate" | "hidden_context" | "result_return"
  status: "success" | "failed"
  error_message: string | null
  timestamp: string // ISO-8601 到秒
  input: TInput
  output: TOutput | null
}
```

## 5. 路由规则（补充）

```ts
intent_recognition -> task_parse | result_return
task_parse -> sql_generation
sql_generation -> sql_validate | hidden_context | result_return
sql_validate -> hidden_context | result_return
hidden_context -> sql_generation | result_return
result_return -> END
```

