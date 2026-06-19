#!/usr/bin/env python3
"""
财报数据同步 — mootdx finance（36字段快照）+ 新浪三表（多期）

mootdx finance 返回单行快照（拼音字段名）:
  zongguben(总股本), liutongguben(流通股本), zongzichan(总资产),
  zhuyingshouru(主营收入), jinglirun(净利润), meigujingzichan(每股净资产),
  jingyingxianjinliu(经营现金流), liudongfuzhai(流动负债),
  changqifuzhai(长期负债), liudongzichan(流动资产), cunhuo(存货) 等36字段

新浪三表 API 返回多期 lrb/fzb/llb 数据，可获取近5年财报。

用法：
    venv/bin/python scripts/sync_financials.py --init   # 全量近5年
    venv/bin/python scripts/sync_financials.py          # 增量（最新一期）
    venv/bin/python scripts/sync_financials.py --code 600519  # 单票测试

cron（每季度财报季结束后第一周）:
    0 3 2 5,9,11 * * cd /opt/AIpicking/backend && venv/bin/python scripts/sync_financials.py
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent.parent
for _env_file in (".env", ".env.production"):
    _path = _ENV_DIR / _env_file
    if _path.exists():
        load_dotenv(_path, override=True)


def _parse_pg_url(url: str) -> dict:
    url = url.replace("+asyncpg", "").replace("+psycopg2", "")
    from urllib.parse import urlparse
    r = urlparse(url)
    return {
        "host": r.hostname or "localhost",
        "port": r.port or 5432,
        "user": r.username or "aipicking",
        "password": r.password or "",
        "dbname": r.path.lstrip("/") or "aipicking",
    }


_default_db = os.getenv("DATABASE_URL", "")
if not _default_db:
    _user = os.getenv("DB_USER", "aipicking")
    _pass = os.getenv("DB_PASSWORD", "")
    _host = os.getenv("DB_HOST", "localhost")
    _port = os.getenv("DB_PORT", "5432")
    _name = os.getenv("DB_NAME", "aipicking")
    _default_db = f"postgresql://{_user}:{_pass}@{_host}:{_port}/{_name}"
_PG_PARAMS = _parse_pg_url(_default_db)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 新浪财务三表 API（返回多期数据，支持近5年）
SINA_FIN_URL = (
    "https://quotes.sina.cn/cn/api/openapi.php/"
    "CompanyFinanceService.getFinanceReport2022"
)

# 报告期 MM-DD → report_type
PERIOD_TYPE_MAP = {
    "0331": "Q1", "0630": "Q2", "0930": "Q3", "1231": "FY",
}

# mootdx finance 拼音字段 → 含义
# 完整 36 字段: market, code, liutongguben, province, industry, updated_date,
# ipo_date, zongguben, guojiagu, faqirenfarengu, farengu, bgu, hgu, zhigonggu,
# zongzichan, liudongzichan, gudingzichan, wuxingzichan, gudongrenshu,
# liudongfuzhai, changqifuzhai, zibengongjijin, jingzichan, zhuyingshouru,
# zhuyinglirun, yingshouzhangkuan, yingyelirun, touzishouyu,
# jingyingxianjinliu, zongxianjinliu, cunhuo, lirunzonghe,
# shuihoulirun, jinglirun, weifenpeilirun, meigujingzichan, baoliu2


def get_conn():
    return psycopg2.connect(**_PG_PARAMS)


def load_stocks():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT ts_code, symbol FROM stocks "
        "WHERE ts_code IS NOT NULL AND ts_code != '' "
        "AND (type IS NULL OR type = 'stock')"
    )
    rows = cur.fetchall()
    conn.close()
    return [{"ts_code": r[0], "symbol": r[1]} for r in rows]


def report_type_from_date(report_date: str) -> str:
    """从 YYYYMMDD 格式推导报告期类型"""
    mmdd = report_date[4:]
    return PERIOD_TYPE_MAP.get(mmdd, "Q1")


def latest_quarter_end(updated_date: int) -> str:
    """根据 updated_date（YYYYMMDD 整数）推算最近财季末日期"""
    d = datetime.strptime(str(updated_date), "%Y%m%d")
    # 找出最近已过的季末
    candidates = [
        d.replace(month=3, day=31),
        d.replace(month=6, day=30),
        d.replace(month=9, day=30),
        d.replace(month=12, day=31),
    ]
    # 若 updated_date 在某个季末之前，退回上一个季末
    quarter_end = None
    for c in reversed(candidates):
        if d >= c:
            quarter_end = c
            break
    if quarter_end is None:
        quarter_end = candidates[-1]  # fallback
    return quarter_end.strftime("%Y-%m-%d")


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def fetch_mootdx_finance(ts_code: str) -> Optional[dict]:
    """从 mootdx 拉取单只股票财务快照（单行 dict）"""
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std")
        data = client.finance(symbol=ts_code)
        if data is None or (hasattr(data, "empty") and data.empty):
            return None
        if hasattr(data, "iloc"):
            row = data.iloc[0]
            if hasattr(row, "to_dict"):
                return row.to_dict()
            else:
                return dict(row)
        elif isinstance(data, dict):
            return data
        return None
    except Exception as e:
        print(f"  ⚠️ mootdx finance({ts_code}) 失败: {e}")
        return None


def fetch_sina_financials(ts_code: str, periods: int = 4) -> Optional[dict]:
    """从新浪拉取多期三表数据（资产负债表/利润表/现金流量表）

    返回 {"lrb": {...}, "fzb": {...}, "llb": {...}}
    每个 source 是 dict，key 为 report_date ("20260331")，
    value 为 {publish_date, data: [{item_title, item_value}, ...]}

    periods 控制拉取期数（每页一期，API num 参数）。
    """
    # 去掉交易所后缀（如 .SH/.SZ），新浪只需要纯数字
    code_clean = ts_code.split(".")[0]
    prefix = "sh" if code_clean.startswith(("6", "9")) else ("bj" if code_clean.startswith("8") else "sz")
    paper_code = f"{prefix}{code_clean}"
    result = {}
    for src in ("lrb", "fzb", "llb"):
        params = {
            "paperCode": paper_code, "source": src,
            "type": "0", "page": "1", "num": str(periods),
        }
        try:
            r = requests.get(
                SINA_FIN_URL, params=params,
                headers={"User-Agent": UA}, timeout=15,
            )
            d = r.json()
            report_list = d.get("result", {}).get("data", {}).get("report_list", {})
            if report_list and isinstance(report_list, dict):
                result[src] = report_list
        except Exception:
            pass
        time.sleep(0.3)
    return result if result else None


def parse_mootdx_snapshot(d: dict, ts_code: str) -> Optional[dict]:
    """将 mootdx finance 快照解析为 financial_reports 记录"""

    updated_date = d.get("updated_date")
    if not updated_date:
        return None

    report_date = latest_quarter_end(int(updated_date))
    if not report_date:
        return None

    report_date_clean = report_date.replace("-", "")

    total_shares_raw = d.get("zongguben")
    total_shares = int(total_shares_raw) if total_shares_raw else None

    float_shares_raw = d.get("liutongguben")
    float_shares = int(float_shares_raw) if float_shares_raw else None

    total_assets = _safe_float(d.get("zongzichan"))
    current_assets = _safe_float(d.get("liudongzichan"))
    current_liabilities = _safe_float(d.get("liudongfuzhai"))
    longterm_liabilities = _safe_float(d.get("changqifuzhai"))
    shareholders_equity = _safe_float(d.get("jingzichan"))
    inventory = _safe_float(d.get("cunhuo"))

    revenue = _safe_float(d.get("zhuyingshouru"))
    net_profit = _safe_float(d.get("jinglirun"))
    cf_operating = _safe_float(d.get("jingyingxianjinliu"))
    bvps = _safe_float(d.get("meigujingzichan"))

    # 计算衍生指标
    eps = round(net_profit / total_shares, 4) if net_profit and total_shares else None
    roe = round(net_profit / shareholders_equity * 100, 2) if net_profit and shareholders_equity and shareholders_equity != 0 else None

    total_liabilities = None
    if current_liabilities is not None and longterm_liabilities is not None:
        total_liabilities = current_liabilities + longterm_liabilities
        if total_assets and total_assets != 0:
            debt_to_assets = round(total_liabilities / total_assets * 100, 2)
        else:
            debt_to_assets = None
    elif current_liabilities is not None and longterm_liabilities is None:
        total_liabilities = current_liabilities
        if total_assets and total_assets != 0:
            debt_to_assets = round(current_liabilities / total_assets * 100, 2)
        else:
            debt_to_assets = None
    else:
        debt_to_assets = None

    current_ratio = None
    if current_assets and current_liabilities and current_liabilities != 0:
        current_ratio = round(current_assets / current_liabilities, 4)

    quick_ratio = None
    if current_assets and current_liabilities and current_liabilities != 0:
        if inventory is not None:
            quick_ratio = round((current_assets - inventory) / current_liabilities, 4)
        else:
            quick_ratio = round(current_assets / current_liabilities, 4)

    return {
        "ts_code": ts_code,
        "report_date": report_date,
        "report_type": report_type_from_date(report_date_clean),
        "pub_date": datetime.strptime(str(updated_date), "%Y%m%d").strftime("%Y-%m-%d"),
        "eps": eps,
        "bvps": bvps,
        "roe": roe,
        "roa": None,
        "gross_margin": None,
        "net_margin": None,
        "net_profit": net_profit,
        "net_profit_yoy": None,
        "revenue": revenue,
        "revenue_yoy": None,
        "debt_to_assets": debt_to_assets,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "cf_operating": cf_operating,
        "cf_ratio": None,
        "total_shares": total_shares,
        "float_shares": float_shares,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "shareholders_equity": shareholders_equity,
        "source": "mootdx",
    }


def parse_sina_period(lrb_data: Optional[list], fzb_data: Optional[list],
                      llb_data: Optional[list], ts_code: str,
                      report_date_raw: str,
                      pub_date: Optional[str] = None) -> Optional[dict]:
    """将新浪单期三表数据解析为 financial_reports 记录

    新浪 item 结构: {"item_title": "营业总收入", "item_value": "54702912385.23", ...}
    """
    # 将 item list 转为 dict
    def _items_dict(items_list: Optional[list]) -> dict:
        if not items_list:
            return {}
        return {it.get("item_title", ""): it.get("item_value") for it in items_list}

    lrb = _items_dict(lrb_data)
    fzb = _items_dict(fzb_data)
    llb = _items_dict(llb_data)

    # report_date 格式 "20260331" → "2026-03-31"
    if len(report_date_raw) != 8:
        return None
    report_date = f"{report_date_raw[:4]}-{report_date_raw[4:6]}-{report_date_raw[6:8]}"
    report_type = report_type_from_date(report_date_raw)

    # 利润表字段
    revenue = _safe_float(lrb.get("营业总收入"))
    cost = _safe_float(lrb.get("营业总成本"))
    net_profit = _safe_float(lrb.get("净利润"))
    operating_profit = _safe_float(lrb.get("营业利润"))

    gross_margin = None
    if revenue and cost and revenue != 0:
        gross_margin = round((revenue - cost) / revenue * 100, 2)

    net_margin = None
    if net_profit and revenue and revenue != 0:
        net_margin = round(net_profit / revenue * 100, 2)

    # 资产负债表字段
    total_assets = _safe_float(fzb.get("资产总计"))
    total_liabilities = _safe_float(fzb.get("负债合计"))
    current_assets = _safe_float(fzb.get("流动资产合计"))
    current_liabilities = _safe_float(fzb.get("流动负债合计"))
    shareholders_equity = _safe_float(fzb.get("归属于母公司股东权益合计"))
    if shareholders_equity is None:
        shareholders_equity = _safe_float(fzb.get("归属母公司股东权益合计"))
    if shareholders_equity is None:
        shareholders_equity = _safe_float(fzb.get("股东权益合计"))
    if shareholders_equity is None:
        shareholders_equity = _safe_float(fzb.get("所有者权益(或股东权益)合计"))
    total_shares_raw = _safe_float(fzb.get("实收资本(或股本)"))
    if total_shares_raw is None:
        total_shares_raw = _safe_float(fzb.get("实收资本（或股本）"))
    total_shares = int(total_shares_raw) if total_shares_raw else None

    # 衍生指标
    eps = round(net_profit / total_shares, 4) if net_profit and total_shares else None
    bvps = round(shareholders_equity / total_shares, 4) if shareholders_equity and total_shares else None
    roe = round(net_profit / shareholders_equity * 100, 2) if net_profit and shareholders_equity and shareholders_equity != 0 else None

    debt_to_assets = None
    if total_assets and total_liabilities and total_assets != 0:
        debt_to_assets = round(total_liabilities / total_assets * 100, 2)

    current_ratio = None
    if current_assets and current_liabilities and current_liabilities != 0:
        current_ratio = round(current_assets / current_liabilities, 4)

    quick_ratio = None
    if current_assets and current_liabilities and current_liabilities != 0:
        inventory = _safe_float(fzb.get("存货"))
        if inventory is not None:
            quick_ratio = round((current_assets - inventory) / current_liabilities, 4)
        else:
            quick_ratio = round(current_assets / current_liabilities, 4)

    # 现金流量表字段
    cf_operating = _safe_float(llb.get("经营活动产生的现金流量净额"))
    cf_ratio = None
    if net_profit and cf_operating and net_profit != 0:
        cf_ratio = round(cf_operating / net_profit, 4)

    return {
        "ts_code": ts_code,
        "report_date": report_date,
        "report_type": report_type,
        "pub_date": pub_date,
        "eps": eps,
        "bvps": bvps,
        "roe": roe,
        "roa": None,
        "gross_margin": gross_margin,
        "net_margin": net_margin,
        "net_profit": net_profit,
        "net_profit_yoy": None,
        "revenue": revenue,
        "revenue_yoy": None,
        "debt_to_assets": debt_to_assets,
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "cf_operating": cf_operating,
        "cf_ratio": cf_ratio,
        "total_shares": total_shares,
        "float_shares": None,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "shareholders_equity": shareholders_equity,
        "source": "sina",
    }


def compute_yoy_growth(records: list):
    """对同一 ts_code 的 records 计算 YoY 增长率（net_profit_yoy, revenue_yoy）

    对照去年同期（同一 report_type，年份 -1），若存在则计算。
    需 records 已按 report_date 排序，此函数原地修改。
    """
    by_period = {}
    for r in records:
        rt = r["report_type"]
        rd = r["report_date"]
        year = int(rd[:4])
        key = (rt, year)
        # 保留每个报告期的最新数据（若有重复）
        if key not in by_period or rd > by_period[key]["report_date"]:
            by_period[key] = r

    for r in records:
        rt = r["report_type"]
        year = int(r["report_date"][:4])
        prev_key = (rt, year - 1)
        if prev_key in by_period:
            prev = by_period[prev_key]
            if r["net_profit"] is not None and prev["net_profit"] is not None and prev["net_profit"] != 0:
                r["net_profit_yoy"] = round(
                    (r["net_profit"] - prev["net_profit"]) / abs(prev["net_profit"]) * 100, 2
                )
            if r["revenue"] is not None and prev["revenue"] is not None and prev["revenue"] != 0:
                r["revenue_yoy"] = round(
                    (r["revenue"] - prev["revenue"]) / abs(prev["revenue"]) * 100, 2
                )


def upsert_one(record: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO financial_reports
            (ts_code, report_date, report_type, pub_date,
             eps, bvps, roe, roa, gross_margin, net_margin,
             net_profit, net_profit_yoy, revenue, revenue_yoy,
             debt_to_assets, current_ratio, quick_ratio,
             cf_operating, cf_ratio, total_shares, float_shares,
             total_assets, total_liabilities, shareholders_equity, source)
        VALUES (%s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s)
        ON CONFLICT (ts_code, report_date) DO UPDATE SET
            eps = COALESCE(EXCLUDED.eps, financial_reports.eps),
            bvps = COALESCE(EXCLUDED.bvps, financial_reports.bvps),
            roe = COALESCE(EXCLUDED.roe, financial_reports.roe),
            roa = COALESCE(EXCLUDED.roa, financial_reports.roa),
            gross_margin = COALESCE(EXCLUDED.gross_margin, financial_reports.gross_margin),
            net_margin = COALESCE(EXCLUDED.net_margin, financial_reports.net_margin),
            net_profit = COALESCE(EXCLUDED.net_profit, financial_reports.net_profit),
            net_profit_yoy = COALESCE(EXCLUDED.net_profit_yoy, financial_reports.net_profit_yoy),
            revenue = COALESCE(EXCLUDED.revenue, financial_reports.revenue),
            revenue_yoy = COALESCE(EXCLUDED.revenue_yoy, financial_reports.revenue_yoy),
            debt_to_assets = COALESCE(EXCLUDED.debt_to_assets, financial_reports.debt_to_assets),
            current_ratio = COALESCE(EXCLUDED.current_ratio, financial_reports.current_ratio),
            quick_ratio = COALESCE(EXCLUDED.quick_ratio, financial_reports.quick_ratio),
            cf_operating = COALESCE(EXCLUDED.cf_operating, financial_reports.cf_operating),
            cf_ratio = COALESCE(EXCLUDED.cf_ratio, financial_reports.cf_ratio),
            total_shares = COALESCE(EXCLUDED.total_shares, financial_reports.total_shares),
            float_shares = COALESCE(EXCLUDED.float_shares, financial_reports.float_shares),
            total_assets = COALESCE(EXCLUDED.total_assets, financial_reports.total_assets),
            total_liabilities = COALESCE(EXCLUDED.total_liabilities, financial_reports.total_liabilities),
            shareholders_equity = COALESCE(EXCLUDED.shareholders_equity, financial_reports.shareholders_equity),
            source = EXCLUDED.source,
            pub_date = COALESCE(EXCLUDED.pub_date, financial_reports.pub_date),
            updated_at = NOW()
    """, (
        record["ts_code"], record["report_date"],
        record["report_type"], record["pub_date"],
        record["eps"], record["bvps"], record["roe"], record["roa"],
        record["gross_margin"], record["net_margin"],
        record["net_profit"], record["net_profit_yoy"],
        record["revenue"], record["revenue_yoy"],
        record["debt_to_assets"], record["current_ratio"],
        record["quick_ratio"],
        record["cf_operating"], record["cf_ratio"],
        record["total_shares"], record["float_shares"],
        record["total_assets"], record["total_liabilities"],
        record["shareholders_equity"], record["source"],
    ))
    conn.commit()
    conn.close()


def sync_stock(ts_code: str, with_sina: bool = True) -> int:
    """同步单只股票财报，返回写入条数

    1. 从 mootdx 获取最新快照
    2. 从新浪获取多期三表数据
    3. 合并去重后 upsert
    """
    records = []

    # 1. mootdx 快照 — 单行最新数据
    mootdx_data = fetch_mootdx_finance(ts_code)
    if mootdx_data:
        r = parse_mootdx_snapshot(mootdx_data, ts_code)
        if r:
            records.append(r)

    # 2. 新浪三表 — 多期数据
    if with_sina:
        try:
            # 获取 8 期数据
            sina_data = fetch_sina_financials(ts_code, periods=8)
            if sina_data:
                lrb_by_date = sina_data.get("lrb", {})
                fzb_by_date = sina_data.get("fzb", {})
                llb_by_date = sina_data.get("llb", {})

                # 收集所有报告期日期
                all_dates = set()
                all_dates.update(lrb_by_date.keys())
                all_dates.update(fzb_by_date.keys())
                all_dates.update(llb_by_date.keys())

                for rd in sorted(all_dates, reverse=True):
                    lrb_entry = lrb_by_date.get(rd, {})
                    fzb_entry = fzb_by_date.get(rd, {})
                    llb_entry = llb_by_date.get(rd, {})

                    lrb_items = lrb_entry.get("data", []) if isinstance(lrb_entry, dict) else []
                    fzb_items = fzb_entry.get("data", []) if isinstance(fzb_entry, dict) else []
                    llb_items = llb_entry.get("data", []) if isinstance(llb_entry, dict) else []

                    pub_date_raw = lrb_entry.get("publish_date", "") if isinstance(lrb_entry, dict) else ""
                    pub_date = None
                    if pub_date_raw and len(pub_date_raw) == 8:
                        pub_date = f"{pub_date_raw[:4]}-{pub_date_raw[4:6]}-{pub_date_raw[6:8]}"

                    r = parse_sina_period(lrb_items, fzb_items, llb_items,
                                          ts_code, rd, pub_date)
                    if r:
                        records.append(r)
        except Exception as e:
            print(f"  ⚠️ Sina({ts_code}) 失败: {e}")

    if not records:
        return 0

    # 按 report_date 降序排列
    records.sort(key=lambda x: x["report_date"], reverse=True)

    # 去重：同一 report_date 保留更完整的记录（优先 Sina 数据）
    deduped = {}
    for r in records:
        rd = r["report_date"]
        if rd not in deduped:
            deduped[rd] = r
        else:
            # 保留 source 为 sina 的记录（更完整），除非已有数据中 sina 不全
            existing = deduped[rd]
            if r["source"] == "sina" and existing["source"] != "sina":
                deduped[rd] = r
            elif r["source"] == "sina" and existing["source"] == "sina":
                # 合并补齐空值
                for key in existing:
                    if existing[key] is None and r[key] is not None:
                        existing[key] = r[key]

    records = list(deduped.values())
    records.sort(key=lambda x: x["report_date"], reverse=True)

    # 只保留最近 20 期
    records = records[:20]

    # 计算 YoY 增长率
    compute_yoy_growth(records)

    # 写入
    for record in records:
        upsert_one(record)

    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="财报数据同步")
    parser.add_argument(
        "--init", action="store_true",
        help="初始化全市场近5年财报数据"
    )
    parser.add_argument(
        "--code", type=str, default=None,
        help="单只股票代码（测试用）"
    )
    parser.add_argument(
        "--pg-url", type=str, default=None,
        help="PG 连接字符串"
    )
    parser.add_argument(
        "--no-sina", action="store_true",
        help="跳过新浪数据补充"
    )
    args = parser.parse_args()

    if args.pg_url:
        _PG_PARAMS = _parse_pg_url(args.pg_url)

    if args.code:
        print(f"测试拉取 {args.code} 财报...")
        n = sync_stock(args.code, with_sina=not args.no_sina)
        print(f"{args.code}: 写入 {n} 期财报")
    elif args.init:
        stocks = load_stocks()
        print(f"全量初始化财务数据，共 {len(stocks)} 只股票...")
        total = 0
        for i, s in enumerate(stocks):
            try:
                n = sync_stock(s["ts_code"], with_sina=True)
                total += n
                if (i + 1) % 100 == 0:
                    print(f"  进度: {i+1}/{len(stocks)}, 已写入 {total} 条")
                time.sleep(0.1)
            except Exception as e:
                print(f"  {s['ts_code']} 失败: {e}")
        print(f"全量初始化完成！共写入 {total} 条财报记录")
    else:
        stocks = load_stocks()
        print(f"增量更新财务数据，共 {len(stocks)} 只股票...")
        total = 0
        for i, s in enumerate(stocks):
            try:
                n = sync_stock(s["ts_code"], with_sina=True)
                total += n
                if (i + 1) % 200 == 0:
                    print(f"  进度: {i+1}/{len(stocks)}, 已写入 {total} 条")
                time.sleep(0.1)
            except Exception as e:
                print(f"  {s['ts_code']} 失败: {e}")
        print(f"增量更新完成！共写入 {total} 条")
