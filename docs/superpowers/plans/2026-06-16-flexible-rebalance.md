# 灵活调仓功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将调仓从"全量接受/拒绝 + T+1 强制"升级为"逐只勾选 + 手数可调 + 随时盘中执行"的灵活工具

**Architecture:** 前端新建 `RebalanceModal` 组件替换 `Modal.confirm`，内嵌勾选框 + 数量输入 + 资金实时计算；后端 API 从 auto-diff 改为接收显式 sells/buys 列表 + 最新收盘价成交

**Tech Stack:** React 18 + TypeScript + Ant Design 6, FastAPI + SQLAlchemy async + PostgreSQL

---

### Task 1: Backend Schema & Helper 变更

**Files:**
- Modify: `backend/app/api/paper_trade.py:40-111` (schemas), `paper_trade.py:138-171` (helpers)

- [ ] **Step 1: 添加 SellItem、BuyItem schema，扩展 ExecuteRequest 和 ExecuteSummary**

在 `ExecuteRequest` 上方新增 `SellItem` 和 `BuyItem`：

```python
class SellItem(BaseModel):
    ts_code: str
    shares: int = 0           # 卖出数量，0 表示跳过


class BuyItem(BaseModel):
    ts_code: str
    shares: int               # 买入数量，必须 >= 1 手
    stock_name: str = ""      # 股票名称（前端从推荐中传入）
```

修改 `ExecuteRequest`（第 48-50 行）：

```python
class ExecuteRequest(BaseModel):
    strategy_id: int
    date: Optional[str] = None          # 推荐日 YYYY-MM-DD
    sells: List[SellItem] = []          # 要卖出的股票
    buys: List[BuyItem] = []            # 要买入的股票
    additional_capital: float = 0.0     # 前端计算好的追加本金
    exec_date: Optional[str] = None     # 执行日 YYYY-MM-DD，盘中=今天
```

修改 `ExecuteSummary`（第 93-103 行），增加 `additional_capital_added`，移除 `kept` 相关字段（后面 Task 3 前端类型同步移除）：

```python
class ExecuteSummary(BaseModel):
    cash_before: float
    cash_after: float
    holdings_before: int
    holdings_after: int
    sell_count: int
    buy_count: int
    keep_count: int                     # 未卖出也未买入的原持仓数
    total_buy_amount: float
    total_sell_amount: float
    total_commission: float
    total_stamp_duty: float
    additional_capital_added: float     # 实际追加的本金
```

- [ ] **Step 2: 添加 `_get_latest_close_prices` 辅助函数**

在 `_find_next_trading_day` 之后（约第 171 行）插入：

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

    subq = (
        select(Daily.ts_code, func.max(Daily.trade_date).label("max_date"))
        .where(Daily.trade_date <= before_date, Daily.ts_code.in_(ts_codes))
        .group_by(Daily.ts_code)
        .subquery()
    )
    rows = await db.execute(
        select(Daily.ts_code, Daily.close).join(
            subq,
            (Daily.ts_code == subq.c.ts_code)
            & (Daily.trade_date == subq.c.max_date),
        )
    )
    return {
        row.ts_code: float(row.close)
        for row in rows
        if row.close and float(row.close) > 0
    }
```

需要在文件顶部 import 中加入 `Dict`（已经在 typing import 中有 `Optional, List`，加上 `Dict`）：

```python
from typing import Optional, List, Dict
```

- [ ] **Step 3: 提交 Schema + Helper 变更**

```bash
git add backend/app/api/paper_trade.py
git commit -m "feat: add flexible rebalance schemas and latest-close-price helper"
```

---

### Task 2: Backend execute_paper_trade 重写

**Files:**
- Modify: `backend/app/api/paper_trade.py:341-599` (execute endpoint)

- [ ] **Step 1: 替换整个 `execute_paper_trade` 函数**

删除第 341-599 行的旧实现，替换为：

```python
@router.post("/execute")
async def execute_paper_trade(
    data: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """执行一次调仓（灵活模式：支持逐只勾选 + 自定义手数 + 盘中执行）

    1. exec_date 默认今天，取最新收盘价
    2. 按前端传入的 sells 列表卖出，支持部分卖出
    3. 按前端传入的 buys 列表买入，支持自定义手数
    4. 资金不足时自动追加本金
    """
    user_id = current_user.id
    exec_date = data.exec_date or _beijing_today()

    # ── 1. 获取配置 ──
    config = await _get_config(db, user_id, data.strategy_id)

    # ── 2. 收集涉及的 ts_code 并获取最新收盘价 ──
    sell_codes = [s.ts_code for s in data.sells if s.shares > 0]
    buy_codes = [b.ts_code for b in data.buys if b.shares > 0]
    all_codes = list(set(sell_codes + buy_codes))

    if not all_codes:
        raise HTTPException(400, "没有指定任何卖出或买入操作")

    close_prices = await _get_latest_close_prices(db, all_codes, exec_date)

    missing = [c for c in all_codes if c not in close_prices]
    if missing:
        raise HTTPException(400, f"缺少最新收盘价: {missing}")

    # ── 3. 计算当前现金 ──
    all_trades = await _get_all_trades(db, user_id, data.strategy_id)
    cash = config.initial_capital + sum(t.net_amount for t in all_trades)
    cash_before = round(cash, 2)

    # ── 4. 追加前端传入的本金 ──
    additional_added = data.additional_capital
    if additional_added > 0:
        config.initial_capital += additional_added
        cash += additional_added

    # ── 5. 执行卖出 ──
    trades_to_insert: List[PaperTrade] = []
    current_holdings = await _compute_holdings(db, user_id, data.strategy_id)
    holdings_map = {h["ts_code"]: h for h in current_holdings}
    sell_count = 0

    for s in data.sells:
        if s.shares <= 0:
            continue
        h = holdings_map.get(s.ts_code)
        if not h:
            raise HTTPException(400, f"未持有 {s.ts_code}，无法卖出")
        if s.shares > h["shares"]:
            raise HTTPException(
                400,
                f"{s.ts_code} {h['stock_name']} 持仓 {h['shares']} 股，"
                f"无法卖出 {s.shares} 股",
            )

        price = close_prices[s.ts_code]
        gross = round(s.shares * price, 2)
        commission = round(gross * SELL_COMMISSION_RATE, 2)
        stamp = round(gross * STAMP_DUTY_RATE, 2)
        net = round(gross - commission - stamp, 2)
        cash += net

        trades_to_insert.append(PaperTrade(
            user_id=user_id,
            strategy_id=data.strategy_id,
            action="sell",
            exec_date=exec_date,
            rec_date=data.date or exec_date,
            ts_code=s.ts_code,
            stock_name=h["stock_name"],
            shares=s.shares,
            price=price,
            amount=gross,
            commission=commission,
            stamp_duty=stamp,
            net_amount=net,
        ))
        sell_count += 1

    # ── 6. 执行买入 ──
    buy_count = 0
    for b in data.buys:
        if b.shares <= 0:
            continue
        price = close_prices[b.ts_code]
        gross = round(b.shares * price, 2)
        commission = round(gross * BUY_COMMISSION_RATE, 2)
        total_cost = round(gross + commission, 2)

        # 资金不足：自动注入差額
        if total_cost > cash:
            shortfall = round(total_cost - cash, 2)
            config.initial_capital += shortfall
            cash += shortfall
            additional_added = round(additional_added + shortfall, 2)

        net = -total_cost
        cash += net

        # stock_name：优先用前端传入，回退到 ts_code
        stock_name = b.stock_name or b.ts_code

        trades_to_insert.append(PaperTrade(
            user_id=user_id,
            strategy_id=data.strategy_id,
            action="buy",
            exec_date=exec_date,
            rec_date=data.date or exec_date,
            ts_code=b.ts_code,
            stock_name=stock_name,
            shares=b.shares,
            price=price,
            amount=gross,
            commission=commission,
            stamp_duty=0.0,
            net_amount=net,
        ))
        buy_count += 1

    # ── 7. 校验 ──
    if not trades_to_insert:
        raise HTTPException(400, "未生成任何有效交易")

    # ── 8. 保存 ──
    db.add_all(trades_to_insert)
    await db.commit()

    for t in trades_to_insert:
        await db.refresh(t)

    # ── 9. 构建响应 ──
    sell_trades = [t for t in trades_to_insert if t.action == "sell"]
    buy_trades = [t for t in trades_to_insert if t.action == "buy"]

    total_buy_amount = sum(t.amount for t in buy_trades)
    total_sell_amount = sum(t.amount for t in sell_trades)
    total_commission = sum(t.commission for t in trades_to_insert)
    total_stamp_duty = sum(t.stamp_duty for t in trades_to_insert)

    final_holdings = await _compute_holdings(db, user_id, data.strategy_id)

    # keep_count = 未出现在 sells 中的原持仓数
    sold_codes = {s.ts_code for s in data.sells if s.shares > 0}
    keep_count = sum(
        1 for h in current_holdings if h["ts_code"] not in sold_codes
    )

    return {
        "executed": True,
        "rec_date": data.date or exec_date,
        "exec_date": exec_date,
        "trades": [
            {
                "id": t.id,
                "action": t.action,
                "exec_date": t.exec_date,
                "rec_date": t.rec_date,
                "ts_code": t.ts_code,
                "stock_name": t.stock_name,
                "shares": t.shares,
                "price": t.price,
                "amount": t.amount,
                "commission": t.commission,
                "stamp_duty": t.stamp_duty,
                "net_amount": t.net_amount,
            }
            for t in trades_to_insert
        ],
        "summary": {
            "cash_before": cash_before,
            "cash_after": round(cash, 2),
            "holdings_before": len(current_holdings),
            "holdings_after": len(final_holdings),
            "sell_count": sell_count,
            "buy_count": buy_count,
            "keep_count": keep_count,
            "total_buy_amount": round(total_buy_amount, 2),
            "total_sell_amount": round(total_sell_amount, 2),
            "total_commission": round(total_commission, 2),
            "total_stamp_duty": round(total_stamp_duty, 2),
            "additional_capital_added": round(additional_added, 2),
        },
    }
```

- [ ] **Step 2: 删除不再使用的辅助函数**

删除 `_find_nearest_trading_day`（第 150-158 行）和 `_find_next_trading_day`（第 162-171 行）—— 仅当确认没有其他地方引用它们时。

先检查引用：

```bash
grep -n "_find_nearest_trading_day\|_find_next_trading_day" backend/app/api/paper_trade.py
```

`_find_nearest_trading_day` 还被 `_compute_holdings` 引用（第 254 行），保留它。只删除 `_find_next_trading_day`。

```python
# 删除第 162-171 行的 _find_next_trading_day 函数
```

- [ ] **Step 3: 验证后端启动正常**

```bash
cd backend && source venv/bin/activate
python -c "from app.api.paper_trade import router, ExecuteRequest, SellItem, BuyItem; print('Import OK')"
```

- [ ] **Step 4: 提交后端改动**

```bash
git add backend/app/api/paper_trade.py
git commit -m "feat: rewrite execute endpoint for flexible rebalance with explicit sells/buys"
```

---

### Task 3: Frontend — paperTradeService 类型同步

**Files:**
- Modify: `frontend/src/services/paperTradeService.ts:1-173`

- [ ] **Step 1: 更新 ExecuteSummary 类型和 execute 方法签名**

修改 `ExecuteSummary`（第 45-58 行），移除 `kept` 字段，添加 `additional_capital_added`：

```typescript
export interface ExecuteSummary {
  cash_before: number;
  cash_after: number;
  holdings_before: number;
  holdings_after: number;
  sell_count: number;
  buy_count: number;
  keep_count: number;
  total_buy_amount: number;
  total_sell_amount: number;
  total_commission: number;
  total_stamp_duty: number;
  additional_capital_added: number;
}
```

修改 `execute` 方法（第 119-128 行），扩展参数：

```typescript
/** 执行一次调仓（灵活模式） */
async execute(payload: {
  strategy_id: number;
  date?: string;
  sells: { ts_code: string; shares: number }[];
  buys: { ts_code: string; shares: number; stock_name?: string }[];
  additional_capital?: number;
  exec_date?: string;
}): Promise<ExecuteResult> {
  const response = await api.post<ExecuteResult>(`${BASE}/execute`, payload);
  return response.data;
},
```

- [ ] **Step 2: 提交前端服务层改动**

```bash
git add frontend/src/services/paperTradeService.ts
git commit -m "feat: update paperTradeService types and execute signature for flexible rebalance"
```

---

### Task 4: Frontend — RebalanceModal 组件

**Files:**
- Create: `frontend/src/components/RebalanceModal.tsx`

- [ ] **Step 1: 创建 RebalanceModal 组件**

```tsx
import { useState, useMemo, useCallback } from 'react';
import {
  Modal, Switch, Table, InputNumber, Space,
  Typography, Tag, Alert, Divider,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Recommendation } from '@/services/strategyTrackerService';
import type { PaperHolding } from '@/services/paperTradeService';

const { Text, Title } = Typography;

// ── Types ──

interface SellRow {
  key: string;
  ts_code: string;
  stock_name: string;
  holding_shares: number;
  sell_shares: number;
  checked: boolean;
}

interface BuyRow {
  key: string;
  ts_code: string;
  stock_name: string;
  suggested_shares: number;
  buy_shares: number;
  checked: boolean;
}

interface RebalanceModalProps {
  open: boolean;
  strategyId: number;
  top3: Recommendation[];
  holdings: PaperHolding[];
  cash: number;
  totalValue: number;
  recDate: string;
  loading?: boolean;
  onClose: () => void;
  onSubmit: (payload: {
    strategy_id: number;
    date: string;
    sells: { ts_code: string; shares: number }[];
    buys: { ts_code: string; shares: number }[];
    additional_capital: number;
    exec_date: string;
  }) => Promise<void>;
}

// ── Helpers ──

function getLotSize(tsCode: string): number {
  return tsCode.startsWith('688') ? 200 : 100;
}

function roundToLot(shares: number, tsCode: string): number {
  const lot = getLotSize(tsCode);
  return Math.floor(shares / lot) * lot;
}

// ── Component ──

export default function RebalanceModal({
  open,
  strategyId,
  top3,
  holdings,
  cash,
  totalValue,
  recDate,
  loading = false,
  onClose,
  onSubmit,
}: RebalanceModalProps) {
  // 开关
  const [sellEnabled, setSellEnabled] = useState(true);
  const [buyEnabled, setBuyEnabled] = useState(true);

  // 兜底收盘价
  const fallbackCloseMap = useMemo(() => {
    const map: Record<string, number> = {};
    holdings.forEach((h) => {
      if (h.last_price && h.last_price > 0) map[h.ts_code] = h.last_price;
    });
    top3.forEach((r) => {
      if (r.close && r.close > 0) map[r.ts_code] = r.close;
    });
    return map;
  }, [holdings, top3]);

  // 卖出列表：持仓中不在 Top3 中的
  const sellRows: SellRow[] = useMemo(() => {
    const topCodes = new Set(top3.map((r) => r.ts_code));
    return holdings
      .filter((h) => !topCodes.has(h.ts_code))
      .map((h) => ({
        key: `sell-${h.ts_code}`,
        ts_code: h.ts_code,
        stock_name: h.stock_name,
        holding_shares: h.shares,
        sell_shares: h.shares, // 默认全卖
        checked: true,
      }));
  }, [holdings, top3]);

  const [sellData, setSellData] = useState<SellRow[]>(sellRows);

  // 当弹窗打开时重置数据
  useState(() => {
    setSellData(sellRows);
  });

  // 买入列表：Top3 中不在持仓中的
  const buyRows: BuyRow[] = useMemo(() => {
    const heldCodes = new Set(holdings.map((h) => h.ts_code));
    return top3
      .filter((r) => !heldCodes.has(r.ts_code))
      .map((r) => {
        const close = r.close || fallbackCloseMap[r.ts_code] || 0;
        const budget = totalValue / 3;
        const rawShares = close > 0 ? budget / close : 0;
        const suggested = roundToLot(Math.floor(rawShares), r.ts_code);
        return {
          key: `buy-${r.ts_code}`,
          ts_code: r.ts_code,
          stock_name: r.name,
          suggested_shares: Math.max(suggested, getLotSize(r.ts_code)),
          buy_shares: Math.max(suggested, getLotSize(r.ts_code)),
          checked: true,
        };
      });
  }, [top3, holdings, fallbackCloseMap, totalValue]);

  const [buyData, setBuyData] = useState<BuyRow[]>(buyRows);

  // 资金计算
  const calcResult = useMemo(() => {
    // 卖出回款
    let sellProceeds = 0;
    const checkedSells = sellEnabled ? sellData.filter((s) => s.checked) : [];
    for (const s of checkedSells) {
      const price = fallbackCloseMap[s.ts_code] || 0;
      const gross = s.sell_shares * price;
      const commission = gross * 0.00015;
      const stamp = gross * 0.0005;
      sellProceeds += gross - commission - stamp;
    }

    const availableCash = cash + sellProceeds;

    // 买入需用
    let buyRequired = 0;
    const checkedBuys = buyEnabled ? buyData.filter((b) => b.checked) : [];
    for (const b of checkedBuys) {
      const price = fallbackCloseMap[b.ts_code] || 0;
      const gross = b.buy_shares * price;
      const commission = gross * 0.00015;
      buyRequired += gross + commission;
    }

    const remaining = availableCash - buyRequired;
    const shortfall = remaining < 0 ? Math.abs(remaining) : 0;

    return {
      sellProceeds: Math.round(sellProceeds * 100) / 100,
      availableCash: Math.round(availableCash * 100) / 100,
      buyRequired: Math.round(buyRequired * 100) / 100,
      remaining: Math.round(remaining * 100) / 100,
      shortfall: Math.round(shortfall * 100) / 100,
      hasShortfall: shortfall > 0.01,
    };
  }, [sellData, buyData, sellEnabled, buyEnabled, cash, fallbackCloseMap]);

  // 提交
  const handleOk = useCallback(async () => {
    const sells = sellEnabled
      ? sellData.filter((s) => s.checked && s.sell_shares > 0).map((s) => ({
          ts_code: s.ts_code,
          shares: s.sell_shares,
        }))
      : [];

    const buys = buyEnabled
      ? buyData.filter((b) => b.checked && b.buy_shares > 0).map((b) => ({
          ts_code: b.ts_code,
          shares: b.buy_shares,
          stock_name: b.stock_name,
        }))
      : [];

    const today = new Date().toISOString().slice(0, 10);

    await onSubmit({
      strategy_id: strategyId,
      date: recDate,
      sells,
      buys,
      additional_capital: calcResult.shortfall,
      exec_date: today,
    });
  }, [sellEnabled, buyEnabled, sellData, buyData, strategyId, recDate, calcResult.shortfall, onSubmit]);

  // 卖出表格列
  const sellColumns: ColumnsType<SellRow> = [
    {
      title: '勾选', dataIndex: 'checked', width: 50,
      render: (_: unknown, record: SellRow) => (
        <input
          type="checkbox"
          checked={record.checked}
          disabled={!sellEnabled}
          onChange={(e) => {
            setSellData((prev) =>
              prev.map((r) =>
                r.key === record.key ? { ...r, checked: e.target.checked } : r
              )
            );
          }}
        />
      ),
    },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { title: '代码', dataIndex: 'ts_code', width: 100, render: (v: string) => <Text type="secondary">{v}</Text> },
    {
      title: '持仓', dataIndex: 'holding_shares', width: 80, align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '卖出数量', dataIndex: 'sell_shares', width: 120,
      render: (_: unknown, record: SellRow) => (
        <InputNumber
          min={0}
          max={record.holding_shares}
          step={getLotSize(record.ts_code)}
          value={record.sell_shares}
          disabled={!sellEnabled || !record.checked}
          style={{ width: '100%' }}
          onChange={(val) => {
            setSellData((prev) =>
              prev.map((r) =>
                r.key === record.key
                  ? { ...r, sell_shares: Math.min(val ?? 0, r.holding_shares) }
                  : r
              )
            );
          }}
        />
      ),
    },
  ];

  // 买入表格列
  const buyColumns: ColumnsType<BuyRow> = [
    {
      title: '勾选', dataIndex: 'checked', width: 50,
      render: (_: unknown, record: BuyRow) => (
        <input
          type="checkbox"
          checked={record.checked}
          disabled={!buyEnabled}
          onChange={(e) => {
            setBuyData((prev) =>
              prev.map((r) =>
                r.key === record.key ? { ...r, checked: e.target.checked } : r
              )
            );
          }}
        />
      ),
    },
    { title: '名称', dataIndex: 'stock_name', width: 100 },
    { title: '代码', dataIndex: 'ts_code', width: 100, render: (v: string) => <Text type="secondary">{v}</Text> },
    {
      title: '建议', dataIndex: 'suggested_shares', width: 80, align: 'right',
      render: (v: number) => <Text type="secondary">{v.toLocaleString()}</Text>,
    },
    {
      title: '买入数量', dataIndex: 'buy_shares', width: 120,
      render: (_: unknown, record: BuyRow) => (
        <InputNumber
          min={0}
          step={getLotSize(record.ts_code)}
          value={record.buy_shares}
          disabled={!buyEnabled || !record.checked}
          style={{ width: '100%' }}
          onChange={(val) => {
            setBuyData((prev) =>
              prev.map((r) =>
                r.key === record.key ? { ...r, buy_shares: val ?? 0 } : r
              )
            );
          }}
        />
      ),
    },
  ];

  // 保持列表
  const keepItems = useMemo(() => {
    const topCodes = new Set(top3.map((r) => r.ts_code));
    return holdings.filter((h) => topCodes.has(h.ts_code));
  }, [holdings, top3]);

  return (
    <Modal
      title="执行调仓"
      open={open}
      width={700}
      confirmLoading={loading}
      onOk={handleOk}
      onCancel={onClose}
      okText="确认执行"
      cancelText="取消"
      okButtonProps={{
        disabled: sellData.every((s) => !s.checked || s.sell_shares <= 0)
          && buyData.every((b) => !b.checked || b.buy_shares <= 0),
      }}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* 顶部信息 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">
            推荐日：{recDate} ｜ 成交价基准：最新收盘价
          </Text>
        </div>

        <Divider style={{ margin: 0 }} />

        {/* 开关 */}
        <Space>
          <Text>执行卖出</Text>
          <Switch checked={sellEnabled} onChange={setSellEnabled} size="small" />
          <Text style={{ marginLeft: 24 }}>执行买入</Text>
          <Switch checked={buyEnabled} onChange={setBuyEnabled} size="small" />
        </Space>

        {/* 保持列表 */}
        {keepItems.length > 0 && (
          <div>
            <Text type="secondary">📌 保持（不变）：</Text>
            {keepItems.map((h) => (
              <Tag key={h.ts_code} color="default" style={{ marginLeft: 4 }}>
                {h.stock_name}（{h.shares.toLocaleString()} 股）
              </Tag>
            ))}
          </div>
        )}

        {/* 卖出区域 */}
        {sellRows.length > 0 && (
          <div>
            <Text strong>📤 卖出（{sellRows.length} 只）</Text>
            <Table
              size="small"
              rowKey="key"
              columns={sellColumns}
              dataSource={sellData}
              pagination={false}
              style={{ marginTop: 4 }}
            />
          </div>
        )}
        {sellRows.length === 0 && sellEnabled && (
          <Text type="secondary">📤 无需要卖出的股票</Text>
        )}

        {/* 买入区域 */}
        {buyRows.length > 0 && (
          <div>
            <Text strong>📥 买入（{buyRows.length} 只）</Text>
            <Table
              size="small"
              rowKey="key"
              columns={buyColumns}
              dataSource={buyData}
              pagination={false}
              style={{ marginTop: 4 }}
            />
          </div>
        )}
        {buyRows.length === 0 && buyEnabled && (
          <Text type="secondary">📥 无需要买入的股票</Text>
        )}

        {/* 资金状态栏 */}
        <div
          style={{
            background: '#fafafa',
            padding: 12,
            borderRadius: 6,
            border: calcResult.hasShortfall ? '1px solid #ff4d4f' : '1px solid #d9d9d9',
          }}
        >
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text>当前现金</Text>
              <Text>{cash.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元</Text>
            </div>
            {calcResult.sellProceeds > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="success">+ 卖出回款</Text>
                <Text type="success">
                  {calcResult.sellProceeds.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元
                </Text>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Text strong>可用资金</Text>
              <Text strong>
                {calcResult.availableCash.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元
              </Text>
            </div>
            {calcResult.buyRequired > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <Text type="warning">- 买入需用</Text>
                <Text type="warning">
                  {calcResult.buyRequired.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元
                </Text>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid #d9d9d9', paddingTop: 4, marginTop: 4 }}>
              {calcResult.hasShortfall ? (
                <>
                  <Text type="danger" strong>⚠️ 资金缺口</Text>
                  <Text type="danger" strong>
                    {calcResult.shortfall.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元
                  </Text>
                  <Text type="secondary" style={{ width: '100%', marginTop: 4 }}>
                    确认执行时将自动追加本金
                  </Text>
                </>
              ) : (
                <>
                  <Text>剩余</Text>
                  <Text type="success">
                    {calcResult.remaining.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元 ✅
                  </Text>
                </>
              )}
            </div>
          </Space>
        </div>
      </Space>
    </Modal>
  );
}
```

- [ ] **Step 2: 验证组件编译**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30
```

如果有类型错误，修复后重新检查。

- [ ] **Step 3: 提交组件**

```bash
git add frontend/src/components/RebalanceModal.tsx
git commit -m "feat: add RebalanceModal component with per-stock checkboxes and share inputs"
```

---

### Task 5: Frontend — StrategyTracker 集成

**Files:**
- Modify: `frontend/src/pages/StrategyTracker.tsx:1-26, 242-294`

- [ ] **Step 1: 引入 RebalanceModal 并添加状态**

在 import 区域（第 1-24 行）添加 import：

```tsx
import RebalanceModal from '@/components/RebalanceModal';
```

在状态声明区域（约第 142 行 `executing` 之后）添加：

```tsx
const [rebalanceOpen, setRebalanceOpen] = useState(false);
```

- [ ] **Step 2: 替换 handleExecute**

将第 242-294 行旧的 `handleExecute`（`Modal.confirm` 版本）替换为：

```tsx
// ── 执行调仓 ──
const handleExecute = () => {
  if (!strategyId) return;
  setRebalanceOpen(true);
};

const handleRebalanceSubmit = async (payload: {
  strategy_id: number;
  date: string;
  sells: { ts_code: string; shares: number }[];
  buys: { ts_code: string; shares: number }[];
  additional_capital: number;
  exec_date: string;
}) => {
  setExecuting(true);
  try {
    const result = await paperTradeService.execute(payload);
    const parts = ['调仓完成！'];
    if (result.summary.sell_count > 0) parts.push(`${result.summary.sell_count} 卖`);
    if (result.summary.buy_count > 0) parts.push(`${result.summary.buy_count} 买`);
    if (result.summary.keep_count > 0) parts.push(`${result.summary.keep_count} 保持`);
    parts.push(`手续费 ¥${result.summary.total_commission.toFixed(2)}`);
    parts.push(`印花税 ¥${result.summary.total_stamp_duty.toFixed(2)}`);
    if (result.summary.additional_capital_added > 0) {
      parts.push(`追加本金 ¥${result.summary.additional_capital_added.toFixed(2)}`);
    }
    message.success(parts.join(' · '), 5);
    setRebalanceOpen(false);
    await loadData(strategyId, selectedDate);
  } catch (err: unknown) {
    const msg =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
      (err as Error)?.message ||
      '执行失败';
    message.error(msg);
  } finally {
    setExecuting(false);
  }
};
```

- [ ] **Step 3: 在 JSX 中渲染 RebalanceModal**

在 return 的 JSX 中找到「执行调仓」按钮的位置（约第 481-488 行），在其之后（或 return 末尾合适位置）添加：

```tsx
<RebalanceModal
  open={rebalanceOpen}
  strategyId={strategyId!}
  top3={top3}
  holdings={status?.holdings || []}
  cash={status?.cash || 0}
  totalValue={(status?.total_nav || 0)}
  recDate={tradeDate || selectedDate}
  loading={executing}
  onClose={() => setRebalanceOpen(false)}
  onSubmit={handleRebalanceSubmit}
/>
```

**注意**：`top3` 定义为 `recommendations.slice(0, 3)`。检查 `StrategyTracker.tsx` 中是否已有 `top3` 变量，如果没有则添加：

在合适位置（例如 `recommendations` 状态之后）添加：

```tsx
const top3 = useMemo(() => recommendations.slice(0, 3), [recommendations]);
```

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -40
```

确保无新错误。

- [ ] **Step 5: 提交集成改动**

```bash
git add frontend/src/pages/StrategyTracker.tsx
git commit -m "feat: integrate RebalanceModal into StrategyTracker replacing Modal.confirm"
```

---

### Task 6: 端到端验证

- [ ] **Step 1: 启动前后端**

```bash
# Terminal 1: Backend
cd backend && source venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

- [ ] **Step 2: 功能验证清单**

在浏览器中访问 `http://localhost:5173/strategy-tracker`，验证：

1. ☐ 点击「执行调仓」按钮弹出新弹窗（不再是 Modal.confirm）
2. ☐ 弹窗正确显示卖出列表（当前持仓不在 Top 3 的）和买入列表（Top 3 不在持仓的）
3. ☐ 保持列表正确显示为 Tag
4. ☐ 勾选/取消卖出项后资金数据实时更新
5. ☐ 勾选/取消买入项后资金数据实时更新
6. ☐ 修改卖出数量后资金数据实时更新
7. ☐ 修改买入数量后资金数据实时更新
8. ☐ 关闭「执行卖出」开关 → 卖出区域禁用
9. ☐ 关闭「执行买入」开关 → 买入区域禁用
10. ☐ 资金充足 → 显示绿色剩余金额
11. ☐ 资金不足 → 显示红色缺口 + 自动追加提示
12. ☐ 点击确认 → 执行成功 → 弹窗关闭 → 数据刷新
13. ☐ 消息提示正确显示买卖数量和追加本金

- [ ] **Step 3: 如有问题，修复后提交 fix commit**

---

### 自审 checklist

- [x] Spec coverage: 每个 spec 需求（逐只勾选、手数输入、盘中执行、最新收盘价、资金追加）都有对应 task
- [x] No placeholders: 所有步骤都是完整代码，无 TBD/TODO
- [x] Type consistency: SellItem/BuyItem 的 ts_code + shares 字段在前端和后端一致；ExecuteSummary 的 `additional_capital_added` 前后端统一
- [x] 保留 `_find_nearest_trading_day`（`_compute_holdings` 仍在使用）
- [x] 只删除 `_find_next_trading_day`（无其他引用）
