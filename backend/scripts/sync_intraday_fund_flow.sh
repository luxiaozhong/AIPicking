#!/bin/bash
# 盘中指数资金流同步 — 分两阶段：
#   1. 指数成分股（展开成分股逐只同步 + 快照）
#   2. 市场指数自身（把指数当个股拉，不展开）
#
# Usage:
#   bash scripts/sync_intraday_fund_flow.sh
#
# Cron（每3分钟，工作日盘中）:
#   */3 9-11 * * 1-5 cd /opt/AIpicking/backend && bash scripts/sync_intraday_fund_flow.sh >> /var/log/aipicking/index_fund_flow.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/../venv/bin/python"
TODAY=$(date +%Y-%m-%d)

CONSTITUENT_INDICES=(980080 900001 399667)
SELF_INDICES=(
    000001   # 上证指数
    000016   # 上证50
    000300   # 沪深300
    000688   # 科创50
    000905   # 中证500
    000852   # 中证1000
    399001   # 深证成指
    399005   # 中小100
    399006   # 创业板指
    399673   # 创业板50
    399750   # 深证主板50
    931643   # 科创创业50
    950180   # 科创AI
    980080   # 国证成长100
)

# ── 阶段 1: 成分股批量同步（含快照） ──
TOTAL=${#CONSTITUENT_INDICES[@]}
for i in "${!CONSTITUENT_INDICES[@]}"; do
    idx="${CONSTITUENT_INDICES[$i]}"
    echo "[$(date '+%H:%M:%S')] 开始同步指数 $idx 成分股资金流..."
    "$PYTHON" "$SCRIPT_DIR/sync_index_fund_flow.py" --index "$idx" --date "$TODAY" --batch-size 100
    echo "[$(date '+%H:%M:%S')] 指数 $idx 成分股完成"

    if [ "$i" -lt $((TOTAL - 1)) ]; then
        sleep 10
    fi
done

# ── 阶段 2: 市场指数自身资金流（--self 模式，不展开成分股） ──
# 传 npm 格式代码（sh=上交所, sz=深交所），避免 exchange 自动推断错误
SELF_CODES=(
    sh000001   # 上证指数
    sh000016   # 上证50
    sh000300   # 沪深300
    sh000688   # 科创50
    sh000905   # 中证500
    sh000852   # 中证1000
    sz399001   # 深证成指
    sz399005   # 中小100
    sz399006   # 创业板指
    sz399673   # 创业板50
    sz399750   # 深证主板50
    sh931643   # 科创创业50
    sh950180   # 科创AI
    sh980080   # 国证成长100
)
SELF_TOTAL=${#SELF_CODES[@]}
echo "[$(date '+%H:%M:%S')] 开始同步 $SELF_TOTAL 个市场指数自身资金流..."
# 用逗号拼接所有指数代码一次请求
CODES=""
for code in "${SELF_CODES[@]}"; do
    if [ -z "$CODES" ]; then
        CODES="$code"
    else
        CODES="$CODES,$code"
    fi
done
"$PYTHON" "$SCRIPT_DIR/sync_index_fund_flow.py" --index "$CODES" --date "$TODAY" --batch-size 50 --self
echo "[$(date '+%H:%M:%S')] 全部完成"
