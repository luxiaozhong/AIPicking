import React, { useMemo } from 'react';
import { Card, Spin, Empty } from 'antd';
import ReactECharts from 'echarts-for-react';
import 'echarts-wordcloud';
import type { ThemeItem } from '@/services/marketHeatService';

interface Props {
  themes: ThemeItem[];
  loading: boolean;
  onThemeClick: (theme: ThemeItem) => void;
}

const ThemeWordCloud: React.FC<Props> = ({ themes, loading, onThemeClick }) => {
  const option = useMemo(() => {
    if (!themes.length) return {};

    const maxCount = Math.max(...themes.map((t) => t.stock_count), 1);

    return {
      tooltip: {
        formatter: (params: any) => {
          return `${params.name}: ${params.value} 只关联股票`;
        },
      },
      series: [{
        type: 'wordCloud',
        shape: 'circle',
        width: '100%',
        height: '100%',
        sizeRange: [14, 48],
        rotationRange: [-30, 30],
        gridSize: 8,
        layoutAnimation: true,
        textStyle: {
          fontFamily: 'sans-serif',
          fontWeight: 'bold',
          color: () => {
            const colors = ['#1677ff', '#52c41a', '#fa541c', '#722ed1', '#fa8c16', '#13c2c2', '#eb2f96'];
            return colors[Math.floor(Math.random() * colors.length)];
          },
        },
        emphasis: {
          textStyle: { shadowBlur: 10, shadowColor: '#333' },
        },
        data: themes.map((t) => ({
          name: t.theme_name,
          value: t.stock_count,
        })),
      }],
    };
  }, [themes]);

  return (
    <Card title="热门主题">
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spin /></div>
      ) : themes.length === 0 ? (
        <Empty description="暂无数据" />
      ) : (
        <ReactECharts
          option={option}
          style={{ height: 350 }}
          onEvents={{
            click: (params: any) => {
              const theme = themes.find((t) => t.theme_name === params.name);
              if (theme) onThemeClick(theme);
            },
          }}
        />
      )}
    </Card>
  );
};

export default ThemeWordCloud;
