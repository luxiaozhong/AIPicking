# 灵活调仓功能设计

**日期**: 2026-06-16
**范围**: 策略跟踪页面 — 执行调仓按钮升级

## 动机

当前调仓功能有两个硬约束：

1. **全量 or 全无**：`Modal.confirm` 只能全部接受或全部取消，不能逐只选
2. **强制 T+1**：必须等下一个交易日开盘价，盘中无法执行

升级目标：调仓成为独立于推荐节奏的灵活工具——随时可调、逐只可选、手数可配。

---

## 前端：增强型调仓弹窗

新建 `frontend/src/components/RebalanceModal.tsx`，替换 `StrategyTracker.tsx` 中 `handleExecute` 的 `Modal.confirm`。

### 组件 Props

```typescript
interface RebalanceModalProps {
  open: boolean;
  strategyId: number;
  top3: Recommendation[];       // 策略 Top 3 推荐（新组合）
  holdings: Holding[];           // 当前持仓
  cash: number;                  // 当前现金
  totalValue: number;            // 总仓位市值（现金 + 持仓市值）
  recDate: string;               // 推荐日 YYYY-MM-DD
  onClose: () => void;
  onExecuted: () => void;        // 执行成功回调（刷新数据）
}
```

### 布局结构

```
┌─ 执行调仓 ──────────────────────────────────────┐
│ 推荐日：YYYY-MM-DD    成交价：最新收盘价           │
├──────────────────────────────────────────────────┤
│ [Switch] 执行卖出        [Switch] 执行买入         │
├──────────────────────────────────────────────────┤
│ 📤 卖出                                               │
│ ┌──────┬──────────┬────────┬──────────┐             │
│ │ 勾选 │ 名称      │ 持仓股数│ 卖出数量  │             │
│ │  ☑   │ 平安银行  │ 5000   │ [5000]   │             │
│ │  ☐   │ 万科A     │ 3000   │ [3000]   │             │
│ └──────┴──────────┴────────┴──────────┘             │
│                                                      │
│ 📥 买入                                               │
│ ┌──────┬──────────┬────────┬──────────┐             │
│ │ 勾选 │ 名称      │ 建议股数│ 买入数量  │             │
│ │  ☑   │ 五粮液    │ 1200   │ [1200]   │             │
│ │  ☑   │ 贵州茅台  │ 200    │ [200]    │             │
│ └──────┴──────────┴────────┴──────────┘             │
├──────────────────────────────────────────────────┤
│ 💰 当前现金 ¥50,000                                 │
│    + 卖出回款 ¥62,500 → 可用 ¥112,500               │
│    - 买入需 ¥108,000 → 剩余 ¥4,500 ✅               │
│                                                     │
│ 或（资金不足时）：                                    │
│ ⚠️ 缺口 ¥15,000 → [自动追加本金]                     │
├──────────────────────────────────────────────────┤
│                              [取消]  [确认执行]      │
└──────────────────────────────────────────────────┘
```

### 关键逻辑

#### 数据计算

- **卖出列表**：当前持仓中**不在** Top 3 中的股票（exit_holdings）
- **买入列表**：Top 3 中**不在**当前持仓中的股票（enter_recs）
- **保持列表**：交集部分不出现在弹窗中，仅作信息展示

#### 卖出数量默认值

```
卖出数量默认值 = 全部持仓股数
允许用户输入任意值（0 ~ 全部持仓股数），超过持仓的截断
```

#### 买入数量默认值

```
每只建议买入金额 = 总仓位市值 / 3
建议股数 = 建议金额 / 最新收盘价 → 向下取整到每手
  - 主板(60/00)：100 股/手
  - 科创板(688)：200 股/手
```

#### 联动逻辑

1. 「执行卖出」开关关闭 → 所有卖出行禁用、不提交
2. 「执行买入」开关关闭 → 所有买入行禁用、不提交
3. 勾选/取消勾选 → 实时重算资金条
4. 修改数量 → 实时重算资金条
5. 资金不足时 → 显示「自动追加本金」链接，点击后计算缺口并标记 `additional_capital`

#### 提交 payload

```typescript
interface ExecutePayload {
  strategy_id: number;
  date: string;                    // 推荐日 YYYY-MM-DD
  sells: { ts_code: string; shares: number }[];
  buys: { ts_code: string; shares: number }[];
  additional_capital: number;      // 追加本金，默认 0
  exec_date: string;               // 执行日 YYYY-MM-DD，盘中=今天
}
```

---

## 后端：API 改造

文件：`backend/app/api/paper_trade.py`

### Schema 变更

```python
class SellItem(BaseModel):
    ts_code: str
    shares: int = 0           # 卖出数量，0 或未传则跳过

class BuyItem(BaseModel):
    ts_code: str
    shares: int               # 买入数量，必须 >= 1 手

class ExecuteRequest(BaseModel):
    strategy_id: int
    date: Optional[str] = None          # 推荐日
    sells: List[SellItem] = []          # 要卖出的股票
    buys: List[BuyItem] = []            # 要买入的股票
    additional_capital: float = 0.0     # 追加本金
    exec_date: Optional[str] = None     # 执行日，默认当天
```

### 价格获取

```python
# 变更前：取 T+1 开盘价
open_prices = {row.ts_code: row.open for row in ...}

# 变更后：取 exec_date 最新收盘价
price_date = exec_date or _beijing_today()
close_prices = {
    row.ts_code: row.close
    for row in await db.execute(
        select(Daily.ts_code, Daily.close).where(
            Daily.trade_date <= price_date,
            Daily.ts_code.in_(all_codes)
        ).order_by(Daily.trade_date.desc())
    )
}
# 取每个 ts_code 最新的 close（GROUP BY ts_code 取 MAX trade_date）
```

实际使用子查询取每个股票在 `<= exec_date` 范围内的最新一条记录。

**盘中场景的天然回退**：如果 `exec_date` 是今天但今天的 `Daily.close` 还未写入（盘中），子查询自动取到最近一个已有数据的交易日收盘价，无需特殊处理。

### 核心流程变更

```
旧流程：
  T 日 → T+1 日开盘价 → auto diff(exit/keep/enter) → 全卖全买

新流程：
  exec_date → 最新收盘价 → 直接用前端传入 sells/buys → 逐笔执行
```

```python
async def execute_paper_trade(data: ExecuteRequest, ...):
    user_id = current_user.id
    exec_date = data.exec_date or _beijing_today()
    
    # 1. 获取配置
    config = await _get_config(db, user_id, data.strategy_id)
    
    # 2. 获取最新收盘价
    # 收集所有涉及的 ts_code
    sell_codes = [s.ts_code for s in data.sells if s.shares > 0]
    buy_codes = [b.ts_code for b in data.buys if b.shares > 0]
    all_codes = list(set(sell_codes + buy_codes))
    close_prices = await _get_latest_close_prices(db, all_codes, exec_date)
    
    # 3. 验证价格完整性
    missing = [c for c in all_codes if c not in close_prices]
    if missing:
        raise HTTPException(400, f"缺少收盘价: {missing}")
    
    # 4. 计算当前现金
    all_trades = await _get_all_trades(db, user_id, data.strategy_id)
    cash = config.initial_capital + sum(t.net_amount for t in all_trades)
    
    # 5. 追加本金（如有）
    if data.additional_capital > 0:
        config.initial_capital += data.additional_capital
        cash += data.additional_capital
    
    # 6. 执行卖出
    trades_to_insert = []
    current_holdings = await _compute_holdings(db, user_id, data.strategy_id)
    holdings_map = {h["ts_code"]: h for h in current_holdings}
    
    for s in data.sells:
        if s.shares <= 0:
            continue
        h = holdings_map.get(s.ts_code)
        if not h:
            raise HTTPException(400, f"未持有 {s.ts_code}，无法卖出")
        if s.shares > h["shares"]:
            raise HTTPException(400, f"{s.ts_code} 持仓 {h['shares']} 股，不足 {s.shares}")
        
        price = close_prices[s.ts_code]
        gross = round(s.shares * price, 2)
        commission = round(gross * SELL_COMMISSION_RATE, 2)
        stamp = round(gross * STAMP_DUTY_RATE, 2)
        net = round(gross - commission - stamp, 2)
        cash += net
        trades_to_insert.append(PaperTrade(...))
    
    # 7. 执行买入
    # 资金不足时：前端计算的 additional_capital 已在前置步骤中注入
    # 如果仍有不足（前端未预判到），后端自动补差
    for b in data.buys:
        if b.shares <= 0:
            continue
        price = close_prices[b.ts_code]
        gross = round(b.shares * price, 2)
        commission = round(gross * BUY_COMMISSION_RATE, 2)
        total_cost = round(gross + commission, 2)
        
        if total_cost > cash:
            shortfall = round(total_cost - cash, 2)
            config.initial_capital += shortfall
            cash += shortfall
            data.additional_capital += shortfall  # 汇总到响应中
        
        net = -total_cost
        cash += net
        trades_to_insert.append(PaperTrade(...))
    
    # 8. 保存
    db.add_all(trades_to_insert)
    await db.commit()
    
    # 9. 响应
    return {
        "executed": True,
        "rec_date": data.date or exec_date,
        "exec_date": exec_date,
        "trades": [...],
        "summary": {
            "cash_before": cash_before,
            "cash_after": round(cash, 2),
            "holdings_before": len(current_holdings),
            "holdings_after": len(await _compute_holdings(...)),
            "sell_count": sell_count,
            "buy_count": buy_count,
            "keep_count": keep_count,
            "total_buy_amount": ...,
            "total_sell_amount": ...,
            "total_commission": ...,
            "total_stamp_duty": ...,
            "additional_capital_added": ...,  # 实际追加的本金
        },
    }
```

### 删除的逻辑

以下旧逻辑全部移除：
- `_find_nearest_trading_day()` — T 日查找
- `_find_next_trading_day()` — T+1 日查找
- T+1 向前回溯逻辑（约 20 行）
- 同一推荐日防重复检查（`rec_date` 级别）
- auto diff 计算（`exit_holdings` / `keep_codes` / `enter_recs`）
- 等权买入逻辑（改为用户指定手数）

### 新增辅助函数

```python
async def _get_latest_close_prices(
    db: AsyncSession, ts_codes: List[str], before_date: str
) -> Dict[str, float]:
    """获取每个 ts_code 在 before_date（含）之前的最新收盘价
    
    使用子查询：按 ts_code 分组取 MAX(trade_date) <= before_date，
    再 JOIN 回去取 close。
    """
    if not ts_codes:
        return {}
    
    # 子查询：每个股票在 before_date 之前的最新交易日
    subq = (
        select(Daily.ts_code, func.max(Daily.trade_date).label("max_date"))
        .where(Daily.trade_date <= before_date, Daily.ts_code.in_(ts_codes))
        .group_by(Daily.ts_code)
        .subquery()
    )
    rows = await db.execute(
        select(Daily.ts_code, Daily.close)
        .join(subq, (Daily.ts_code == subq.c.ts_code) & (Daily.trade_date == subq.c.max_date))
    )
    return {row.ts_code: float(row.close) for row in rows if row.close and float(row.close) > 0}
```

### 保留的逻辑

- `_get_config()` — 获取/创建用户策略配置
- `_compute_holdings()` — FIFO 持仓聚合
- `_get_all_trades()` — 交易历史用于计算现金
- `_lot_size()` — 每手股数
- 费率常量

---

## 数据流

```
用户点击"执行调仓"
  → RebalanceModal 打开
  → 计算 exit_holdings（旧不在新）和 enter_recs（新不在旧）
  → 用户勾选 + 调整手数
  → 用户确认
  → POST /api/v1/paper-trade/execute
     payload: { strategy_id, date, sells, buys, additional_capital, exec_date }
  → 后端取最新收盘价
  → 逐笔执行卖出 → 更新现金
  → 逐笔执行买入 → 不足自动追加本金
  → 返回交易明细 + 摘要
  → 前端刷新页面数据
```

---

## 边界情况

| 场景 | 处理 |
|------|------|
| 勾选买入但资金不足 | 自动计算缺口，追加本金 |
| 卖出数量超过持仓 | 后端校验拒绝，提示"持仓不足" |
| 买卖都为空 | 提示"无操作" |
| 某股票无收盘价 | 后端拒绝，提示缺失的 ts_code |
| 重复执行同一推荐日 | **允许**，不再设防重复逻辑 |
| 分区卖出（卖一部分留一部分） | 支持，卖出数量 < 持仓数，剩余保留 |
| 科创板(688) | 每手 200 股，前端默认值和后端校验遵循 |
| 新股买入不够一手 | 前端默认值已向下取整，后端校验拒绝 0 股 |

---

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `frontend/src/components/RebalanceModal.tsx` | **新建** |
| `frontend/src/pages/StrategyTracker.tsx` | 修改 — 替换 `handleExecute` 中的 `Modal.confirm` 为 `RebalanceModal` |
| `frontend/src/services/paperTradeService.ts` | 修改 — `execute()` 方法签名扩展 |
| `backend/app/api/paper_trade.py` | 修改 — Schema + `execute_paper_trade` 逻辑重写 |
