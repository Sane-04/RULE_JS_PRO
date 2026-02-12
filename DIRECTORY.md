# DIRECTORY

本文件描述当前仓库结构（截至 2026-02-11）。  
线上地址：http://47.97.122.195/

```text
RULE_JS_PRO/
├─ app/                         FastAPI 后端主应用
│  ├─ core/                     配置与安全（config、security）
│  ├─ db/                       SQLAlchemy 会话与 Base
│  ├─ knowledge/                知识库文件
│  ├─ models/                   ORM 模型
│  ├─ prompts/                  LLM 提示词
│  ├─ routers/                  API 路由（auth/admin/data/chat/cockpit/import/metric）
│  ├─ schemas/                  请求与响应结构
│  ├─ services/                 业务服务（含 chat_graph、chat_stream_service）
│  ├─ deps.py                   依赖注入
│  └─ main.py                   FastAPI 应用工厂
├─ frontend/                    Vue 3 前端
│  ├─ src/
│  │  ├─ api/                   前端 API 封装
│  │  ├─ components/            通用组件
│  │  ├─ layouts/               布局组件
│  │  ├─ router/                前端路由
│  │  ├─ stores/                Pinia 状态
│  │  ├─ styles/                样式
│  │  └─ views/                 页面视图（Login/Data/Cockpit/Chat）
│  ├─ public/
│  ├─ index.html
│  ├─ package.json
│  ├─ package-lock.json
│  ├─ tsconfig.json
│  └─ vite.config.ts
├─ scripts/                     初始化与数据脚本
│  ├─ init_db.py
│  ├─ init_admin.py
│  ├─ generate_mock_data.py
│  ├─ fill_recent_attendance.py
│  └─ build_schema_kb.py
├─ deploy/
│  └─ nginx/
│     └─ default.conf           Nginx 反向代理与 SSE 配置
├─ Dockerfile.backend           后端镜像构建文件
├─ Dockerfile.web               前端构建 + Nginx 镜像文件
├─ docker-compose.yml           服务编排文件
├─ requirements.txt             Python 依赖
├─ main.py                      应用启动入口
├─ README.md                    项目总览文档
├─ DEV_PLAN.md                  项目完结归档
├─ DEPLOY_DOCKER.md             部署与运维文档
├─ .env                         本地/部署环境变量文件
├─ .dockerignore
└─ .gitignore
```

说明：
- `.codex/`、`.idea/`、`.vscode/`、`local_logs/`、`tmp_test_import/` 为本地开发辅助目录，不属于生产交付核心代码。
- `frontend/node_modules/`、`frontend/dist/` 为构建产物目录，不纳入文档主结构清单。
