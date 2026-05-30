import React from 'react';
import { Button } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import type { CaseStep } from '@/services/educationService';

interface StepNavigatorProps {
  steps: CaseStep[];
  currentStep: number;
  onStepChange: (step: number) => void;
}

const StepNavigator: React.FC<StepNavigatorProps> = ({ steps, currentStep, onStepChange }) => {
  if (!steps || steps.length === 0) return null;

  const current = steps.find((s) => s.step === currentStep) || steps[0];

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 16px',
        background: '#fafafa',
        borderRadius: 8,
        marginTop: 12,
      }}
    >
      <span style={{ fontWeight: 'bold', fontSize: 13, whiteSpace: 'nowrap' }}>📍 学习步骤</span>
      <div style={{ display: 'flex', gap: 4 }}>
        {steps.map((s) => (
          <div
            key={s.step}
            onClick={() => onStepChange(s.step)}
            style={{
              width: 26,
              height: 26,
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 12,
              fontWeight: 'bold',
              cursor: 'pointer',
              color: s.step <= currentStep ? '#fff' : '#999',
              background:
                s.step === currentStep
                  ? '#1677ff'
                  : s.step < currentStep
                  ? '#91caff'
                  : '#f0f0f0',
              transition: 'all 0.2s',
            }}
          >
            {s.step}
          </div>
        ))}
      </div>
      <span style={{ flex: 1, fontSize: 12, color: '#333' }}>
        {current.title}
      </span>
      <Button
        size="small"
        icon={<LeftOutlined />}
        disabled={currentStep <= 1}
        onClick={() => onStepChange(currentStep - 1)}
      />
      <Button
        size="small"
        icon={<RightOutlined />}
        disabled={currentStep >= steps.length}
        onClick={() => onStepChange(currentStep + 1)}
      />
    </div>
  );
};

export default StepNavigator;
