# update_daily.py 实时报价批量请求优化

> 日期：2026-07-21
> 状态：待确认
> 目标：把 `update_daily.py` 中 qt 实时报价接口（盘中日线 + 盘后兜底）从「一只一个 HTTP 请求」改为「批量逗号拼接（N 只一次请求）」，把 5000+ 只的 HTTP 往返数降低一个数量级，显著缩短盘后 `update_daily --date today` 与盘中 `--intraday` 的耗时。

---

## 1. 背景与问题

### 1.1 现状（已读代码确认）

`backend/scripts/update_daily.py` 有两段通过腾讯 `qt.gtimg.cn` 实时接口取价：

| 段 | 函数 | 调用方式 | 5000+ 只时的请求数 |
|----|------|----------|-------------------|
| 盘中 | `run_intraday`（`fetch_realtime_quote` 单只） | 每只 `QUOTE_API{symbol}` 一次 GET | ~5191 次（30 并发） |
| 盘后兜底 | `run_history` 的 qt 兜底段（已实现 30 并发 + 批量写） | 每只 `fetch_realtime_quote` 一次 GET | ~5186 次（30 并发） |

`fetch_realtime_quote`（`:368`）目前**每次只拼 1 只 symbol**：

```368:373:backend/scripts/update_daily.py
async def fetch_realtime_quote(session, symbol, trade_date):
    url = f"{QUOTE_API}{symbol}"       # ← 单只
```

即便 30 并发，数千次网络往返仍是主要耗时来源。

### 1.2 为什么日内 fund_flow job 快

参考 `scripts/sync_intraday_fund_flow.sh:78-87` 与 `sync_index_fund_flow.py`，其 `--self` 模式把 15 个指数代码逗号拼成**一次请求**；更关键的是项目内 `app` 层的 `quote_service.py`（见 `2026-07-20-voice-broadcast.md` §4.1）已验证：

> 腾讯财经 `http://qt.gtimg.cn/q=sh600519,sz000001`（免费、免鉴权）
> **批量**：一次请求最多 ~100 只代码（逗号拼接），超时 5s，失败单只跳过。
> 返回格式：`v_sh600519="1~贵州茅台~600519~1480.50~..."`，按 `~` 切分。

即 qt 接口**原生支持批量**，返回的每一行是一个 `v_<symbol>="..."` 段，字段顺序与单只完全一致。本优化就是把这套已被验证的批量模式搬进 `update_daily.py`。

---

## 2. 设计方案

### 2.1 新增批量拉取函数

```python
BATCH_SYMBOLS = 100   # 与 quote_service 一致；URL 长度安全（~100*10=1k 字符）

async def fetch_realtime_batch(session, pairs, trade_date):
    """
    批量拉取实时报价。
    pairs: list[(ts_code, symbol), ...]，symbol 已是 sh600519 / sz000001 形式（沿用现有输入）。
    trade_date: YYYY-MM-DD。
    返回: list[(ts_code, record_tuple), ...]（仅成功解析的）。
    """
    symbols = [s for _, s in pairs]
    url = f"{QUOTE_API}{','.join(symbols)}"
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            raw = await resp.read()
        text = raw.decode("gbk", errors="replace")
    except Exception:
        return None   # 整组失败 → 调用方降级为单只重试

    # 按行扫描 v_xxx="..." 段，顺序与请求顺序一致 → 与 pairs 一一对应
    lines = [ln for ln in text.split("\n") if ln.strip().startswith("v_")]
    results = []
    for (ts_code, _), line in zip(pairs, lines):
        record = _parse_qt_line(line, trade_date)   # 抽出原 fetch_realtime_quote 的解析体
        if record:
            results.append((ts_code, record))
    return results
```

### 2.2 抽出公共解析体（重构，非新增逻辑）

把现有 `fetch_realtime_quote`（`:381-416`）里的「`=` 切分 → `~` 切分 → 取字段[3][4][5][33][34][6][37] → 校验 → 组装 record」整段抽出为纯函数：

```python
def _parse_qt_line(line: str, trade_date: str):
    """解析单行 v_xxx="..." 为 record_tuple；失败返回 None。
    逻辑完全复用现有 fetch_realtime_quote 的解析（字段索引、价格/成交量校验、actual_date 推导）不变。"""
```

`fetch_realtime_quote` 保留为**单只降级入口**（批量失败时对每组逐只回退调用它），内部改为调用 `_parse_qt_line`，不重复解析代码。

### 2.3 改造调用方（两段）

**`run_intraday`（盘中，`:459-494`）**
- 将「每只一个 `bounded_fetch` task」改为「每 `BATCH_SYMBOLS` 只一组，每组一个 `bounded_batch` task」：
  ```python
  async def bounded_batch(group_pairs):
      async with semaphore:
          res = await fetch_realtime_batch(session, group_pairs, trade_date)
          if res is None:   # 整组失败 → 逐只降级
              res = [(tc, await fetch_realtime_quote(session, sym, trade_date))
                     for tc, sym in group_pairs]
          return res
  groups = [stocks[i:i+BATCH_SYMBOLS] for i in range(0, len(stocks), BATCH_SYMBOLS)]
  tasks = [bounded_batch([(s["ts_code"], s["symbol"]) for s in g]) for g in groups]
  ```
- 收集 `(ts_code, record)` 后逻辑不变（`(ts_code,)+record[1:]` 入 batch，`bulk_upsert(200)`）。

**`run_history` 的 qt 兜底段（上次已改的并发段，`:543-565`）**
- `failed` 已是 `[(ts_code, symbol), ...]` 列表，直接按 `BATCH_SYMBOLS` 分组，`bounded_qt` 内部改用 `fetch_realtime_batch` + 同样的整组失败降级。其余批量写逻辑不变。

### 2.4 配置项

- 新增模块级常量 `BATCH_SYMBOLS = 100`（与项目内 `quote_service` 对齐；如需保守可下调到 50~60）。
- 不改变 `CONCURRENCY = 30`、`TIMEOUT`、`BATCH_SIZE = 200` 写入批大小。

---

## 3. 接口 / 行为变更清单

| 项 | 变更 |
|----|------|
| `fetch_realtime_quote` | 保留，内部复用 `_parse_qt_line`；仅作为批量失败时的单只降级入口 |
| `_parse_qt_line`（新增） | 从 `fetch_realtime_quote` 抽出的公共解析体，纯函数 |
| `fetch_realtime_batch`（新增） | 批量拉取，返回 `list[(ts_code, record)]` |
| `run_intraday` | 分组批量调用 + 整组失败降级单只，结果聚合后批量写 |
| `run_history` qt 兜底段 | `failed` 列表分组批量调用 + 降级单只 |
| DB 写入语义 | **不变**（仍是 `ON CONFLICT` 幂等 upsert，close/pre_close 等 >0 才覆盖） |
| 返回计数 | `updated/new_count` 含义不变（成功只数 / 覆盖条数） |

> 无 schema 变更，无对外 API 变更，纯内部取数效率优化。

---

## 4. 异常处理与降级策略

1. **整组请求异常**（超时 / 连接错误）：`fetch_realtime_batch` 返回 `None` → 调用方对该组逐只回退 `fetch_realtime_quote`，保证与现状行为一致（不会因为批量失败而丢数据）。
2. **组内部分行解析失败**（某只字段不全）：`_parse_qt_line` 返回 `None`，该行被跳过，不影响同组其他只。
3. **返回行数 < 请求数**：按 `zip(pairs, lines)` 顺序对齐，多出的请求行视为失败，自动进入下次（或降级）重拉——实际腾讯按请求顺序返回，行数对得上。
4. 日志：批量模式下把"✅ 单只"打印改为"✅ 组 done（n/m 只）"抽样打印，避免刷屏（沿用现有 `updated<=3 or updated%500==0` 节奏）。

---

## 5. 性能预期

| 路径 | 现状请求数 | 批量化后（100/组） |
|------|-----------:|-------------------:|
| 盘中 `run_intraday` | ~5191 | **~52** |
| 盘后 qt 兜底 | ~5186 | **~52** |

30 并发下，网络往返从"数千次"降到"数十次"，预计 qt 段整体耗时可压缩一个数量级（受接口 RTT 与并发限制）。DB 写入已是 `bulk_upsert(200)` 批量，非瓶颈。

---

## 6. 实施计划

| Step | 内容 | 状态 |
|------|------|------|
| 1 | 抽出 `_parse_qt_line(line, trade_date)`，改 `fetch_realtime_quote` 复用之 | 待 coding |
| 2 | 新增 `fetch_realtime_batch(session, pairs, trade_date)` + `BATCH_SYMBOLS=100` | 待 coding |
| 3 | 改造 `run_intraday` 为分组批量 + 整组失败时单只降级 | 待 coding |
| 4 | 改造 `run_history` qt 兜底段为分组批量 + 降级 | 待 coding |
| 5 | 本地 dry-run 验证：打印分组数/请求数，并跑一次 `--date today` 比对行数（应仍=5191）与耗时 | 待 coding |

---

## 7. 验证方式

1. **正确性**：重跑 `update_daily.py --date today`，`daily` 表 2026-07-21 行数与改写前一致（当前 5191 有效 + 5 条 pre_close 空残留），涨跌幅分布合理（中位接近真实收盘口径，非上午快照）。
2. **效率**：用 `date +%s` 计时本次与改写前对比（注意：今日已跑过，数据幂等，可直接复跑比对耗时）。
3. **降级**：临时把 `BATCH_SYMBOLS` 设为 1 或模拟批量失败，确认单只降级路径仍能补全数据。
4. 不改 `stats_change_pct.py` / `sync_intraday_*.sh` 等调用方——对外行为一致。

---

## 8. 已确认前提

- qt 接口批量格式由项目内 `quote_service.py` 已验证（逗号拼接、按行 `v_xxx=` 返回、字段索引与单只一致），本优化直接复用该模式。
- `update_daily.py` 当前单只请求已能正常取数，说明传入的 `symbol` 字段已是 `sh600519`/`sz000001` 形式，批量拼接无需改动 symbol 生成逻辑。
- 属纯效率重构，不引入新依赖、不改 DB schema。
