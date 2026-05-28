"""应用配置"""

import os
from pathlib import Path


class Settings:
    """应用配置类"""
    
    def __init__(self):
        # 应用配置
        self.APP_NAME = os.getenv("APP_NAME", "AIpicking")
        self.DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
        
        # 数据库配置
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL",
            f"sqlite+aiosqlite:///{Path(__file__).parent.parent / 'data' / 'database' / 'aipicking.db'}"
        )
        
        # CORS 配置
        cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
        self.CORS_ORIGINS = [origin.strip() for origin in cors_origins_str.split(",")]
        
        # 回测配置
        self.BACKTEST_DATA_DIR = os.getenv("BACKTEST_DATA_DIR", "./data/market_data")
        
        # JWT 密钥
        self.JWT_SECRET_KEY = os.getenv(
            "JWT_SECRET_KEY",
            "aipicking-dev-secret-key-change-in-production"
        )

        # 股票历史数据库路径
        self.STOCK_DB_PATH = os.getenv(
            "STOCK_DB_PATH",
            "/opt/stock_data/stock_db.sqlite"
        )


settings = Settings()
