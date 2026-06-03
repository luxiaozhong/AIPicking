# backend/app/factors/trade_sim_stops.py
"""止损止盈因子注册表

扩展方式：编写 check_fn 函数 → 调用 StopFactorRegistry.register() 注册。
check_fn(df, position, params) -> TriggerResult | None
  - df: list[dict], 该股从买入日到当前日的日线数据（含 trade_date, open, high, low, close, adj_close）
  - position: dict {buy_price, buy_date, buy_idx}
  - params: dict, 因子参数
  - 返回 TriggerResult 表示触发，返回 None 表示未触发
"""

from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, Any


def _get_price(day: dict, key: str = "adj_close") -> Optional[float]:
    """获取优先复权价，key 为 None 时不回退"""
    v = day.get("adj_close")
    if v is not None:
        return v
    return day.get("close")


@dataclass
class ParamDef:
    name: str
    type: str            # "int" | "float"
    default: Any
    description: str


@dataclass
class TriggerResult:
    reason: str           # 触发描述
    sell_price: Optional[float] = None  # 可选卖出价（默认由引擎决定）


class StopFactorRegistry:
    """止损止盈因子注册表"""

    _factors: Dict[str, dict] = {}

    @classmethod
    def register(cls, id: str, name: str, params: List[ParamDef], check_fn: Callable):
        cls._factors[id] = {
            "name": name,
            "params": params,
            "check": check_fn,
        }

    @classmethod
    def get_all(cls) -> Dict[str, dict]:
        """返回所有已注册因子（供前端展示）"""
        return {
            fid: {"name": f["name"], "params": [p.__dict__ for p in f["params"]]}
            for fid, f in cls._factors.items()
        }

    @classmethod
    def get_check_fn(cls, id: str) -> Callable:
        if id not in cls._factors:
            raise ValueError(f"未知止损止盈因子: {id}")
        return cls._factors[id]["check"]

    @classmethod
    def get_name(cls, id: str) -> str:
        if id not in cls._factors:
            return id
        return cls._factors[id]["name"]


# ========== 内置因子 ==========

def _check_stop_prev_low(df: list, position: dict, params: dict) -> Optional[TriggerResult]:
    """破前低止损：当日收盘价 < 过去 ref_days 个交易日最低收盘价（不含今日）"""
    ref_days = params.get("ref_days", 20)
    if len(df) < ref_days + 1:  # 至少需要 ref_days 天历史 + 今天
        return None

    today = df[-1]
    # 过去 ref_days 天（不含今天），找最低收盘价作为"前低"
    lookback = df[-(ref_days + 1):-1]

    close_price = _get_price(today)
    if close_price is None:
        return None

    ref_low = None
    for day in lookback:
        p = _get_price(day)
        if p is not None:
            if ref_low is None or p < ref_low:
                ref_low = p

    if ref_low is None:
        return None

    if close_price < ref_low:
        return TriggerResult(reason=f"破前低止损（{ref_days}日最低收盘价 {ref_low:.2f}）")
    return None


StopFactorRegistry.register(
    id="stop_prev_low",
    name="破前低止损",
    params=[
        ParamDef(name="ref_days", type="int", default=20, description="前低参考天数"),
    ],
    check_fn=_check_stop_prev_low,
)


def _check_stop_ma10_cross(df: list, position: dict, params: dict) -> Optional[TriggerResult]:
    """MA10跌破止损：连续 buffer_days 天收盘价 < MA10 × coefficient"""
    coefficient = params.get("coefficient", 0.93)
    buffer_days = params.get("buffer_days", 2)

    if len(df) < 9 + buffer_days:  # 至少需要 10 天算 MA10 + 缓冲窗口
        return None

    # 计算最近 buffer_days 天是否都满足条件
    consecutive = 0
    for i in range(len(df) - buffer_days, len(df)):
        day = df[i]
        close_price = _get_price(day)
        if close_price is None:
            continue

        # 计算当天 MA10（基于当天及前 9 天的收盘价）
        start_idx = max(0, i - 9)
        closes = []
        for j in range(start_idx, i + 1):
            c = _get_price(df[j])
            if c is not None:
                closes.append(c)
        if len(closes) < 10:
            continue
        ma10 = sum(closes) / len(closes)

        if close_price < ma10 * coefficient:
            consecutive += 1
        else:
            consecutive = 0  # 缓冲计数重置

    if consecutive >= buffer_days:
        return TriggerResult(
            reason=f"MA10跌破止损（MA10×{coefficient}，连续{buffer_days}天）"
        )
    return None


StopFactorRegistry.register(
    id="stop_ma10_cross",
    name="MA10跌破止损",
    params=[
        ParamDef(name="coefficient", type="float", default=0.93, description="MA10系数"),
        ParamDef(name="buffer_days", type="int", default=2, description="缓冲确认天数"),
    ],
    check_fn=_check_stop_ma10_cross,
)


def _check_take_profit_pct(df: list, position: dict, params: dict) -> Optional[TriggerResult]:
    """固定止盈：涨幅 >= profit_pct%"""
    profit_pct = params.get("profit_pct", 5.0)
    buy_price = position.get("buy_price")
    if buy_price is None or buy_price <= 0:
        return None

    today = df[-1]
    close_price = _get_price(today)
    if close_price is None:
        return None

    return_pct = (close_price - buy_price) / buy_price * 100
    if return_pct >= profit_pct:
        return TriggerResult(reason=f"止盈{profit_pct}%（涨幅 {return_pct:.2f}%）")
    return None


StopFactorRegistry.register(
    id="take_profit_pct",
    name="固定止盈",
    params=[
        ParamDef(name="profit_pct", type="float", default=5.0, description="止盈百分比"),
    ],
    check_fn=_check_take_profit_pct,
)
