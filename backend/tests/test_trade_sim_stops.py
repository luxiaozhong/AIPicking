# backend/tests/test_trade_sim_stops.py
import pytest
from app.factors.trade_sim_stops import (
    StopFactorRegistry,
    TriggerResult,
    _check_stop_prev_low,
    _check_take_profit_pct,
    _check_stop_ma10_cross,
)


def make_daily(closes, adj_closes=None):
    """构建日线数据"""
    if adj_closes is None:
        adj_closes = closes
    return [
        {"trade_date": f"2026-01-{i+1:02d}", "open": c, "high": c, "low": c,
         "close": c, "adj_close": ac}
        for i, (c, ac) in enumerate(zip(closes, adj_closes))
    ]


class TestStopPrevLow:
    def test_not_triggered_when_above(self):
        """当前价高于前低，不触发"""
        df = make_daily([10.0] * 19 + [10.5])
        result = _check_stop_prev_low(df, {}, {"ref_days": 20})
        assert result is None

    def test_triggered_when_below(self):
        """当前价低于20日前，触发"""
        df = make_daily([12.0] + [10.0] * 18 + [9.5])
        result = _check_stop_prev_low(df, {}, {"ref_days": 20})
        assert result is not None
        assert "破前低止损" in result.reason

    def test_not_enough_data(self):
        """数据不足，不触发"""
        df = make_daily([10.0] * 10)
        result = _check_stop_prev_low(df, {}, {"ref_days": 20})
        assert result is None


class TestTakeProfit:
    def test_not_triggered_below_target(self):
        """涨幅不足，不触发"""
        df = make_daily([10.0, 10.3])
        result = _check_take_profit_pct(df, {"buy_price": 10.0}, {"profit_pct": 5.0})
        assert result is None

    def test_triggered_at_target(self):
        """涨幅达到目标，触发"""
        df = make_daily([10.0, 10.50])
        result = _check_take_profit_pct(df, {"buy_price": 10.0}, {"profit_pct": 5.0})
        assert result is not None
        assert "止盈" in result.reason


class TestStopMA10Cross:
    def test_not_triggered_without_consecutive(self):
        """不连续跌破，不触发（中间回升）"""
        prices = [10.0] * 10 + [9.0, 10.5, 9.0]  # 跌、回升、又跌，不连续
        df = make_daily(prices)
        result = _check_stop_ma10_cross(df, {}, {"coefficient": 0.93, "buffer_days": 2})
        assert result is None

    def test_triggered_consecutive(self):
        """连续跌破，触发"""
        prices = [10.0] * 11 + [9.0, 9.0]
        df = make_daily(prices)
        result = _check_stop_ma10_cross(df, {}, {"coefficient": 0.93, "buffer_days": 2})
        assert result is not None
        assert "MA10" in result.reason


class TestStopFactorRegistry:
    def test_register_and_retrieve(self):
        """注册和获取因子"""
        factors = StopFactorRegistry.get_all()
        assert "stop_prev_low" in factors
        assert "stop_ma10_cross" in factors
        assert "take_profit_pct" in factors
        assert len(factors) == 3

    def test_get_check_fn(self):
        """获取检查函数"""
        fn = StopFactorRegistry.get_check_fn("take_profit_pct")
        assert fn is not None
        assert callable(fn)

    def test_unknown_factor_raises(self):
        """未知因子抛出异常"""
        with pytest.raises(ValueError, match="未知止损止盈因子"):
            StopFactorRegistry.get_check_fn("unknown")
