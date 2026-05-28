"""迁移脚本：添加用户认证功能

运行方式：
    cd backend && source venv/bin/activate && python migrate_add_auth.py
"""

import sqlite3
import os
from pathlib import Path

# 数据库路径
DB_PATH = Path(__file__).parent / "data" / "database" / "aipicking.db"


def migrate():
    if not DB_PATH.exists():
        print(f"数据库文件不存在: {DB_PATH}")
        print("请先启动应用创建数据库后再运行此脚本")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # 1. 创建 users 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("1. users 表已创建（或已存在）")

        # 2. 检查是否已有 admin 用户
        cursor.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1")
        admin = cursor.fetchone()

        if admin is None:
            # 创建默认 admin（密码: admin123）
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            password_hash = pwd_context.hash("admin123")
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, 1)",
                ("admin", password_hash, "admin")
            )
            conn.commit()
            admin_id = cursor.lastrowid
            print(f"2. 默认管理员已创建: admin / admin123 (id={admin_id})")
        else:
            admin_id = admin[0]
            print(f"2. 管理员已存在 (id={admin_id})")

        # 3. 为现有表添加 user_id 列
        tables = ["strategies", "backtest_reports", "strategy_runs"]
        for table in tables:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)")
                print(f"3. {table}.user_id 列已添加")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print(f"3. {table}.user_id 列已存在")
                else:
                    raise

        # 4. 为 user_id 创建索引
        for table in tables:
            try:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")
                print(f"4. idx_{table}_user_id 索引已创建")
            except sqlite3.OperationalError as e:
                print(f"4. idx_{table}_user_id 索引创建失败（可能已存在）: {e}")

        # 5. 回填现有数据的 user_id
        for table in tables:
            cursor.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (admin_id,))
            updated = cursor.rowcount
            if updated > 0:
                print(f"5. {table}: {updated} 行数据已关联到管理员")

        conn.commit()
        print("\n迁移完成！")

    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
