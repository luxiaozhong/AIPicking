"""
选股条件 & 评分修正 注册表
=========================

双层因子体系的 Tier 2 — 基于横截面数据（板块资金流、龙虎榜、热门股/题材）的
选股预筛选和评分修正。

与 K 线因子不同，这些条件的逻辑在 code_generator 中**内联生成**到策略代码中，
不需要独立的 factor.py 文件和 compute() 函数。

每个条件定义包含：
- meta: 元数据（id / name / category / type / description / params）
- setup:  索引构建代码模板（策略 run() 函数开头执行一次）
- check:  pre_filter 判定代码模板（每只股票 loop 内执行）
- score:  score_modifier 计算代码模板（每只股票 loop 内执行）
"""

from typing import Dict, List, Optional

# ── 板块资金流 工具函数（内联到生成代码中）────────────────────────────
_SF_HELPERS = '''
# ---- 板块资金流辅助 ----
def _sf_build_index(raw_data):
    """构建 sector_flow 查询索引。
    返回:
      sf_index: {("concept"|"industry", sector_name): {trade_date: row}}
      sf_ranking: [(sector_type, sector_name, total_inflow), ...] 按 net_inflow 降序
    """
    sf_index = {}
    sf_totals = {}
    for row in raw_data:
        st = row.get("sector_type", "")
        sn = row.get("sector_name", "")
        td = row.get("trade_date", "")
        net = row.get("net_inflow") or 0
        key = (st, sn)
        if key not in sf_index:
            sf_index[key] = {}
            sf_totals[key] = 0.0
        sf_index[key][td] = row
        sf_totals[key] += net
    sf_ranking = sorted(sf_totals.items(), key=lambda x: x[1], reverse=True)
    return sf_index, sf_ranking


def _sf_stock_sectors(sf_index, stock):
    """查找个股匹配的所有 sector_flow 板块。
    匹配逻辑：
      - sector_type='industry' → 匹配 stocks.industry_l2 / industry_l1
      - sector_type='concept'  → 匹配 stocks.concepts（JSON 数组）
    """
    import json
    matched = []
    ind1 = (stock.get("industry_l1") or "").strip()
    ind2 = (stock.get("industry_l2") or "").strip()
    concepts_str = (stock.get("concepts") or "").strip()
    concepts = []
    if concepts_str:
        try:
            concepts = json.loads(concepts_str)
        except Exception:
            concepts = [c.strip() for c in concepts_str.split(",") if c.strip()]
    for (st, sn), rows in sf_index.items():
        if st == "industry":
            if sn == ind2 or sn == ind1:
                matched.append((st, sn, rows))
        elif st == "concept":
            for c in concepts:
                if sn in c or c in sn:
                    matched.append((st, sn, rows))
                    break
    return matched


def _sf_rank(sf_ranking, sector_name, sector_type="concept"):
    """获取板块在排名列表中的位置 (1-based)，不在列表中返回 999。"""
    for i, (st, sn, _) in enumerate(sf_ranking):
        if st == sector_type and sn == sector_name:
            return i + 1
    return 999
'''

# ── 龙虎榜 工具函数 ────────────────────────────────────────────────
_DT_HELPERS = '''
# ---- 龙虎榜辅助 ----
def _dt_build_index(raw_data, raw_seats):
    """构建龙虎榜查询索引。
    返回:
      dt_index: {stock_code: [(row, [seat_rows])]}
    """
    from collections import defaultdict
    # 按 stock_code + trade_date 分组席位
    seats_by_code_date = defaultdict(list)
    for s in raw_seats:
        seats_by_code_date[(s.get("stock_code",""), s.get("trade_date",""))].append(s)
    dt_index = defaultdict(list)
    for row in raw_data:
        sc = row.get("stock_code", "")
        td = row.get("trade_date", "")
        seat_rows = seats_by_code_date.get((sc, td), [])
        dt_index[sc].append((row, seat_rows))
    return dt_index


def _dt_has_institution(dt_rows, cutoff_date, days):
    """近 days 日内是否有机构席位参与（买入方向）。"""
    from datetime import datetime, timedelta
    cutoff = datetime.strptime(cutoff_date, "%Y%m%d")
    start = cutoff - timedelta(days=days)
    for row, seats in dt_rows:
        td = str(row.get("trade_date", ""))
        if len(td) == 10:
            td = td.replace("-", "")
        try:
            d = datetime.strptime(td, "%Y%m%d")
        except Exception:
            continue
        if d < start or d > cutoff:
            continue
        for seat in seats:
            if seat.get("is_institution") and (seat.get("buy_amt_wan") or 0) > 0:
                return True
    return False


def _dt_net_buy_total(dt_rows, cutoff_date, days):
    """近 days 日内龙虎榜净买入总额（万元）。"""
    from datetime import datetime, timedelta
    cutoff = datetime.strptime(cutoff_date, "%Y%m%d")
    start = cutoff - timedelta(days=days)
    total = 0.0
    for row, seats in dt_rows:
        td = str(row.get("trade_date", ""))
        if len(td) == 10:
            td = td.replace("-", "")
        try:
            d = datetime.strptime(td, "%Y%m%d")
        except Exception:
            continue
        if d < start or d > cutoff:
            continue
        total += row.get("net_buy_wan") or 0
    return total
'''


# ── 条件注册表 ─────────────────────────────────────────────────────

CONDITION_REGISTRY: Dict[str, dict] = {}


def _register(meta: dict):
    CONDITION_REGISTRY[meta["id"]] = meta


def list_conditions(category: Optional[str] = None) -> List[dict]:
    """列出所有条件，可选按分类过滤"""
    conditions = list(CONDITION_REGISTRY.values())
    if category:
        conditions = [c for c in conditions if c["category"] == category]
    return sorted(conditions, key=lambda x: (x["category"], x["name"]))


def get_condition_meta(condition_id: str) -> Optional[dict]:
    return CONDITION_REGISTRY.get(condition_id)


def get_condition_categories() -> List[str]:
    categories = sorted(set(c["category"] for c in CONDITION_REGISTRY.values()))
    return categories


def get_helper_code() -> str:
    """返回所有工具函数的代码（去重后的 setup 代码）"""
    return _SF_HELPERS + _DT_HELPERS + _FIN_HELPERS


# ══════════════════════════════════════════════════════════════════════
#  龙虎榜 条件
# ══════════════════════════════════════════════════════════════════════

_register({
    "id": "dt_on_board",
    "name": "龙虎榜上榜",
    "category": "龙虎榜",
    "type": "pre_filter",
    "description": "近N日曾上龙虎榜的股票才纳入候选",
    "params": [
        {"name": "days", "label": "近N日", "type": "int", "default": 5, "min": 1, "max": 30},
    ],
    # check 模板：{var} = dt_index 变量名, {days} = 参数值
    "check": "        if {ts_code} not in dt_index:\n            continue\n"
             "        _dt_dates_{idx} = {{r[0].get(\"trade_date\",\"\") for r in dt_index[{ts_code}]}}\n"
             "        _dt_recent_{idx} = [d for d in _dt_dates_{idx} "
             "if _in_days(d, cutoff_date, {days})]\n"
             "        if not _dt_recent_{idx}:\n            continue",
})

_register({
    "id": "dt_net_buy",
    "name": "龙虎榜净买入额",
    "category": "龙虎榜",
    "type": "pre_filter",
    "description": "近N日龙虎榜净买入额大于指定门槛",
    "params": [
        {"name": "days", "label": "近N日", "type": "int", "default": 5, "min": 1, "max": 30},
        {"name": "min_wan", "label": "最低净买入(万)", "type": "float", "default": 1000, "min": 0, "max": 100000},
    ],
    "check": "        _dt_net_{idx} = _dt_net_buy_total(\n"
             "            dt_index.get({ts_code}, []), cutoff_date, {days})\n"
             "        if _dt_net_{idx} < {min_wan}:\n            continue",
})

_register({
    "id": "dt_institution",
    "name": "机构参与龙虎榜",
    "category": "龙虎榜",
    "type": "pre_filter",
    "description": "近N日内有机构席位在龙虎榜买入",
    "params": [
        {"name": "days", "label": "近N日", "type": "int", "default": 5, "min": 1, "max": 30},
    ],
    "check": "        if not _dt_has_institution(\n"
             "            dt_index.get({ts_code}, []), cutoff_date, {days}):\n"
             "            continue",
})

_register({
    "id": "dt_net_buy_score",
    "name": "龙虎榜净买入加分",
    "category": "龙虎榜",
    "type": "score_modifier",
    "description": "按近N日龙虎榜净买入额给予加分（非线性映射）",
    "params": [
        {"name": "days", "label": "近N日", "type": "int", "default": 5, "min": 1, "max": 30},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 15, "min": 0, "max": 30},
    ],
    "score": "        _dt_net_{idx} = _dt_net_buy_total(\n"
             "            dt_index.get({ts_code}, []), cutoff_date, {days})\n"
             "        if _dt_net_{idx} > 0:\n"
             "            score += min({max_score}, _dt_net_{idx} / 500)",
})

# ══════════════════════════════════════════════════════════════════════
#  板块资金流 条件
# ══════════════════════════════════════════════════════════════════════

_register({
    "id": "sf_net_inflow",
    "name": "板块资金净流入",
    "category": "板块资金流",
    "type": "pre_filter",
    "description": "所属板块（概念/行业）近N日累计资金净流入 > 0",
    "params": [
        {"name": "days", "label": "近N日", "type": "int", "default": 3, "min": 1, "max": 30},
        {"name": "sector_type", "label": "板块类型", "type": "enum", "default": "concept",
         "options": [{"label": "概念板块", "value": "concept"}, {"label": "行业板块", "value": "industry"}]},
    ],
    "check": "        _sf_matched_{idx} = _sf_stock_sectors(sf_index, stock)\n"
             "        _sf_matched_{idx} = [m for m in _sf_matched_{idx} if m[0] == \"{sector_type}\"]\n"
             "        if not _sf_matched_{idx}:\n            continue\n"
             "        _sf_ok_{idx} = False\n"
             "        for _st, _sn, _rows in _sf_matched_{idx}:\n"
             "            _total = sum(r.get(\"net_inflow\") or 0 for d, r in _rows.items() "
             "if _in_days(d, cutoff_date, {days}))\n"
             "            if _total > 0:\n"
             "                _sf_ok_{idx} = True\n"
             "                break\n"
             "        if not _sf_ok_{idx}:\n            continue",
})

_register({
    "id": "sf_rank",
    "name": "板块资金流排名",
    "category": "板块资金流",
    "type": "pre_filter",
    "description": "所属板块资金净流入排名在前N名",
    "params": [
        {"name": "top_n", "label": "排名前N", "type": "int", "default": 10, "min": 1, "max": 50},
        {"name": "sector_type", "label": "板块类型", "type": "enum", "default": "concept",
         "options": [{"label": "概念板块", "value": "concept"}, {"label": "行业板块", "value": "industry"}]},
    ],
    "check": "        _sf_matched_{idx} = _sf_stock_sectors(sf_index, stock)\n"
             "        _sf_matched_{idx} = [m for m in _sf_matched_{idx} if m[0] == \"{sector_type}\"]\n"
             "        if not _sf_matched_{idx}:\n            continue\n"
             "        _sf_ok_{idx} = False\n"
             "        for _st, _sn, _rows in _sf_matched_{idx}:\n"
             "            if _sf_rank(sf_ranking, _sn, _st) <= {top_n}:\n"
             "                _sf_ok_{idx} = True\n"
             "                break\n"
             "        if not _sf_ok_{idx}:\n            continue",
})

_register({
    "id": "sf_inflow_score",
    "name": "板块资金流加分",
    "category": "板块资金流",
    "type": "score_modifier",
    "description": "按所属板块的资金流排名给予线性加分（排名越高加分越多）",
    "params": [
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10, "min": 0, "max": 25},
    ],
    "score": "        _sf_matched_{idx} = _sf_stock_sectors(sf_index, stock)\n"
             "        if _sf_matched_{idx}:\n"
             "            _sf_best_rank_{idx} = min(\n"
             "                _sf_rank(sf_ranking, _sn, _st) for _st, _sn, _ in _sf_matched_{idx})\n"
             "            if _sf_best_rank_{idx} <= 20:\n"
             "                score += round({max_score} * (1 - _sf_best_rank_{idx} / 21), 1)",
})

# ══════════════════════════════════════════════════════════════════════
#  热门题材 条件
# ══════════════════════════════════════════════════════════════════════

_register({
    "id": "ht_in_theme",
    "name": "属于热门题材",
    "category": "热门题材",
    "type": "pre_filter",
    "description": "股票所属概念匹配当日热门题材（同花顺热点）",
    "params": [
        {"name": "min_stocks", "label": "题材最小股票数", "type": "int", "default": 5, "min": 1, "max": 50},
    ],
    "check": "        _ht_ok_{idx} = False\n"
             "        _stock_concepts_{idx} = []\n"
             "        _conc_str_{idx} = (stock.get(\"concepts\") or \"\").strip()\n"
             "        if _conc_str_{idx}:\n"
             "            try:\n"
             "                import json\n"
             "                _stock_concepts_{idx} = json.loads(_conc_str_{idx})\n"
             "            except Exception:\n"
             "                _stock_concepts_{idx} = [c.strip() for c in _conc_str_{idx}.split(\",\")]\n"
             "        for _ht_name in hot_theme_names:\n"
             "            if len(_ht_name) < 2:\n"
             "                continue\n"
             "            for _sc in _stock_concepts_{idx}:\n"
             "                if _ht_name in _sc or _sc in _ht_name:\n"
             "                    _ht_ok_{idx} = True\n"
             "                    break\n"
             "            if _ht_ok_{idx}:\n"
             "                break\n"
             "        if not _ht_ok_{idx}:\n            continue",
})

# ══════════════════════════════════════════════════════════════════════
#  热门股 条件
# ══════════════════════════════════════════════════════════════════════

_register({
    "id": "hs_on_list",
    "name": "热门股上榜",
    "category": "热门股",
    "type": "pre_filter",
    "description": "当日热门股名单中的股票才纳入候选",
    "params": [
        {"name": "top_n", "label": "排名前N", "type": "int", "default": 50, "min": 1, "max": 200},
    ],
    "check": "        _hs_info_{idx} = hot_stock_map.get({ts_code})\n"
             "        if _hs_info_{idx} is None:\n            continue\n"
             "        if _hs_info_{idx}.get(\"sort_order\", 999) > {top_n}:\n"
             "            continue",
})

_register({
    "id": "hs_dde_score",
    "name": "DDE 净流入加分",
    "category": "热门股",
    "type": "score_modifier",
    "description": "按热门股 DDE 大单净流入给予加分",
    "params": [
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10, "min": 0, "max": 20},
    ],
    "score": "        _hs_info_{idx} = hot_stock_map.get({ts_code})\n"
             "        if _hs_info_{idx}:\n"
             "            _dde_{idx} = _hs_info_{idx}.get(\"dde_net\") or 0\n"
             "            if _dde_{idx} > 0:\n"
             "                score += min({max_score}, _dde_{idx} / 1000)",
})


# ══════════════════════════════════════════════════════════════════════
#  基本面 条件 (fundamental_*)
# ══════════════════════════════════════════════════════════════════════

_register({
    "id": "fundamental_roe",
    "name": "ROE（净资产收益率）",
    "category": "基本面类",
    "type": "score_modifier",
    "description": "基于 ROE 打分/筛选。ROE 越高代表股东回报率越高。",
    "params": [
        {"name": "min_roe", "label": "最低 ROE(%)", "type": "float", "default": 10.0, "min": 0, "max": 50},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 15.0, "min": 0, "max": 30},
    ],
    "check": (
        "        _fin_{idx} = fundamental_roe_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} <= 0:\n"
        "            continue"
    ),
    "score": (
        "        _fin_{idx} = fundamental_roe_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} > 0:\n"
        "            score += _fin_{idx}"
    ),
})

_register({
    "id": "fundamental_eps_growth",
    "name": "净利润增长率",
    "category": "基本面类",
    "type": "score_modifier",
    "description": "基于净利润同比增长率打分/筛选。增速越高代表盈利成长性越强。",
    "params": [
        {"name": "min_growth", "label": "最低增速(%)", "type": "float", "default": 10.0, "min": -100, "max": 500},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 15.0, "min": 0, "max": 30},
    ],
    "check": (
        "        _fin_{idx} = fundamental_eps_growth_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} <= 0:\n"
        "            continue"
    ),
    "score": (
        "        _fin_{idx} = fundamental_eps_growth_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} > 0:\n"
        "            score += _fin_{idx}"
    ),
})

_register({
    "id": "fundamental_revenue_growth",
    "name": "营收增长率",
    "category": "基本面类",
    "type": "score_modifier",
    "description": "基于营业收入同比增长率打分/筛选。增速越高代表业务扩张越快。",
    "params": [
        {"name": "min_growth", "label": "最低增速(%)", "type": "float", "default": 5.0, "min": -100, "max": 500},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10.0, "min": 0, "max": 25},
    ],
    "check": (
        "        _fin_{idx} = fundamental_revenue_growth_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} <= 0:\n"
        "            continue"
    ),
    "score": (
        "        _fin_{idx} = fundamental_revenue_growth_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} > 0:\n"
        "            score += _fin_{idx}"
    ),
})

_register({
    "id": "fundamental_gross_margin",
    "name": "毛利率",
    "category": "基本面类",
    "type": "score_modifier",
    "description": "基于毛利率打分/筛选。高毛利率通常代表强定价权或品牌壁垒。",
    "params": [
        {"name": "min_margin", "label": "最低毛利率(%)", "type": "float", "default": 20.0, "min": 0, "max": 100},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10.0, "min": 0, "max": 20},
    ],
    "check": (
        "        _fin_{idx} = fundamental_gross_margin_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} <= 0:\n"
        "            continue"
    ),
    "score": (
        "        _fin_{idx} = fundamental_gross_margin_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} > 0:\n"
        "            score += _fin_{idx}"
    ),
})

_register({
    "id": "fundamental_net_margin",
    "name": "净利率",
    "category": "基本面类",
    "type": "score_modifier",
    "description": "基于净利率打分/筛选。高净利率代表强盈利效率。",
    "params": [
        {"name": "min_margin", "label": "最低净利率(%)", "type": "float", "default": 5.0, "min": 0, "max": 100},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 10.0, "min": 0, "max": 20},
    ],
    "check": (
        "        _fin_{idx} = fundamental_net_margin_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} <= 0:\n"
        "            continue"
    ),
    "score": (
        "        _fin_{idx} = fundamental_net_margin_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} > 0:\n"
        "            score += _fin_{idx}"
    ),
})

_register({
    "id": "fundamental_debt_ratio",
    "name": "资产负债率",
    "category": "基本面类",
    "type": "pre_filter",
    "description": "基于资产负债率筛选。负债率过高 → 剔除，控制财务风险。",
    "params": [
        {"name": "max_debt", "label": "最高负债率(%)", "type": "float", "default": 70.0, "min": 0, "max": 100},
    ],
    "check": (
        "        _fin_{idx} = fundamental_debt_ratio_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} < 0:\n"
        "            continue"
    ),
})

_register({
    "id": "fundamental_cf_ratio",
    "name": "现金流比率",
    "category": "基本面类",
    "type": "score_modifier",
    "description": "经营现金流/营业收入比率。比率高说明盈利质量好。",
    "params": [
        {"name": "min_ratio", "label": "最低比率(%)", "type": "float", "default": 5.0, "min": -100, "max": 200},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 8.0, "min": 0, "max": 20},
    ],
    "check": (
        "        _fin_{idx} = fundamental_cf_ratio_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} <= 0:\n"
        "            continue"
    ),
    "score": (
        "        _fin_{idx} = fundamental_cf_ratio_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} > 0:\n"
        "            score += _fin_{idx}"
    ),
})

_register({
    "id": "fundamental_pe_pb",
    "name": "PE/PB 估值",
    "category": "基本面类",
    "type": "score_modifier",
    "description": "基于 PE/PB 估值打分/筛选。低估值加分。PE/PB 从日线市值 + 财报数据实时计算。",
    "params": [
        {"name": "max_pe", "label": "最高 PE（筛选）", "type": "float", "default": 50.0, "min": 0, "max": 500},
        {"name": "max_pb", "label": "最高 PB（筛选）", "type": "float", "default": 10.0, "min": 0, "max": 50},
        {"name": "pe_score_weight", "label": "PE 打分权重", "type": "float", "default": 0.7, "min": 0, "max": 1},
        {"name": "max_score", "label": "最高加分", "type": "float", "default": 15.0, "min": 0, "max": 30},
    ],
    "check": (
        "        _fin_{idx} = fundamental_pe_pb_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} <= 0:\n"
        "            continue"
    ),
    "score": (
        "        _fin_{idx} = fundamental_pe_pb_compute(fin, _fin_mkt, {params_json})\n"
        "        if _fin_{idx} > 0:\n"
        "            score += _fin_{idx}"
    ),
})


# ── code_generator 使用的辅助 ─────────────────────────────────────

# 基本面辅助函数（内联到生成代码中）
_FIN_HELPERS = '''
# ---- 基本面辅助 ----
def _fin_get_latest(financials_index, ts_code, cutoff_date):
    """获取股票在截止日前的最新一期财报"""
    reports = financials_index.get(ts_code, [])
    best = None
    for r in reports:
        pub = r.get("pub_date", "")
        report_date = r.get("report_date", "")
        if pub and pub <= cutoff_date:
            if best is None or report_date > best.get("report_date", ""):
                best = r
    return best
'''


def has_fundamental_conditions(factor_config: dict) -> bool:
    """检查策略配置是否包含任何基本面条件"""
    selection = factor_config.get("selection_conditions", {})
    scorers = factor_config.get("scoring_modifiers", [])

    for cond in selection.get("conditions", []):
        if (cond.get("condition_id", "") or "").startswith("fundamental_"):
            return True
    for sc in scorers:
        if (sc.get("condition_id", "") or "").startswith("fundamental_"):
            return True
    return False


def get_financial_setup_code() -> str:
    """生成基本面数据索引构建代码"""
    return (
        "    # 基本面数据索引\n"
        "    financials_index = {}\n"
        '    for _fin_row in data.get("financials", []):\n'
        '        _fin_ts = _fin_row.get("ts_code", "")\n'
        "        if _fin_ts not in financials_index:\n"
        "            financials_index[_fin_ts] = []\n"
        "        financials_index[_fin_ts].append(_fin_row)\n"
    )


def get_financial_lookup_code() -> str:
    """生成 per-stock 基本面查找代码（插入在选股条件之前）"""
    return (
        "        # 获取该股票最新财报\n"
        "        fin = _fin_get_latest(financials_index, ts_code, cutoff_date)\n"
        "        if fin is None:\n"
        "            continue\n"
        "\n"
        "        # 构建市场数据（用于 PE/PB 计算）\n"
        "        _fin_mkt = {\n"
        '            "market_cap": float(df["market_cap"].iloc[-1]) '
        'if "market_cap" in df.columns and df["market_cap"].iloc[-1] else 0,\n'
        '            "close": float(df["close"].iloc[-1]) '
        'if "close" in df.columns else 0,\n'
        "        }\n"
    )


def get_setup_code() -> str:
    """生成 setup 代码块（构建索引等，放在 run() 开头，loop 之前）"""
    lines = [
        "    # === 选股条件：构建索引 ===",
        "    # 日期辅助",
        "    from datetime import datetime, timedelta",
        "    def _in_days(date_str, cutoff_str, days):",
        "        try:",
        "            d = datetime.strptime(str(date_str).replace('-','')[:8], '%Y%m%d')",
        "            c = datetime.strptime(str(cutoff_str).replace('-','')[:8], '%Y%m%d')",
        "            return c - timedelta(days=days) <= d <= c",
        "        except:",
        "            return False",
        "",
        "    # 板块资金流索引",
        "    daily_sector_flow = data.get('daily_sector_flow', [])",
        "    sf_index, sf_ranking = _sf_build_index(daily_sector_flow)",
        "",
        "    # 热门股索引",
        "    hot_stocks = data.get('hot_stocks', [])",
        "    hot_stock_map = {}",
        "    for _hs in hot_stocks:",
        "        hot_stock_map[_hs.get('stock_code', '')] = _hs",
        "",
        "    # 热门题材名称集合",
        "    hot_themes = data.get('hot_themes', [])",
        "    hot_theme_names = {_ht.get('theme_name', '') for _ht in hot_themes "
        "if (_ht.get('stock_count') or 0) >= 1}",
        "",
        "    # 龙虎榜索引",
        "    dragon_tiger = data.get('dragon_tiger', [])",
        "    dragon_tiger_seats = data.get('dragon_tiger_seats', [])",
        "    dt_index = _dt_build_index(dragon_tiger, dragon_tiger_seats)",
        "",
    ]
    return "\n".join(lines)
