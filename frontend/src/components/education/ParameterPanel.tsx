import React from 'react';
import { Button, Slider } from 'antd';
import { UndoOutlined } from '@ant-design/icons';

export interface MACDParams {
  fast: number;
  slow: number;
  signal: number;
}

interface ParameterPanelProps {
  params: MACDParams;
  defaultParams: MACDParams;
  highlightParam: string | null; // 'fast' | 'slow' | 'signal' — highlights which slider the user should try
  onChange: (params: MACDParams) => void;
}

const ParameterPanel: React.FC<ParameterPanelProps> = ({
  params,
  defaultParams,
  highlightParam,
  onChange,
}) => {
  const handleChange = (key: keyof MACDParams, value: number) => {
    onChange({ ...params, [key]: value });
  };

  const handleReset = () => {
    onChange({ ...defaultParams });
  };

  const sliderStyle = (key: string): React.CSSProperties => ({
    border: highlightParam === key ? '2px solid #1677ff' : '2px solid transparent',
    borderRadius: 6,
    padding: '4px 8px',
    transition: 'border 0.3s',
  });

  return (
    <div style={{ padding: '12px 0' }}>
      <h4 style={{ marginBottom: 16 }}>🎚️ 参数调节</h4>
      <div style={sliderStyle('fast')}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>快线 EMA</span>
          <strong>{params.fast}</strong>
        </div>
        <Slider
          min={2}
          max={50}
          value={params.fast}
          onChange={(v) => handleChange('fast', v)}
        />
      </div>
      <div style={{ ...sliderStyle('slow'), marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>慢线 EMA</span>
          <strong>{params.slow}</strong>
        </div>
        <Slider
          min={5}
          max={100}
          value={params.slow}
          onChange={(v) => handleChange('slow', v)}
        />
      </div>
      <div style={{ ...sliderStyle('signal'), marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>信号线 EMA</span>
          <strong>{params.signal}</strong>
        </div>
        <Slider
          min={2}
          max={30}
          value={params.signal}
          onChange={(v) => handleChange('signal', v)}
        />
      </div>
      <Button
        icon={<UndoOutlined />}
        onClick={handleReset}
        block
        style={{ marginTop: 16 }}
      >
        恢复默认 ({defaultParams.fast}, {defaultParams.slow}, {defaultParams.signal})
      </Button>
    </div>
  );
};

export default ParameterPanel;
