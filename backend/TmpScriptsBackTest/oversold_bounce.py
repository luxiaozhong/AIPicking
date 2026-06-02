"""科技股超跌反弹策略：捕捉放量急跌→缩量止跌→放量反弹的三阶段信号链"""
from datetime import date, timedelta

from sqlalchemy import and_

from database import SessionLocal
from models import Stock, DailyIndicator, DailyPrice
from strategy.base import BaseStrategy, SignalResult
from strategy.registry import register


@register
class OversoldBounceStrategy(BaseStrategy):
    name = "oversold_bounce"
    description = "科技股超跌反弹策略：三阶段信号链捕捉放量急跌后的止跌反弹。仅限创业板+科创板。条件全满足才出信号，按换手率降序排列"
    default_config = {
        "drawdown_pct": 15.0,        # 回撤幅度 %
        "lookback_days": 20,         # 找高点回溯天数（交易日）
        "panic_vol_ratio": 2.0,      # 恐慌放量：量 > 20日均量 × N
        "shrink_vol_ratio": 0.6,     # 缩量标准：量 < 20日均量 × N
        "bounce_vol_ratio": 1.2,     # 反弹放量：买入日量 > 止跌日量 × N
        "close_upper_ratio": 0.0,    # 收盘在振幅上半区：0=不检查
        "ma20_deviation": 5.0,       # MA20偏离度 %
        "low_tolerance": 0.04,       # 止跌日最低价容差
        "stabilize_window": 3,       # 止跌日搜索窗口
        "min_list_days": 60,         # 最低上市天数
        # 大盘择时
        "market_timing": True,        # 是否启用大盘择时
        "market_index": "399006",     # 参考指数（创业板指）
        "market_ma20_below": 1.5,     # 指数收盘需低于MA20至少N%才算超跌市
    }
    param_schema = {
        "drawdown_pct": {"label": "回撤幅度(%)", "hint": "20日内从高点回撤≥N%", "min": 5.0, "max": 40.0, "step": 1.0, "type": "float"},
        "lookback_days": {"label": "回溯天数", "hint": "找高点+恐慌量的窗口", "min": 10, "max": 40, "step": 5, "type": "int"},
        "panic_vol_ratio": {"label": "恐慌放量倍数", "hint": "某日量>20日均量×N", "min": 1.5, "max": 5.0, "step": 0.5, "type": "float"},
        "shrink_vol_ratio": {"label": "缩量比例", "hint": "止跌日量<20日均量×N", "min": 0.2, "max": 0.8, "step": 0.1, "type": "float"},
        "bounce_vol_ratio": {"label": "反弹放量倍数", "hint": "买入日量>止跌日量×N", "min": 1.0, "max": 3.0, "step": 0.1, "type": "float"},
        "close_upper_ratio": {"label": "收盘强势比例", "hint": "0=不检查", "min": 0.0, "max": 0.9, "step": 0.05, "type": "float"},
        "ma20_deviation": {"label": "MA20偏离(%)", "hint": "收盘价低于MA20超过N%", "min": 3.0, "max": 20.0, "step": 1.0, "type": "float"},
        "low_tolerance": {"label": "止跌低点容差", "hint": "低点≥前日低×(1-N)", "min": 0.0, "max": 0.05, "step": 0.01, "type": "float"},
        "stabilize_window": {"label": "止跌搜索窗(天)", "hint": "在买入日前N天内找止跌日", "min": 1, "max": 5, "step": 1, "type": "int"},
        "min_list_days": {"label": "最低上市天数", "hint": "排除新股", "min": 30, "max": 250, "step": 10, "type": "int"},
        "market_timing": {"label": "大盘择时", "hint": "创业板指也超跌时才出信号", "min": 0, "max": 1, "step": 1, "type": "int"},
        "market_ma20_below": {"label": "指数低于MA20(%)", "hint": "指数收盘需低于MA20至少N%", "min": 0.0, "max": 10.0, "step": 0.5, "type": "float"},
    }
    output_columns = [
        {"key": "stock_code",   "label": "代码",       "width": 120, "type": "text"},
        {"key": "stock_name",   "label": "名称",       "width": 120, "type": "text"},
        {"key": "score",        "label": "评分",       "width": 80,  "type": "score"},
        {"key": "reason",       "label": "筛选依据",    "minWidth": 300, "type": "reason"},
        {"key": "details.bounce_close", "label": "买入价", "width": 90, "type": "number"},
        {"key": "details.turnover_rate", "label": "换手率", "width": 90, "type": "number"},
        {"key": "details.drawdown_pct",  "label": "回撤%", "width": 80, "type": "change"},
        {"key": "details.shrink_vol_ratio_actual", "label": "缩量比", "width": 80, "type": "number"},
    ]

    def screen(self, target_date: date, stock_pool: list[str] | None = None) -> list[SignalResult]:
        config = self.config
        db = SessionLocal()

        # ── 大盘择时：创业板指也处于超跌状态才启用策略 ──
        if config.get("market_timing", True):
            if not _is_market_oversold(config, target_date):
                db.close()
                return []

        # ── 股票池：创业板 + 科创板 ──
        base_query = db.query(Stock.code, Stock.name, Stock.list_date, Stock.is_st)
        if stock_pool:
            base_query = base_query.filter(Stock.code.in_(stock_pool))
        else:
            base_query = base_query.filter(
                (Stock.code.startswith("300"))
                | (Stock.code.startswith("301"))
                | (Stock.code.startswith("688"))
                | (Stock.code.startswith("689"))
            )
        stocks = base_query.all()

        results = []
        for code, name, list_date, is_st in stocks:
            if is_st:
                continue
            if list_date and (target_date - list_date).days < config["min_list_days"]:
                continue

            # ── 获取数据：回溯窗口 + 额外 30 天用于均线计算 ──
            start = target_date - timedelta(days=config["lookback_days"] + 60)
            rows = (
                db.query(DailyIndicator)
                .filter(
                    and_(
                        DailyIndicator.stock_code == code,
                        DailyIndicator.trade_date >= start,
                        DailyIndicator.trade_date <= target_date,
                    )
                )
                .order_by(DailyIndicator.trade_date.asc())
                .all()
            )
            if len(rows) < config["lookback_days"] + 5:
                continue

            # ── 匹配 DailyPrice ──
            dates_needed = [r.trade_date for r in rows]
            prices = (
                db.query(DailyPrice)
                .filter(
                    and_(
                        DailyPrice.stock_code == code,
                        DailyPrice.trade_date.in_(dates_needed),
                    )
                )
                .all()
            )
            price_map = {
                p.trade_date: (p.close, p.open, p.high, p.low, p.volume, p.turnover_rate)
                for p in prices
            }

            # ── 构建合并数据 ──
            data = []
            for r in rows:
                if r.trade_date in price_map:
                    close, open_, high, low, volume, turnover = price_map[r.trade_date]
                    data.append({
                        "trade_date": r.trade_date,
                        "close": close,
                        "open": open_,
                        "high": high,
                        "low": low,
                        "volume": volume,
                        "turnover_rate": turnover,
                        "ma20": r.ma20,
                        "vol_ma20": r.vol_ma20,
                    })

            valid = [d for d in data if d["close"] is not None and d["volume"] is not None]
            if len(valid) < config["lookback_days"] + 5:
                continue

            # 索引：target_date 在数组末尾
            target_idx = len(valid) - 1
            target_row = valid[target_idx]

            # ── 阶段一：急跌识别（在 target_date 上检查）──
            # 1a. 在 lookback_days 窗口内找最高收盘价
            lookback_start = max(0, target_idx - config["lookback_days"])
            window = valid[lookback_start : target_idx + 1]
            peak_close = max(d["close"] for d in window)

            # 1b. 回撤幅度
            drawdown_pct = (peak_close - target_row["close"]) / peak_close * 100
            if drawdown_pct < config["drawdown_pct"]:
                continue

            # 1c. MA20 偏离：收盘价低于 MA20
            ma20 = target_row.get("ma20")
            if ma20 is None or ma20 <= 0:
                continue
            ma20_dist = (ma20 - target_row["close"]) / ma20 * 100
            if ma20_dist < config["ma20_deviation"]:
                continue

            # 1d. 恐慌放量
            has_panic_vol = any(
                d.get("vol_ma20") and d["vol_ma20"] > 0 and d["volume"] > d["vol_ma20"] * config["panic_vol_ratio"]
                for d in window
            )
            if not has_panic_vol:
                continue

            # ── 阶段二：在 [target_idx - stabilize_window, target_idx - 1] 内找止跌日 ──
            stabilize_idx = None
            search_start = max(0, target_idx - config["stabilize_window"])
            for s in range(target_idx - 1, search_start - 1, -1):
                if s < 1:
                    continue
                sd = valid[s]

                # 2a. 缩量：止跌日量 < 20日均量 × shrink_vol_ratio
                if sd.get("vol_ma20") is None or sd["vol_ma20"] <= 0:
                    continue
                if sd["volume"] >= sd["vol_ma20"] * config["shrink_vol_ratio"]:
                    continue

                # 2b. 缩量递减：止跌日量 < 前日量
                prev1 = valid[s - 1]
                if sd["volume"] >= prev1["volume"]:
                    continue

                # 2c. 不再创新低：止跌日最低 ≥ 前日最低 × (1 - tolerance)
                if sd["low"] < prev1["low"] * (1 - config["low_tolerance"]):
                    continue

                stabilize_idx = s
                break

            if stabilize_idx is None:
                continue

            stabilize_row = valid[stabilize_idx]

            # ── 阶段三：反弹触发（target_date，对比止跌日）──
            # 3a. 放量反弹：买入日量 > 止跌日量 × bounce_vol_ratio
            stab_vol = stabilize_row["volume"]
            if stab_vol <= 0:
                continue
            if target_row["volume"] <= stab_vol * config["bounce_vol_ratio"]:
                continue

            # 3b. 收盘位置（仅当 close_upper_ratio > 0 时检查）
            close_position = 0.5  # default
            if config["close_upper_ratio"] > 0:
                if target_row["high"] <= target_row["low"]:
                    continue
                close_position = (target_row["close"] - target_row["low"]) / (target_row["high"] - target_row["low"])
                if close_position < config["close_upper_ratio"]:
                    continue

            # ── 全部条件通过 ──
            # 构建原因文字
            shrink_vol_ratio_actual = round(stabilize_row["volume"] / stabilize_row["vol_ma20"], 2) if stabilize_row.get("vol_ma20") and stabilize_row["vol_ma20"] > 0 else None
            bounce_vol_ratio_actual = round(target_row["volume"] / stab_vol, 1) if stab_vol > 0 else None

            parts = [
                f"回撤{drawdown_pct:.1f}%",
                f"恐慌放量",
                f"缩量至{shrink_vol_ratio_actual:.2f}x均量",
                f"反弹放量{bounce_vol_ratio_actual:.1f}倍",
            ]
            reason = " → ".join(parts)

            # score 直接使用换手率映射（方便排序）
            turnover = target_row.get("turnover_rate") or 0

            results.append(SignalResult(
                stock_code=code,
                stock_name=name,
                score=round(turnover * 100, 1),  # 换手率 × 100 作为评分
                reason=reason,
                details={
                    "reason": reason,
                    # 阶段一
                    "drawdown_pct": round(drawdown_pct, 2),
                    "peak_close": round(peak_close, 2),
                    "ma20_dist": round(ma20_dist, 2),
                    "has_panic_vol": True,
                    # 阶段二
                    "stabilize_date": stabilize_row["trade_date"].isoformat(),
                    "stabilize_low": round(stabilize_row["low"], 2),
                    "stabilize_close": round(stabilize_row["close"], 2),
                    "shrink_vol_ratio_actual": shrink_vol_ratio_actual,
                    # 阶段三
                    "bounce_close": round(target_row["close"], 2),
                    "bounce_vol_ratio_actual": bounce_vol_ratio_actual,
                    "close_position": round(close_position, 2),
                    # 其他
                    "turnover_rate": round(turnover, 4),
                    "close": round(target_row["close"], 2),
                    "ma20": round(ma20, 2) if ma20 else None,
                    "change_3d": _calc_change(valid, target_idx, 3),
                    "change_5d": _calc_change(valid, target_idx, 5),
                    "change_10d": _calc_change(valid, target_idx, 10),
                },
            ))

        db.close()

        # 按换手率（score）降序排列
        results.sort(key=lambda x: x.score, reverse=True)
        return results


def _is_market_oversold(config: dict, target_date: date) -> bool:
    """检查创业板指（399006）是否处于超跌状态：收盘价低于 MA20 至少 N%"""
    from datetime import timedelta

    index_code = config.get("market_index", "399006")
    threshold = config.get("market_ma20_below", 3.0)

    db = SessionLocal()
    try:
        # 查询指数最近的数据
        row = (
            db.query(DailyIndicator)
            .filter(
                DailyIndicator.stock_code == index_code,
                DailyIndicator.trade_date <= target_date,
            )
            .order_by(DailyIndicator.trade_date.desc())
            .first()
        )
        if row is None:
            # 指数数据不存在，默认通过（不阻止）
            return True

        ma20 = row.ma20
        if ma20 is None or ma20 <= 0:
            return True

        # 还需要收盘价
        from models import DailyPrice
        price = (
            db.query(DailyPrice)
            .filter(
                DailyPrice.stock_code == index_code,
                DailyPrice.trade_date == row.trade_date,
            )
            .first()
        )
        if price is None or price.close is None or price.close <= 0:
            return True

        # 检查：指数收盘价低于 MA20 至少 threshold%
        deviation = (ma20 - price.close) / ma20 * 100
        return deviation >= threshold
    finally:
        db.close()


def _calc_change(data: list[dict], idx: int, days: int) -> float | None:
    """计算 N 日涨跌幅"""
    p = idx - days
    if p < 0:
        return None
    prev_close = data[p].get("close")
    curr_close = data[idx].get("close")
    if prev_close and curr_close and prev_close > 0:
        return round((curr_close - prev_close) / prev_close * 100, 2)
    return None
