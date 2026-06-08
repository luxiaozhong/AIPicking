"""市场热度服务 — Core 级别 SQL 查询"""
import re
from typing import Optional
from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock_tables import (
    Daily, DailySectorFlow, DailyHotStock, DailyHotTheme,
    DailyNorthboundFlow, DailyDragonTiger, DailyDragonTigerSeat,
    DailyMarketStress,
)

# ── 板块→个股模糊匹配：名称归一化 ──────────────────────────────

# 常见后缀（东财板块名 vs stocks 行业名 差异来源）
# 按长度降序排列，确保长后缀先匹配（如 "制造业" 优先于 "制造"）
_NORMALIZE_STRIPS = sorted([
    "制造业", "及其他", "和其他", "与服务", "及服务", "及设备",
    "及元件", "零部件", "行业", "板块", "制品", "加工",
    "销售", "生产", "经营", "器械", "设备", "开发",
    "服务", "制造",
], key=lambda x: -len(x))

# ── 东财行业 → 申万行业 + 概念关键词 映射表 ─────────────────────
# 当 stocks.industry_l1/l2 与东财分类体系不兼容时，通过此映射查找个股。
# 格式：{东财板块名: {"industries": [申万l1], "keywords": [额外搜索词]}}
_SECTOR_MAP: dict[str, dict] = {
    # ── 制造业细分 ──
    "玻璃玻纤":       {"industries": ["建筑材料", "基础化工"], "keywords": ["玻璃", "玻纤"]},
    "玻璃纤维":       {"industries": ["建筑材料", "基础化工"], "keywords": ["玻璃", "玻纤"]},
    "水泥":          {"industries": ["建筑材料"], "keywords": ["水泥"]},
    "装修建材":       {"industries": ["建筑材料", "建筑装饰"], "keywords": ["建材", "装修"]},
    "房屋建设Ⅱ":      {"industries": ["建筑装饰", "房地产"], "keywords": ["房屋建设", "施工"]},
    "基础建设":       {"industries": ["建筑装饰"], "keywords": ["基建", "工程"]},
    "专业工程":       {"industries": ["建筑装饰"], "keywords": ["工程"]},
    "工程机械":       {"industries": ["机械设备"], "keywords": ["工程机械", "挖掘机", "起重机"]},
    "通用设备":       {"industries": ["机械设备"], "keywords": ["通用设备"]},
    "专用设备":       {"industries": ["机械设备"], "keywords": ["专用设备"]},
    "自动化设备":     {"industries": ["机械设备", "电力设备"], "keywords": ["自动化", "机器人"]},
    "轨交设备Ⅱ":      {"industries": ["机械设备", "交通运输"], "keywords": ["轨交", "铁路", "高铁"]},
    "电机Ⅱ":         {"industries": ["电力设备", "机械设备"], "keywords": ["电机"]},
    "电网设备":       {"industries": ["电力设备"], "keywords": ["电网", "输配电", "电力"]},
    "风电设备":       {"industries": ["电力设备"], "keywords": ["风电", "风机"]},
    "光伏设备":       {"industries": ["电力设备"], "keywords": ["光伏", "太阳能"]},
    "电池":          {"industries": ["电力设备"], "keywords": ["电池", "锂电", "储能"]},
    "其他电源设备Ⅱ":  {"industries": ["电力设备"], "keywords": ["电源", "充电"]},
    "家用电器":       {"industries": ["家用电器"], "keywords": ["家电"]},
    "白色家电":       {"industries": ["家用电器"], "keywords": ["白电", "空调", "冰箱", "洗衣机"]},
    "黑色家电":       {"industries": ["家用电器", "电子"], "keywords": ["黑电", "电视"]},
    "小家电":         {"industries": ["家用电器"], "keywords": ["小家电"]},
    "厨卫电器":       {"industries": ["家用电器"], "keywords": ["厨卫", "油烟机"]},
    "照明设备Ⅱ":      {"industries": ["家用电器", "电子"], "keywords": ["照明", "灯具"]},
    "家电零部件Ⅱ":    {"industries": ["家用电器", "机械设备"], "keywords": ["家电配件"]},
    "汽车":          {"industries": ["汽车"], "keywords": ["汽车"]},
    "乘用车":        {"industries": ["汽车"], "keywords": ["乘用车", "整车"]},
    "商用车":        {"industries": ["汽车"], "keywords": ["商用车", "客车", "货车"]},
    "汽车零部件":     {"industries": ["汽车"], "keywords": ["汽车零部件", "汽配"]},
    "汽车服务":       {"industries": ["汽车", "商贸零售"], "keywords": ["汽车服务", "4S"]},
    "摩托车及其他":   {"industries": ["汽车", "交通运输"], "keywords": ["摩托车"]},
    "化学制品":       {"industries": ["基础化工"], "keywords": ["化工", "化学"]},
    "化学原料":       {"industries": ["基础化工"], "keywords": ["化学原料"]},
    "化学纤维":       {"industries": ["基础化工"], "keywords": ["化纤"]},
    "农化制品":       {"industries": ["基础化工", "农林牧渔"], "keywords": ["农化", "化肥", "农药"]},
    "塑料":          {"industries": ["基础化工"], "keywords": ["塑料"]},
    "橡胶":          {"industries": ["基础化工"], "keywords": ["橡胶", "轮胎"]},
    "非金属材料Ⅱ":    {"industries": ["基础化工", "建筑材料"], "keywords": ["非金属材料", "碳纤维"]},
    "电子化学品Ⅱ":    {"industries": ["电子", "基础化工"], "keywords": ["电子化学品", "光刻胶"]},
    "能源金属":       {"industries": ["有色金属"], "keywords": ["锂", "钴", "镍", "能源金属"]},
    "小金属":         {"industries": ["有色金属"], "keywords": ["小金属", "钨", "钼", "稀土"]},
    "工业金属":       {"industries": ["有色金属"], "keywords": ["铜", "铝", "锌", "工业金属"]},
    "贵金属":         {"industries": ["有色金属"], "keywords": ["黄金", "白银", "贵金属"]},
    "金属新材料":     {"industries": ["有色金属", "基础化工"], "keywords": ["新材料", "合金"]},
    "冶钢原料":       {"industries": ["钢铁", "有色金属"], "keywords": ["冶钢", "铁矿石"]},
    "普钢":          {"industries": ["钢铁"], "keywords": ["钢铁"]},
    "特钢Ⅱ":         {"industries": ["钢铁"], "keywords": ["特钢", "不锈钢"]},
    "元件":          {"industries": ["电子"], "keywords": ["元件", "电容", "电阻", "电感"]},
    "半导体":         {"industries": ["电子"], "keywords": ["半导体", "芯片", "晶圆"]},
    "光学光电子":     {"industries": ["电子"], "keywords": ["光学", "光电", "LED"]},
    "消费电子":       {"industries": ["电子"], "keywords": ["消费电子", "手机", "智能穿戴"]},
    "其他电子Ⅱ":      {"industries": ["电子"], "keywords": ["电子"]},
    "计算机设备":     {"industries": ["计算机"], "keywords": ["计算机", "服务器"]},
    "软件开发":       {"industries": ["计算机"], "keywords": ["软件", "IT"]},
    "IT服务Ⅱ":       {"industries": ["计算机"], "keywords": ["IT服务", "云计算", "大数据"]},
    "通信设备":       {"industries": ["通信"], "keywords": ["通信设备", "5G", "光通信"]},
    "通信服务":       {"industries": ["通信"], "keywords": ["通信服务", "运营商"]},
    "军工电子Ⅱ":      {"industries": ["国防军工", "电子"], "keywords": ["军工电子", "雷达"]},
    "航天装备Ⅱ":      {"industries": ["国防军工"], "keywords": ["航天", "火箭", "卫星"]},
    "航空装备Ⅱ":      {"industries": ["国防军工"], "keywords": ["航空", "飞机", "发动机"]},
    "航海装备Ⅱ":      {"industries": ["国防军工"], "keywords": ["航海", "船舶", "舰艇"]},
    "地面兵装Ⅱ":      {"industries": ["国防军工"], "keywords": ["兵装", "武器", "弹药"]},
    # ── 消费类 ──
    "白酒Ⅱ":         {"industries": ["食品饮料"], "keywords": ["白酒"]},
    "非白酒":         {"industries": ["食品饮料"], "keywords": ["啤酒", "红酒", "黄酒"]},
    "饮料乳品":       {"industries": ["食品饮料"], "keywords": ["饮料", "乳品", "牛奶"]},
    "休闲食品":       {"industries": ["食品饮料"], "keywords": ["零食", "食品"]},
    "调味发酵品Ⅱ":    {"industries": ["食品饮料"], "keywords": ["调味", "酱油", "酵母"]},
    "食品加工":       {"industries": ["食品饮料", "农林牧渔"], "keywords": ["食品加工", "肉制品"]},
    "纺织制造":       {"industries": ["纺织服饰"], "keywords": ["纺织", "面料"]},
    "服装家纺":       {"industries": ["纺织服饰"], "keywords": ["服装", "家纺"]},
    "饰品":          {"industries": ["纺织服饰", "轻工制造"], "keywords": ["饰品", "珠宝"]},
    "家居用品":       {"industries": ["轻工制造"], "keywords": ["家居", "家具"]},
    "文娱用品":       {"industries": ["轻工制造"], "keywords": ["文娱", "文具", "玩具"]},
    "造纸":          {"industries": ["轻工制造"], "keywords": ["造纸", "纸业"]},
    "包装印刷":       {"industries": ["轻工制造"], "keywords": ["包装", "印刷"]},
    "个护用品":       {"industries": ["美容护理"], "keywords": ["日化", "洗护", "卫生巾"]},
    "化妆品":         {"industries": ["美容护理"], "keywords": ["化妆", "护肤"]},
    "医疗美容":       {"industries": ["医药生物", "美容护理"], "keywords": ["医美"]},
    # ── 医药细分 ──
    "化学制药":       {"industries": ["医药生物"], "keywords": ["化学制药", "原料药"]},
    "中药Ⅱ":         {"industries": ["医药生物"], "keywords": ["中药", "中成药"]},
    "生物制品":       {"industries": ["医药生物"], "keywords": ["生物制品", "疫苗", "血液制品"]},
    "医疗器械":       {"industries": ["医药生物"], "keywords": ["医疗器械", "医疗设备"]},
    "医疗服务":       {"industries": ["医药生物"], "keywords": ["医疗服务", "医院", "检测"]},
    "医药商业":       {"industries": ["医药生物"], "keywords": ["医药商业", "药店"]},
    "动物保健Ⅱ":      {"industries": ["农林牧渔", "医药生物"], "keywords": ["动物保健", "兽药"]},
    # ── 服务类 ──
    "证券Ⅱ":         {"industries": ["非银金融"], "keywords": ["证券", "券商"]},
    "保险Ⅱ":         {"industries": ["非银金融"], "keywords": ["保险"]},
    "多元金融":       {"industries": ["非银金融"], "keywords": ["金融", "信托", "期货"]},
    "银行Ⅱ":         {"industries": ["银行"], "keywords": ["银行"]},
    "房地产开发":     {"industries": ["房地产"], "keywords": ["房地产", "开发商"]},
    "房地产服务":     {"industries": ["房地产", "社会服务"], "keywords": ["物业", "中介"]},
    "一般零售":       {"industries": ["商贸零售"], "keywords": ["零售", "百货", "超市"]},
    "贸易Ⅱ":         {"industries": ["商贸零售"], "keywords": ["贸易"]},
    "互联网电商":     {"industries": ["商贸零售", "传媒"], "keywords": ["电商", "互联网"]},
    "旅游零售Ⅱ":      {"industries": ["商贸零售", "社会服务"], "keywords": ["免税", "旅游零售"]},
    "专业连锁Ⅱ":      {"industries": ["商贸零售"], "keywords": ["连锁"]},
    "旅游及景区":     {"industries": ["社会服务"], "keywords": ["旅游", "景区"]},
    "酒店餐饮":       {"industries": ["社会服务"], "keywords": ["酒店", "餐饮"]},
    "教育":          {"industries": ["社会服务"], "keywords": ["教育", "培训"]},
    "体育Ⅱ":         {"industries": ["社会服务", "传媒"], "keywords": ["体育"]},
    "专业服务":       {"industries": ["社会服务"], "keywords": ["检测", "咨询", "人力资源"]},
    "物流":          {"industries": ["交通运输"], "keywords": ["物流", "快递"]},
    "航运港口":       {"industries": ["交通运输"], "keywords": ["航运", "港口", "海运"]},
    "铁路公路":       {"industries": ["交通运输"], "keywords": ["铁路", "公路", "高速"]},
    "航空机场":       {"industries": ["交通运输"], "keywords": ["航空", "机场", "飞机"]},
    "广告营销":       {"industries": ["传媒"], "keywords": ["广告", "营销"]},
    "游戏Ⅱ":         {"industries": ["传媒", "计算机"], "keywords": ["游戏"]},
    "数字媒体":       {"industries": ["传媒"], "keywords": ["数字媒体", "新媒体"]},
    "影视院线":       {"industries": ["传媒"], "keywords": ["影视", "电影", "院线"]},
    "出版":          {"industries": ["传媒"], "keywords": ["出版", "图书"]},
    "电视广播Ⅱ":      {"industries": ["传媒"], "keywords": ["电视", "广播"]},
    # ── 公用事业 / 能源 ──
    "电力":          {"industries": ["公用事业"], "keywords": ["电力", "发电", "电网"]},
    "燃气Ⅱ":         {"industries": ["公用事业"], "keywords": ["燃气", "天然气"]},
    "环保设备Ⅱ":      {"industries": ["环保", "机械设备"], "keywords": ["环保设备", "污水处理"]},
    "环境治理":       {"industries": ["环保"], "keywords": ["环境治理", "固废", "水务"]},
    "煤炭开采":       {"industries": ["煤炭"], "keywords": ["煤炭", "煤矿"]},
    "焦炭Ⅱ":         {"industries": ["煤炭", "钢铁"], "keywords": ["焦炭", "焦化"]},
    "石油石化":       {"industries": ["石油石化"], "keywords": []},
    "炼化及贸易":     {"industries": ["石油石化"], "keywords": ["炼化", "石化"]},
    "油服工程":       {"industries": ["石油石化"], "keywords": ["油服", "油田"]},
    "油气开采Ⅱ":      {"industries": ["石油石化"], "keywords": ["油气", "开采"]},
    # ── 农林牧渔 ──
    "种植业":         {"industries": ["农林牧渔"], "keywords": ["种植", "种子"]},
    "养殖业":         {"industries": ["农林牧渔"], "keywords": ["养殖", "畜牧", "生猪"]},
    "饲料":          {"industries": ["农林牧渔"], "keywords": ["饲料"]},
    "渔业":          {"industries": ["农林牧渔"], "keywords": ["渔业", "水产"]},
    "农产品加工":     {"industries": ["农林牧渔", "食品饮料"], "keywords": ["农产品加工"]},
    "林业Ⅱ":         {"industries": ["农林牧渔"], "keywords": ["林业"]},
    "农业综合Ⅱ":      {"industries": ["农林牧渔"], "keywords": ["农业"]},
}


def _normalize_trade_date(d: str) -> str:
    """'20260604' → '2026-06-04'，已是标准格式则原样返回"""
    if not d:
        return d
    if len(d) == 8 and '-' not in d:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d

def _normalize_sector_name(name: str) -> list[str]:
    """归一化板块名称，返回多个候选形式用于模糊匹配。

    递归剥离常见后缀，生成从完整到最简短的一系列候选。
    例如 "房地产开发经营" → ["房地产开发经营", "房地产开发", "房地产"]
    例如 "半导体及元件"   → ["半导体及元件", "半导体"]
    例如 "汽车零部件"     → ["汽车零部件", "汽车"]
    """
    if not name:
        return [""]
    # 去除罗马数字后缀
    base = re.sub(r'[Ⅰ-ⅧⅠⅡⅢⅣⅤⅥⅦⅧ]+$', '', name).strip()
    candidates = [base]

    # 递归剥离后缀，直到无法再剥离
    current = base
    while True:
        stripped = False
        for suffix in _NORMALIZE_STRIPS:
            if current.endswith(suffix) and len(current) - len(suffix) >= 2:
                current = current[:-len(suffix)].strip()
                stripped = True
                break
        if not stripped:
            break
        if current not in candidates:
            candidates.append(current)

    # 尝试去掉常见前缀（如 "其他"）
    for prefix in ["其他", "其它"]:
        if base.startswith(prefix) and len(base) - len(prefix) >= 2:
            short = base[len(prefix):].strip()
            if short not in candidates:
                candidates.append(short)

    return candidates


def _build_sector_stock_match(sector_name: str, Stock, max_variants: int = 6):
    """构建板块名→个股行业/概念的 SQLAlchemy OR 条件。

    多层匹配策略（按特异性从高到低）：
      1. 东财→申万映射表精确匹配 industry_l1
      2. 精确匹配 industry_l2 / industry_l1（含归一化候选）
      3. 双向 ILIKE：个股行业字段包含板块名
      4. concepts 字段 ILIKE 匹配
      5. 公司名称 ILIKE 匹配（兜底：如"玻璃玻纤" → 公司名含"玻璃"）
    """
    # 去除罗马数字后缀得到干净的板块名
    base_name = re.sub(r'[Ⅰ-ⅧⅠⅡⅢⅣⅤⅥⅦⅧ]+$', '', sector_name).strip()
    candidates = _normalize_sector_name(sector_name)
    conditions = []

    # ── Layer 0: 映射表优先 ──
    # 查找最匹配的映射（精确匹配 > 归一化匹配）
    mapping = _SECTOR_MAP.get(sector_name) or _SECTOR_MAP.get(base_name)
    if not mapping:
        # 用短候选名再试
        for c in candidates[1:]:
            mapping = _SECTOR_MAP.get(c)
            if mapping:
                break

    if mapping:
        # 仅对窄行业（< 200 只）做精确匹配，避免大类匹配到过多无关股票
        _BROAD_INDUSTRIES = {"机械设备", "电子", "医药生物", "基础化工", "电力设备", "计算机", "汽车"}
        for ind in mapping.get("industries", []):
            if ind not in _BROAD_INDUSTRIES:
                conditions.append(Stock.industry_l1 == ind)

        # 映射表关键词 → ILIKE 匹配所有相关字段（industry + concepts + name）
        for kw in mapping.get("keywords", []):
            if len(kw) >= 2:
                conditions.append(Stock.industry_l1.ilike(f"%{kw}%"))
                conditions.append(Stock.industry_l2.ilike(f"%{kw}%"))
                conditions.append(Stock.concepts.ilike(f"%{kw}%"))
                conditions.append(Stock.name.ilike(f"%{kw}%"))

    # ── Layer 1+2: 精确 + 归一化精确匹配 ──
    seen = set()
    for c in candidates[:max_variants]:
        if c in seen:
            continue
        seen.add(c)
        conditions.append(Stock.industry_l2 == c)
        conditions.append(Stock.industry_l1 == c)

    # ── Layer 3: 双向 ILIKE（个股行业字段包含板块名）──
    primary = candidates[0] if candidates else sector_name
    conditions.append(Stock.industry_l2.ilike(f"%{primary}%"))
    conditions.append(Stock.industry_l1.ilike(f"%{primary}%"))

    # 短候选名也做 ILIKE
    for c in candidates[1:4]:
        if len(c) >= 2 and c not in seen:
            seen.add(c)
            conditions.append(Stock.industry_l2.ilike(f"%{c}%"))
            conditions.append(Stock.industry_l1.ilike(f"%{c}%"))

    # ── Layer 4: concepts 字段 ──
    for c in candidates[:4]:
        if len(c) >= 2:
            conditions.append(Stock.concepts.ilike(f"%{c}%"))

    # ── Layer 5: 公司名称兜底 ──
    # 板块名中的关键词在公司名称中出现（如"玻璃玻纤"→"XX玻璃"）
    for c in candidates[:4]:
        if len(c) >= 2 and not c.endswith(("板块", "行业", "概念")):
            conditions.append(Stock.name.ilike(f"%{c}%"))

    return or_(*conditions)


class MarketHeatService:

    # ── 工具方法 ─────────────────────────────────────────────

    @staticmethod
    async def _get_latest_date_for(db: AsyncSession, table) -> Optional[str]:
        """获取指定表最新有数据的交易日"""
        stmt = select(func.max(table.trade_date))
        result = await db.execute(stmt)
        return result.scalar()

    # ── 概览 KPI ─────────────────────────────────────────────

    @staticmethod
    async def get_overview(db: AsyncSession, trade_date: Optional[str] = None) -> dict:
        """返回 4 个核心 KPI：市场温度、北向资金、涨跌比、领涨板块"""

        daily_date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        nb_date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyNorthboundFlow.__table__.c)
        sector_date = trade_date or await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)

        if not daily_date:
            return {"trade_date": None, "temperature": None, "northbound": None,
                    "advance_decline": None, "leading_sectors": []}

        # 北向资金
        northbound = None
        if nb_date:
            nb_stmt = select(DailyNorthboundFlow.__table__).where(
                DailyNorthboundFlow.trade_date == nb_date
            )
            nb_result = await db.execute(nb_stmt)
            nb_row = nb_result.mappings().first()
            northbound = dict(nb_row) if nb_row else None

        # 涨跌比（用 daily 表的日期）
        # 使用标准日间涨跌幅公式 (close - pre_close) / pre_close，与涨跌分布弹窗一致
        # pre_close 优先取同步存储值（同一复权因子），回退到自连接前一日 close
        adv_daily_a = Daily.__table__.alias()
        adv_prev_a = Daily.__table__.alias()
        adv_change = (
            (adv_daily_a.c.close - func.coalesce(adv_daily_a.c.pre_close, adv_prev_a.c.close))
            / func.nullif(func.coalesce(adv_daily_a.c.pre_close, adv_prev_a.c.close), 0)
        )
        adv_stmt = select(
            func.count().label("total"),
            func.sum(case((adv_change > 0, 1), else_=0)).label("up_count"),
            func.sum(case((adv_change < 0, 1), else_=0)).label("down_count"),
        ).select_from(adv_daily_a).outerjoin(
            adv_prev_a,
            (adv_daily_a.c.ts_code == adv_prev_a.c.ts_code)
            & (adv_prev_a.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == adv_daily_a.c.ts_code)
                    & (Daily.__table__.c.trade_date < daily_date)
                )
                .scalar_subquery()
            )),
        ).where(
            adv_daily_a.c.trade_date == daily_date,
            ~adv_daily_a.c.ts_code.like("%.IDX"),
        )
        adv_result = await db.execute(adv_stmt)
        adv_row = adv_result.mappings().first()
        adv = dict(adv_row) if adv_row else {"total": 0, "up_count": 0, "down_count": 0}

        # 领涨板块 Top 2
        leading = []
        # 领跌板块 Bottom 2
        lagging = []
        if sector_date:
            sector_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == sector_date,
                DailySectorFlow.sector_type == "industry"
            ).order_by(DailySectorFlow.change_pct.desc()).limit(2)
            sector_result = await db.execute(sector_stmt)
            leading = [dict(r) for r in sector_result.mappings().all()]

            lagging_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == sector_date,
                DailySectorFlow.sector_type == "industry"
            ).order_by(DailySectorFlow.change_pct.asc()).limit(2)
            lagging_result = await db.execute(lagging_stmt)
            lagging = [dict(r) for r in lagging_result.mappings().all()]

        # 计算市场温度
        temperature = await MarketHeatService._calc_temperature(
            northbound=northbound,
            adv=adv,
            date=daily_date,
            db=db,
        )

        def _fmt_sector(s):
            return {
                "sector_name": s["sector_name"],
                "change_pct": s["change_pct"],
                "main_net_yi": s["main_net_yi"],
            }

        # 板块温度（尝试从持久化表读取，失败则跳过）
        board_temps = await MarketHeatService.get_board_temperatures(db, daily_date)

        # 四大板块涨跌幅（中位数）
        from sqlalchemy import text as sa_text
        board_changes = []
        daily_a = Daily.__table__.alias()
        prev_a = Daily.__table__.alias()
        change_expr = (
            (daily_a.c.close - func.coalesce(daily_a.c.pre_close, prev_a.c.close, daily_a.c.open))
            / func.nullif(func.coalesce(daily_a.c.pre_close, prev_a.c.close, daily_a.c.open), 0)
            * 100
        )
        for board_code, board_name, ts_pattern in MarketHeatService.BOARD_DEFINITIONS:
            bc_stmt = select(
                func.percentile_cont(0.5).within_group(change_expr).label("median_change_pct"),
            ).select_from(daily_a).outerjoin(
                prev_a,
                (daily_a.c.ts_code == prev_a.c.ts_code)
                & (prev_a.c.trade_date == (
                    select(func.max(Daily.__table__.c.trade_date))
                    .where(
                        (Daily.__table__.c.ts_code == daily_a.c.ts_code)
                        & (Daily.__table__.c.trade_date < daily_date)
                    )
                    .scalar_subquery()
                )),
            ).where(
                daily_a.c.trade_date == daily_date,
                ~daily_a.c.ts_code.like("%.IDX"),
                sa_text(f"daily_1.ts_code ~ '{ts_pattern}'"),
            )
            bc_result = await db.execute(bc_stmt)
            median_change = bc_result.scalar()
            board_changes.append({
                "board_code": board_code,
                "board_name": board_name,
                "change_pct": round(median_change, 2) if median_change is not None else None,
            })

        return {
            "trade_date": daily_date,
            "temperature": temperature,
            "northbound": northbound,
            "advance_decline": adv,
            "leading_sectors": [_fmt_sector(s) for s in leading],
            "lagging_sectors": [_fmt_sector(s) for s in lagging],
            "board_temperatures": board_temps,
            "board_changes": board_changes,
        }

    # ── 板块资金流 ────────────────────────────────────────────

    @staticmethod
    async def get_sectors(
        db: AsyncSession, trade_date: Optional[str], sector_type: str = "industry"
    ) -> list[dict]:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
        if not date:
            return []

        async def _query(d: str) -> list[dict]:
            stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == d,
                DailySectorFlow.sector_type == sector_type,
            ).order_by(DailySectorFlow.net_inflow.desc())
            result = await db.execute(stmt)
            return [dict(r) for r in result.mappings().all()]

        items = await _query(date)
        # 指定日期无数据时自动回退到最新
        if not items and trade_date:
            fallback = await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
            if fallback and fallback != date:
                items = await _query(fallback)
        return items

    @staticmethod
    async def get_sector_detail(
        db: AsyncSession, sector_code: str, trade_date: Optional[str], days: int = 10
    ) -> dict:
        """板块详情：近 N 日资金流趋势 + 成分股 Top5"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
        if not date:
            return {"trend": [], "stocks": [], "info": None}

        async def _fetch(d: str) -> tuple:
            info_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.trade_date == d,
                DailySectorFlow.sector_code == sector_code,
            )
            info_result = await db.execute(info_stmt)
            info_row = info_result.mappings().first()
            info = dict(info_row) if info_row else None

            trend_stmt = select(DailySectorFlow.__table__).where(
                DailySectorFlow.sector_code == sector_code,
                DailySectorFlow.trade_date <= d,
            ).order_by(DailySectorFlow.trade_date.desc()).limit(days)
            trend_result = await db.execute(trend_stmt)
            trend = [dict(r) for r in reversed(list(trend_result.mappings().all()))]
            return info, trend

        info, trend = await _fetch(date)

        # 指定日期无数据时自动回退到最新
        if not info and trade_date:
            fallback = await MarketHeatService._get_latest_date_for(db, DailySectorFlow.__table__.c)
            if fallback and fallback != date:
                info, trend = await _fetch(fallback)
                date = fallback

        # 成分股 Top5（daily 表已统一为 YYYY-MM-DD）
        top5 = []
        if info:
            from ..models.stock_tables import Stock

            # 使用 pre_close 计算日涨跌幅（优先使用同步存储的值，回退到自连接）
            PrevDaily2 = aliased(Daily)
            pre_close_subq2 = (
                select(PrevDaily2.close)
                .where(PrevDaily2.ts_code == Stock.ts_code, PrevDaily2.trade_date < date)
                .order_by(PrevDaily2.trade_date.desc())
                .limit(1)
                .correlate(Stock)
                .scalar_subquery()
            )
            effective_pre_close = func.coalesce(Daily.pre_close, pre_close_subq2)
            change_expr_sector = (
                (Daily.close - effective_pre_close)
                / func.nullif(effective_pre_close, 0) * 100
            )

            # 模糊匹配板块→个股行业/概念
            match_cond = _build_sector_stock_match(info["sector_name"], Stock)

            stock_stmt = (
                select(Stock.ts_code, Stock.name, Daily.close, Daily.open,
                       change_expr_sector.label("change_pct"))
                .join(Daily, Stock.ts_code == Daily.ts_code)
                .where(
                    Daily.trade_date == date,
                    match_cond,
                )
                .order_by(
                    change_expr_sector.desc()
                )
                .limit(5)
            )
            stock_result = await db.execute(stock_stmt)
            top5 = [
                {"ts_code": r.ts_code, "name": r.name, "close": r.close, "open": r.open,
                 "change_pct": round(r.change_pct, 2) if r.change_pct else None}
                for r in stock_result.all()
            ]

        return {"info": info, "trend": trend, "stocks": top5}

    # ── 主题 ─────────────────────────────────────────────────

    @staticmethod
    async def get_themes(db: AsyncSession, trade_date: Optional[str], limit: int = 20) -> list[dict]:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyHotTheme.__table__.c)
        if not date:
            return []
        # date is already YYYY-MM-DD (all tables unified)
        stmt = select(DailyHotTheme.__table__).where(
            DailyHotTheme.trade_date == date
        ).order_by(DailyHotTheme.stock_count.desc()).limit(limit)
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def get_theme_detail(
        db: AsyncSession, theme_name: str, trade_date: Optional[str]
    ) -> list[dict]:
        """主题关联股票：从 hot_stocks 的 reason 字段模糊匹配"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyHotStock.__table__.c)
        if not date:
            return []
        # date is already YYYY-MM-DD (all tables unified)
        stmt = select(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date,
            DailyHotStock.reason.ilike(f"%{theme_name}%"),
        ).order_by(DailyHotStock.sort_order.asc())
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]
        return await MarketHeatService._enrich_with_daily(db, items, date)

    # ── 数据增强 ─────────────────────────────────────────────

    @staticmethod
    async def _enrich_with_daily(
        db: AsyncSession, items: list[dict], yyyymmdd_date: str
    ) -> list[dict]:
        """从 daily 表和 stocks 表补齐收盘价、涨幅、换手率"""
        if not items:
            return items

        daily_date = yyyymmdd_date  # daily 表已统一为 YYYY-MM-DD
        codes = [it["stock_code"] for it in items]
        from ..models.stock_tables import Stock

        # 将纯数字 code 转为 ts_code: 6xxxxx→SH, 其他→SZ
        def _to_ts(code: str) -> str:
            if code.startswith(("6", "9")):
                return f"{code}.SH"
            return f"{code}.SZ"

        code_to_ts = {c: _to_ts(c) for c in codes}
        ts_codes = list(code_to_ts.values())

        # 流通股本
        stock_stmt = select(Stock.ts_code, Stock.float_shares).where(
            Stock.ts_code.in_(ts_codes)
        )
        stock_result = await db.execute(stock_stmt)
        ts_to_shares = {r.ts_code: (r.float_shares or 0) for r in stock_result.all()}

        # 当日行情 + 前一日收盘价
        if ts_codes:
            daily_alias = Daily.__table__.alias()
            prev_alias = Daily.__table__.alias()

            stmt = (
                select(
                    daily_alias.c.ts_code,
                    daily_alias.c.close,
                    daily_alias.c.open,
                    daily_alias.c.vol,
                    func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open).label("prev_close"),
                )
                .select_from(daily_alias)
                .outerjoin(
                    prev_alias,
                    (daily_alias.c.ts_code == prev_alias.c.ts_code)
                    & (prev_alias.c.trade_date == (
                        select(func.max(Daily.__table__.c.trade_date))
                        .where(
                            (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                            & (Daily.__table__.c.trade_date < daily_date)
                        )
                        .scalar_subquery()
                    )),
                )
                .where(
                    daily_alias.c.trade_date == daily_date,
                    daily_alias.c.ts_code.in_(ts_codes),
                )
            )
            result = await db.execute(stmt)
            daily_map = {}
            for r in result.mappings().all():
                d = dict(r)
                code = d.pop("ts_code")
                daily_map[code] = d
        else:
            daily_map = {}

        for item in items:
            code = item["stock_code"]
            ts = code_to_ts.get(code)
            d = daily_map.get(ts, {}) if ts else {}
            item["close"] = d.get("close")
            item["open"] = d.get("open")
            if d.get("close") and d.get("prev_close") and d["prev_close"] != 0:
                item["change_pct"] = round(
                    (d["close"] - d["prev_close"]) / d["prev_close"] * 100, 2
                )
            vol = d.get("vol") or 0
            shares = ts_to_shares.get(ts, 0) or 0 if ts else 0
            if vol and shares:
                item["turnover_pct"] = round(vol * 100 / shares * 100, 2)

        return items

    # ── 热门股票 / 龙虎榜 / 北向 ──────────────────────────────

    @staticmethod
    async def get_hot_stocks(
        db: AsyncSession, trade_date: Optional[str], page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyHotStock.__table__.c)
        if not date:
            return {"items": [], "total": 0}
        # date is already YYYY-MM-DD (all tables unified)

        # 总数
        count_stmt = select(func.count()).select_from(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(DailyHotStock.__table__).where(
            DailyHotStock.trade_date == date
        ).order_by(DailyHotStock.sort_order.asc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]
        items = await MarketHeatService._enrich_with_daily(db, items, date)
        return {"items": items, "total": total}

    @staticmethod
    async def get_dragon_tiger(
        db: AsyncSession, trade_date: Optional[str], page: int = 1, page_size: int = 20
    ) -> dict:
        date = trade_date or await MarketHeatService._get_latest_date_for(db, DailyDragonTiger.__table__.c)
        if not date:
            return {"items": [], "total": 0}
        # date is already YYYY-MM-DD (all tables unified)

        count_stmt = select(func.count()).select_from(DailyDragonTiger.__table__).where(
            DailyDragonTiger.trade_date == date
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        stmt = select(DailyDragonTiger.__table__).where(
            DailyDragonTiger.trade_date == date
        ).order_by(DailyDragonTiger.net_buy_wan.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size)
        result = await db.execute(stmt)
        items = [dict(r) for r in result.mappings().all()]

        # 批量加载席位明细（避免 N+1）
        if items:
            codes = [item["stock_code"] for item in items]
            seat_stmt = select(DailyDragonTigerSeat.__table__).where(
                DailyDragonTigerSeat.trade_date == date,
                DailyDragonTigerSeat.stock_code.in_(codes),
            ).order_by(DailyDragonTigerSeat.stock_code, DailyDragonTigerSeat.seat_type, DailyDragonTigerSeat.rank)
            seat_result = await db.execute(seat_stmt)
            all_seats = [dict(s) for s in seat_result.mappings().all()]

            # 按 stock_code 分组
            seats_by_code: dict[str, list[dict]] = {}
            for seat in all_seats:
                code = seat["stock_code"]
                seats_by_code.setdefault(code, []).append(seat)

            for item in items:
                item["seats"] = seats_by_code.get(item["stock_code"], [])

        return {"items": items, "total": total}

    @staticmethod
    async def get_northbound(db: AsyncSession, days: int = 30) -> list[dict]:
        # 子查询取最新 N 天，外层升序（图表从左到右时间递增）
        subq = (
            select(DailyNorthboundFlow.__table__)
            .order_by(DailyNorthboundFlow.__table__.c.trade_date.desc())
            .limit(days)
            .subquery()
        )
        stmt = select(subq).order_by(subq.c.trade_date.asc())
        result = await db.execute(stmt)
        return [dict(r) for r in result.mappings().all()]

    @staticmethod
    async def get_available_dates(db: AsyncSession, days: int = 20) -> list[str]:
        """有数据的交易日列表（从 daily 表取，覆盖最广）"""
        stmt = (
            select(Daily.__table__.c.trade_date)
            .distinct()
            .order_by(Daily.__table__.c.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        return [r[0] for r in result.all()]

    # ── 市场温度计算 ─────────────────────────────────────────

    @staticmethod
    def _score_to_level(total_score: int) -> str:
        if total_score <= 30:
            return "冰点"
        elif total_score <= 50:
            return "偏冷"
        elif total_score <= 70:
            return "中性"
        elif total_score <= 85:
            return "偏热"
        return "过热"

    @staticmethod
    async def _calc_capital_score(northbound: Optional[dict]) -> int:
        """1. 资金面 (20): 北向净流入方向+规模"""
        if northbound and northbound.get("total_net_yi") is not None:
            net = northbound["total_net_yi"]
            if net > 50:
                return 20
            elif net > 20:
                return 17
            elif net > 0:
                return 14
            elif net > -20:
                return 7
            elif net > -50:
                return 3
            else:
                return 0
        return 10  # 无数据 → 中性

    @staticmethod
    def _calc_breadth_score(adv: dict) -> int:
        """2. 涨跌结构 (20): 上涨占比"""
        total = adv.get("total", 0) or 0
        up = adv.get("up_count", 0) or 0
        ratio = up / total if total > 0 else 0.5
        return min(20, round(ratio * 25))  # 80%+ = 满分

    @staticmethod
    async def _calc_sentiment_score(db: AsyncSession, date: str) -> int:
        """3. 情绪面 (20): 涨停/跌停比 + 活跃度

        通过 daily 表自连接计算真实日涨跌幅 (close - prev_close) / prev_close，
        统计涨停(>=9.8%)和跌停(<=-9.8%)数量。
        """
        # 自连接获取 prev_close，与 _enrich_with_daily 中模式一致
        # 优先使用同步时存储的 pre_close（同一复权因子），回退到自连接
        daily_alias = Daily.__table__.alias()
        prev_alias = Daily.__table__.alias()

        change_expr = (
            (daily_alias.c.close - func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open))
            / func.nullif(func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open), 0)
            * 100
        )

        stmt = select(
            func.count().label("total"),
            func.sum(case((change_expr >= 9.8, 1), else_=0)).label("limit_up"),
            func.sum(case((change_expr <= -9.8, 1), else_=0)).label("limit_down"),
        ).select_from(daily_alias).outerjoin(
            prev_alias,
            (daily_alias.c.ts_code == prev_alias.c.ts_code)
            & (prev_alias.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                    & (Daily.__table__.c.trade_date < date)
                )
                .scalar_subquery()
            )),
        ).where(
            daily_alias.c.trade_date == date,
            ~daily_alias.c.ts_code.like("%.IDX"),
        )

        result = await db.execute(stmt)
        row = result.mappings().first()
        if not row:
            return 10

        limit_up = row.get("limit_up", 0) or 0
        limit_down = row.get("limit_down", 0) or 0
        total_limits = limit_up + limit_down

        if total_limits == 0:
            return 10  # 无涨跌停 → 中性

        # 涨跌停方向比
        limit_ratio = limit_up / total_limits

        # 活跃度因子：触及涨跌停的股票越多，市场越活跃
        activity_factor = min(1.0, total_limits / 100.0)

        # 方向分 + 活跃度加权
        sentiment_raw = limit_ratio * 20
        sentiment = round(sentiment_raw * (0.5 + 0.5 * activity_factor))
        return max(0, min(20, sentiment))

    @staticmethod
    async def _calc_concentration_score(db: AsyncSession, date: str) -> int:
        """4. 板块集中度 (20): 头部 3 行业资金流入占比

        适度集中最好（30%-50%），过度集中或过度分散都不健康。
        """
        stmt = select(DailySectorFlow.__table__.c.net_inflow).where(
            DailySectorFlow.trade_date == date,
            DailySectorFlow.sector_type == "industry",
        )
        result = await db.execute(stmt)
        inflows = [abs(r[0]) for r in result.all() if r[0] is not None]

        if not inflows:
            return 10

        total_abs = sum(inflows)
        if total_abs == 0:
            return 10

        top3_abs = sum(sorted(inflows, reverse=True)[:3])
        concentration = top3_abs / total_abs  # 0.0 - 1.0

        # 倒 U 型评分：适度集中最好
        if 0.30 <= concentration <= 0.50:
            return 20
        elif 0.20 <= concentration < 0.30 or 0.50 < concentration <= 0.60:
            return 15
        elif 0.10 <= concentration < 0.20 or 0.60 < concentration <= 0.70:
            return 10
        elif 0.0 < concentration < 0.10 or 0.70 < concentration <= 0.80:
            return 5
        else:  # > 0.80 过度集中
            return 0

    @staticmethod
    async def _calc_continuity_score(db: AsyncSession, date: str) -> int:
        """5. 热度延续 (20): 热门主题与前一日 Jaccard 相似度"""
        # 当日主题
        today_stmt = select(DailyHotTheme.theme_name).where(
            DailyHotTheme.trade_date == date,
        )
        today_result = await db.execute(today_stmt)
        today_themes = {r[0] for r in today_result.all()}

        if not today_themes:
            return 10

        # 前一交易日
        prev_stmt = select(func.max(DailyHotTheme.trade_date)).where(
            DailyHotTheme.trade_date < date,
        )
        prev_date_result = await db.execute(prev_stmt)
        prev_date = prev_date_result.scalar()

        if not prev_date:
            return 10  # 无前一日数据 → 中性

        yesterday_stmt = select(DailyHotTheme.theme_name).where(
            DailyHotTheme.trade_date == prev_date,
        )
        yesterday_result = await db.execute(yesterday_stmt)
        yesterday_themes = {r[0] for r in yesterday_result.all()}

        if not yesterday_themes:
            return 10

        intersection = today_themes & yesterday_themes
        union = today_themes | yesterday_themes
        jaccard = len(intersection) / len(union) if union else 0

        return round(jaccard * 20)

    @staticmethod
    async def _calc_temperature(
        northbound: Optional[dict],
        adv: dict,
        date: str,
        db: AsyncSession,
    ) -> dict:
        """5 维度综合评分，每维度 0-20 分，满分 100"""
        scores = {}

        scores["capital"] = await MarketHeatService._calc_capital_score(northbound)
        scores["breadth"] = MarketHeatService._calc_breadth_score(adv)
        scores["sentiment"] = await MarketHeatService._calc_sentiment_score(db, date)
        scores["concentration"] = await MarketHeatService._calc_concentration_score(db, date)
        scores["continuity"] = await MarketHeatService._calc_continuity_score(db, date)

        total_score = sum(scores.values())
        level = MarketHeatService._score_to_level(total_score)

        return {
            "score": total_score,
            "level": level,
            "dimensions": scores,
        }

    @staticmethod
    async def save_temperature(db: AsyncSession, trade_date: str) -> dict:
        """计算并持久化指定交易日市场温度（幂等）"""
        from ..models.stock_tables import DailyMarketTemperature

        # 获取概览所需的基础数据
        nb_stmt = select(DailyNorthboundFlow.__table__).where(
            DailyNorthboundFlow.trade_date == trade_date
        )
        nb_result = await db.execute(nb_stmt)
        nb_row = nb_result.mappings().first()
        northbound = dict(nb_row) if nb_row else None

        # 使用标准日间涨跌幅公式，与 get_change_distribution 一致
        save_daily_a = Daily.__table__.alias()
        save_prev_a = Daily.__table__.alias()
        save_change = (
            (save_daily_a.c.close - func.coalesce(save_daily_a.c.pre_close, save_prev_a.c.close))
            / func.nullif(func.coalesce(save_daily_a.c.pre_close, save_prev_a.c.close), 0)
        )
        adv_stmt = select(
            func.count().label("total"),
            func.sum(case((save_change > 0, 1), else_=0)).label("up_count"),
            func.sum(case((save_change < 0, 1), else_=0)).label("down_count"),
        ).select_from(save_daily_a).outerjoin(
            save_prev_a,
            (save_daily_a.c.ts_code == save_prev_a.c.ts_code)
            & (save_prev_a.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == save_daily_a.c.ts_code)
                    & (Daily.__table__.c.trade_date < trade_date)
                )
                .scalar_subquery()
            )),
        ).where(
            save_daily_a.c.trade_date == trade_date,
            ~save_daily_a.c.ts_code.like("%.IDX"),
        )
        adv_result = await db.execute(adv_stmt)
        adv_row = adv_result.mappings().first()
        adv = dict(adv_row) if adv_row else {"total": 0, "up_count": 0, "down_count": 0}

        temperature = await MarketHeatService._calc_temperature(
            northbound=northbound, adv=adv, date=trade_date, db=db,
        )

        dims = temperature["dimensions"]

        # 幂等 upsert（Core 级别）
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(DailyMarketTemperature.__table__).values(
            trade_date=trade_date,
            score=temperature["score"],
            level=temperature["level"],
            capital_score=dims["capital"],
            breadth_score=dims["breadth"],
            sentiment_score=dims["sentiment"],
            concentration_score=dims["concentration"],
            continuity_score=dims["continuity"],
        ).on_conflict_do_update(
            constraint="uq_market_temp_date",
            set_=dict(
                score=temperature["score"],
                level=temperature["level"],
                capital_score=dims["capital"],
                breadth_score=dims["breadth"],
                sentiment_score=dims["sentiment"],
                concentration_score=dims["concentration"],
                continuity_score=dims["continuity"],
            ),
        )
        await db.execute(stmt)
        await db.commit()

        return temperature

    @staticmethod
    async def get_temperature_history(
        db: AsyncSession, days: int = 60
    ) -> list[dict]:
        """近 N 日市场温度历史"""
        from ..models.stock_tables import DailyMarketTemperature

        stmt = (
            select(DailyMarketTemperature.__table__)
            .order_by(DailyMarketTemperature.__table__.c.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.mappings().all()

        history = []
        for row in reversed(list(rows)):
            r = dict(row)
            history.append({
                "trade_date": r["trade_date"],
                "score": r["score"],
                "level": r["level"],
                "dimensions": {
                    "capital": r["capital_score"],
                    "breadth": r["breadth_score"],
                    "sentiment": r["sentiment_score"],
                    "concentration": r["concentration_score"],
                    "continuity": r["continuity_score"],
                },
            })
        return history

    # ── 四大指数板块温度 ────────────────────────────────────

    # 板块定义：board_code → (board_name, PostgreSQL ts_code 正则)
    BOARD_DEFINITIONS = [
        ("sh_main",  "上证主板", r"^[56]0[0-5]"),
        ("sh_star",  "科创板",   r"^688"),
        ("sz_main",  "深证主板", r"^00[0-3]"),
        ("sz_chi",   "创业板",   r"^30[01]"),
    ]

    @staticmethod
    async def _calc_board_temp(
        db: AsyncSession,
        date: str,
        ts_pattern: str,
    ) -> dict:
        """计算单个板块的温度（3 维度 × 100 分）"""
        from sqlalchemy import text as sa_text

        daily_alias = Daily.__table__.alias()
        prev_alias = Daily.__table__.alias()

        change_expr = (
            (daily_alias.c.close - func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open))
            / func.nullif(func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open), 0)
            * 100
        )

        # 涨跌结构 + 情绪面 + 成交量
        stmt = select(
            func.count().label("total"),
            func.sum(case((daily_alias.c.close > daily_alias.c.open, 1), else_=0)).label("up_count"),
            func.sum(case((daily_alias.c.close < daily_alias.c.open, 1), else_=0)).label("down_count"),
            func.sum(case((change_expr >= 9.8, 1), else_=0)).label("limit_up"),
            func.sum(case((change_expr <= -9.8, 1), else_=0)).label("limit_down"),
            func.sum(daily_alias.c.amount).label("total_amount"),
        ).select_from(daily_alias).outerjoin(
            prev_alias,
            (daily_alias.c.ts_code == prev_alias.c.ts_code)
            & (prev_alias.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                    & (Daily.__table__.c.trade_date < date)
                )
                .scalar_subquery()
            )),
        ).where(
            daily_alias.c.trade_date == date,
            ~daily_alias.c.ts_code.like("%.IDX"),
            sa_text(f"daily_1.ts_code ~ '{ts_pattern}'"),
        )

        result = await db.execute(stmt)
        row = result.mappings().first()
        if not row or (row.get("total", 0) or 0) == 0:
            return {"score": 50, "level": "中性",
                    "dimensions": {"breadth": 20, "sentiment": 15, "volume": 15}}

        total = row["total"] or 0
        up = row["up_count"] or 0
        limit_up = row["limit_up"] or 0
        limit_down = row["limit_down"] or 0
        total_amount = row["total_amount"] or 0

        # 1. 涨跌结构 (0-40)
        ratio = up / total if total > 0 else 0.5
        breadth = min(40, round(ratio * 50))

        # 2. 情绪面 (0-30)
        total_limits = limit_up + limit_down
        if total_limits > 0:
            limit_ratio = limit_up / total_limits
            activity = min(1.0, total_limits / (total * 0.03))  # 活跃度：3%触及涨跌停即满分
            sentiment = round(limit_ratio * 30 * (0.5 + 0.5 * activity))
        else:
            sentiment = 15

        # 3. 量能活跃度 (0-30): 当日成交额 vs 近20日日均成交额
        # 先按日汇总板块成交额，再取20日均值
        daily_sum_subq = (
            select(
                Daily.__table__.c.trade_date,
                func.sum(Daily.__table__.c.amount).label("daily_total"),
            )
            .where(
                Daily.__table__.c.trade_date < date,
                sa_text(f"daily.ts_code ~ '{ts_pattern}'"),
                ~Daily.__table__.c.ts_code.like("%.IDX"),
            )
            .group_by(Daily.__table__.c.trade_date)
            .order_by(Daily.__table__.c.trade_date.desc())
            .limit(20)
        ).subquery()
        avg_amt_stmt = select(func.avg(daily_sum_subq.c.daily_total))
        avg_result = await db.execute(avg_amt_stmt)
        avg_amount = avg_result.scalar() or total_amount

        if avg_amount and avg_amount > 0 and total_amount > 0:
            vol_ratio = total_amount / avg_amount
            volume = min(30, round(vol_ratio * 15))
        else:
            volume = 15

        # 防护：有交易股票时量能不能为 0（数据不完整时 vol_ratio 可能极小）
        if total > 0 and volume == 0:
            import logging
            logging.getLogger("market_heat").warning(
                f"板块 {ts_pattern} trade_date={date} volume=0（total={total}, "
                f"total_amount={total_amount}, avg_amount={avg_amount}），修正为 1"
            )
            volume = 1

        scores = {"breadth": breadth, "sentiment": max(0, min(30, sentiment)), "volume": max(0, min(30, volume))}
        total_score = sum(scores.values())
        level = MarketHeatService._score_to_level(total_score)

        return {"score": total_score, "level": level, "dimensions": scores}

    @staticmethod
    async def save_board_temperatures(db: AsyncSession, trade_date: str) -> list[dict]:
        """计算并持久化四大板块温度（幂等）"""
        from ..models.stock_tables import DailyBoardTemperature
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        results = []
        for board_code, board_name, ts_pattern in MarketHeatService.BOARD_DEFINITIONS:
            temp = await MarketHeatService._calc_board_temp(db, trade_date, ts_pattern)
            dims = temp["dimensions"]

            stmt = pg_insert(DailyBoardTemperature.__table__).values(
                trade_date=trade_date,
                board_code=board_code,
                board_name=board_name,
                score=temp["score"],
                level=temp["level"],
                breadth_score=dims["breadth"],
                sentiment_score=dims["sentiment"],
                volume_score=dims["volume"],
            ).on_conflict_do_update(
                constraint="uq_board_temp",
                set_=dict(
                    score=temp["score"],
                    level=temp["level"],
                    breadth_score=dims["breadth"],
                    sentiment_score=dims["sentiment"],
                    volume_score=dims["volume"],
                ),
            )
            await db.execute(stmt)
            results.append({
                "board_code": board_code,
                "board_name": board_name,
                **temp,
            })

        await db.commit()
        return results

    @staticmethod
    async def get_board_temperatures(
        db: AsyncSession, trade_date: Optional[str] = None
    ) -> list[dict]:
        """获取指定日期的板块温度（默认最新）"""
        from ..models.stock_tables import DailyBoardTemperature

        if not trade_date:
            stmt = select(func.max(DailyBoardTemperature.__table__.c.trade_date))
            result = await db.execute(stmt)
            trade_date = result.scalar()
        if not trade_date:
            return []

        stmt = select(DailyBoardTemperature.__table__).where(
            DailyBoardTemperature.__table__.c.trade_date == trade_date,
        ).order_by(DailyBoardTemperature.__table__.c.board_code)
        result = await db.execute(stmt)
        rows = result.mappings().all()

        return [
            {
                "board_code": r["board_code"],
                "board_name": r["board_name"],
                "score": r["score"],
                "level": r["level"],
                "dimensions": {
                    "breadth": r["breadth_score"],
                    "sentiment": r["sentiment_score"],
                    "volume": r["volume_score"],
                },
            }
            for r in rows
        ]

    @staticmethod
    async def get_board_temperature_history(
        db: AsyncSession, board_code: str, days: int = 60
    ) -> list[dict]:
        """近 N 日板块温度历史"""
        from ..models.stock_tables import DailyBoardTemperature

        stmt = (
            select(DailyBoardTemperature.__table__)
            .where(DailyBoardTemperature.__table__.c.board_code == board_code)
            .order_by(DailyBoardTemperature.__table__.c.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.mappings().all()

        history = []
        for row in reversed(list(rows)):
            r = dict(row)
            history.append({
                "trade_date": r["trade_date"],
                "board_code": r["board_code"],
                "board_name": r["board_name"],
                "score": r["score"],
                "level": r["level"],
                "dimensions": {
                    "breadth": r["breadth_score"],
                    "sentiment": r["sentiment_score"],
                    "volume": r["volume_score"],
                },
            })
        return history

    # ── 涨跌分布 ─────────────────────────────────────────────

    @staticmethod
    async def get_change_distribution(
        db: AsyncSession, trade_date: Optional[str] = None, board: Optional[str] = None
    ) -> list[dict]:
        """涨跌幅度分段统计（用于柱状图）

        使用标准当日涨跌幅公式：(close - pre_close) / pre_close * 100。
        优先使用同步时存储的 pre_close（同一复权因子），NULL 时回退到自连接的前一交易日 close。
        """
        date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        if not date:
            return []

        # 板块过滤：从 BOARD_DEFINITIONS 取正则
        ts_pattern: Optional[str] = None
        if board:
            for code, _name, pattern in MarketHeatService.BOARD_DEFINITIONS:
                if code == board:
                    ts_pattern = pattern
                    break
            if ts_pattern is None:
                return []  # 无效 board 参数

        from sqlalchemy import text as sa_text

        # 自连接：优先使用 pre_close，回退到前一交易日 close
        daily_alias = Daily.__table__.alias()
        prev_alias = Daily.__table__.alias()

        change_expr = (
            (daily_alias.c.close - func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open))
            / func.nullif(func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open), 0)
            * 100
        )

        buckets = [
            (-100, -10, "-10%以下"),
            (-10, -5, "-10%~-5%"),
            (-5, -2, "-5%~-2%"),
            (-2, 0, "-2%~0%"),
            (0, 2, "0%~2%"),
            (2, 5, "2%~5%"),
            (5, 10, "5%~10%"),
            (10, 100, "10%以上"),
        ]

        # 单个聚合查询一次性统计所有分段，比 8 次 COUNT 更高效
        where_conds = [
            daily_alias.c.trade_date == date,
            ~daily_alias.c.ts_code.like("%.IDX"),
        ]
        if ts_pattern:
            where_conds.append(sa_text(f"daily_1.ts_code ~ '{ts_pattern}'"))

        agg_cols = [
            func.sum(
                case((and_(change_expr >= lo, change_expr < hi), 1), else_=0)
            ).label(label)
            for lo, hi, label in buckets
        ]

        stmt = (
            select(*agg_cols)
            .select_from(daily_alias)
            .outerjoin(
                prev_alias,
                (daily_alias.c.ts_code == prev_alias.c.ts_code)
                & (prev_alias.c.trade_date == (
                    select(func.max(Daily.__table__.c.trade_date))
                    .where(
                        (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                        & (Daily.__table__.c.trade_date < date)
                    )
                    .scalar_subquery()
                )),
            )
            .where(and_(*where_conds))
        )

        result_row = (await db.execute(stmt)).mappings().first()

        result = []
        for lo, hi, label in buckets:
            cnt = result_row[label] if result_row else 0
            result.append({"label": label, "lo": lo, "hi": hi, "count": cnt or 0})

        return result

    # ── 领涨板块个股 ──────────────────────────────────────────

    @staticmethod
    async def get_leading_sector_stocks(
        db: AsyncSession, sector_name: str, trade_date: Optional[str] = None,
        sort_order: str = "desc",
    ) -> list[dict]:
        """板块内个股 Top 15：sort_order='desc' 领涨（涨幅靠前），'asc' 领跌（跌幅靠前）"""
        date = trade_date or await MarketHeatService._get_latest_date_for(db, Daily.__table__.c)
        if not date:
            return []

        from ..models.stock_tables import Stock

        # 标准当日涨跌幅 = (close - pre_close) / pre_close * 100
        # 优先使用同步时存储的 pre_close（同一复权因子），保证计算正确
        # 对于历史数据 pre_close 可能为 NULL，则回退到关联子查询
        PrevDaily = aliased(Daily)
        pre_close_subq = (
            select(PrevDaily.close)
            .where(PrevDaily.ts_code == Stock.ts_code, PrevDaily.trade_date < date)
            .order_by(PrevDaily.trade_date.desc())
            .limit(1)
            .correlate(Stock)
            .scalar_subquery()
        )
        effective_pre_close = func.coalesce(Daily.pre_close, pre_close_subq)
        change_expr = (
            (Daily.close - effective_pre_close)
            / func.nullif(effective_pre_close, 0) * 100
        )
        order_clause = change_expr.desc() if sort_order == "desc" else change_expr.asc()

        # 模糊匹配板块→个股行业/概念
        match_cond = _build_sector_stock_match(sector_name, Stock)

        stmt = (
            select(
                Stock.ts_code, Stock.name, Daily.close, Daily.open,
                change_expr.label("change_pct"),
            )
            .join(Daily, Stock.ts_code == Daily.ts_code)
            .where(
                Daily.trade_date == date,
                match_cond,
                ~Stock.ts_code.like("%.IDX"),
            )
            .order_by(order_clause)
            .limit(15)
        )
        result = await db.execute(stmt)
        return [
            {"ts_code": r.ts_code, "name": r.name, "close": r.close, "open": r.open,
             "change_pct": round(r.change_pct, 2) if r.change_pct else None}
            for r in result.all()
        ]

    # ── 板块资金流综合 ────────────────────────────────────────

    @staticmethod
    async def get_sector_fund_overview(
        db: AsyncSession, trade_date: Optional[str] = None
    ) -> dict:
        """板块资金流总览 — 当日全行业板块资金净额合计"""
        from datetime import date as _date

        d = trade_date or await MarketHeatService._get_latest_date_for(
            db, DailySectorFlow.__table__.c
        )
        if not d:
            return {"trade_date": None, "total_net_yi": 0, "sector_count": 0}

        async def _query(td: str) -> dict:
            stmt = select(
                func.sum(DailySectorFlow.__table__.c.net_inflow).label("total_net"),
                func.count().label("cnt"),
            ).where(
                DailySectorFlow.__table__.c.trade_date == td,
                DailySectorFlow.__table__.c.sector_type == "industry",
            )
            result = await db.execute(stmt)
            row = result.mappings().first()
            normalized = _normalize_trade_date(td)
            return {
                "trade_date": normalized,
                "total_net_yi": round(row["total_net"] or 0, 2),
                "sector_count": row["cnt"] or 0,
            }

        data = await _query(d)
        if not data.get("sector_count") and trade_date:
            fallback = await MarketHeatService._get_latest_date_for(
                db, DailySectorFlow.__table__.c
            )
            if fallback and fallback != d:
                data = await _query(fallback)
        return data

    @staticmethod
    async def get_sector_fund_history(
        db: AsyncSession, days: int = 90
    ) -> list[dict]:
        """板块资金流历史 — 近 N 日每日全行业资金净额合计"""
        from datetime import date as _date, timedelta
        cutoff = (_date.today() - timedelta(days=days)).strftime('%Y%m%d')

        stmt = (
            select(
                DailySectorFlow.__table__.c.trade_date,
                func.sum(DailySectorFlow.__table__.c.net_inflow).label("total_net_yi"),
                func.count().label("sector_count"),
            )
            .where(
                DailySectorFlow.__table__.c.sector_type == "industry",
                DailySectorFlow.__table__.c.trade_date >= cutoff,
            )
            .group_by(DailySectorFlow.__table__.c.trade_date)
            .order_by(DailySectorFlow.__table__.c.trade_date.asc())
        )
        result = await db.execute(stmt)
        rows = result.mappings().all()

        history = []
        for row in rows:
            history.append({
                "trade_date": _normalize_trade_date(row["trade_date"]),
                "total_net_yi": round(row["total_net_yi"] or 0, 2),
                "sector_count": row["sector_count"] or 0,
            })
        return history

    # ── 市场压力指数 ─────────────────────────────────────────

    @staticmethod
    def _score_to_stress_level(score: int) -> str:
        if score <= 25:
            return "平稳"
        elif score <= 40:
            return "关注"
        elif score <= 60:
            return "压力"
        elif score <= 80:
            return "恐慌"
        return "危机"

    @staticmethod
    def _calc_decline_score(avg_return: float) -> float:
        """1. 指数跌幅 (0-25): 全 A 等权涨跌幅分档"""
        pct = avg_return * 100  # 转为百分比
        if pct > 2:
            return 0
        elif pct > 1:
            return 3
        elif pct > 0:
            return 8
        elif pct > -1:
            return 12
        elif pct > -2:
            return 16
        elif pct > -3:
            return 20
        elif pct > -4:
            return 23
        return 25

    @staticmethod
    def _calc_volatility_score(ann_vol: float) -> float:
        """2. 波动率 (0-25): 20 日年化波动率分档"""
        # ann_vol 为小数，如 0.20 = 20%
        vol_pct = ann_vol * 100
        if vol_pct < 15:
            return 0
        elif vol_pct < 20:
            return 5
        elif vol_pct < 25:
            return 10
        elif vol_pct < 30:
            return 15
        elif vol_pct < 40:
            return 20
        return 25

    @staticmethod
    def _calc_limitdown_pressure_score(ld_ratio: float) -> float:
        """3. 跌停潮 (0-25): 跌停占比分档"""
        # ld_ratio 为百分比，如 0.02 = 2%
        pct = ld_ratio * 100
        if pct < 0.5:
            return 0
        elif pct < 1:
            return 5
        elif pct < 2:
            return 10
        elif pct < 5:
            return 15
        elif pct < 10:
            return 20
        return 25

    @staticmethod
    def _calc_stress_breadth_score(down_ratio: float) -> float:
        """4. 下跌广度 (0-15): 下跌家数占比分档"""
        pct = down_ratio * 100
        if pct < 40:
            return 0
        elif pct < 50:
            return 3
        elif pct < 60:
            return 6
        elif pct < 70:
            return 9
        elif pct < 80:
            return 12
        return 15

    @staticmethod
    def _calc_stress_northbound_score(net_yi: Optional[float]) -> float:
        """5. 北向出逃 (0-10): 净流出金额分档"""
        if net_yi is None:
            return 3  # 无数据中性
        if net_yi >= 0:
            return 0
        if net_yi > -20:
            return 2
        if net_yi > -50:
            return 4
        if net_yi > -100:
            return 7
        return 10

    @staticmethod
    async def _calc_stress_index(
        northbound: Optional[dict],
        adv: dict,
        date: str,
        db: AsyncSession,
    ) -> dict:
        """5 维度综合评分，满分 100，越高越恐慌"""
        scores = {}

        # 1. 指数跌幅 (0-25): 全 A 等权涨跌幅
        from sqlalchemy import text as sa_text
        # 合并 pre_close 或自连接获取前收盘
        daily_alias = Daily.__table__.alias()
        prev_alias = Daily.__table__.alias()
        change_expr = (
            (daily_alias.c.close - func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open))
            / func.nullif(func.coalesce(daily_alias.c.pre_close, prev_alias.c.close, daily_alias.c.open), 0)
        )
        avg_return_stmt = select(func.avg(change_expr)).select_from(daily_alias).outerjoin(
            prev_alias,
            (daily_alias.c.ts_code == prev_alias.c.ts_code)
            & (prev_alias.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == daily_alias.c.ts_code)
                    & (Daily.__table__.c.trade_date < date)
                )
                .scalar_subquery()
            )),
        ).where(
            daily_alias.c.trade_date == date,
            ~daily_alias.c.ts_code.like("%.IDX"),
            ~daily_alias.c.ts_code.like("%.BJ"),  # 排除北交所
        )
        avg_result = await db.execute(avg_return_stmt)
        avg_return = avg_result.scalar() or 0
        scores["decline"] = MarketHeatService._calc_decline_score(avg_return)

        # 2. 波动率 (0-25): 近 20 日全 A 等权日收益的 std × √252
        import math
        # 获取近 21 个交易日（含当日）的日期列表
        dates_stmt = (
            select(Daily.__table__.c.trade_date)
            .distinct()
            .where(Daily.__table__.c.trade_date <= date)
            .order_by(Daily.__table__.c.trade_date.desc())
            .limit(22)
        )
        dates_result = await db.execute(dates_stmt)
        dates = [r[0] for r in dates_result.all()]
        dates_sorted = sorted(dates)  # 升序

        if len(dates_sorted) >= 5:
            # 逐日计算等权日收益率
            daily_returns = []
            for d in dates_sorted:
                d_alias = Daily.__table__.alias()
                p_alias = Daily.__table__.alias()
                daily_chg = (
                    (d_alias.c.close - func.coalesce(d_alias.c.pre_close, p_alias.c.close, d_alias.c.open))
                    / func.nullif(func.coalesce(d_alias.c.pre_close, p_alias.c.close, d_alias.c.open), 0)
                )
                d_stmt = select(func.avg(daily_chg)).select_from(d_alias).outerjoin(
                    p_alias,
                    (d_alias.c.ts_code == p_alias.c.ts_code)
                    & (p_alias.c.trade_date == (
                        select(func.max(Daily.__table__.c.trade_date))
                        .where(
                            (Daily.__table__.c.ts_code == d_alias.c.ts_code)
                            & (Daily.__table__.c.trade_date < d)
                        )
                        .scalar_subquery()
                    )),
                ).where(
                    d_alias.c.trade_date == d,
                    ~d_alias.c.ts_code.like("%.IDX"),
                    ~d_alias.c.ts_code.like("%.BJ"),
                )
                d_result = await db.execute(d_stmt)
                d_ret = d_result.scalar()
                if d_ret is not None:
                    daily_returns.append(d_ret)

            if len(daily_returns) >= 5:
                mean_ret = sum(daily_returns) / len(daily_returns)
                variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
                daily_std = math.sqrt(variance)
                ann_vol = daily_std * math.sqrt(252)  # 年化波动率
            else:
                ann_vol = 0.15  # 默认 15%
        else:
            ann_vol = 0.15
        scores["volatility"] = MarketHeatService._calc_volatility_score(ann_vol)

        # 3. 跌停潮 (0-25): 跌停数(≤-9.8%) / 总股票数
        limit_alias = Daily.__table__.alias()
        lp_alias = Daily.__table__.alias()
        ld_change = (
            (limit_alias.c.close - func.coalesce(limit_alias.c.pre_close, lp_alias.c.close, limit_alias.c.open))
            / func.nullif(func.coalesce(limit_alias.c.pre_close, lp_alias.c.close, limit_alias.c.open), 0)
        )
        ld_stmt = select(
            func.count().label("total"),
            func.sum(case((ld_change <= -0.098, 1), else_=0)).label("limit_down"),
        ).select_from(limit_alias).outerjoin(
            lp_alias,
            (limit_alias.c.ts_code == lp_alias.c.ts_code)
            & (lp_alias.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == limit_alias.c.ts_code)
                    & (Daily.__table__.c.trade_date < date)
                )
                .scalar_subquery()
            )),
        ).where(
            limit_alias.c.trade_date == date,
            ~limit_alias.c.ts_code.like("%.IDX"),
            ~limit_alias.c.ts_code.like("%.BJ"),
        )
        ld_result = await db.execute(ld_stmt)
        ld_row = ld_result.mappings().first()
        ld_total = ld_row["total"] or 0
        ld_count = ld_row["limit_down"] or 0
        ld_ratio = ld_count / ld_total if ld_total > 0 else 0
        scores["limitdown"] = MarketHeatService._calc_limitdown_pressure_score(ld_ratio)

        # 4. 下跌广度 (0-15)
        adv_total = adv.get("total", 0) or 0
        adv_down = adv.get("down_count", 0) or 0
        down_ratio = adv_down / adv_total if adv_total > 0 else 0.5
        scores["breadth"] = MarketHeatService._calc_stress_breadth_score(down_ratio)

        # 5. 北向出逃 (0-10)
        net_yi = northbound.get("total_net_yi") if northbound else None
        scores["northbound"] = MarketHeatService._calc_stress_northbound_score(net_yi)

        total_score = round(sum(scores.values()))
        level = MarketHeatService._score_to_stress_level(total_score)

        return {
            "score": total_score,
            "level": level,
            "dimensions": scores,
        }

    @staticmethod
    async def save_stress_index(db: AsyncSession, trade_date: str) -> dict:
        """计算并持久化指定交易日市场压力指数（幂等）"""
        # 获取北向数据
        nb_stmt = select(DailyNorthboundFlow.__table__).where(
            DailyNorthboundFlow.trade_date == trade_date
        )
        nb_result = await db.execute(nb_stmt)
        nb_row = nb_result.mappings().first()
        northbound = dict(nb_row) if nb_row else None

        # 获取涨跌数据
        # 使用标准日间涨跌幅公式，与 get_change_distribution 一致
        stress_daily_a = Daily.__table__.alias()
        stress_prev_a = Daily.__table__.alias()
        stress_change = (
            (stress_daily_a.c.close - func.coalesce(stress_daily_a.c.pre_close, stress_prev_a.c.close))
            / func.nullif(func.coalesce(stress_daily_a.c.pre_close, stress_prev_a.c.close), 0)
        )
        adv_stmt = select(
            func.count().label("total"),
            func.sum(case((stress_change > 0, 1), else_=0)).label("up_count"),
            func.sum(case((stress_change < 0, 1), else_=0)).label("down_count"),
        ).select_from(stress_daily_a).outerjoin(
            stress_prev_a,
            (stress_daily_a.c.ts_code == stress_prev_a.c.ts_code)
            & (stress_prev_a.c.trade_date == (
                select(func.max(Daily.__table__.c.trade_date))
                .where(
                    (Daily.__table__.c.ts_code == stress_daily_a.c.ts_code)
                    & (Daily.__table__.c.trade_date < trade_date)
                )
                .scalar_subquery()
            )),
        ).where(
            stress_daily_a.c.trade_date == trade_date,
            ~stress_daily_a.c.ts_code.like("%.IDX"),
        )
        adv_result = await db.execute(adv_stmt)
        adv_row = adv_result.mappings().first()
        adv = dict(adv_row) if adv_row else {"total": 0, "up_count": 0, "down_count": 0}

        stress = await MarketHeatService._calc_stress_index(
            northbound=northbound, adv=adv, date=trade_date, db=db,
        )

        dims = stress["dimensions"]

        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(DailyMarketStress.__table__).values(
            trade_date=trade_date,
            score=stress["score"],
            level=stress["level"],
            decline_score=dims["decline"],
            volatility_score=dims["volatility"],
            limitdown_score=dims["limitdown"],
            breadth_score=dims["breadth"],
            northbound_score=dims["northbound"],
        ).on_conflict_do_update(
            constraint="uq_market_stress_date",
            set_=dict(
                score=stress["score"],
                level=stress["level"],
                decline_score=dims["decline"],
                volatility_score=dims["volatility"],
                limitdown_score=dims["limitdown"],
                breadth_score=dims["breadth"],
                northbound_score=dims["northbound"],
            ),
        )
        await db.execute(stmt)
        await db.commit()

        return stress

    @staticmethod
    async def get_stress_overview(
        db: AsyncSession, trade_date: Optional[str] = None
    ) -> Optional[dict]:
        """获取指定日期压力指数概览"""
        if not trade_date:
            stmt = select(func.max(DailyMarketStress.__table__.c.trade_date))
            result = await db.execute(stmt)
            trade_date = result.scalar()
        if not trade_date:
            return None

        stmt = select(DailyMarketStress.__table__).where(
            DailyMarketStress.__table__.c.trade_date == trade_date,
        )
        result = await db.execute(stmt)
        row = result.mappings().first()
        if not row:
            return None

        r = dict(row)
        return {
            "trade_date": r["trade_date"],
            "score": r["score"],
            "level": r["level"],
            "dimensions": {
                "decline": r["decline_score"],
                "volatility": r["volatility_score"],
                "limitdown": r["limitdown_score"],
                "breadth": r["breadth_score"],
                "northbound": r["northbound_score"],
            },
        }

    @staticmethod
    async def get_stress_history(
        db: AsyncSession, days: int = 60
    ) -> list[dict]:
        """近 N 日压力指数历史"""
        stmt = (
            select(DailyMarketStress.__table__)
            .order_by(DailyMarketStress.__table__.c.trade_date.desc())
            .limit(days)
        )
        result = await db.execute(stmt)
        rows = result.mappings().all()

        history = []
        for row in reversed(list(rows)):
            r = dict(row)
            history.append({
                "trade_date": r["trade_date"],
                "score": r["score"],
                "level": r["level"],
                "dimensions": {
                    "decline": r["decline_score"],
                    "volatility": r["volatility_score"],
                    "limitdown": r["limitdown_score"],
                    "breadth": r["breadth_score"],
                    "northbound": r["northbound_score"],
                },
            })
        return history
