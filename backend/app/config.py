"""应用配置 — 支持 dev/prod 分离，敏感信息只从环境变量读取"""

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

# 加载顺序：.env（dev） → .env.production（prod 覆盖）
# rsync 部署时排除 .env，服务器上用 .env.production
_env_dir = Path(__file__).parent.parent

for _env_file in (".env", ".env.production"):
    _path = _env_dir / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


def _require_env(key: str) -> str:
    """读取必需的环境变量，未设置时抛出明确错误"""
    value = os.getenv(key, "").strip()
    if not value:
        raise RuntimeError(
            f"缺少必需的环境变量: {key}，请在 .env 或 .env.production 中设置"
        )
    return value


class Settings:
    """应用配置类 — 所有敏感信息必须从环境变量读取，不提供硬编码默认值"""

    def __init__(self):
        # 应用配置
        self.APP_NAME = os.getenv("APP_NAME", "AIpicking")
        self.DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

        # 数据库配置 — 必须通过环境变量设置，不提供含密码的默认值
        self.DATABASE_URL = os.getenv("DATABASE_URL", "")
        if not self.DATABASE_URL:
            if self.DEBUG:
                # 开发环境：回退到本地 PostgreSQL（密码通过环境变量或 .env 设置）
                db_user = os.getenv("DB_USER", "aipicking")
                db_pass = os.getenv("DB_PASSWORD", "")
                db_host = os.getenv("DB_HOST", "localhost")
                db_port = os.getenv("DB_PORT", "5432")
                db_name = os.getenv("DB_NAME", "aipicking")
                self.DATABASE_URL = (
                    f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
                )
            else:
                self.DATABASE_URL = _require_env("DATABASE_URL")

        self.SYNC_DATABASE_URL = os.getenv(
            "SYNC_DATABASE_URL",
            self.DATABASE_URL.replace("+asyncpg", "+psycopg2") if self.DATABASE_URL else "",
        )

        # CORS 配置
        cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        self.CORS_ORIGINS = [origin.strip() for origin in cors_origins_str.split(",")]

        # 回测配置
        self.BACKTEST_DATA_DIR = os.getenv("BACKTEST_DATA_DIR", "./data/market_data")

        # JWT 密钥 — 生产环境必须设置，开发环境自动生成
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
        if not self.JWT_SECRET_KEY:
            if self.DEBUG:
                # 开发环境：使用固定密钥方便调试（重启不失效）
                self.JWT_SECRET_KEY = "aipicking-dev-jwt-secret--change-in-production"
            else:
                self.JWT_SECRET_KEY = _require_env("JWT_SECRET_KEY")

        # DeepSeek API 配置
        self.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
        self.DEEPSEEK_BASE_URL = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "120"))


settings = Settings()
