#!/bin/bash
# 回填科创100 (000698.SH) 2026年资金流数据
# 模式: --self（市场指数自身，不展开成分股）
#
# Usage:
#   bash scripts/backfill_000698_2026.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python"
START_DATE="${1:-2026-01-01}"
END_DATE="${2:-$(date +%Y-%m-%d)}"

INDEX_CODE="sh000698"

echo "============================================"
echo "  科创100 资金流回填 2026"
echo "  指数: $INDEX_CODE"
echo "  范围: $START_DATE → $END_DATE"
echo "============================================"

current="$START_DATE"
total_days=0
trading_days=0
skipped=0
success=0
failed=0

while [[ "$current" < "$END_DATE" || "$current" == "$END_DATE" ]]; do
    total_days=$((total_days + 1))
    dow=$(date -j -f "%Y-%m-%d" "$current" +%u 2>/dev/null || date -d "$current" +%u 2>/dev/null)

    if [ "$dow" -ge 6 ]; then
        echo "[$(date '+%H:%M:%S')] 跳过 $current (周末)"
        skipped=$((skipped + 1))
    else
        trading_days=$((trading_days + 1))
        echo ""
        echo "── [$trading_days] $current ──────────────────────────────"

        if "$PYTHON" "$SCRIPT_DIR/sync_index_fund_flow.py" \
            --index "$INDEX_CODE" --date "$current" --self --log-level INFO; then
            success=$((success + 1))
        else
            echo "  ⚠ $current 失败，继续"
            failed=$((failed + 1))
        fi

        sleep 1
    fi

    # 下一天
    current=$(date -j -v+1d -f "%Y-%m-%d" "$current" +%Y-%m-%d 2>/dev/null || \
              date -d "$current + 1 day" +%Y-%m-%d)
done

echo ""
echo "============================================"
echo "  回填完成"
echo "  总天数: $total_days | 交易日: $trading_days | 跳过(周末): $skipped"
echo "  成功: $success | 失败: $failed"
echo "============================================"
