#!/bin/bash
set -e

# ============================================================
# AIpicking 一键部署脚本
# 适用于 Ubuntu 20.04+ / Debian 11+
# 用法: chmod +x deploy.sh && sudo ./deploy.sh
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ---------- 配置变量（按需修改）----------
PROJECT_DIR="/opt/AIpicking"
REPO_URL="https://github.com/luxiaozhong/AIPicking.git"
BACKEND_PORT=8000
DOMAIN_OR_IP="_"          # 有域名则替换为你的域名
NODE_VERSION=20
PYTHON_BIN="python3"
# -----------------------------------------

if [[ $EUID -ne 0 ]]; then
    err "请用 sudo 运行: sudo ./deploy.sh"
fi

# 实际用户（sudo 情况下的执行者）
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

log "开始部署 AIpicking..."

# ============================================================
# 1. 安装系统依赖
# ============================================================
log "安装系统依赖..."

apt update -qq

# Python
if ! command -v $PYTHON_BIN &>/dev/null; then
    apt install -y -qq $PYTHON_BIN $PYTHON_BIN-venv $PYTHON_BIN-pip
    log "Python3 已安装"
else
    log "Python3 已存在，跳过"
fi

# Node.js (via NodeSource)
if ! command -v node &>/dev/null || [[ $(node -v | sed 's/v//' | cut -d. -f1) -lt $NODE_VERSION ]]; then
    curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash -
    apt install -y -qq nodejs
    log "Node.js $(node -v) 已安装"
else
    log "Node.js $(node -v) 已存在，跳过"
fi

# Git
if ! command -v git &>/dev/null; then
    apt install -y -qq git
fi

# Nginx
if ! command -v nginx &>/dev/null; then
    apt install -y -qq nginx
    log "Nginx 已安装"
else
    log "Nginx 已存在，跳过"
fi

# ============================================================
# 2. 拉取代码
# ============================================================
if [[ -d "$PROJECT_DIR/.git" ]]; then
    log "项目已存在，拉取最新代码..."
    cd "$PROJECT_DIR"
    sudo -u "$ACTUAL_USER" git pull origin main
else
    log "克隆项目..."
    mkdir -p "$(dirname "$PROJECT_DIR")"
    sudo -u "$ACTUAL_USER" git clone "$REPO_URL" "$PROJECT_DIR"
fi

# ============================================================
# 3. 配置后端
# ============================================================
log "配置后端..."

cd "$PROJECT_DIR/backend"

# 虚拟环境
if [[ ! -d venv ]]; then
    sudo -u "$ACTUAL_USER" $PYTHON_BIN -m venv venv
    log "Python 虚拟环境已创建"
fi

# 安装 Python 依赖
./venv/bin/pip install -r requirements.txt -q
log "Python 依赖已安装"

# 数据目录
sudo -u "$ACTUAL_USER" mkdir -p data/database data/market_data strategies/examples

# 生产环境配置（首次部署时生成，后续不覆盖）
if [[ ! -f .env.production ]]; then
    JWT_SECRET=$(openssl rand -hex 32)
    cat > .env << 'DOTENV'
APP_NAME=AIpicking
DEBUG=False
DATABASE_URL=sqlite+aiosqlite:///./data/database/aipicking.db
CORS_ORIGINS=["http://DOMAIN_PLACEHOLDER"]
BACKTEST_DATA_DIR=./data/market_data
JWT_SECRET_KEY=JWT_PLACEHOLDER
STOCK_DB_PATH=/opt/stock_data/stock_db.sqlite
DOTENV
    sudo -u "$ACTUAL_USER" sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN_OR_IP}/" .env
    sudo -u "$ACTUAL_USER" sed -i "s/JWT_PLACEHOLDER/${JWT_SECRET}/" .env
    log ".env 已生成（JWT_SECRET 已随机生成）"
else
    log ".env 已存在，跳过"
fi

# ============================================================
# 4. 构建前端
# ============================================================
log "构建前端..."

cd "$PROJECT_DIR/frontend"

# 生产环境前端配置
sudo -u "$ACTUAL_USER" cat > .env.production << 'DOTENV'
VITE_API_BASE_URL=/api/v1
VITE_APP_TITLE=AIpicking 量化交易平台
DOTENV

sudo -u "$ACTUAL_USER" npm install --silent
sudo -u "$ACTUAL_USER" npm run build
log "前端构建完成 → dist/"

# ============================================================
# 5. 配置 Nginx
# ============================================================
log "配置 Nginx..."

cat > /etc/nginx/sites-available/aipicking << NGINX_EOF
server {
    listen 80;
    server_name ${DOMAIN_OR_IP};

    root ${PROJECT_DIR}/frontend/dist;
    index index.html;

    # gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml image/svg+xml;

    # API 反向代理
    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    # SPA fallback
    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX_EOF

# 启用站点
ln -sf /etc/nginx/sites-available/aipicking /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl reload nginx
log "Nginx 已配置并重载"

# ============================================================
# 6. 配置 systemd 服务
# ============================================================
log "配置后端服务..."

cat > /etc/systemd/system/aipicking.service << SYSTEMD_EOF
[Unit]
Description=AIpicking Backend
After=network.target

[Service]
User=${ACTUAL_USER}
WorkingDirectory=${PROJECT_DIR}/backend
EnvironmentFile=${PROJECT_DIR}/backend/.env
ExecStart=${PROJECT_DIR}/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${BACKEND_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

systemctl daemon-reload
systemctl enable aipicking
systemctl restart aipicking
log "后端服务已启动"

# ============================================================
# 7. 检查状态
# ============================================================
echo ""
echo "========================================"
echo "  部署完成！"
echo "========================================"
echo ""

# 后端状态
if systemctl is-active --quiet aipicking; then
    log "后端: 运行中 (systemctl status aipicking)"
else
    warn "后端: 未运行，请检查 journalctl -u aipicking -f"
fi

# Nginx 状态
if systemctl is-active --quiet nginx; then
    log "Nginx: 运行中"
else
    warn "Nginx: 未运行"
fi

echo ""
echo "访问地址:"
echo "  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP')"
echo ""
echo "默认管理员账号: admin / admin123"
echo ""
echo "常用命令:"
echo "  systemctl status aipicking   # 查看后端状态"
echo "  systemctl restart aipicking  # 重启后端"
echo "  journalctl -u aipicking -f   # 查看后端日志"
echo "  nginx -t && systemctl reload nginx  # 重载 Nginx"
echo "  cd ${PROJECT_DIR} && git pull  # 更新代码后重新部署"
echo ""
echo "重要提示:"
echo "  如有域名，请修改 /etc/nginx/sites-available/aipicking 中的 server_name"
echo "  如需 HTTPS，运行: sudo certbot --nginx -d 你的域名"
echo "  请将股票数据库文件放到: ${PROJECT_DIR}/backend/data/market_data/"
echo ""
