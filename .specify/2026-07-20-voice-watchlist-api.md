# 语音播报关注列表管理接口

日期：2026-07-20
状态：待确认（草稿）

## 背景

当前语音播报的关注股票只能通过 SSH 上服务器跑
`scripts/setup_voice.py --stocks / --remove` 来增删，运维成本高。
希望开放 HTTP 接口，让管理员（或前端页面）直接增删关注股票、查看列表，
免登服务器。

播报页是轮询拉取数据库关注列表（默认指数 `VOICE_WATCHLIST_INDEX`，即 `900099`），
因此增删只动 DB，**无需重启后端**，下一次轮询（默认 30s）即生效。

## 目标

新增一组「管理端」接口（与现有公开 H5 接口分离），对语音播报关注列表做：
- 查看当前列表
- 添加股票
- 删除股票

## 接口设计

统一挂载在 `/api/v1/voice/watchlist`，**需要登录鉴权**
（`Depends(get_current_user)`，复用 `backend/app/middleware/auth.py` 的 JWT 校验）。

### 1. 查看列表
```
GET /api/v1/voice/watchlist?index_code=900099
```
- 鉴权：需登录
- 响应：
```json
{
  "code": 0,
  "data": {
    "index_code": "900099",
    "index_name": "语音播报关注",
    "stocks": [
      {"ts_code": "600519.SH", "stock_name": "贵州茅台"},
      {"ts_code": "601318.SH", "stock_name": "中国平安"}
    ]
  }
}
```
- 实现：调用 `watchlist_service.get_stocks(db, index_code=...)`

### 2. 添加股票
```
POST /api/v1/voice/watchlist
Content-Type: application/json
{ "ts_codes": ["600519.SH", "000001.SZ"] }
```
- 鉴权：需登录
- 行为：`add_stocks` 幂等，只加不存在的，不影响列表外其它股票
- 响应：
```json
{
  "code": 0,
  "data": {
    "added": 1,
    "ts_codes": ["000001.SZ"],
    "stocks": [ ... 当前完整列表 ... ]
  }
}
```
- 实现：先 `ensure_index_info`（幂等），再 `add_stocks(db, ts_codes, index_code=...)`

### 3. 删除股票
```
DELETE /api/v1/voice/watchlist
Content-Type: application/json
{ "ts_codes": ["601318.SH"] }
```
- 鉴权：需登录
- 行为：逐只 `remove_stock`，返回删除成功的列表
- 响应：
```json
{
  "code": 0,
  "data": {
    "removed": ["601318.SH"],
    "stocks": [ ... 当前完整列表 ... ]
  }
}
```
- 实现：`watchlist_service.remove_stock(db, ts_code, index_code=...)`

## 实现要点

- 文件：`backend/app/api/voice.py` 内新增一个子 router（或一个独立 `voice_admin.py` 挂到同一 prefix）。
  - 倾向：在 `voice.py` 内新增 3 个端点即可，保持简单；或拆 `voice_admin.py` 更清晰。
- 复用：`backend/app/services/watchlist_service.py` 的
  `ensure_index_info / add_stocks / remove_stock / get_stocks`，无需改 service 层。
- 入参校验：`ts_codes` 非空、格式基础校验（`.SH/.SZ` 结尾等可选）。
- 错误：股票代码无效 / 行情库查不到名称时，`add_stocks` 目前行为需确认（是否忽略还是报错）。

## 安全考量

- 这些端点会改全局播报列表，必须登录；是否进一步限制为 `role == admin` 待定。
- 与公开 H5 接口（`/voice/{token}`、`/api/v1/voice/announce`）区分：
  公开接口无 JWT、靠 token；管理接口有 JWT。

## 不在本期范围（可选扩展）

- **token 管理接口**：当前 token 写在 `.env.production` 的 `VOICE_TOKENS`，
  改完要重启后端。若要接口化生成/轮换 token，需把 token 存 DB（较大改动），本期不纳入。
- **前端管理页面**：是否要一个 UI 页面来增删，待定（本期先只做后端 API）。

## 待确认

1. 接口鉴权范围：仅登录即可，还是必须 `admin` 角色？
2. 是否一期就做前端管理页面（增删股票的 UI），还是只做后端接口？
3. 是否需要把「生成 token」也接口化（涉及 DB 存储 token，工作量更大）？
