#!/bin/bash
# 全量 A 股日线同步（不含指数过滤）
# 14:45 跑一次，确保当天所有股票日线数据完整
#
# Cron:
#   45 14 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_daily_full.sh >> /var/log/aipicking/update_daily_full.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python"
TODAY=$(date +%Y-%m-%d)

# 延迟 30 秒，避免与 */5 的 sync_intraday_daily.sh 重合
sleep 30

echo "[$(date '+%H:%M:%S')] 开始全量日线同步..."
"$PYTHON" "$SCRIPT_DIR/update_daily.py" --intraday --date "$TODAY"
echo "[$(date '+%H:%M:%S')] 全量日线同步完成"
