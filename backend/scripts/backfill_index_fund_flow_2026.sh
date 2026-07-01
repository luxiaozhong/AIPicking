#!/bin/bash
# 回填 2026 年指数资金流数据
#   - 阶段 1: 成分股指数（展开成分股逐只同步 + 快照）
#   - 阶段 2: 市场指数自身（--self 模式）
#
# Usage:
#   bash scripts/backfill_index_fund_flow_2026.sh [start_date] [end_date]
#
# 默认: 2026-01-01 → 今天

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python"
START_DATE="${1:-2026-01-01}"
END_DATE="${2:-$(date +%Y-%m-%d)}"

CONSTITUENT_INDICES=(980080 900001 399667 399966)
SELF_CODES="sh000001,sh000016,sh000300,sh000688,sh000905,sh000852,sz399001,sz399005,sz399006,sz399673,sz399750,sh931643,sh950180,sh980080"

echo "============================================"
echo "  指数资金流回填 2026"
echo "  范围: $START_DATE → $END_DATE"
echo "============================================"

# 生成所有交易日（周一到周五，排除周末）
current="$START_DATE"
total_days=0
trading_days=0
skipped=0

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

        # 阶段 1: 成分股指数
        for idx in "${CONSTITUENT_INDICES[@]}"; do
            echo "[$(date '+%H:%M:%S')] 成分股指数 $idx @ $current ..."
            "$PYTHON" "$SCRIPT_DIR/sync_index_fund_flow.py" \
                --index "$idx" --date "$current" --batch-size 100 || \
                echo "  ⚠ 指数 $idx 失败，继续下一个"
        done

        # 阶段 2: 市场指数自身
        echo "[$(date '+%H:%M:%S')] 市场指数自身 @ $current ..."
        "$PYTHON" "$SCRIPT_DIR/sync_index_fund_flow.py" \
            --index "$SELF_CODES" --date "$current" --batch-size 50 --self || \
            echo "  ⚠ 市场指数自身失败，继续"

        # 礼貌间隔
        sleep 2
    fi

    # 下一天 (macOS/BSD date 兼容)
    current=$(date -j -v+1d -f "%Y-%m-%d" "$current" +%Y-%m-%d 2>/dev/null || \
              date -d "$current + 1 day" +%Y-%m-%d)
done

echo ""
echo "============================================"
echo "  回填完成"
echo "  总天数: $total_days | 交易日: $trading_days | 跳过: $skipped"
echo "============================================"
