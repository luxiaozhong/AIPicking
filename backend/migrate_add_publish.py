"""迁移脚本：添加策略发布、评分、评论功能

运行方式：
    cd backend && source venv/bin/activate && python migrate_add_publish.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from app.config import settings

def migrate():
    # 从 DATABASE_URL 解析连接参数
    # psycopg2 不接受 +psycopg2 前缀，需要去除
    sync_url = settings.SYNC_DATABASE_URL.replace("+psycopg2", "")
    conn = psycopg2.connect(sync_url)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # 1. strategies 表增加 is_published 列
        cursor.execute("""
            ALTER TABLE strategies
            ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT FALSE
        """)
        print("1. strategies.is_published 列已添加（或已存在）")

        # 2. 创建 strategy_ratings 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_ratings (
                id SERIAL PRIMARY KEY,
                strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(strategy_id, user_id)
            )
        """)
        print("2. strategy_ratings 表已创建（或已存在）")

        # 3. 创建 strategy_ratings 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_ratings_strategy_id
            ON strategy_ratings(strategy_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_ratings_user_id
            ON strategy_ratings(user_id)
        """)
        print("3. strategy_ratings 索引已创建")

        # 4. 创建 strategy_comments 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_comments (
                id SERIAL PRIMARY KEY,
                strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        print("4. strategy_comments 表已创建（或已存在）")

        # 5. 创建 strategy_comments 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_comments_strategy_id
            ON strategy_comments(strategy_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_comments_user_id
            ON strategy_comments(user_id)
        """)
        print("5. strategy_comments 索引已创建")

        # 6. 创建 is_published 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategies_is_published
            ON strategies(is_published)
        """)
        print("6. strategies.is_published 索引已创建")

        conn.commit()
        print("\n迁移完成！")

    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrate()
