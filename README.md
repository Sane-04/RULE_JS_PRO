# 教务驾驶舱系统（RULE_JS_PRO）

项目状态：已完成并已上线。

- 线上访问地址：http://47.97.122.195/
- 部署方式：Docker + Docker Compose
- 架构：前后端分离（Vue 3 + FastAPI）

## 1. 项目简介

本项目提供教务数据管理、驾驶舱分析与智能问答能力，覆盖管理员日常使用的核心场景：

- 管理员登录与权限校验
- 核心主数据管理（学生、教师、学院、专业、班级、课程等）
- 驾驶舱指标、趋势、榜单、风险清单与导出
- 基于 LangGraph 的智能问答工作流（意图识别、任务解析、SQL 生成、SQL 校验、结果返回）

## 2. 技术栈

- 后端：FastAPI、SQLAlchemy、MySQL、LangGraph
- 前端：Vue 3、Vite、TypeScript、Pinia、Vue Router
- 模型接入：OpenAI 兼容接口（由 `LLM_BASE_URL`、`LLM_API_KEY` 配置）
- 部署：Docker、Docker Compose、Nginx

## 3. 已实现能力

### 3.1 认证与会话

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/admin/profile`
- 聊天会话列表、消息查询、删除、清空

### 3.2 数据管理

- 通用数据接口（分页、过滤、搜索、排序、软删除）
- 高级筛选支持 `*_id` 字段的编码/名称自动映射（如 `major_id=M001` 会自动映射到对应数值 ID）
- 学生成绩明细查询
- 多业务表切换管理

### 3.3 导入能力

- `POST /api/import/{table}`
- 支持 CSV/XLSX
- 导入日志落库（`import_log`）

### 3.4 驾驶舱

- `GET /api/cockpit/overview`
- `GET /api/cockpit/risk/export`
- 指标卡、趋势图、分布图、风险榜单
- 学期/学院/专业/年级筛选联动

### 3.5 智能问答

- `POST /api/chat`
- `POST /api/chat/stream`（SSE）
- `sql_generation` 节点支持独立模型配置（默认 `qwen3-coder-plus`）
- 工作流节点：
  - `intent_recognition`
  - `task_parse`
  - `sql_generation`
  - `sql_validate`
  - `hidden_context`
  - `result_return`

## 4. 关键目录

```text
app/            后端主代码（路由、服务、模型、Schema、配置）
frontend/       前端代码（页面、路由、状态、API）
scripts/        初始化、管理与数据脚本
deploy/nginx/   Nginx 反向代理配置
```

详细目录见：`DIRECTORY.md`

## 5. 环境变量

参考项目根目录 `.env`（如自行抽离可复制为 `.env.example`），至少需要：

- `DB_HOST` `DB_PORT` `DB_USER` `DB_PASSWORD` `DB_NAME`
- `JWT_SECRET` `JWT_ALGORITHM`
- `LLM_API_KEY` `LLM_BASE_URL` `LLM_MODEL_INTENT`
- `LLM_MODEL_SQL_GENERATION`（仅 SQL 生成节点，默认 `qwen3-coder-plus`）
- `CHAT_STREAM_MODE`

## 6. 部署与运维

已提供完整 Docker 部署文件：

- `Dockerfile.backend`
- `Dockerfile.web`
- `docker-compose.yml`
- `deploy/nginx/default.conf`
- `.dockerignore`

部署文档见：`DEPLOY_DOCKER.md`

## 7. 文档索引

- 项目目录：`DIRECTORY.md`
- 部署文档：`DEPLOY_DOCKER.md`
- 任务归档：`DEV_PLAN.md`
