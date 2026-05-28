"""迁移脚本：重建 backtest_reports 和 strategy_runs 表"""
import sqlite3
import sys
import os

DB_PATH = "data/database/aipicking.db"

# 删除旧表
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("DROP TABLE IF EXISTS backtest_reports")
cur.execute("DROP TABLE IF EXISTS strategy_runs")
print("已删除旧表")

conn.commit()
conn.close()

# 用新模型重建表
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import engine
from app.models import Base, BacktestReport, StrategyRun

Base.metadata.create_all(bind=engine, tables=[BacktestReport.__table__, StrategyRun.__table__])
print("新表创建成功")
print("迁移完成")
