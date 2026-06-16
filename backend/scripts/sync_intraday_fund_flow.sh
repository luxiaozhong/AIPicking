#!/bin/bash
# 盘中指数成分股资金流同步 — 依次更新多个指数，间隔 1 分钟避免并发
#
# Usage:
#   bash scripts/sync_intraday_fund_flow.sh                         # 默认 980080,900001
#   bash scripts/sync_intraday_fund_flow.sh 980080 900001 880001    # 自定义指数列表
#
# Cron（每5分钟，工作日盘中）:
#   */5 9-10 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /var/log/aipicking/index_fund_flow.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python"
TODAY=$(date +%Y-%m-%d)

if [ $# -eq 0 ]; then
    INDICES=(980080 900001)
else
    INDICES=("$@")
fi

TOTAL=${#INDICES[@]}
for i in "${!INDICES[@]}"; do
    idx="${INDICES[$i]}"
    echo "[$(date '+%H:%M:%S')] 开始同步指数 $idx 成分股资金流..."
    "$PYTHON" "$SCRIPT_DIR/sync_index_fund_flow.py" --index "$idx" --date "$TODAY" --batch-size 100
    echo "[$(date '+%H:%M:%S')] 指数 $idx 资金流完成"

    if [ "$i" -lt $((TOTAL - 1)) ]; then
        sleep 60
    fi
done

echo "[$(date '+%H:%M:%S')] 全部完成"
