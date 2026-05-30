#!/bin/bash
set -e

# ============================================================
# AIpicking 更新部署脚本
# 用法: cd /opt/AIpicking && ./update.sh
# ============================================================

PROJECT_DIR="/opt/AIpicking"
cd "$PROJECT_DIR"

echo "=== 拉取最新代码 ==="
git checkout main
git pull

echo ""
echo "=== 更新后端依赖 ==="
cd "$PROJECT_DIR/backend"
source venv/bin/activate
pip install -r requirements.txt -q

echo ""
echo "=== 构建前端 ==="
cd "$PROJECT_DIR/frontend"
npm install --silent
npm run build

echo ""
echo "=== 重启服务 ==="
sudo systemctl restart aipicking

echo ""
echo "=== 验证 ==="
sleep 3
curl -s http://localhost:8000/health

echo ""
echo "=== 部署完成 ==="
