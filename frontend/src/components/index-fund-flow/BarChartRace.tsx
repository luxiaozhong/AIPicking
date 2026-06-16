import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { Button, Space, Tag, Typography, Spin, Empty, Segmented } from 'antd';
import { CaretRightOutlined, PauseOutlined, ReloadOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { SnapshotData, SnapshotFrame } from '@/services/indexFundFlowService';

const { Text } = Typography;
const RED_COLOR = '#cf1322';
const GREEN_COLOR = '#3f8600';

type RaceMode = 'today' | '5d';

interface Props {
  snapshots: SnapshotData | null;
  loading: boolean;
  isPolling: boolean;
  onTogglePolling: () => void;
  onStockClick?: (tsCode: string) => void;
}

function fmtYi(v: number): string {
  const sign = v >= 0 ? '+' : '';
  return sign + (v / 1e8).toFixed(2) + '亿';
}

interface RaceStock {
  ts_code: string;
  stock_name: string;
  value: number;       // total bar value (今日=main_net_flow, 5日=main_net_flow_5d)
  prev4d?: number;     // 5d mode: 前4日累计 = 5d_total - today
  today?: number;      // 5d mode: 今日净流入
}

interface RaceFrame {
  time: string;
  stocks: RaceStock[];
}

const RACE_MODE_OPTIONS: { label: string; value: RaceMode }[] = [
  { label: '今日', value: 'today' },
  { label: '5日累计', value: '5d' },
];

const BarChartRace: React.FC<Props> = ({ snapshots, loading, isPolling, onTogglePolling, onStockClick }) => {
  const [currentFrame, setCurrentFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [raceMode, setRaceMode] = useState<RaceMode>('today');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const chartRef = useRef<any>(null);
  const currentStocksRef = useRef<RaceStock[]>([]);

  // Pre-process frames: sort each frame by the selected mode's field, take top 15
  const frames: RaceFrame[] = useMemo(() => {
    if (!snapshots || !snapshots.snapshots || snapshots.snapshots.length === 0) return [];
    const is5d = raceMode === '5d';
    return snapshots.snapshots.map((f: SnapshotFrame) => ({
      time: formatSnapshotTime(f.snapshot_time),
      stocks: [...f.stocks]
        .sort((a, b) => {
          const av = is5d ? a.main_net_flow_5d : a.main_net_flow;
          const bv = is5d ? b.main_net_flow_5d : b.main_net_flow;
          return bv - av;
        })
        .slice(0, 15)
        .map((s) => ({
          ts_code: s.ts_code,
          stock_name: s.stock_name,
          value: is5d ? s.main_net_flow_5d : s.main_net_flow,
          prev4d: is5d ? s.main_net_flow_5d - s.main_net_flow : undefined,
          today: is5d ? s.main_net_flow : undefined,
        })),
    }));
  }, [snapshots, raceMode]);

  const totalFrames = frames.length;
  const modeLabel = raceMode === '5d' ? '5日累计主力净流入' : '今日主力净流入';

  // Reset frame index on mode change
  useEffect(() => {
    stopPlayback();
    setCurrentFrame(0);
  }, [raceMode]);

  // Stop playback when we run past last frame
  useEffect(() => {
    if (currentFrame >= totalFrames) {
      stopPlayback();
    }
  }, [currentFrame, totalFrames]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const stopPlayback = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setPlaying(false);
  }, []);

  const startPlayback = useCallback(() => {
    if (frames.length === 0) return;
    stopPlayback();

    // If at end, restart from beginning
    if (currentFrame >= totalFrames - 1) {
      setCurrentFrame(0);
    }

    timerRef.current = setInterval(() => {
      setCurrentFrame((prev) => {
        const next = prev + 1;
        if (next >= totalFrames) {
          stopPlayback();
          return prev;
        }
        return next;
      });
    }, 800);
    setPlaying(true);
  }, [frames.length, currentFrame, totalFrames, stopPlayback]);

  const handleTogglePlay = () => {
    if (playing) {
      stopPlayback();
    } else {
      startPlayback();
    }
  };

  const handleReset = () => {
    stopPlayback();
    setCurrentFrame(0);
  };

  const option = useMemo(() => {
    if (frames.length === 0 || !frames[currentFrame]) return {};

    const frame = frames[currentFrame];
    const is5d = raceMode === '5d';
    // #1 ranked stock at the top
    const stocks = [...frame.stocks];
            currentStocksRef.current = stocks;

    const series: any[] = is5d
      ? [
          {
            name: '前4日',
            type: 'bar',
            stack: 'total',
            data: stocks.map((s) => ({
              value: s.prev4d ?? 0,
              itemStyle: {
                color: (s.prev4d ?? 0) >= 0 ? '#f5bcbf' : '#d2f0a9',
                borderRadius: 0,
              },
            })),
            animationDuration: 400,
            animationDurationUpdate: 700,
            animationEasing: 'linear' as const,
            animationEasingUpdate: 'linear' as const,
          },
          {
            name: '今日',
            type: 'bar',
            stack: 'total',
            data: stocks.map((s) => ({
              value: s.today ?? 0,
              itemStyle: {
                color: (s.today ?? 0) >= 0 ? RED_COLOR : GREEN_COLOR,
                borderRadius: [0, 4, 4, 0],
              },
            })),
            label: {
              show: true,
              position: 'right',
              formatter: (params: any) => {
                const s = stocks[params.dataIndex];
                return s ? fmtYi(s.value) : '';
              },
              color: '#555',
            },
            animationDuration: 400,
            animationDurationUpdate: 700,
            animationEasing: 'linear' as const,
            animationEasingUpdate: 'linear' as const,
          },
        ]
      : [
          {
            type: 'bar',
            data: stocks.map((s) => ({
              value: s.value,
              itemStyle: {
                color: s.value >= 0 ? RED_COLOR : GREEN_COLOR,
                borderRadius: [0, 4, 4, 0],
              },
            })),
            label: {
              show: true,
              position: 'right',
              formatter: (params: any) => fmtYi(params.value),
              color: '#555',
            },
            animationDuration: 400,
            animationDurationUpdate: 700,
            animationEasing: 'linear' as const,
            animationEasingUpdate: 'linear' as const,
          },
        ];

    return {
      title: {
        text: `${frame.time} ｜ ${modeLabel}`,
        left: 'center',
        textStyle: { fontSize: 16, fontWeight: 'bold' },
      },
      legend: is5d ? { bottom: 0, textStyle: { fontSize: 11 } } : undefined,
      grid: { left: 120, right: 80, top: 55, bottom: is5d ? 35 : 30 },
      xAxis: {
        type: 'value',
        axisLabel: {
          formatter: (v: number) => (v / 1e8).toFixed(1) + '亿',
        },
        splitLine: { lineStyle: { type: 'dashed' } },
      },
      yAxis: {
        type: 'category',
        data: stocks.map((s) => s.stock_name || s.ts_code),
        axisTick: { show: false },
        axisLine: { show: false },
        inverse: true,
        animationDuration: 300,
        animationDurationUpdate: 300,
      },
      series,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: any) => {
          if (!Array.isArray(params) || params.length === 0) return '';
          const name = params[0].name;
          let html = `<strong>${name}</strong><br/>`;
          if (is5d && params.length >= 2) {
            const prev4d = params.find((p: any) => p.seriesName === '前4日')?.value ?? 0;
            const today = params.find((p: any) => p.seriesName === '今日')?.value ?? 0;
            const total = prev4d + today;
            html += `前4日累计: ${fmtYi(prev4d)}<br/>`;
            html += `今日流入: ${fmtYi(today)}<br/>`;
            html += `<b>5日合计: ${fmtYi(total)}</b>`;
          } else {
            html += `${modeLabel}: ${fmtYi(params[0].value)}`;
          }
          return html;
        },
      },
      animation: true,
    };
  }, [frames, currentFrame, modeLabel, raceMode]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 500 }}>
        <Spin tip="加载快照数据..." />
      </div>
    );
  }

  if (frames.length === 0) {
    return <Empty description="暂无盘中快照数据（需等待同步脚本写入）" />;
  }

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
        <Space>
          <Button
            type="primary"
            icon={playing ? <PauseOutlined /> : <CaretRightOutlined />}
            onClick={handleTogglePlay}
          >
            {playing ? '暂停' : '播放'}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={handleReset}>
            重置
          </Button>
          <Segmented
            options={RACE_MODE_OPTIONS}
            value={raceMode}
            onChange={(v) => setRaceMode(v as RaceMode)}
            size="small"
          />
        </Space>
        <Space>
          <Text type="secondary">
            Frame {currentFrame + 1}/{totalFrames}
          </Text>
          {isPolling && (
            <Button size="small" danger onClick={onTogglePolling}>
              🔴 停止刷新
            </Button>
          )}
          {!isPolling && (
            <Button size="small" onClick={onTogglePolling}>
              开启自动刷新
            </Button>
          )}
        </Space>
      </div>
      <ReactECharts
        ref={chartRef}
        option={option}
        style={{ height: 500, width: '100%' }}
        notMerge
        onEvents={{
          click: (params: any) => {
            const stock = currentStocksRef.current[params.dataIndex];
            if (stock?.ts_code) onStockClick?.(stock.ts_code);
          },
        }}
      />
    </div>
  );
};

function formatSnapshotTime(iso: string): string {
  try {
    const d = new Date(iso);
    const h = d.getHours().toString().padStart(2, '0');
    const m = d.getMinutes().toString().padStart(2, '0');
    const s = d.getSeconds().toString().padStart(2, '0');
    return `${h}:${m}:${s}`;
  } catch {
    const match = iso.match(/T?(\d{2}:\d{2}:\d{2})/);
    return match ? match[1] : iso;
  }
}

export default BarChartRace;
