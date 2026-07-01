"""
momentum_rotation — 量价动量轮动策略

策略逻辑：
1. 多指数成分股池构建（去重）
2. 价格动量得分：短周期 + 长周期加权收益率
3. 成交量得分：量比（短期均量 / 长期均量）
4. 全市场 Z-score 标准化后加权合成
5. 按得分降序，返回 top N

参数（通过 config 传入）：
- index_codes: 逗号分隔的指数代码，如 "399006,000300"，空字符串则走板块过滤
- N: 推荐数量，默认 10
- mom_fast: 短周期动量窗口（交易日），默认 20
- mom_slow: 长周期动量窗口（交易日），默认 60
- mom_fast_weight: 短周期权重，默认 0.6
- vol_short: 短期均量窗口（交易日），默认 5
- vol_long: 长期均量窗口（交易日），默认 20
- volume_weight: 成交量在总分中的权重，默认 0.4

数据依赖：
REQUIRED_DATA = ["index_constituents"]
"""

import numpy as np

REQUIRED_DATA = ["index_constituents"]

# ── 默认参数 ──────────────────────────────────────────────────
DEFAULT_INDEX_CODES = ""
DEFAULT_N = 10
DEFAULT_MOM_FAST = 20
DEFAULT_MOM_SLOW = 60
DEFAULT_MOM_FAST_WEIGHT = 0.6
DEFAULT_VOL_SHORT = 5
DEFAULT_VOL_LONG = 20
DEFAULT_VOLUME_WEIGHT = 0.4


def run(data):
    """入口函数，回测引擎调用

    data 结构（由 BacktestEngine 注入）：
        - cutoff_date: str  YYYYMMDD
        - stocks:       [{ts_code, symbol, name, ...}]
        - daily:        {ts_code: [{trade_date, open, high, low, close, vol, ...}]}
        - index_constituents: [{index_code, ts_code, stock_name, ...}]
        - config:       {index_codes, N, mom_fast, ...}
    """
    config = data.get("config", {})

    # ── 解析参数 ──────────────────────────────────────────
    idx_str = str(config.get("index_codes", DEFAULT_INDEX_CODES)).strip()
    N = int(config.get("N", DEFAULT_N))
    mom_fast = int(config.get("mom_fast", DEFAULT_MOM_FAST))
    mom_slow = int(config.get("mom_slow", DEFAULT_MOM_SLOW))
    mom_fast_weight = float(config.get("mom_fast_weight", DEFAULT_MOM_FAST_WEIGHT))
    vol_short = int(config.get("vol_short", DEFAULT_VOL_SHORT))
    vol_long = int(config.get("vol_long", DEFAULT_VOL_LONG))
    volume_weight = float(config.get("volume_weight", DEFAULT_VOLUME_WEIGHT))

    min_bars = max(mom_slow, vol_long)
    daily = data.get("daily", {})

    # ── 1. 构建股票池 ─────────────────────────────────────

    # 预计算 name_map（无论哪种股票池都需要）
    name_map = {}
    for s in data.get("stocks", []):
        name_map[s["ts_code"]] = s.get("name", s["ts_code"])

    index_codes = [c.strip() for c in idx_str.split(",") if c.strip()] if idx_str else []

    if index_codes:
        # 从指数成分股构建股票池，多指数取并集去重
        constituents = data.get("index_constituents", [])
        # 第一步：收集目标指数的所有 raw_code（symbol，前 6 位）
        seen_raw = set()
        pool_ts_codes = []
        for c in constituents:
            if c.get("index_code") in index_codes:
                ts_code = c.get("ts_code", "")
                raw_code = ts_code[:6]
                if raw_code not in seen_raw:
                    seen_raw.add(raw_code)
                    pool_ts_codes.append(ts_code)
        stock_pool = pool_ts_codes
    else:
        # 空 index_codes：使用引擎过滤后的全量 stocks
        stock_pool = [s["ts_code"] for s in data.get("stocks", [])]

    # ── 2. 逐股计算原始得分 ───────────────────────────────

    results = []
    for ts_code in stock_pool:
        if ts_code not in daily:
            continue

        rows = daily[ts_code]
        if len(rows) < min_bars:
            continue

        # 取最后 min_bars 条（已按 trade_date 升序）
        window = rows[-min_bars:]
        closes = np.array([r["close"] for r in window], dtype=float)
        vols = np.array([r.get("vol") or r.get("volume") or 0 for r in window], dtype=float)

        # 动量原始分
        if closes[-mom_fast] != 0:
            ret_fast = (closes[-1] / closes[-mom_fast] - 1) * 100
        else:
            ret_fast = 0.0

        if closes[-mom_slow] != 0:
            ret_slow = (closes[-1] / closes[-mom_slow] - 1) * 100
        else:
            ret_slow = 0.0

        mom_raw = mom_fast_weight * ret_fast + (1 - mom_fast_weight) * ret_slow

        # 量比
        avg_short = np.mean(vols[-vol_short:])
        avg_long = np.mean(vols[-vol_long:])
        vol_ratio = avg_short / avg_long if avg_long > 0 else 1.0

        results.append({
            "ts_code": ts_code,
            "mom_raw": mom_raw,
            "vol_ratio": vol_ratio,
        })

    if not results:
        return []

    # ── 3. Z-score 标准化 ──────────────────────────────────

    mom_arr = np.array([r["mom_raw"] for r in results])
    vol_arr = np.array([r["vol_ratio"] for r in results])

    mom_mean = np.mean(mom_arr)
    mom_std = np.std(mom_arr)
    vol_mean = np.mean(vol_arr)
    vol_std = np.std(vol_arr)

    for r in results:
        mom_z = (r["mom_raw"] - mom_mean) / mom_std if mom_std > 0 else 0.0
        vol_z = (r["vol_ratio"] - vol_mean) / vol_std if vol_std > 0 else 0.0
        r["score"] = round((1 - volume_weight) * float(mom_z) + volume_weight * float(vol_z), 4)

    # ── 4. 排序输出 ────────────────────────────────────────

    results.sort(key=lambda x: x["score"], reverse=True)

    recommendations = []
    for r in results[:N]:
        recommendations.append({
            "ts_code": r["ts_code"],
            "name": name_map.get(r["ts_code"], r["ts_code"]),
            "score": r["score"],
            "signal": _describe(r["mom_raw"], r["vol_ratio"], index_codes),
        })

    return recommendations


def _describe(mom_raw: float, vol_ratio: float, index_codes: list) -> str:
    """生成信号描述"""
    mom_dir = "+" if mom_raw >= 0 else ""
    parts = [f"动量{mom_dir}{mom_raw:.1f}%", f"量比{vol_ratio:.2f}"]
    if index_codes:
        parts.append(f"指数{','.join(index_codes)}")
    return " | ".join(parts)
