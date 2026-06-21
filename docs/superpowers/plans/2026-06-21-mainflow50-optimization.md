# 主力资金 50 指数优化 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将日更 Top 50 指数改为周更（周五）+ 缓冲垫（45/55）+ 趋势过滤（20MA + 5日涨幅）+ 保留历史

**Architecture:** 单文件改动 `backend/scripts/update_mainflow_index.py`。在现有 pg 聚合流程中插入三个纯逻辑函数（rebalance check、buffer、trend filter）并修改 run() 编排。不涉及 DDL、不涉及前端、不涉及 sync_all.py 改动。

**Tech Stack:** Python 3, psycopg2, PostgreSQL

## Global Constraints

- 所有日期格式遵循数据库日期格式 `YYYY-MM-DD`
- 指数代码 `900001`，元数据不变
- 排除规则不变（ST/北交所/次新股）
- 15 日滚动窗口和等权方式不变
- 现有 CLI 参数保持兼容

---

### Task 1: 调仓频率（日更 → 周更）+ 保留历史

**Files:**
- Modify: `backend/scripts/update_mainflow_index.py`

**Interfaces:**
- Consumes: 现有 `is_trade_day()`, `HOLIDAYS`
- Produces: `is_rebalance_day(date_str: str) -> bool`, 修改 `run()` 签名 `run(..., force: bool = False)`, 修改 `main()` 添加 `--force`, 修改 `upsert_constituents()` 移除 DELETE

- [ ] **Step 1: 添加 `is_rebalance_day()` 函数**

在 `get_latest_trade_day()` 之后插入：

```python
def is_rebalance_day(date_str: str) -> bool:
    """判断 date_str 是否为调仓日。

    规则：最近一个周五（含当日），如果周五是节假日则顺延到下一交易日。

    Args:
        date_str: YYYY-MM-DD 格式日期

    Returns:
        True 如果当天是调仓日
    """
    d = datetime.strptime(date_str, "%Y-%m-%d")

    # 1. 找最近一个周五
    days_since_friday = (d.weekday() - 4) % 7
    last_friday = d - timedelta(days=days_since_friday)
    last_friday_key = last_friday.strftime("%Y%m%d")

    # 2. 最近周五是交易日 且 今天就是那个周五 → 调仓日
    if is_trade_day(last_friday_key) and d == last_friday:
        return True

    # 3. 最近周五是节假日 → 找顺延后的第一个交易日
    if not is_trade_day(last_friday_key):
        next_day = last_friday + timedelta(days=1)
        for _ in range(7):
            if is_trade_day(next_day.strftime("%Y%m%d")):
                return d == next_day  # 今天就是顺延日
            next_day += timedelta(days=1)

    return False
```

- [ ] **Step 2: 修改 `upsert_constituents()` — 移除 DELETE，保留历史**

找到函数中这段代码（约第 259-264 行）并**删除**：

```python
        # 删除该指数所有旧记录，确保表中只有最新一批成分股
        cur.execute(
            "DELETE FROM index_constituents WHERE index_code = %s",
            (INDEX_CODE,),
        )
        logging.info("已删除 %s 旧成分股记录", cur.rowcount)
```

- [ ] **Step 3: 修改 `run()` 签名和开头，加入调仓日检查**

```python
def run(eff_date: str, top_n: int = DEFAULT_TOP_N, dry_run: bool = False, force: bool = False) -> dict:
    """主流程"""
    conn = get_conn()
    try:
        # 0. 调仓日检查（--force 或 --date 指定日期时跳过）
        if not force and not is_rebalance_day(eff_date):
            logging.info("非调仓日（%s），跳过。可用 --force 强制运行", eff_date)
            return {"success": True, "mode": "skip", "reason": "not_rebalance_day", "eff_date": eff_date}

        # 1. 取最近 N 个交易日
        trade_dates = get_lookback_trade_dates(conn, eff_date, LOOKBACK_DAYS)
        # ... 保持不变 ...
```

- [ ] **Step 4: 修改 `main()` 添加 `--force` 参数并传递**

在 `main()` 的 parser 中添加：

```python
    p.add_argument("--force", action="store_true",
                   help="忽略调仓日检查，强制运行（用于回测补跑）")
```

并将 `run()` 调用改为：

```python
    # 指定 --date 时自动视为 force（允许在非周五回测）
    is_force = args.force or args.date is not None
    result = run(eff_date=eff_date, top_n=args.top, dry_run=args.dry_run, force=is_force)
```

同时更新成功消息以区分模式：

```python
    if result["success"]:
        if result.get("mode") == "skip":
            print(f"⏭ 非调仓日，已跳过（{result['eff_date']}）")
        elif result.get("mode") == "dry_run":
            print(f"\n✅ [DRY RUN] 预览完成：{result['count']} 只")
        else:
            print(f"\n✅ 主力资金50 更新完成：{result['count']} 只成分股（{result['eff_date']}）")
```

- [ ] **Step 5: 手动验证**

```bash
cd backend && source venv/bin/activate

# 1. 非周五默认跳过
python scripts/update_mainflow_index.py
# 期望输出: ⏭ 非调仓日，已跳过

# 2. --force 强制运行
python scripts/update_mainflow_index.py --force --dry-run
# 期望输出: ✅ [DRY RUN] 预览完成

# 3. --date 指定周五自动 force
python scripts/update_mainflow_index.py --date 2026-06-19 --dry-run
# （2026-06-19 是周五）期望输出: ✅ [DRY RUN] 预览完成
```

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/update_mainflow_index.py
git commit -m "feat: 主力资金50指数 — 周更调仓 + 保留历史

- 新增 is_rebalance_day() 判断周五调仓日（节假日顺延）
- run() 开头检查调仓日，非调仓日跳过
- --force / --date 可绕过调仓日检查
- upsert_constituents() 移除 DELETE，保留历史 eff_date

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 缓冲垫机制（45/55 + 补满）

**Files:**
- Modify: `backend/scripts/update_mainflow_index.py`

**Interfaces:**
- Consumes: `get_current_holdings(conn) -> list[dict]`, `compute_rankings(conn, trade_dates, limit) -> list[dict]`
- Produces: `apply_buffer(rankings, holdings, top_n) -> list[dict]`

- [ ] **Step 1: 添加常量**

在 Constants 区域已有常量的下方添加：

```python
BUFFER_KICK_RANK = 55       # 持仓排名 > 此值则强制踢出
BUFFER_ENTER_RANK = 45      # 未持仓排名 ≤ 此值则优先纳入
RANKING_LIMIT = 60          # 计算排名时取 top 60（>= BUFFER_KICK_RANK）
```

- [ ] **Step 2: 添加 `get_current_holdings()` 函数**

```python
def get_current_holdings(conn) -> list[dict]:
    """读取最新一批成分股持仓。

    Returns:
        [{ts_code, stock_name, weight}, ...]，无历史持仓时返回空列表
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts_code, stock_name, weight
            FROM index_constituents
            WHERE index_code = %s
              AND eff_date = (
                  SELECT MAX(eff_date) FROM index_constituents
                  WHERE index_code = %s
              )
            """,
            (INDEX_CODE, INDEX_CODE),
        )
        rows = cur.fetchall()
    holdings = [
        {"ts_code": r[0], "stock_name": r[1], "weight": float(r[2])}
        for r in rows
    ]
    if holdings:
        logging.info("当前持仓: %d 只（eff_date 最新批次）", len(holdings))
    else:
        logging.info("无历史持仓，将直接取 Top %d", DEFAULT_TOP_N)
    return holdings
```

- [ ] **Step 3: 修改 `compute_top_stocks()` → `compute_rankings()`**

将函数重命名并修改 `top_n` → `limit`，默认值改为 `RANKING_LIMIT`：

```python
def compute_rankings(conn, trade_dates: list[str], limit: int = RANKING_LIMIT) -> list[dict]:
    """
    聚合最近 N 日主力净流入，返回排名列表（降序）。

    排除规则同 compute_top_stocks。

    Returns:
        [{ts_code, stock_name, flow_15d}, ...]  按 flow_15d 降序，最多 limit 条
    """
    if not trade_dates:
        logging.error("没有交易日数据，无法计算")
        return []

    min_list_date = (datetime.now() - timedelta(days=MIN_LIST_DAYS)).strftime("%Y%m%d")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                sff.ts_code,
                s.name AS stock_name,
                SUM(sff.main_net_flow) AS flow_15d
            FROM daily_stock_fund_flow sff
            JOIN stocks s ON s.ts_code = sff.ts_code
            WHERE sff.trade_date = ANY(%s)
              AND s.type = 'stock'
              AND s.name NOT LIKE '%%ST%%'
              AND sff.ts_code NOT LIKE '%%.BJ'
              AND (s.list_date IS NULL OR s.list_date = '' OR s.list_date <= %s)
            GROUP BY sff.ts_code, s.name
            HAVING SUM(sff.main_net_flow) > 0
            ORDER BY flow_15d DESC
            LIMIT %s
            """,
            (trade_dates, min_list_date, limit),
        )
        rows = cur.fetchall()

    stocks = [
        {
            "ts_code": r[0],
            "stock_name": r[1],
            "flow_15d": float(r[2]),
        }
        for r in rows
    ]

    if len(stocks) < limit:
        logging.warning(
            "符合条件的股票仅 %d 只（查询 limit=%d）—— 全市场主力净流入>0 的不足",
            len(stocks), limit,
        )
    else:
        logging.info("排名计算完成: %d 只，主力净流入范围: %.2f亿 ~ %.2f亿",
                     len(stocks),
                     stocks[-1]["flow_15d"] / 1e8,
                     stocks[0]["flow_15d"] / 1e8)

    return stocks
```

- [ ] **Step 4: 添加 `apply_buffer()` 函数**

```python
def apply_buffer(rankings: list[dict], holdings: list[dict], top_n: int) -> list[dict]:
    """应用缓冲垫规则，返回最终成分股列表。

    规则：
      1. 持仓股中排名 ≤ BUFFER_KICK_RANK → 保留
      2. 持仓股中排名 > BUFFER_KICK_RANK 或不在排名中 → 踢出
      3. 未持仓股中排名 ≤ BUFFER_ENTER_RANK → 优先纳入
      4. 保留+纳入 < top_n → 从排名最高未持仓股中补满

    Args:
        rankings: 排名列表，index 0 = rank 1（已过滤趋势）
        holdings: 当前持仓列表
        top_n: 目标成分股数量

    Returns:
        [{ts_code, stock_name, flow_15d, weight}, ...]
    """
    holding_codes = {h["ts_code"] for h in holdings}
    ranking_by_code = {r["ts_code"]: r for r in rankings}

    # 1. 保留持仓中排名仍在 BUFFER_KICK_RANK 以内的
    keep = []
    kicked = []
    for h in holdings:
        if h["ts_code"] in ranking_by_code:
            # 查找排名位置（0-based）
            rank_pos = next(
                i for i, r in enumerate(rankings) if r["ts_code"] == h["ts_code"]
            )
            if rank_pos < BUFFER_KICK_RANK:
                keep.append(dict(ranking_by_code[h["ts_code"]]))
            else:
                kicked.append((h["ts_code"], rank_pos + 1))
        else:
            # 不在排名中（可能退市/停牌）→ 踢出
            kicked.append((h["ts_code"], None))

    if kicked:
        for code, rank in kicked:
            if rank:
                logging.info("  踢出: %s（排名 %d > %d）", code, rank, BUFFER_KICK_RANK)
            else:
                logging.info("  踢出: %s（不在排名中，可能退市/停牌）", code)
    logging.info("保留持仓: %d 只", len(keep))

    # 2. 优先纳入：未持仓中排名 ≤ BUFFER_ENTER_RANK
    keep_codes = {k["ts_code"] for k in keep}
    priority_add = []
    for i, r in enumerate(rankings):
        if r["ts_code"] not in holding_codes and i < BUFFER_ENTER_RANK:
            priority_add.append(dict(r))
    logging.info("优先纳入: %d 只（排名 ≤ %d）", len(priority_add), BUFFER_ENTER_RANK)

    result = keep + priority_add
    result_codes = {r["ts_code"] for r in result}

    # 3. 补满到 top_n
    if len(result) < top_n:
        for r in rankings:
            if r["ts_code"] not in result_codes and r["ts_code"] not in holding_codes:
                result.append(dict(r))
                result_codes.add(r["ts_code"])
                if len(result) >= top_n:
                    break
        logging.info("补满: %d 只", len(result) - len(keep) - len(priority_add))

    # 4. 赋等权重
    for r in result:
        r["weight"] = EQUAL_WEIGHT

    logging.info("缓冲垫调整完成: 保留 %d + 纳入 %d → 最终 %d 只",
                 len(keep), len(result) - len(keep), len(result))

    return result[:top_n]
```

- [ ] **Step 5: 手动验证缓冲垫逻辑**

```bash
cd backend && source venv/bin/activate

# 以 dry-run 验证完整流程（force 因为今天可能不是周五）
python scripts/update_mainflow_index.py --force --dry-run 2>&1 | head -30
# 检查日志输出：
#   - 当前持仓: X 只
#   - 保留持仓: X 只
#   - 踢出: ... (如有)
#   - 优先纳入: ... (如有)
#   - 补满: ... (如有)
```

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/update_mainflow_index.py
git commit -m "feat: 缓冲垫机制（45/55 + 补满）降低无效换手

- compute_top_stocks → compute_rankings，取 top 60 给缓冲垫留空间
- 新增 get_current_holdings() 读取最新批次持仓
- 新增 apply_buffer() 实现 45/55 缓冲 + 自动补满
- 首次运行无持仓时直接取 top N

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 趋势过滤（20MA + 5日涨幅 < 15%）

**Files:**
- Modify: `backend/scripts/update_mainflow_index.py`

**Interfaces:**
- Consumes: `daily` 表（close, trade_date, ts_code）
- Produces: `apply_trend_filter(conn, ts_codes: list[str], end_date: str) -> set[str]`

- [ ] **Step 1: 添加常量**

```python
MA_PERIOD = 20              # 均线周期
MAX_5D_GAIN = 0.15          # 5日最大涨幅（15%）
```

- [ ] **Step 2: 添加 `apply_trend_filter()` 函数**

```python
def apply_trend_filter(conn, ts_codes: list[str], end_date: str) -> set[str]:
    """批量趋势过滤，返回通过过滤的 ts_code 集合。

    两个条件（AND）：
      1. 收盘价 > 20日均线（基于最近 20 个交易日的 AVG(close)）
      2. 5日涨幅 < 15%（(close - close_5d_ago) / close_5d_ago）

    Args:
        conn: psycopg2 连接
        ts_codes: 待检查的股票代码列表
        end_date: 截止交易日 YYYY-MM-DD

    Returns:
        通过过滤的 ts_code 集合
    """
    if not ts_codes:
        return set()

    with conn.cursor() as cur:
        cur.execute(
            """
            WITH daily_window AS (
                SELECT
                    ts_code,
                    trade_date,
                    close,
                    AVG(close) OVER (
                        PARTITION BY ts_code ORDER BY trade_date
                        ROWS BETWEEN %s PRECEDING AND CURRENT ROW
                    ) AS ma,
                    LAG(close, %s) OVER (
                        PARTITION BY ts_code ORDER BY trade_date
                    ) AS close_5d_ago
                FROM daily
                WHERE ts_code = ANY(%s)
                  AND trade_date <= %s
            ),
            latest AS (
                SELECT DISTINCT ON (ts_code)
                    ts_code, close, ma, close_5d_ago
                FROM daily_window
                WHERE trade_date = (
                    SELECT MAX(trade_date) FROM daily_window
                    WHERE ts_code = daily_window.ts_code
                )
            )
            SELECT ts_code FROM latest
            WHERE close > ma
              AND close_5d_ago IS NOT NULL
              AND close_5d_ago > 0
              AND (close - close_5d_ago) / close_5d_ago < %s
            """,
            (MA_PERIOD - 1, 4, ts_codes, end_date, MAX_5D_GAIN),
        )
        passed = {r[0] for r in cur.fetchall()}

    failed = len(ts_codes) - len(passed)
    if failed:
        logging.info("趋势过滤: %d/%d 通过, %d 未通过（20MA或5日涨幅≥15%%）",
                     len(passed), len(ts_codes), failed)
    else:
        logging.info("趋势过滤: %d/%d 全部通过", len(passed), len(ts_codes))

    return passed
```

- [ ] **Step 3: 修改 `run()` 集成趋势过滤**

在 `run()` 中，排名计算之后、缓冲垫之前插入趋势过滤逻辑。替换 Task 1 Step 3 中 `run()` 的 `# 1. 取最近 N 个交易日` 之后的代码块为：

```python
        # 2. 计算排名（取 top RANKING_LIMIT，给缓冲垫留空间）
        rankings = compute_rankings(conn, trade_dates, RANKING_LIMIT)
        if not rankings:
            logging.error("无符合条件的股票")
            return {"success": False, "error": "no_qualified_stocks"}

        # 3. 获取当前持仓
        holdings = get_current_holdings(conn)

        # 4. 趋势过滤（仅对未持仓的候选股）
        holding_codes = {h["ts_code"] for h in holdings}
        candidate_codes = [
            r["ts_code"] for r in rankings if r["ts_code"] not in holding_codes
        ]
        if candidate_codes:
            passed_codes = apply_trend_filter(conn, candidate_codes, trade_dates[0])
        else:
            passed_codes = set()

        # 构建过滤后的排名列表：持仓股始终保留（不受趋势过滤影响）
        filtered_rankings = [
            r for r in rankings
            if r["ts_code"] in holding_codes or r["ts_code"] in passed_codes
        ]

        # 5. 应用缓冲垫
        if holdings:
            stocks = apply_buffer(filtered_rankings, holdings, top_n)
        else:
            # 首次运行：无历史持仓，直接取过滤后 Top N
            stocks = filtered_rankings[:top_n]
            for s in stocks:
                s["weight"] = EQUAL_WEIGHT
            logging.info("首次运行: 直接取过滤后 Top %d", len(stocks))

        if len(stocks) < top_n:
            logging.warning(
                "最终成分股仅 %d 只（目标 %d）—— 趋势过滤后符合条件的不足",
                len(stocks), top_n,
            )

        if dry_run:
            # ... 保持现有 dry_run 输出 ...
```

- [ ] **Step 4: 更新 `upsert_index_info` 的 constituent_count**

`upsert_index_info` 目前写死 `DEFAULT_TOP_N`，应改为传入实际数量：

```python
def upsert_index_info(conn, eff_date: str, count: int) -> None:
    """幂等写入指数元数据到 index_info"""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO index_info (index_code, index_name, full_name, publisher,
                                    constituent_count, data_source, last_sync_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (index_code) DO UPDATE SET
                constituent_count = EXCLUDED.constituent_count,
                last_sync_date = EXCLUDED.last_sync_date,
                updated_at = NOW() AT TIME ZONE 'Asia/Shanghai'
            """,
            (INDEX_CODE, INDEX_NAME, FULL_NAME, PUBLISHER,
             count, DATA_SOURCE, eff_date),
        )
    conn.commit()
    logging.info("指数元数据已更新: %s (%s), %d 只成分股", FULL_NAME, INDEX_CODE, count)
```

并在 `run()` 中调用 `upsert_index_info(conn, eff_date, len(stocks))`。

- [ ] **Step 5: 手动验证趋势过滤**

```bash
cd backend && source venv/bin/activate

python scripts/update_mainflow_index.py --force --dry-run 2>&1 | grep -E "趋势过滤|最终成分股|首次运行"
# 期望看到：趋势过滤: X/Y 通过, Z 未通过
```

- [ ] **Step 6: Commit**

```bash
git add backend/scripts/update_mainflow_index.py
git commit -m "feat: 趋势过滤 — 20日均线 + 5日涨幅 < 15%

- 新增 apply_trend_filter() 使用 SQL 窗口函数批量过滤
- 持仓股不受趋势过滤影响（只看排名踢出）
- 候选纳入股必须通过两道 AND 检查
- upsert_index_info 改为接收实际成分股数量

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 集成验证 + 边界情况处理

**Files:**
- Modify: `backend/scripts/update_mainflow_index.py`

**Interfaces:**
- Consumes: Task 1-3 的所有函数
- Produces: 完整的 `run()` 编排函数

- [ ] **Step 1: 确保 `run()` 完整编排逻辑正确**

检查 `run()` 中所有路径的返回值格式一致：

```python
def run(eff_date: str, top_n: int = DEFAULT_TOP_N, dry_run: bool = False, force: bool = False) -> dict:
    """主流程"""
    conn = get_conn()
    try:
        # 0. 调仓日检查
        if not force and not is_rebalance_day(eff_date):
            logging.info("非调仓日（%s），跳过。可用 --force 强制运行", eff_date)
            return {"success": True, "mode": "skip", "reason": "not_rebalance_day", "eff_date": eff_date}

        # 1. 取最近 N 个交易日
        trade_dates = get_lookback_trade_dates(conn, eff_date, LOOKBACK_DAYS)
        if len(trade_dates) < 3:
            logging.error("交易日数据不足（仅 %d 天），无法计算滚动 %d 日",
                          len(trade_dates), LOOKBACK_DAYS)
            return {"success": False, "error": "insufficient_trade_days"}

        # 2. 计算排名
        rankings = compute_rankings(conn, trade_dates, RANKING_LIMIT)
        if not rankings:
            logging.error("无符合条件的股票")
            return {"success": False, "error": "no_qualified_stocks"}

        # 3. 获取当前持仓
        holdings = get_current_holdings(conn)

        # 4. 趋势过滤（仅对未持仓的候选股）
        holding_codes = {h["ts_code"] for h in holdings}
        candidate_codes = [
            r["ts_code"] for r in rankings if r["ts_code"] not in holding_codes
        ]
        if candidate_codes:
            passed_codes = apply_trend_filter(conn, candidate_codes, trade_dates[0])
        else:
            passed_codes = set()

        filtered_rankings = [
            r for r in rankings
            if r["ts_code"] in holding_codes or r["ts_code"] in passed_codes
        ]

        # 5. 应用缓冲垫
        if holdings:
            stocks = apply_buffer(filtered_rankings, holdings, top_n)
        else:
            stocks = filtered_rankings[:top_n]
            for s in stocks:
                s["weight"] = EQUAL_WEIGHT
            logging.info("首次运行: 直接取过滤后 Top %d", len(stocks))

        if len(stocks) < top_n:
            logging.warning(
                "最终成分股仅 %d 只（目标 %d）—— 趋势过滤后符合条件的不足",
                len(stocks), top_n,
            )

        if dry_run:
            logging.info("[DRY RUN] 不写入数据库")
            print("\n  排名 | 代码       | 名称       | 15日主力净流入(亿)")
            print("  " + "-" * 55)
            for i, s in enumerate(stocks, 1):
                print(f"  {i:>4} | {s['ts_code']:<10} | {s['stock_name']:<8} | {s['flow_15d']/1e8:>10.2f}")
            return {"success": True, "mode": "dry_run", "count": len(stocks)}

        # 6. 写入
        upsert_index_info(conn, eff_date, len(stocks))
        upsert_constituents(conn, stocks, eff_date)

        # 7. 验证
        verify(conn, eff_date)

        return {"success": True, "count": len(stocks), "eff_date": eff_date}

    finally:
        conn.close()
```

- [ ] **Step 2: 确认 `main()` 的 skip 模式输出**

确认 `main()` 中处理 `mode == "skip"` 的代码（已在 Task 1 Step 4 添加）。

- [ ] **Step 3: 全流程 dry-run 验证**

```bash
cd backend && source venv/bin/activate

# 完整 dry-run
python scripts/update_mainflow_index.py --force --dry-run
# 检查输出包含：
#   - 最近 15 个交易日日志
#   - 排名计算完成日志
#   - 当前持仓日志
#   - 趋势过滤日志
#   - 缓冲垫调整日志
#   - 最终排名预览表格
#   - ✅ [DRY RUN] 预览完成

# 非周五默认跳过
python scripts/update_mainflow_index.py
# 期望: ⏭ 非调仓日，已跳过
```

- [ ] **Step 4: 检查代码质量**

```bash
cd backend
ruff check scripts/update_mainflow_index.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/update_mainflow_index.py
git commit -m "feat: 集成验证 — 完整编排 run() 流程

将周更、缓冲垫、趋势过滤、历史保留四项优化完整集成到 run()。
首次运行自动降级为直接 top N。

Co-Authored-By: Claude <noreply@anthropic.com>"
```
