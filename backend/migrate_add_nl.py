"""Migration: add task_type to ai_strategy_tasks and create ai_factors table"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "database", "aipicking.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if task_type column exists
    cursor.execute("PRAGMA table_info(ai_strategy_tasks)")
    columns = [col[1] for col in cursor.fetchall()]

    if "task_type" not in columns:
        print("Adding task_type column to ai_strategy_tasks...")
        cursor.execute("ALTER TABLE ai_strategy_tasks ADD COLUMN task_type VARCHAR(20) DEFAULT 'stock_reference'")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_ai_strategy_tasks_task_type ON ai_strategy_tasks(task_type)")
        print("Done.")
    else:
        print("task_type column already exists.")

    # Create ai_factors table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_factors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factor_id VARCHAR(100) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            description TEXT,
            params_schema TEXT,
            file_path VARCHAR(200),
            created_by INTEGER REFERENCES users(id),
            usage_count INTEGER DEFAULT 0,
            created_at DATETIME,
            updated_at DATETIME
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_ai_factors_factor_id ON ai_factors(factor_id)")
    print("ai_factors table ready.")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
