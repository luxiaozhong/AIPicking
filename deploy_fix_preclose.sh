#!/bin/bash
# ============================================================
# 部署脚本：pre_close 修复 (fix/preclose-calculation → main)
# 在服务器上执行，需要先 git pull 拉取最新代码
# ============================================================
# 用法：
#   cd /opt/AIpicking
#   git pull origin main
#   bash deploy_fix_preclose.sh
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

echo "=========================================="
echo "  pre_close 修复部署"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 1. 数据库迁移：添加 pre_close 列 + 回填近30天
echo ""
echo "[1/4] 数据库迁移..."
cd "$BACKEND_DIR"
source venv/bin/activate
python scripts/migrate_add_pre_close.py

# 2. 重新同步最近几天的日线数据（修复复权因子不一致）
echo ""
echo "[2/4] 重新同步近5天日线..."
for d in $(python -c "
from datetime import date, timedelta
d = date.today()
dates = []
while len(dates) < 5:
    if d.weekday() < 5:  # skip weekends
        dates.append(d.strftime('%Y-%m-%d'))
    d -= timedelta(days=1)
print(' '.join(dates))
"); do
    echo "  同步 $d ..."
    python scripts/update_daily.py --date "$d"
done

# 3. 前端构建
echo ""
echo "[3/4] 前端构建..."
cd "$SCRIPT_DIR/frontend"
npm run build

# 4. 重启服务
echo ""
echo "[4/4] 重启服务..."
sudo systemctl restart aipicking

echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "验证：访问市场温度页 → 领跌板块 → 点击板块"
echo "确认涨跌幅在 ±10%（主板）/ ±20%（科创创业）范围内"
