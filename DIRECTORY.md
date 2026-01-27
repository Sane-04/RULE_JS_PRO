# DIRECTORY

本文件描述当前仓库结构（截至 2026-01-27）。

```
RULE_JS_PRO/
├─ .codex/                  Codex 代理指令与本地文档
│  ├─ AGENTS.md
│  └─ RIPER-5-CN.md
├─ .git/                    Git 元数据
├─ .idea/                   JetBrains IDE 配置
├─ .vscode/                 VS Code 配置
├─ app/                     FastAPI 应用包
│  ├─ core/                 应用配置与安全工具
│  │  ├─ config.py
│  │  └─ security.py
│  ├─ db/                   SQLAlchemy 基础与会话配置
│  │  ├─ base.py
│  │  └─ session.py
│  ├─ models/               ORM 模型
│  │  ├─ admin.py
│  │  └─ __init__.py
│  ├─ routers/              API 路由模块
│  │  ├─ admin.py
│  │  ├─ auth.py
│  │  └─ __init__.py
│  ├─ schemas/              Pydantic 请求/响应结构
│  │  ├─ admin.py
│  │  ├─ auth.py
│  │  └─ __init__.py
│  ├─ services/             业务服务层逻辑
│  │  └─ auth_service.py
│  ├─ deps.py               依赖注入辅助函数
│  ├─ main.py               FastAPI 工厂与路由注册
│  └─ __init__.py
├─ scripts/                 辅助脚本
│  └─ init_admin.py
├─ .env                     本地环境变量
├─ DEV_PLAN.md              开发计划与任务清单
├─ DIRECTORY.md             目录结构说明（本文件）
├─ main.py                  暴露 FastAPI 应用的入口
├─ README.md                项目蓝图与需求说明
├─ requirements.txt         Python 依赖列表
└─ _cn_test.txt             小型测试文件
```

说明：
- 已存在的 Python __pycache__ 目录在此处省略。
