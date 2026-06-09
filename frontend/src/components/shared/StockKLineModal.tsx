import { useEffect, useState } from 'react';
import { Modal, Alert } from 'antd';
import { useKLineData } from '@/hooks/useKLineData';
import KLineChart from '@/components/charts/KLineChart';
import { stockService } from '@/services/stockService';
import type { ValuationData } from '@/types/stock';

interface StockKLineModalProps {
  ts_code: string;
  name?: string;
  open: boolean;
  onClose: () => void;
  days?: number;
  buyDate?: string;
  buyPrice?: number;
  sellDate?: string;
  sellPrice?: number;
}

export default function StockKLineModal({
  ts_code,
  name,
  open,
  onClose,
  days = 504,
  buyDate,
  buyPrice,
  sellDate,
  sellPrice,
}: StockKLineModalProps) {
  const { data, loading, error } = useKLineData(open ? ts_code : null, days);
  const [valuation, setValuation] = useState<ValuationData | null>(null);

  useEffect(() => {
    if (open && ts_code) {
      stockService.getValuation(ts_code).then(setValuation).catch(() => setValuation(null));
    } else {
      setValuation(null);
    }
  }, [open, ts_code]);

  // ts_code 格式为 "300658.SZ" → 转换为 "SZ300658"
  const xueqiuCode = ts_code ? ts_code.replace(/^(\d+)\.(SH|SZ|BJ)$/, '$2$1') : ts_code;
  const xueqiuUrl = xueqiuCode ? `https://xueqiu.com/S/${xueqiuCode}` : '#';

  const daysLabel = days >= 504 ? '近两年' : days >= 365 ? '近一年' : `近${days}天`;
  const stockLabel = name || ts_code;
  const title = (
    <span>
      <a href={xueqiuUrl} target="_blank" rel="noopener noreferrer">{stockLabel}</a>
      <span style={{ fontWeight: 400 }}>（{ts_code}）— {daysLabel} K 线图</span>
    </span>
  );

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      width={960}
      footer={null}
      destroyOnHidden
    >
      {error && <Alert type="error" message={error} style={{ marginBottom: 16 }} />}
      <KLineChart
        data={data?.items ?? []}
        loading={loading}
        height={520}
        buyMarker={buyDate && buyPrice != null ? { date: buyDate, price: buyPrice } : undefined}
        sellMarker={sellDate && sellPrice != null ? { date: sellDate, price: sellPrice } : undefined}
        pb={valuation?.pb ?? null}
        pe={valuation?.pe_ttm ?? null}
        initialZoomStart={75}
        initialZoomEnd={100}
      />
    </Modal>
  );
}
