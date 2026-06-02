import pytest
from datetime import date
from app.models.trade_sim import TradeSimReport


class TestTradeSimModel:
    def test_trade_sim_report_creation(self):
        """测试 TradeSimReport 实例创建"""
        report = TradeSimReport(
            strategy_id=1,
            user_id=1,
            cutoff_date=date(2026, 1, 5),
            config='{"total_amount": 100000, "top_n": 5, "max_hold_days": 60}',
            status="pending",
        )
        assert report.strategy_id == 1
        assert report.cutoff_date == date(2026, 1, 5)
        assert report.status == "pending"
        assert report.trades == "[]"
        assert report.summary == "{}"

    def test_trade_sim_report_defaults(self):
        """测试默认值"""
        report = TradeSimReport(
            strategy_id=1,
            user_id=1,
            cutoff_date=date(2026, 1, 5),
        )
        assert report.status == "pending"
        assert report.config == "{}"
