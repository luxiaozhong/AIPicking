# 语音播报：一 token 一列表

日期：2026-07-20
状态：实现中

## 背景

当前语音播报的「关注列表」全局绑定在单一指数 `VOICE_WATCHLIST_INDEX`（默认 900099），
所有 token 共享同一份列表。用户希望给不同朋友发不同链接、各自有独立关注列表。

## 目标

每个 voice token 对应一份**独立**的关注列表，互不干扰。重新生成 token/URL 即得到一份全新列表
（默认种子为 茅台/平安，可后续增删）。

## 设计

### 数据模型（新增表 `voice_tokens`）
- `token` VARCHAR(64) PK/唯一 —— 访问钥匙（URL 中传入）
- `label` —— 备注（如 elder）
- `index_code` VARCHAR(20) —— 该 token 专属的指数代码（独立列表载体）
- `index_name` —— 列表标题（注入 H5 页）
- `active` BOOLEAN —— 是否启用
- `created_at` / `updated_at`

每个 token 拥有自己的 `index_info` 记录 + `index_constituents` 成分股，复用现有 watchlist 服务。

### token 解析（DB 化）
- 移除原内存 `_TOKEN_MAP` / `_require_token`（从 env 加载）。
- 改为 `_resolve_token(db, token)`：查 `voice_tokens`，不存在/未启用 → 403。
- `voice_page` / `announce` / `watchlist_manager` 均通过 token 解析出 `index_code`，
  不再使用全局 `VOICE_WATCHLIST_INDEX`。

### 启动种子（向后兼容）
- `seed_voice_tokens(db, settings)`：
  1. 确保默认指数 900099 元数据存在（原行为）。
  2. 若 `voice_tokens` 表为空且 env `VOICE_TOKENS` 有值，把每个 `label:token`
     种子成一行，绑定到 `VOICE_WATCHLIST_INDEX`（保留现有 token 看到的仍是当前列表）。

### 接口变更（`backend/app/api/voice.py`）
- `GET /voice/{token}`：解析 token → 注入其 `index_name` 作标题。
- `GET /api/v1/voice/announce?token=`：用 token 的 `index_code` 取列表。
- `GET /api/v1/voice/watchlist?token=&action=&codes=`：
  - `list` / `add` / `remove`：操作**该 token 自己的列表**（index_code 来自 token）。
  - 新增 `create_token`：生成新 token + 新指数 + 种子默认股票，返回 token 与 URL。
    需管理员校验（`VOICE_ADMIN_TOKEN`；未配置时任一有效 token 可作为管理员）。
  - 新增 `delete_token`：删除指定 token（&target=）。需管理员校验。

### 配置
- `config.py` 新增 `VOICE_ADMIN_TOKEN`（可选）。

### 迁移
- `migrate_schema.py` 新增创建 `voice_tokens` 表（幂等）。

## 使用方式（部署后）
- 查看/增删某朋友的列表：用发给他的 token 调 `watchlist`。
- 给新朋友开一份独立列表：`.../watchlist?token=<管理员token>&action=create_token&name=朋友B`
  返回新 token 与 URL，各自独立。
- 删除：`.../watchlist?token=<管理员token>&action=delete_token&target=<要删的token>`
