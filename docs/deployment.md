# Deployment

## 服务器信息

- 服务器 IP：`<YOUR_SERVER_IP>`
- 登录凭据：请使用 SSH key 或安全的凭据管理方式，**不要**将密码写入文档
- 部署路径：`/opt/AIpicking`
- 更新脚本：`update.sh`
- Cron 定时任务已配置（详见 aipicking-deployment memory）

## systemd

```bash
systemctl restart aipicking   # 重启服务
systemctl status aipicking    # 查看状态
journalctl -u aipicking -f    # 查看日志
```

## 手动更新流程

> ⚠️ **禁止 scp/sftp 直接传文件到服务器**。所有代码变更必须通过 git。

```bash
# 本地：修改代码 → 提交 → 推送
git add -A && git commit -m "描述改动"
git push origin main

# 服务器：拉取 → 安装依赖 → 重启服务
ssh root@101.35.254.125
cd /opt/AIpicking
git pull
pip install -r backend/requirements.txt    # 含 httpx, python-dotenv
cd frontend && npm install --silent && npm run build
systemctl restart aipicking
```

## .env 必要配置

```bash
# backend/.env
DATABASE_URL=postgresql://...
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TIMEOUT=60
CORS_ORIGINS=http://localhost:5173,...
```

## 本地开发重启

```bash
./restart.sh                         # Backend :8000 + Frontend :5173
nohup bash restart.sh > /tmp/aipicking.log 2>&1 &  # 后台运行
```
