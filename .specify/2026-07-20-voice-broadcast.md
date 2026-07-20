# 老年人股票语音播报（微信链接入口）

> 日期：2026-07-20
> 状态：待确认
> 目标：视力不好的老人，在微信聊天框点开一个 URL，即可听到自己关注股票的实时价格语音播报。

---

## 1. 背景与用户场景

- **用户**：老年人，眼睛不好，看不清小字行情。
- **诉求**：监听自己关注的几只股票的实时价格，用**语音播报**出来。
- **入口方式（已确认）**：不做微信推送服务号，而是生成一个 **URL**，老人把这个 URL 保存在微信聊天/收藏里，点开即可播报（微信内置浏览器直接播放，或跳转外部浏览器）。
- **部署（已确认）**：项目已部署到云端，有公网 IP，当前是 **HTTP**（非 HTTPS）。
- **语音方案（已确认）**：**服务端 Edge-TTS 生成 mp3**，比浏览器 TTS 在安卓微信里稳定。

### 典型使用流

```
家人/管理员在后台把老人关注的股票加入 900002 临时观察指数
        │
        ▼
生成一个播报 URL（带 token）：http://<公网IP>:<port>/voice/<token>
        │
        ▼
老人微信里点开 URL → H5 大字页加载 → 显示实时价 + 大「🔊 播报」按钮
        │
        ▼
点按钮（或自动尝试）→ 服务端 Edge-TTS 生成的 mp3 播放："贵州茅台 1480.50 涨 1.2% …"
```

---

## 2. 整体架构

```
                  ┌─────────────────────────────────────┐
                  │   家人/管理员（后台，admin）          │
                  │   维护 900002 关注列表                │
                  └───────────────┬─────────────────────┘
                                  │ (已有 /api/v1/watchlist)
                                  ▼
  微信聊天框  ──点击 URL──▶  [老人手机]  ──HTTP──▶  FastAPI 后端
  /voice/<token>                              │
                                              ├─ 校验 token
                                              ├─ quote_service  (腾讯财经 qt.gtimg.cn 实时报价)
                                              ├─ tts_service    (Edge-TTS 生成 mp3，文件缓存)
                                              └─ 返回 H5 页面 + 实时数据 + 音频 URL
```

---

## 3. 现有能力复用

| 能力 | 现状 | 复用方式 |
|------|------|----------|
| 关注列表 | `watchlist_service.py`（已参数化 index_code）+ `watchlist.py`（admin 增删，支持 index_code 参数） | **新增独立指数 `900099` 语音播报关注**作为老人的关注列表（不复用 900002，家人用 admin 接口维护） |
| 股票名称 | `stocks` 表 | 取名称和代码展示 |
| 部署/后端 | FastAPI，已有 `/api/v1/watchlist` 路由 | 新增 `voice` 路由 + 静态 H5 |
| HTTP 公网 | 已具备 | H5 与音频均走 HTTP，无需 HTTPS 即可用 |

> MVP 阶段**不引入 per-user watchlist**，用独立指数 `900099` 承载老人的关注列表；家人通过 `POST /api/v1/watchlist/stocks?index_code=900099` 维护。

---

## 4. 新增模块

### 4.1 `quote_service.py` — 实时报价（新增）

- **数据源**：腾讯财经 `http://qt.gtimg.cn/q=sh600519,sz000001`（免费、免鉴权、A 股稳定）。
- **编码**：返回 GBK，需 `resp.content.decode('gbk')`。
- **代码转换**：`600519.SH` → `sh600519`；`000001.SZ` → `sz000001`。
- **返回格式**：`v_sh600519="1~贵州茅台~600519~1480.50~1450.10~...~..."`，按 `~` 切分，取：
  - `[1]` 名称、`[3]` 当前价、`[4]` 昨收、`[31]` 涨跌额、`[32]` 涨跌幅(%)、`[30]` 时间。
- **输出**：统一结构
  ```json
  { "ts_code": "600519.SH", "name": "贵州茅台", "price": 1480.50,
    "pre_close": 1450.10, "change": 30.40, "pct": 2.10, "time": "2026-07-20 14:30:00" }
  ```
- **批量**：一次请求最多 ~100 只代码（逗号拼接），超时 5s，失败单只跳过。

### 4.2 `tts_service.py` — Edge-TTS 语音合成（新增）

- **依赖**：`edge-tts`（免费，无需 API key）。
- **音色**：默认 `zh-CN-XiaoxiaoNeural`（自然女声），可配置。
- **合成文本**：把报价拼成口语化播报，例如：
  > "您关注的股票：贵州茅台，1480.50 元，上涨 2.10%；平安银行，12.30 元，下跌 0.80%。"
- **缓存**：按 `hash(text+voice)` 存 `backend/data/voice_cache/<hash>.mp3`，命中直接返回，避免重复合成。
- **接口函数**：`async def synthesize(text, voice) -> path`；`async def synthesize_to_base64(text, voice) -> str`（备用）。

### 4.3 `voice` API（新增路由 `voice.py`）

| Method | Path | 说明 | 鉴权 |
|--------|------|------|------|
| `GET` | `/voice/{token}` | 返回 H5 大字播报页（HTML） | token |
| `GET` | `/api/v1/voice/announce?token=` | 返回关注股实时报价 JSON + 预生成 `audio_url` | token |
| `GET` | `/api/v1/voice/tts?text=&voice=` | 生成（命中缓存则返回）mp3 音频文件 | 限流/可选 token |
| `GET` | `/api/v1/voice/audio/{hash}.mp3` | 返回缓存的 mp3（供 `<audio src>` 播放） | 公开 |

**`announce` 响应示例**：
```json
{
  "updated_at": "2026-07-20 14:30:05",
  "stocks": [
    {"ts_code":"600519.SH","name":"贵州茅台","price":1480.50,"change":30.40,"pct":2.10,"time":"2026-07-20 14:30:00"}
  ],
  "summary_text": "您关注的股票：贵州茅台，1480.50 元，上涨 2.10%。",
  "audio_url": "/api/v1/voice/tts?text=...&voice=zh-CN-XiaoxiaoNeural"
}
```

### 4.4 H5 大字播报页（新增 `backend/app/static/voice.html`）

- 后端用 `app.mount` 或 `FileResponse` 提供；移动端优先、高对比、超大字体。
- 加载即 `fetch(/api/v1/voice/announce?token=)` 显示：股票名（特大）、价格（特大）、涨跌幅（红涨绿跌用大字+箭头）。
- 一个**超大「🔊 播报」按钮**：点击 → `new Audio(audio_url).play()`。
- 自动播放兜底：页面 onload 尝试播放一次（被浏览器拦截则靠按钮）。
- 交易时段每 30s 自动刷新价格（非交易时段提示「已收盘」）。
- 顶部显示「最后更新时间」，避免老人困惑。

### 4.5 访问控制（token）

- 生成方式：在 admin 侧/脚本生成一个随机 token（如 `secrets.token_urlsafe(16)`），URL = `/voice/<token>`。
- 校验：token 映射到一位老人用户。MVP 用**环境变量** `VOICE_TOKENS`（格式 `label:token`，可多个），启动时加载到内存；后续可落 `voice_tokens` 表。
- 不在 URL 用 `?uid=elder` 明文（可猜），用不可猜的 token。
- 播报列表统一用独立指数 `900099`（家人维护，admin 接口 `?index_code=900099`）。

---

## 5. 配置 / 环境变量（新增）

```bash
# 语音播报 token（可多个，逗号分隔，格式 label:token）
VOICE_TOKENS=elder:a1b2c3d4e5f6g7h8
# Edge-TTS 音色（可选，默认 zh-CN-XiaoxiaoNeural）
VOICE_TTS_VOICE=zh-CN-XiaoxiaoNeural
# 报价源（可选，默认 腾讯财经）
VOICE_QUOTE_SOURCE=tencent
```

---

## 6. 部署与 HTTP 注意事项

- 当前 HTTP 公网即可用：微信内置浏览器能打开 HTTP 链接、能播放 HTTP 音频。
- **已知限制**：iOS 微信对自动播放更严格，按钮兜底即可；个别网络环境微信会提示「非官方网页」，仍可继续打开。
- **建议（非阻塞）**：后续配 HTTPS（如用 Nginx + 免费证书），自动播放与稳定性更好。本期不强制。
- Edge-TTS 需要服务器能访问微软 TTS 服务（境外域名）；若服务器网络受限，备用方案：预生成音频或换本地 TTS 引擎（如 VITS / 本地模型）。

---

## 7. 实施计划

| 阶段 | 内容 | 状态 |
|------|------|------|
| Step 1 | `quote_service.py`：腾讯财经实时报价抓取与解析 | ✅ 完成 |
| Step 2 | `tts_service.py`：Edge-TTS 合成 + 文件缓存 | ✅ 完成 |
| Step 3 | `voice.py` API：announce / tts / audio / H5 路由 + token 校验 | ✅ 完成 |
| Step 4 | `voice.html` 大字播报页 + 自动刷新 + 播报按钮 | ✅ 完成 |
| Step 5 | 环境变量配置 + 启动加载 token + 独立指数 900099 | ✅ 完成 |
| Step 6 | 联调：HTTP 公网下微信打开 URL 实测播报 | 待实测 |

**预估**：约 0.5~1 天可跑通 MVP。

---

## 8. 已确认决策（2026-07-20）

1. **关注列表**：新增独立指数 `900099`（不复用 900002），家人用 admin 接口 `?index_code=900099` 维护。
2. **播报内容**：只读「名称 + 现价 + 涨跌幅」（口语化）。
3. **自动刷新**：老人点开页面后，交易时段每 30s 自动刷新价格（可配置 `VOICE_REFRESH_SECONDS`）。
4. **token**：先支持单个 token（`VOICE_TOKENS=elder:xxxx`，逗号可多组）。

> 状态：已确认，已 coding 完成并通过基础联调（实时报价 / Edge-TTS 合成 / token 校验 / H5 注入均验证通过）。

## 9. 上云初始化脚本

手动配置易漏，已固化为 `backend/scripts/setup_voice.py`（仅操作 DB，不依赖 Edge-TTS）：

```bash
cd /opt/AIpicking/backend
./venv/bin/python scripts/setup_voice.py --gen-token --public-ip <公网IP> --port 80
./venv/bin/python scripts/setup_voice.py --stocks 600519.SH 601318.SH   # 加/改关注股票
```

脚本会：① 幂等注册指数 900099；② 批量加股票；③ `--gen-token` 时输出 `.env.production` 配置片段与可直接发给老人的 URL。
把配置片段追加进 `.env.production` 后需 `systemctl restart aipicking` 让后端加载新 token。

> 2026-07-20 更新：播报改为「轮询播报」——点「开始播报」后逐只朗读，本轮播完若不足 30s 则停顿补足后再重新获取最新行情循环播报（可随时停止）。对应 commit 见 git。
