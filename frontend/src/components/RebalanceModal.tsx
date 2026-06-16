import { useState, useMemo, useCallback } from 'react';
import {
  Modal, Switch, Table, InputNumber, Space,
  Typography, Tag, Divider, AutoComplete, Button,
} from 'antd';
import { PlusOutlined, CloseOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import type { Recommendation } from '@/services/strategyTrackerService';
import type { PaperHolding } from '@/services/paperTradeService';
import { stockService } from '@/services/stockService';

const { Text } = Typography;

// ── Types ──

interface SellRow {
  key: string;
  ts_code: string;
  stock_name: string;
  holding_shares: number;
  sell_shares: number;
  checked: boolean;
  isTop3: boolean;  // true = in top3, unchecked by default（keep）
}

interface BuyRow {
  key: string;
  ts_code: string;
  stock_name: string;
  suggested_shares: number;
  buy_shares: number;
  checked: boolean;
  isCustom: boolean;  // true = manually added
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
    buys: { ts_code: string; shares: number; stock_name?: string }[];
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

function generateKey(): string {
  return `custom-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
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
  // Switch toggles
  const [sellEnabled, setSellEnabled] = useState(true);
  const [buyEnabled, setBuyEnabled] = useState(true);

  // Custom buy: search state
  const [buySearchValue, setBuySearchValue] = useState('');
  const [buySearchOptions, setBuySearchOptions] = useState<{ value: string; label: string; item: { ts_code: string; name: string } }[]>([]);
  const [showBuySearch, setShowBuySearch] = useState(false);

  // Build fallback close price map
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

  // Sell rows: ALL holdings, top3 ones default unchecked
  const initialSellRows: SellRow[] = useMemo(() => {
    const topCodes = new Set(top3.map((r) => r.ts_code));
    return holdings.map((h) => {
      const inTop3 = topCodes.has(h.ts_code);
      return {
        key: `sell-${h.ts_code}`,
        ts_code: h.ts_code,
        stock_name: h.stock_name,
        holding_shares: h.shares,
        sell_shares: h.shares,
        checked: !inTop3,  // unchecked if in top3 (keep by default)
        isTop3: inTop3,
      };
    });
  }, [holdings, top3]);

  const [sellData, setSellData] = useState<SellRow[]>([]);

  // Buy rows: top3 NOT in holdings
  const initialBuyRows: BuyRow[] = useMemo(() => {
    const heldCodes = new Set(holdings.map((h) => h.ts_code));
    return top3
      .filter((r) => !heldCodes.has(r.ts_code))
      .map((r) => {
        const close = r.close || fallbackCloseMap[r.ts_code] || 0;
        const budget = totalValue / 3;
        const rawShares = close > 0 ? budget / close : 0;
        const suggested = roundToLot(Math.floor(rawShares), r.ts_code);
        const minLot = getLotSize(r.ts_code);
        return {
          key: `buy-${r.ts_code}`,
          ts_code: r.ts_code,
          stock_name: r.name,
          suggested_shares: Math.max(suggested, minLot),
          buy_shares: Math.max(suggested, minLot),
          checked: true,
          isCustom: false,
        };
      });
  }, [top3, holdings, fallbackCloseMap, totalValue]);

  const [buyData, setBuyData] = useState<BuyRow[]>([]);
  const [customBuyRows, setCustomBuyRows] = useState<BuyRow[]>([]);

  // Merge and deduplicate buy data
  const mergedBuyData = useMemo(() => {
    const customCodes = new Set(customBuyRows.map((r) => r.ts_code));
    // Remove custom codes from initial to avoid duplicates
    const filtered = buyData.filter((r) => !customCodes.has(r.ts_code));
    return [...filtered, ...customBuyRows];
  }, [buyData, customBuyRows]);

  // Reset data when modal opens
  const [prevOpen, setPrevOpen] = useState(false);
  if (open && !prevOpen) {
    setPrevOpen(true);
    setSellData(initialSellRows);
    setBuyData(initialBuyRows);
    setCustomBuyRows([]);
    setShowBuySearch(false);
    setBuySearchValue('');
  } else if (!open && prevOpen) {
    setPrevOpen(false);
  }

  // Stock search handler
  const handleBuySearch = useCallback(async (value: string) => {
    setBuySearchValue(value);
    if (!value || value.length < 1) {
      setBuySearchOptions([]);
      return;
    }
    try {
      const items = await stockService.search(value, 8);
      setBuySearchOptions(
        items.map((item) => ({
          value: `${item.ts_code} ${item.name}`,
          label: `${item.ts_code} ${item.name}`,
          item: { ts_code: item.ts_code, name: item.name },
        }))
      );
    } catch {
      setBuySearchOptions([]);
    }
  }, []);

  // Add custom buy from search
  const handleAddCustomBuy = useCallback((stock: { ts_code: string; name: string }) => {
    // Check if already in buy list
    if (mergedBuyData.some((r) => r.ts_code === stock.ts_code)) return;

    const close = fallbackCloseMap[stock.ts_code] || 0;
    const budget = totalValue / 3;
    const rawShares = close > 0 ? budget / close : 0;
    const suggested = roundToLot(Math.floor(rawShares), stock.ts_code);
    const minLot = getLotSize(stock.ts_code);

    const newRow: BuyRow = {
      key: generateKey(),
      ts_code: stock.ts_code,
      stock_name: stock.name,
      suggested_shares: Math.max(suggested, minLot),
      buy_shares: Math.max(suggested, minLot),
      checked: true,
      isCustom: true,
    };
    setCustomBuyRows((prev) => [...prev, newRow]);
    setShowBuySearch(false);
    setBuySearchValue('');
  }, [mergedBuyData, fallbackCloseMap, totalValue]);

  // Remove custom buy row
  const handleRemoveCustomBuy = useCallback((key: string) => {
    setCustomBuyRows((prev) => prev.filter((r) => r.key !== key));
  }, []);

  // Capital calculation
  const calcResult = useMemo(() => {
    // Sell proceeds
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

    // Buy required
    let buyRequired = 0;
    const checkedBuys = buyEnabled ? mergedBuyData.filter((b) => b.checked) : [];
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
  }, [sellData, mergedBuyData, sellEnabled, buyEnabled, cash, fallbackCloseMap]);

  // Submit handler
  const handleOk = useCallback(async () => {
    const sells = sellEnabled
      ? sellData.filter((s) => s.checked && s.sell_shares > 0).map((s) => ({
          ts_code: s.ts_code,
          shares: s.sell_shares,
        }))
      : [];

    const buys = buyEnabled
      ? mergedBuyData.filter((b) => b.checked && b.buy_shares > 0).map((b) => ({
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
  }, [sellEnabled, buyEnabled, sellData, mergedBuyData, strategyId, recDate, calcResult.shortfall, onSubmit]);

  // Determine if submit should be disabled
  const hasAnySell = sellEnabled && sellData.some((s) => s.checked && s.sell_shares > 0);
  const hasAnyBuy = buyEnabled && mergedBuyData.some((b) => b.checked && b.buy_shares > 0);
  const hasAnyAction = hasAnySell || hasAnyBuy;

  // Count of top3 holdings (keep by default)
  const keepCount = initialSellRows.filter((s) => s.isTop3).length;
  const exitCount = initialSellRows.filter((s) => !s.isTop3).length;

  // Sell table columns
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
    {
      title: '名称', dataIndex: 'stock_name', width: 100,
      render: (v: string, record: SellRow) => (
        <Space size={4}>
          {v}
          {record.isTop3 && (
            <Tag color="blue" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>策略持有</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '代码', dataIndex: 'ts_code', width: 100,
      render: (v: string) => <Text type="secondary">{v}</Text>,
    },
    {
      title: '持仓', dataIndex: 'holding_shares', width: 80, align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '卖出数量', dataIndex: 'sell_shares', width: 130,
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

  // Buy table columns
  const buyColumns: ColumnsType<BuyRow> = [
    {
      title: '勾选', dataIndex: 'checked', width: 50,
      render: (_: unknown, record: BuyRow) => (
        <input
          type="checkbox"
          checked={record.checked}
          disabled={!buyEnabled}
          onChange={(e) => {
            if (record.isCustom) {
              setCustomBuyRows((prev) =>
                prev.map((r) =>
                  r.key === record.key ? { ...r, checked: e.target.checked } : r
                )
              );
            } else {
              setBuyData((prev) =>
                prev.map((r) =>
                  r.key === record.key ? { ...r, checked: e.target.checked } : r
                )
              );
            }
          }}
        />
      ),
    },
    {
      title: '名称', dataIndex: 'stock_name', width: 100,
      render: (v: string, record: BuyRow) => (
        <Space size={4}>
          {v}
          {record.isCustom && (
            <Tag color="orange" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>自定义</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '代码', dataIndex: 'ts_code', width: 100,
      render: (v: string) => <Text type="secondary">{v}</Text>,
    },
    {
      title: '建议', dataIndex: 'suggested_shares', width: 80, align: 'right',
      render: (v: number) => <Text type="secondary">{v.toLocaleString()}</Text>,
    },
    {
      title: '买入数量', dataIndex: 'buy_shares', width: 130,
      render: (_: unknown, record: BuyRow) => (
        <InputNumber
          min={0}
          step={getLotSize(record.ts_code)}
          value={record.buy_shares}
          disabled={!buyEnabled || !record.checked}
          style={{ width: '100%' }}
          onChange={(val) => {
            if (record.isCustom) {
              setCustomBuyRows((prev) =>
                prev.map((r) =>
                  r.key === record.key ? { ...r, buy_shares: val ?? 0 } : r
                )
              );
            } else {
              setBuyData((prev) =>
                prev.map((r) =>
                  r.key === record.key ? { ...r, buy_shares: val ?? 0 } : r
                )
              );
            }
          }}
        />
      ),
    },
    {
      title: '', dataIndex: 'actions', width: 30,
      render: (_: unknown, record: BuyRow) =>
        record.isCustom ? (
          <Button
            type="text" size="small" danger
            icon={<CloseOutlined />}
            onClick={() => handleRemoveCustomBuy(record.key)}
          />
        ) : null,
    },
  ];

  return (
    <Modal
      title="执行调仓"
      open={open}
      width={740}
      confirmLoading={loading}
      onOk={handleOk}
      onCancel={onClose}
      okText="确认执行"
      cancelText="取消"
      okButtonProps={{ disabled: !hasAnyAction }}
      destroyOnClose
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {/* Top info */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">
            推荐日：{recDate} ｜ 成交价基准：最新收盘价
          </Text>
        </div>

        <Divider style={{ margin: 0 }} />

        {/* Toggle switches */}
        <Space>
          <Text>执行卖出</Text>
          <Switch checked={sellEnabled} onChange={setSellEnabled} size="small" />
          <Text style={{ marginLeft: 24 }}>执行买入</Text>
          <Switch checked={buyEnabled} onChange={setBuyEnabled} size="small" />
        </Space>

        {/* Strategy keep hint */}
        {keepCount > 0 && (
          <div>
            <Text type="secondary">
              💡 策略推荐继续持有 {keepCount} 只（蓝色「策略持有」标签），如需卖出请手动勾选
            </Text>
          </div>
        )}

        {/* Sell section */}
        {initialSellRows.length > 0 && (
          <div>
            <Text strong>📤 卖出（全部 {initialSellRows.length} 只持仓，默认卖出 {exitCount} 只）</Text>
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
        {initialSellRows.length === 0 && (
          <Text type="secondary">📤 无持仓</Text>
        )}

        {/* Buy section */}
        {(initialBuyRows.length > 0 || mergedBuyData.length > 0) && (
          <div>
            <Text strong>📥 买入（{mergedBuyData.length} 只）</Text>
            <Table
              size="small"
              rowKey="key"
              columns={buyColumns}
              dataSource={mergedBuyData}
              pagination={false}
              style={{ marginTop: 4 }}
            />
          </div>
        )}
        {mergedBuyData.length === 0 && buyEnabled && (
          <Text type="secondary">📥 无待买入股票</Text>
        )}

        {/* Add custom buy */}
        {buyEnabled && (
          <div>
            {!showBuySearch ? (
              <Button
                type="dashed" size="small" icon={<PlusOutlined />}
                onClick={() => setShowBuySearch(true)}
              >
                添加买入
              </Button>
            ) : (
              <Space>
                <AutoComplete
                  value={buySearchValue}
                  options={buySearchOptions}
                  onSearch={handleBuySearch}
                  onSelect={(_, option) => handleAddCustomBuy(option.item)}
                  placeholder="输入代码或名称搜索…"
                  style={{ width: 260 }}
                  allowClear
                  onClear={() => { setBuySearchValue(''); setShowBuySearch(false); }}
                />
                <Button size="small" onClick={() => { setShowBuySearch(false); setBuySearchValue(''); }}>
                  取消
                </Button>
              </Space>
            )}
          </div>
        )}

        {/* Capital status bar */}
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
            <div style={{
              display: 'flex', justifyContent: 'space-between',
              borderTop: '1px solid #d9d9d9', paddingTop: 4, marginTop: 4,
            }}>
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
