# 教务驾驶舱系统（多 Agents 工作流）蓝图

本文档作为后续开发的“项目蓝图”，指导 AI 与开发者在统一框架下推进前后端分离的教务驾驶舱系统。系统面向 **管理员**，以“监控、洞察、预警、可解释”为主线，同时保留“数据管理”能力作为底座，覆盖大规模数据（教师 1100+、学生 20000+、专业 64、每专业约 6 个班级）。

---

## 1. 项目定位与目标

### 1.1 驾驶舱作用
- 一屏掌握关键指标，形成教务全局视角
- 监控趋势与变化，辅助管理决策
- 预警异常与风险，提前暴露问题
- 结果可解释、可追溯，提升可信度与可控性

### 1.2 核心目标
- 管理员登录与权限控制
- 教务指标看板与趋势分析
- 预警中心与异常提示
- 智能聊天与可解释查询
- 历史记录与知识资产沉淀
- 多 Agents 工作流自动化执行
- SSE 实时反馈流程执行状态
- 全量数据查询、修改与录入（含批量导入）

### 1.3 角色与权限
- **仅管理员** 角色
- 可访问所有模块与数据

---

## 2. 技术选型

### 2.1 前端
- Vue 3 + Vite
- UI 框架：建议 Element Plus 或 Arco（最终可替换）
- 状态管理：Pinia
- 请求与 SSE：Axios + EventSource

### 2.2 后端
- FastAPI
- LangGraph（多 Agents 流程编排）
- SQLAlchemy（或 MySQL 原生驱动）
- MySQL 8.0.25

### 2.3 LLM 调用
- 预留多模型接入：DeepSeek、通义千问、ChatGPT
- 统一配置入口（全局配置文件）
- 支持切换模型与多 provider

---

## 3. 功能模块描述（驾驶舱主线）

### 3.1 驾驶舱总览
- 关键指标汇总（规模、质量、风险）
- 近期趋势与环比/同比

### 3.2 指标看板
- 指标定义、口径与刷新策略
- 指标可解释说明（字段映射、计算逻辑）

### 3.3 预警中心
- 预警规则配置
- 预警事件列表与处理状态

### 3.4 智能聊天（可解释）
- 管理员自然语言查询/修改
- 输出可解释信息（字段映射、表关联、逻辑摘要）
- 风险等级提示与高风险确认

### 3.5 工作流可视化
- 节点级输入/输出展示
- 执行路径回放与异常定位

### 3.6 历史记录与知识资产
- 保存聊天与工作流历史
- 抽取常用查询模板并沉淀为知识资产

### 3.7 数据底座（管理能力）
- 全量业务表查询、修改
- 条件过滤、分页、排序
- 单条录入与批量导入（CSV/Excel）

### 3.8 系统配置
- 模型配置
- 数据导入配置
- 策略规则配置

---

## 4. 最小驾驶舱视图（MVP）

### 4.1 必备视图
- 核心指标卡片（学生总数、教师总数、课程总数、缺勤率、挂科率）
- 趋势折线（缺勤率/挂科率近 7~30 天）
- 预警列表（阈值触发的异常班级/课程）

### 4.2 展示原则
- 视图优先级：指标卡片 > 趋势 > 预警
- 单屏完成“看见问题、理解问题”

---

## 5. 指标体系与预警示例

### 5.1 指标类别
- 规模类：学生总数、教师总数、课程总数
- 质量类：平均成绩、挂科率、缺勤率
- 风险类：高风险课程数、异常班级数

### 5.2 预警示例
- 某班级缺勤率超过阈值
- 某课程挂科率连续上升
- 某学院课程容量不足

---

## 6. 数据库设计（MySQL 8.0.25）

### 6.1 设计原则
- 使用下划线命名
- 每表包含审计字段：
  - created_at（创建时间）
  - updated_at（更新时间）
  - created_by（创建人）
  - updated_by（更新人）
  - is_deleted（逻辑删除）
- 统一主键 id
- 重要字段建立索引

### 6.2 核心业务表

以下为推荐表结构，每个字段均附中文含义说明，便于 LLM 进行 SQL 语义映射。

#### 6.2.1 管理员表 admin
- id：主键
- username：账号
- password_hash：密码哈希
- real_name：姓名
- phone：手机号
- email：邮箱
- last_login_at：最后登录时间
- status：状态（启用/禁用）
- created_at：创建时间
- updated_at：更新时间
- created_by：创建人
- updated_by：更新人
- is_deleted：逻辑删除

#### 6.2.2 学院表 college
- id：主键
- college_name：学院名称
- college_code：学院编码
- description：描述
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.3 专业表 major
- id：主键
- major_name：专业名称
- major_code：专业编码
- college_id：所属学院
- degree_type：学历类型（本科/硕士/博士）
- description：描述
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.4 班级表 class
- id：主键
- class_name：班级名称
- class_code：班级编码
- major_id：所属专业
- grade_year：入学年份
- head_teacher_id：班主任教师
- student_count：班级人数
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.5 学生表 student
- id：主键
- student_no：学号
- real_name：姓名
- gender：性别
- id_card：身份证号
- birth_date：出生日期
- phone：手机号
- email：邮箱
- address：家庭住址
- class_id：所属班级
- major_id：专业
- college_id：学院
- enroll_year：入学年份
- status：学籍状态（在读/休学/毕业）
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.6 教师表 teacher
- id：主键
- teacher_no：工号
- real_name：姓名
- gender：性别
- id_card：身份证号
- birth_date：出生日期
- phone：手机号
- email：邮箱
- title：职称
- college_id：学院
- status：状态（在职/离职/退休）
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.7 课程表 course
- id：主键
- course_name：课程名称
- course_code：课程编码
- credit：学分
- hours：学时
- course_type：课程类型（必修/选修）
- college_id：所属学院
- description：描述
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.8 教学班/开课表 course_class
- id：主键
- course_id：课程
- class_id：班级
- teacher_id：授课教师
- term：学期（如 2025-2026-1）
- schedule_info：上课时间地点（文本）
- max_students：最大人数
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.9 选课表 enroll
- id：主键
- student_id：学生
- course_class_id：教学班
- enroll_time：选课时间
- status：选课状态
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.10 成绩表 score
- id：主键
- student_id：学生
- course_id：课程
- course_class_id：教学班
- term：学期
- score_value：成绩
- score_level：成绩等级
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.11 考勤表 attendance
- id：主键
- student_id：学生
- course_class_id：教学班
- attend_date：日期
- status：出勤状态（出勤/缺勤/迟到/早退）
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.12 教室表 classroom
- id：主键
- building：教学楼
- room_no：教室编号
- capacity：容量
- status：状态（可用/维护）
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.13 指标定义表 metric_def
- id：主键
- metric_code：指标编码
- metric_name：指标名称
- metric_category：指标类别（规模/质量/风险）
- calc_rule：计算规则（文本）
- refresh_cycle：刷新周期
- description：指标说明
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.14 指标快照表 metric_snapshot
- id：主键
- metric_id：指标
- metric_value：指标值
- stat_time：统计时间
- dimension_json：维度信息
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.15 预警规则表 alert_rule
- id：主键
- rule_name：规则名称
- metric_id：关联指标
- condition_expr：触发条件表达式
- level：预警等级（低/中/高）
- action_hint：处置建议
- status：启用状态
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.16 预警事件表 alert_event
- id：主键
- rule_id：规则
- metric_snapshot_id：指标快照
- event_time：触发时间
- level：事件等级
- status：处理状态
- handler：处理人
- handle_time：处理时间
- handle_note：处理说明
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.17 历史记录表 chat_history
- id：主键
- admin_id：管理员
- session_id：会话编号
- message_role：角色（user/assistant/system）
- message_content：内容
- tokens：消耗 tokens
- model_name：模型名称
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.18 工作流执行记录表 workflow_log
- id：主键
- session_id：会话编号
- step_name：步骤名称
- input_json：步骤输入
- output_json：步骤输出
- status：执行状态（成功/失败）
- error_message：错误信息
- risk_level：风险等级
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.19 SQL 执行记录表 sql_log
- id：主键
- session_id：会话编号
- sql_text：SQL 语句
- params_json：SQL 参数
- exec_time_ms：执行耗时
- row_count：影响行数
- status：执行状态
- error_message：错误信息
- risk_level：风险等级
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.20 策略配置表 strategy_policy
- id：主键
- policy_name：策略名称
- policy_type：策略类型（风险/权限/白名单）
- policy_rule：策略规则（JSON）
- status：启用状态
- description：策略说明
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.21 查询模板表 query_template
- id：主键
- template_name：模板名称
- template_desc：模板说明
- template_sql：模板 SQL
- params_schema：参数结构
- source_session_id：来源会话
- status：启用状态
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.22 操作审计表 audit_log
- id：主键
- admin_id：管理员
- action_type：操作类型（查询/修改/删除/导入）
- action_target：操作对象
- before_json：变更前数据
- after_json：变更后数据
- risk_level：风险等级
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

#### 6.2.23 系统配置表 system_config
- id：主键
- config_key：配置键
- config_value：配置值
- description：配置说明
- created_at
- updated_at
- created_by
- updated_by
- is_deleted

---

## 7. 多 Agents 工作流设计

### 7.1 工作流总览
当前实现链路：`intent_recognition -> task_parse(条件执行) -> sql_generation(条件执行) -> end`

- 当 `intent=chat` 时：跳过 `task_parse`，直接结束并返回。
- 当 `intent=business_query` 时：进入 `task_parse`，再进入 `sql_generation`。
- 上下文来源：统一从数据库 `chat_history` 按 `session_id` 读取最近 4 条 `user` 消息。
- 当前实现不包含兜底规则：意图识别、任务解析、SQL 生成均依赖 LLM，缺少配置或输出不合法会直接报错。

### 7.2 工作流输入/输出规范

#### 7.2.1 输入总格式（来自前端）
```json
{
  "session_id": "string",
  "message": "string",
  "model_name": "string|null"
}
```
说明：
- `session_id` 可选，首次可不传；不传则后端自动生成。
- 前端不再传 `history`；后端从数据库读取历史上下文。

#### 7.2.2 意图识别节点
- 输入：当前问题 + 数据库中最近 4 条 `user` 消息
- 规则：
  - 意图仅允许 `chat` / `business_query`
  - LLM 输出必须是合法 JSON
  - 必须包含有效 `confidence`、`merged_query`、`rewritten_query`
  - `confidence < threshold` 时将意图降级为 `chat`
- 输出：
```json
{
  "intent": "chat|business_query",
  "is_followup": true,
  "merged_query": "...",
  "rewritten_query": "...",
  "confidence": 0.91
}
```
说明：当前无兜底分支；若 LLM 不可用或输出非法，节点直接抛错。

#### 7.2.3 任务解析节点
- 触发条件：仅当 `intent=business_query`
- 规则：
  - 使用知识库 `app/knowledge/schema_kb_core.json` 生成 `kb_field_whitelist` 与 `alias_hints`
  - 模型输出必须是合法 JSON，且 `operation` 在白名单内
  - `filters.field` 只保留白名单字段（`table.field`）
  - 输出结构固定，供后续 SQL 生成节点消费
- 输出：
```json
{
  "intent": "business_query",
  "entities": [{"type": "grade", "value": "22级"}],
  "dimensions": ["class.class_name"],
  "metrics": ["count"],
  "filters": [{"field": "student.gender", "op": "=", "value": "男"}],
  "time_range": {"start": null, "end": null},
  "operation": "detail|aggregate|ranking|trend",
  "confidence": 0.82
}
```

#### 7.2.4 SQL 生成节点
- 规则：
  - SQL 生成输入除 `task` 外，还会注入知识库语义提示（`kb_schema_hints`，包含表描述与字段描述）；
  - SQL 必须使用 `WITH`（CTE）开头（MySQL 8）；
  - SQL 中所有字段必须使用 `table.field` 形式，不允许别名字段（如 `s.name`）；
  - SQL 字段白名单校验针对真实表字段；若字段前缀是 CTE 名称（如 `base.course_name`），则跳过白名单校验；
  - 必须输出 `entity_mappings`，并覆盖 `entities` 的全部关键实体；
  - 任一关键实体映射失败或映射字段未出现在 SQL 中，节点直接抛错。
- 输出：
```json
{
  "sql": "WITH ... SELECT ...",
  "entity_mappings": [
    {"type": "grade", "value": "22级", "field": "student.enroll_year", "reason": "别名命中"}
  ],
  "sql_fields": ["student.enroll_year", "student.gender"]
}
```

#### 7.2.5 SQL 验证节点（待实现）
- 规则：不使用 LLM，仅执行 SQL 做可执行性验证
- 输出：
```json
{
  "is_valid": true,
  "row_count": 123,
  "error": null,
  "next_on_fail": "hidden_context_discovery",
  "next_on_success": "result_return"
}
```

#### 7.2.6 隐藏上下文探索节点（待实现）
- 输出：
```json
{
  "value_mapping": {
    "term": ["2025-2026-1"],
    "student_status": ["在读", "休学"],
    "course_name": ["高等数学A", "大学英语"]
  },
  "hints": ["term 字段使用 score.term", "status 值需与库内枚举一致"]
}
```

#### 7.2.7 结果返回节点（待实现）
- 输出：
```json
{
  "data": [...],
  "summary": "...",
  "rows": 123,
  "status": "ok"
}
```

### 7.3 SSE 事件规范
- event: workflow_start
- event: step_start
- event: step_end
- event: workflow_error
- event: workflow_end

每个事件 payload 统一格式：
```json
{
  "session_id": "...",
  "step": "intent|task_parse|sql_gen|sql_validate|hidden_context|result",
  "status": "start|end|error",
  "message": "...",
  "timestamp": "2026-01-23T12:00:00Z"
}
```

---

## 8. 后端 API 设计（FastAPI）

### 8.1 认证
- POST /api/auth/login
- POST /api/auth/logout

### 8.2 管理员与基础数据
- GET /api/admin/profile
- GET /api/admin/list
- POST /api/admin/create
- PUT /api/admin/{id}

### 8.3 基础表 CRUD
- GET /api/{table}/list
- GET /api/{table}/{id}
- POST /api/{table}/create
- PUT /api/{table}/{id}
- DELETE /api/{table}/{id}

### 8.4 批量导入
- POST /api/import/{table}

### 8.5 驾驶舱与指标
- GET /api/cockpit/overview
- GET /api/metric/def
- GET /api/metric/snapshot
- POST /api/metric/refresh

### 8.6 预警中心
- GET /api/alert/rule
- POST /api/alert/rule
- GET /api/alert/event
- PUT /api/alert/event/{id}

### 8.7 智能聊天
- POST /api/chat
- GET /api/chat/stream (SSE，待实现)

`POST /api/chat` 当前返回结构：
```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "session_id": "string",
    "intent": "chat|business_query",
    "is_followup": true,
    "merged_query": "合并后的问题",
    "rewritten_query": "合并后的问题",
    "skipped": false,
    "reason": null,
    "task": {
      "intent": "business_query",
      "entities": [{"type": "grade", "value": "2022级"}],
      "dimensions": ["class.class_name"],
      "metrics": ["count"],
      "filters": [{"field": "student.gender", "op": "=", "value": "男"}],
      "time_range": {"start": null, "end": null},
      "operation": "aggregate",
      "confidence": 0.82
    },
    "sql_result": {
      "sql": "WITH ... SELECT ...",
      "entity_mappings": [
        {"type": "grade", "value": "2022级", "field": "student.enroll_year", "reason": "年级映射"}
      ],
      "sql_fields": ["student.enroll_year", "student.gender"]
    }
  }
}
```
说明：
- 前端请求体仅包含 `session_id/message/model_name`，不再包含 `history`；
- 历史上下文统一由后端从数据库读取最近 4 条 `user` 消息；
- `intent=chat` 时 `skipped=true` 且 `task=null` 且 `sql_result=null`，不会进入任务解析和 SQL 生成节点；
- `filters.field` 仅允许知识库白名单字段（`table.field`）；
- SQL 节点会做静态自检：`WITH` 校验、真实表字段白名单校验（CTE 名字段跳过）、关键实体映射覆盖校验；
- 意图识别、任务解析、SQL 生成均无兜底分支：LLM 不可用或输出非法会直接报错；
- 会写入 `chat_history`（user+assistant 两条）与 `workflow_log(intent_recognition/task_parse/sql_generation)`；
- 节点输入输出会落盘到 `NODE_IO_LOG_DIR/<session_id>/<step_name>/`；
- TASK010/TASK011/TASK015 在同一张 LangGraph 中执行（节点：`intent_recognition`、`task_parse`、`sql_generation`），统一实现位于 `app/services/chat_graph.py`。

### 8.8 历史记录与模板
- GET /api/history/session
- GET /api/history/{session_id}
- GET /api/template/list
- POST /api/template/create

### 8.9 策略与审计
- GET /api/strategy/list
- POST /api/strategy/create
- GET /api/audit/log

### 8.10 工作流日志
- GET /api/workflow/log
- GET /api/sql/log

---

## 9. 前端页面与路由

- /login 登录页
- /cockpit 驾驶舱总览
- /kpi 指标看板
- /alerts 预警中心
- /insights 洞察与趋势
- /data 数据管理
- /chat 智能助手
- /workflow-view 工作流可视化
- /history 历史记录
- /templates 查询模板库
- /settings 系统配置

---

## 10. 安全与审计建议

- 登录失败次数限制
- 操作日志审计
- SQL 只允许白名单表
- 风险分级（低/中/高）
- 高风险操作二次确认
- API 限流与防重放（后续可加）

---

## 11. 配置说明（全局配置文件）

建议新增配置文件 `config.yaml`：
- db 连接信息
- 模型 provider 切换
- 模型 API Key
- SSE 开关
- 日志等级

示例结构：
```yaml
app:
  env: "dev"
  log_level: "INFO"

db:
  host: "127.0.0.1"
  port: 3306
  user: "root"
  password: "***"
  database: "edu_admin"

llm:
  provider: "deepseek"
  models:
    deepseek:
      api_key: "***"
      base_url: "https://api.deepseek.com"
    qwen:
      api_key: "***"
      base_url: "https://dashscope.aliyuncs.com"
    chatgpt:
      api_key: "***"
      base_url: "https://api.openai.com"
```

---

## 12. 数据规模与导入说明

- 教师 1100+ 条
- 学生 20000+ 条
- 专业 64 条
- 每专业班级约 6 条
- 需支持批量导入脚本或接口

---

## 12.1 数据库建表与模拟数据

- 建表：
  - `python scripts/init_db.py`
- 生成模拟数据（可重复执行）：
  - `python scripts/generate_mock_data.py --truncate --seed 42`
  - 生成规则：真实格式但虚构，默认中国学生占多数，学校为“三峡科技MOCK大学”。

---

## 13. 交互体验

- SSE 实时输出每个步骤进度
- 聊天界面支持流式返回
- 出错时给出清晰提示，并保留重试上下文

---

## 14. 后续可扩展方向

- 多角色权限体系（教师/学生）
- 课程表与教室自动排课
- 成绩分析报表与可视化
- 异常数据检测（如缺考、挂科趋势）

---

以上为项目总体蓝图，详细开发任务与步骤请见 `DEV_PLAN.md`。
