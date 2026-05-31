import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import { Row, Col, Card, Statistic, Typography } from 'antd';
import {
  LineChartOutlined,
  BarChartOutlined,
  ExperimentOutlined,
  TrophyOutlined,
  RobotOutlined,
  BuildOutlined,
} from '@ant-design/icons';
import PageHeader from '@/components/shared/PageHeader';
import { useStrategyStore } from '@/stores/strategyStore';
import { useBacktestStore } from '@/stores/backtestStore';

const { Text } = Typography;

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
        <Col span={24}>
          <Card title="快捷操作">
            <Row gutter={[12, 12]}>
              {[
                {
                  icon: <RobotOutlined style={{ fontSize: 24, color: '#1677ff' }} />,
                  title: 'AI 参考选股',
                  description:
                    '以一只好股票的过去某一天为参考，AI 自动找出全市场最相似的标的。辅助你找到启动点信号，并可回测过去任意交易日。',
                  path: '/strategies/ai-builder',
                },
                {
                  icon: <BuildOutlined style={{ fontSize: 24, color: '#52c41a' }} />,
                  title: '可视化构建策略',
                  description:
                    '拖拽因子组合生成买卖信号策略，或用自然语言描述量化特征生成策略。',
                  path: '/strategies/builder',
                },
                {
                  icon: <LineChartOutlined style={{ fontSize: 24, color: '#722ed1' }} />,
                  title: '策略列表',
                  description: '查看、编辑、执行和回测已创建的所有策略。',
                  path: '/strategies',
                },
                {
                  icon: <BarChartOutlined style={{ fontSize: 24, color: '#faad14' }} />,
                  title: '回测报告',
                  description: '查看历史回测结果、收益曲线和胜率分析。',
                  path: '/backtests',
                },
              ].map((action) => (
                <Col xs={24} sm={12} key={action.path}>
                  <Card
                    hoverable
                    onClick={() => navigate(action.path)}
                    style={{ height: '100%' }}
                  >
                    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                      <div style={{ flexShrink: 0, marginTop: 2 }}>{action.icon}</div>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 4 }}>
                          {action.title}
                        </div>
                        <Text type="secondary" style={{ fontSize: 13, lineHeight: 1.6 }}>
                          {action.description}
                        </Text>
                      </div>
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
      </Row>
    </>
  );
}
