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
  days = 365,
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

  const daysLabel = days >= 365 ? '近一年' : `近${days}天`;
  const title = name
    ? `${name}（${ts_code}）— ${daysLabel} K 线图`
    : `${ts_code} — ${daysLabel} K 线图`;

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
      />
    </Modal>
  );
}
