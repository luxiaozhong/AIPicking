import StrategyRating from './StrategyRating';
import StrategyComments from './StrategyComments';

interface Props {
  strategyId: number;
  isOwner: boolean;
}

export default function StrategyCommunity({ strategyId, isOwner }: Props) {
  return (
    <div>
      <StrategyRating strategyId={strategyId} />
      <div style={{ marginTop: 24 }}>
        <StrategyComments strategyId={strategyId} isOwner={isOwner} />
      </div>
    </div>
  );
}
