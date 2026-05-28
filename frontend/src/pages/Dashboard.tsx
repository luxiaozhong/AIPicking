import { Row, Col, Card, Statistic } from 'antd';
import {
  LineChartOutlined,
  BarChartOutlined,
  ExperimentOutlined,
  TrophyOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import PageHeader from '@/components/shared/PageHeader';
import { useStrategyStore } from '@/stores/strategyStore';
import { useBacktestStore } from '@/stores/backtestStore';

export default function Dashboard() {
  const navigate = useNavigate();
  const { strategies, fetchStrategies } = useStrategyStore();
  const { backtests, fetchBacktests } = useBacktestStore();

  useEffect(() => {
    fetchStrategies({ page: 1, limit: 5 });
    fetchBacktests({ page: 1, limit: 5 });
  }, [fetchStrategies, fetchBacktests]);

  const completed = backtests.filter((b) => b.status === 'completed');
  const avgWinRate =
    completed.length > 0
      ? completed.reduce((sum, b) => sum + (b.summary?.win_rate_15d || 0), 0) / completed.length
      : 0;

  const statCards = [
    {
      title: '策略管理',
      value: strategies.length,
      icon: <LineChartOutlined style={{ fontSize: 32, color: '#1677ff' }} />,
      onClick: () => navigate('/strategies'),
    },
    {
      title: '回测报告',
      value: backtests.length,
      icon: <BarChartOutlined style={{ fontSize: 32, color: '#52c41a' }} />,
      onClick: () => navigate('/backtests'),
    },
    {
      title: '已完成回测',
      value: completed.length,
      icon: <ExperimentOutlined style={{ fontSize: 32, color: '#722ed1' }} />,
      onClick: () => navigate('/backtests?status=completed'),
    },
    {
      title: '15天胜率',
      value: completed.length > 0 ? `${(avgWinRate * 100).toFixed(1)}%` : '—',
      icon: <TrophyOutlined style={{ fontSize: 32, color: '#faad14' }} />,
    },
  ];

  return (
    <>
      <PageHeader title="仪表盘" breadcrumb={[{ title: '仪表盘' }]} />
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {statCards.map((card) => (
          <Col xs={24} sm={12} lg={6} key={card.title}>
            <Card
              hoverable={!!card.onClick}
              onClick={card.onClick}
              style={{ cursor: card.onClick ? 'pointer' : 'default' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Statistic title={card.title} value={card.value} />
                {card.icon}
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="快捷操作">
            <Row gutter={[8, 8]}>
              {[
                { label: '可视化构建策略', path: '/strategies/builder' },
                { label: '上传策略脚本', path: '/strategies/upload' },
                { label: '查看策略列表', path: '/strategies' },
                { label: '查看回测报告', path: '/backtests' },
              ].map((action) => (
                <Col span={12} key={action.path}>
                  <Card
                    size="small"
                    hoverable
                    onClick={() => navigate(action.path)}
                    style={{ textAlign: 'center' }}
                  >
                    {action.label}
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="快速入门">
            <ol style={{ paddingLeft: 20, lineHeight: 2 }}>
              <li>在「策略管理」中创建或上传量化策略</li>
              <li>使用可视化构建器选择因子组合策略</li>
              <li>提交回测任务，验证策略在历史数据上的表现</li>
              <li>查看回测报告，分析推荐股票的后续涨跌</li>
              <li>执行策略获取当前市场推荐</li>
            </ol>
          </Card>
        </Col>
      </Row>
    </>
  );
}
