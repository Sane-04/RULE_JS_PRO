# Docker 部署指南

当前仓库已包含一套面向生产环境的 Docker 基线，包含：
- `backend`：FastAPI（`uvicorn`）
- `web`：Nginx 托管 Vue 构建产物，并反向代理 `/api`
- `mysql`（可选）：通过 `with-mysql` profile 启用本地 MySQL 容器

## 1. 新增文件

- `Dockerfile.backend`
- `Dockerfile.web`
- `docker-compose.yml`
- `deploy/nginx/default.conf`
- `.dockerignore`
- `.env.example`

## 2. 环境准备

1. 将 `.env.example` 复制为 `.env`。
2. 填写真实配置，重点包括：
   - `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
   - `JWT_SECRET`
   - `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL_INTENT`
3. 如果使用本地 MySQL 容器，请将 `DB_HOST` 设置为 `mysql`。

## 3. 启动服务

### 方案 A：使用外部 MySQL（推荐）

```bash
docker compose up -d --build
```

### 方案 B：使用 Compose 内置 MySQL

```bash
docker compose --profile with-mysql up -d --build
```

## 4. 初始化数据库

容器启动后，在后端容器中执行初始化脚本：

```bash
docker compose run --rm backend python scripts/init_db.py
docker compose run --rm backend python scripts/init_admin.py --username admin --password <your_password>
```

如需生成演示数据：

```bash
docker compose run --rm backend python scripts/generate_mock_data.py --truncate --seed 42
```

## 5. 健康检查

- 应用健康检查接口：`GET /healthz`
- 通过 Web 容器访问：`http://<server>/healthz`
- API 基础路径：`http://<server>/api`

`/api/chat/stream` 已按 SSE 场景配置：
- `deploy/nginx/default.conf` 中已关闭 Nginx 缓冲。

## 6. 生产注意事项

1. 不要将 `.env` 提交到 Git；如果历史中出现过密钥，请立即轮换。
2. 通过挂载 `./local_logs` 持久化日志。
3. 若对公网提供服务，建议在外层反向代理或网关终止 HTTPS（或在本 Nginx 层补充 TLS 证书配置）。
4. 使用固定镜像标签，并保留上一版本，便于快速回滚。

## 7. 如果 `.gitignore` 看起来“没生效”

`.gitignore` 只对“未跟踪文件”生效。  
如果敏感文件已经被 Git 跟踪，需要先取消跟踪一次：

```bash
git rm -r --cached .codex .idea .vscode local_logs tmp_test_import frontend/node_modules frontend/dist .env resp.json
git commit -m "chore: stop tracking local and sensitive files"
```
