#!/bin/bash
# cron wrapper: 每日盘后简单回测（Trend Upstart Flow + grow_with_money）
# 由 crontab 调用，每天 16:30 运行
#
# crontab 条目（已配置）：
#   30 16 * * 1-5 cd /Users/aklu/CodeBuddy/AIpicking/backend && bash TmpScriptsBackTest/cron_trend_upstart_flow.sh

set -e

PROJ_DIR="/Users/aklu/CodeBuddy/AIpicking/backend"
LOG_DIR="$PROJ_DIR/TmpScriptsBackTest/logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/daily_backtests_$(date +%Y%m%d).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "  盘后回测 — $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

cd "$PROJ_DIR"
source venv/bin/activate

python TmpScriptsBackTest/run_daily_backtests.py \
    -q \
    -s "Trend Upstart Flow" \
    -s "grow_with_money" \
    2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "  ✅ 完成 — $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG_FILE"
