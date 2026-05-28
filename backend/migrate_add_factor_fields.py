"""
数据库迁移脚本：为 strategies 表添加 factor_config 和 generated_code 字段
"""
import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "backend", "data", "database", "aipicking.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"数据库不存在: {DB_PATH}")
        print("将在首次启动时自动创建新表")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查字段是否已存在
    cursor.execute("PRAGMA table_info(strategies)")
    columns = [row[1] for row in cursor.fetchall()]

    if "factor_config" not in columns:
        cursor.execute("ALTER TABLE strategies ADD COLUMN factor_config TEXT")
        print("✅ 已添加字段: factor_config")
    else:
        print("⏭  字段已存在: factor_config")

    if "generated_code" not in columns:
        cursor.execute("ALTER TABLE strategies ADD COLUMN generated_code TEXT")
        print("✅ 已添加字段: generated_code")
    else:
        print("⏭  字段已存在: generated_code")

    conn.commit()
    conn.close()
    print("迁移完成！")

if __name__ == "__main__":
    migrate()
