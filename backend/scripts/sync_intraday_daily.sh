#!/bin/bash
# 盘中日线同步 — 指数日线 + 成分股日线，依次执行避免并发
#
# Usage:
#   bash scripts/sync_intraday_daily.sh                    # 默认 980080,900001
#   bash scripts/sync_intraday_daily.sh 980080 900001 931643  # 自定义指数列表
#
# Cron（每5分钟，仅交易时段 9:30-11:30 / 13:00-15:00）:
#   # 上午（9:30-11:30）
#   30-59/5 9 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /var/log/aipicking/update_daily_intraday.log 2>&1
#   */5 10 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /var/log/aipicking/update_daily_intraday.log 2>&1
#   0-30/5 11 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /var/log/aipicking/update_daily_intraday.log 2>&1
#   # 下午（13:00-15:00）
#   */5 13 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /var/log/aipicking/update_daily_intraday.log 2>&1
#   */5 14 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /var/log/aipicking/update_daily_intraday.log 2>&1
#   0 15 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_daily.sh >> /var/log/aipicking/update_daily_intraday.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python"

# ── 1. 指数日线（上证/深证/创业板/科创50 等，秒级） ──
echo "[$(date '+%H:%M:%S')] 开始更新指数日线..."
"$PYTHON" "$SCRIPT_DIR/update_index_daily.py" --intraday
echo "[$(date '+%H:%M:%S')] 指数日线完成"
sleep 30

# ── 2. 成分股日线（按指数过滤） ──
if [ $# -eq 0 ]; then
    INDICES=(980080 900001 900002 399667 399966)
else
    INDICES=("$@")
fi

TOTAL=${#INDICES[@]}
for i in "${!INDICES[@]}"; do
    idx="${INDICES[$i]}"
    echo "[$(date '+%H:%M:%S')] 开始更新指数 $idx 成分股日线..."
    "$PYTHON" "$SCRIPT_DIR/update_daily.py" --intraday --index "$idx"
    echo "[$(date '+%H:%M:%S')] 指数 $idx 成分股完成"

    if [ "$i" -lt $((TOTAL - 1)) ]; then
        sleep 60
    fi
done

echo "[$(date '+%H:%M:%S')] 全部完成"
