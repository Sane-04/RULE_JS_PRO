import os
from datetime import timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)


class Settings:
    app_name = "edu_cockpit"

    db_host = os.getenv("DB_HOST", "127.0.0.1")
    db_port = int(os.getenv("DB_PORT", "3306"))
    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "edu_admin")

    jwt_secret = os.getenv("JWT_SECRET", "sane")
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

    llm_provider = os.getenv("LLM_PROVIDER", "dashcope")
    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model_intent = os.getenv("LLM_MODEL_INTENT", "qwen-plus")
    llm_model_sql_generation = os.getenv("LLM_MODEL_SQL_GENERATION", "qwen3-coder-plus")
    _raw_llm_response_format_sql = os.getenv("LLM_RESPONSE_FORMAT_SQL", "").strip().lower()
    llm_response_format_sql = _raw_llm_response_format_sql if _raw_llm_response_format_sql in {"json_object"} else ""
    intent_confidence_threshold = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.7"))
    node_io_log_dir = os.getenv("NODE_IO_LOG_DIR", "local_logs/node_io")
    chat_export_dir = os.getenv("CHAT_EXPORT_DIR", "local_logs/chat_exports")
    _raw_chat_stream_mode = os.getenv("CHAT_STREAM_MODE", "stream").strip().lower()
    chat_stream_mode = _raw_chat_stream_mode if _raw_chat_stream_mode in {"stream", "sync"} else "stream"
    chat_stream_workflow_start_message = "收到！让我帮您查一查"
    chat_stream_workflow_end_message = "搞定啦，结果在这儿"
    chat_stream_step_message_placeholders = {
        "intent_recognition": {
            "start": "让我先想想您想问什么",
            "end": "懂了！"
        },
        "task_parse": {
            "start": "拆解一下问题结构",
            "end": "思路清晰了"
        },
        "sql_generation": {
            "start": "开始拼装查询语句",
            "end": "语句组装完成"
        },
        "sql_validate": {
            "start": "再帮您检查一遍",
            "end": "看起来没问题"
        },
        "hidden_context": {
            "start": "看样子SQL生成有误，别慌，我会救场！",
            "end": "救场完毕！重新生成试试！"
        },
        "result_return": {
            "start": "整理一下结果给您",
            "end": "整理好咯"
        },
    }

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def access_token_expires(self) -> timedelta:
        return timedelta(minutes=self.access_token_expire_minutes)


settings = Settings()
