#!/bin/bash
set -e

# ============================================================
# AIpicking 一键部署脚本
# 支持 Ubuntu/Debian (apt) 和 CentOS/RHEL/TencentOS (yum/dnf)
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
DOMAIN_OR_IP="_"
NODE_MAJOR=20
# -----------------------------------------

if [[ $EUID -ne 0 ]]; then
    err "请用 sudo 运行: sudo ./deploy.sh"
fi

ACTUAL_USER="${SUDO_USER:-$USER}"

# -------------------- 检测包管理器 --------------------
if command -v apt &>/dev/null; then
    PKG_MGR="apt"
elif command -v dnf &>/dev/null; then
    PKG_MGR="dnf"
elif command -v yum &>/dev/null; then
    PKG_MGR="yum"
else
    err "未检测到 apt/dnf/yum 包管理器"
fi

log "检测到包管理器: ${PKG_MGR}"
log "开始部署 AIpicking..."

# ============================================================
# 1. 安装系统依赖
# ============================================================
log "安装系统依赖..."

case $PKG_MGR in
    apt)
        apt update -qq
        apt install -y -qq curl git nginx
        # Python
        if ! command -v python3 &>/dev/null; then
            apt install -y -qq python3 python3-venv python3-pip
        fi
        # Node.js (NodeSource)
        if ! command -v node &>/dev/null || [[ $(node -v | sed 's/v//' | cut -d. -f1) -lt $NODE_MAJOR ]]; then
            curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash -
            apt install -y -qq nodejs
        fi
        NGINX_CONF_DIR="/etc/nginx/sites-available"
        NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"
        NGINX_DEFAULT_CONF="/etc/nginx/sites-enabled/default"
        ;;
    dnf|yum)
        $PKG_MGR update -y -q 2>/dev/null || true
        $PKG_MGR install -y -q curl git nginx
        # Python
        if ! command -v python3 &>/dev/null; then
            $PKG_MGR install -y -q python3 python3-pip
        fi
        # Node.js (NodeSource)
        if ! command -v node &>/dev/null || [[ $(node -v | sed 's/v//' | cut -d. -f1) -lt $NODE_MAJOR ]]; then
            curl -fsSL https://rpm.nodesource.com/setup_${NODE_MAJOR}.x | bash -
            $PKG_MGR install -y -q nodejs
        fi
        NGINX_CONF_DIR="/etc/nginx/conf.d"
        NGINX_ENABLED_DIR="/etc/nginx/conf.d"
        NGINX_DEFAULT_CONF="/etc/nginx/conf.d/default.conf"
        ;;
esac

# Python 虚拟环境模块（CentOS 可能缺失）
if ! python3 -m venv --help &>/dev/null 2>&1; then
    if [[ $PKG_MGR == "yum" || $PKG_MGR == "dnf" ]]; then
        $PKG_MGR install -y -q python3-venv 2>/dev/null || true
    fi
fi

log "基础依赖安装完成"
log "Python: $(python3 --version 2>&1)"
log "Node.js: $(node -v 2>&1)"
log "Nginx: $(nginx -v 2>&1)"

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

if [[ ! -d venv ]]; then
    sudo -u "$ACTUAL_USER" python3 -m venv venv
    log "Python 虚拟环境已创建"
fi

./venv/bin/pip install -r requirements.txt -q
log "Python 依赖已安装"

sudo -u "$ACTUAL_USER" mkdir -p data/database data/market_data strategies/examples

# 生产环境配置（首次生成，后续不覆盖）
if [[ ! -f .env ]]; then
    JWT_SECRET=$(openssl rand -hex 32)
    cat > .env << DOTENV
APP_NAME=AIpicking
DEBUG=False
DATABASE_URL=sqlite+aiosqlite:///./data/database/aipicking.db
CORS_ORIGINS=http://DOMAIN_PLACEHOLDER
BACKTEST_DATA_DIR=./data/market_data
JWT_SECRET_KEY=JWT_PLACEHOLDER
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TIMEOUT=120
DOTENV
    sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN_OR_IP}/" .env
    sed -i "s/JWT_PLACEHOLDER/${JWT_SECRET}/" .env
    log ".env 已生成（JWT_SECRET 已随机生成，请修改 DEEPSEEK_API_KEY）"
else
    log ".env 已存在，跳过"
    warn "若刚升级，请确保 .env 包含: DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_TIMEOUT"
fi

# ============================================================
# 4. 构建前端
# ============================================================
log "构建前端..."

cd "$PROJECT_DIR/frontend"

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

mkdir -p "$NGINX_CONF_DIR"

cat > "${NGINX_CONF_DIR}/aipicking.conf" << NGINX_EOF
server {
    listen 80;
    server_name ${DOMAIN_OR_IP};

    root ${PROJECT_DIR}/frontend/dist;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml image/svg+xml;

    location /api/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    # 语音播报 H5 页（根路径 /voice/{token}，不在 /api/ 下，必须单独代理到后端）
    location /voice/ {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX_EOF

# Ubuntu/Debian 需要软链；CentOS conf.d 直接生效
if [[ "$PKG_MGR" == "apt" ]]; then
    ln -sf "${NGINX_CONF_DIR}/aipicking.conf" "${NGINX_ENABLED_DIR}/aipicking.conf"
    rm -f "$NGINX_DEFAULT_CONF"
else
    rm -f "$NGINX_DEFAULT_CONF"
fi

nginx -t && systemctl reload nginx 2>/dev/null || systemctl start nginx
systemctl enable nginx
log "Nginx 已配置"

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
# 7. 防火墙（如果 firewalld 在运行则放行 80 端口）
# ============================================================
if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld 2>/dev/null; then
    firewall-cmd --permanent --add-service=http 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
    log "防火墙已放行 80 端口"
fi

# ============================================================
# 8. 状态检查
# ============================================================
echo ""
echo "========================================"
echo "  部署完成！"
echo "========================================"
echo ""

if systemctl is-active --quiet aipicking; then
    log "后端: 运行中"
else
    warn "后端: 未运行，查看日志: journalctl -u aipicking -f"
fi

if systemctl is-active --quiet nginx; then
    log "Nginx: 运行中"
else
    warn "Nginx: 未运行"
fi

echo ""
echo "  访问: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP')"
echo ""
echo "  默认管理员账号: admin（⚠️  首次登录后请立即修改密码！）"
echo ""
echo "常用:"
echo "  systemctl restart aipicking     # 重启后端"
echo "  journalctl -u aipicking -f      # 后端日志"
echo "  nginx -t && systemctl reload nginx"
echo "  cd ${PROJECT_DIR} && git pull && cd backend && ./venv/bin/pip install -r requirements.txt -q && cd ../frontend && npm install --silent && npm run build && systemctl restart aipicking  # 更新"
echo ""
