#!/usr/bin/env python3
"""
数据同步报告脚本
优先读取 sync_all.py 生成的结构化摘要 JSON；JSON 不存在时回退到日志解析。

用法:
  python sync_report.py                          # 自动取最新日期
  python sync_report.py --date 2026-06-03        # 指定日期

所需环境变量（建议写在 ~/.bashrc 或 crontab 中）:
  SMTP_USER=你的QQ号@qq.com
  SMTP_PASS=你的QQ邮箱授权码
  REPORT_TO=接收报告的邮箱
"""

import os
import re
import sys
import json
import smtplib
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # backend/
_LOCAL_LOG_DIR = _PROJECT_ROOT.parent / "logs"           # project-root/logs/

# 日志目录：环境变量 > 服务器路径（有实际日志文件）> 本地项目路径
def _find_log_dir() -> Path:
    if "AIPICKING_LOG_DIR" in os.environ:
        return Path(os.environ["AIPICKING_LOG_DIR"])
    server_dir = Path("/var/log/aipicking")
    if (server_dir / "update_daily.log").exists() or (server_dir / "ingest.log").exists():
        return server_dir
    return _LOCAL_LOG_DIR

LOG_DIR = _find_log_dir()

UPDATE_LOG = LOG_DIR / "update_daily.log"
INGEST_LOG = LOG_DIR / "ingest.log"
SUMMARY_FILE = LOG_DIR / "sync_summary.json"

# SMTP 配置文件：服务器路径 > 本地项目路径
_SERVER_ENV = Path("/opt/AIpicking/backend/.sync_report_env")
ENV_FILE = _SERVER_ENV if _SERVER_ENV.exists() else _PROJECT_ROOT / ".sync_report_env"


def load_env():
    """加载环境变量（优先从 .sync_report_env 文件读取）"""
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = val


# ═════════════════════════════════════════════════════════════════════════
# 数据加载
# ═════════════════════════════════════════════════════════════════════════

def load_summary(target_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """尝试读取 sync_all.py 生成的结构化摘要 JSON。"""
    if not SUMMARY_FILE.exists():
        return None

    try:
        data = json.loads(SUMMARY_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    if target_date:
        target = target_date.replace("-", "")
        if data.get("date") != target:
            return None

    return data


# ═════════════════════════════════════════════════════════════════════════
# 旧版日志解析（当 sync_summary.json 不存在时回退使用）
# ═════════════════════════════════════════════════════════════════════════

def _parse_update_log(target_date=None):
    """解析 update_daily.log — 旧版回退路径。"""
    if not UPDATE_LOG.exists():
        return {"error": f"日志文件不存在: {UPDATE_LOG}"}

    text = UPDATE_LOG.read_text()
    lines = text.splitlines()

    RUN_HEADER_PATTERNS = [
        re.compile(r"📅 盘后更新今天\((\d{8})\)"),
        re.compile(r"✅ 今天\((\d{8})\)已有"),
        re.compile(r"✅ 最近交易日\((\d{8})\)已有"),
        re.compile(r"📅 今天\((\d{8})\)无数据"),
        re.compile(r"📅 最近交易日\((\d{8})\)无数据"),
    ]

    runs = []
    current_start = None
    current_date = None

    for i, line in enumerate(lines):
        for pat in RUN_HEADER_PATTERNS:
            m = pat.search(line)
            if m:
                new_date = m.group(1)
                if current_date == new_date and current_start is not None:
                    break
                if current_start is not None:
                    runs.append({"date": current_date, "start": current_start, "end": i})
                current_start = i
                current_date = new_date
                break

    if current_start is not None:
        runs.append({"date": current_date, "start": current_start, "end": len(lines)})

    if not runs:
        return {"error": "未找到任何同步记录"}

    if target_date:
        target = target_date.replace("-", "")
        runs = [r for r in runs if r["date"] == target]
        if not runs:
            return {"error": f"未找到 {target_date} 的同步记录"}

    latest_date = runs[-1]["date"]
    day_runs = [r for r in runs if r["date"] == latest_date]

    total_records = 0
    for run in day_runs:
        run_lines = lines[run["start"]:run["end"]]
        for line in run_lines:
            m = re.search(r"🎉 历史更新完成！新增/覆盖 (\d+) 条", line)
            if m:
                total_records += int(m.group(1))
            m = re.search(r"🎉 历史更新完成！跳过 — 已有 ([\d,]+) 条", line)
            if m and total_records == 0:
                total_records = int(m.group(1).replace(",", ""))
            m = re.search(r"🎉 实时更新完成！成功 (\d+) 只", line)
            if m and total_records == 0:
                total_records = int(m.group(1))

    display_date = f"{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:8]}"
    return {"date": display_date, "records": total_records}


def _parse_ingest_log(target_date=None):
    """解析 ingest.log — 旧版回退路径。"""
    if not INGEST_LOG.exists():
        return {"error": f"日志文件不存在: {INGEST_LOG}"}

    text = INGEST_LOG.read_text()
    lines = text.splitlines()

    sync_dates = []
    for line in lines:
        m = re.search(r"Sync (\d{4}-\d{2}-\d{2}) complete:", line)
        if m:
            sync_dates.append(m.group(1))

    if not sync_dates:
        return {"error": "未找到市场数据同步记录"}

    if target_date:
        target = target_date if len(target_date) == 10 else f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
        if target not in sync_dates:
            return {"error": f"未找到 {target} 的市场数据同步记录"}
        target_date_str = target
    else:
        target_date_str = sync_dates[-1]

    result = {
        "date": target_date_str,
        "dragon_tiger": None,
        "hot_stocks": None,
        "themes": None,
        "northbound": "",
        "industries": None,
        "concepts": None,
    }

    dt_pattern = re.compile(rf"Saved (\d+) dragon tiger stocks for {target_date_str}")
    for line in lines:
        m = dt_pattern.search(line)
        if m:
            result["dragon_tiger"] = int(m.group(1))

    complete_pattern = re.compile(
        rf"Sync {target_date_str} complete: "
        r"stocks=(\d+) themes=(\d+) northbound=(\S+) industries=(\d+) concepts=(\d+)"
    )
    for line in lines:
        m = complete_pattern.search(line)
        if m:
            result["hot_stocks"] = int(m.group(1))
            result["themes"] = int(m.group(2))
            result["northbound"] = m.group(3)
            result["industries"] = int(m.group(4))
            result["concepts"] = int(m.group(5))

    return result


# ═════════════════════════════════════════════════════════════════════════
# HTML 生成
# ═════════════════════════════════════════════════════════════════════════

def _ok(val, default="N/A"):
    if val is None:
        return f'<span style="color:#999">{default}</span>'
    return str(val)


def _num(val, suffix=""):
    if val is None:
        return '<span style="color:#999">N/A</span>'
    return f"{val:,}{suffix}"


def _job_row(label: str, job: Dict[str, Any], extra: str = "") -> str:
    """生成单个 job 的状态行。"""
    if not job.get("ok"):
        err = job.get("error", "执行失败")
        return f'<tr><td>{label}</td><td style="color:#e74c3c">✗ {err}</td></tr>'
    if extra:
        return f"<tr><td>{label}</td><td>{extra}</td></tr>"
    return ""


def _build_section(icon: str, title: str, rows: str) -> str:
    if not rows:
        return ""
    return f"""
    <h2 style="font-size:16px; color:#1a1a2e; border-bottom:2px solid #3498db; padding-bottom:8px; margin-top:24px">
      {icon} {title}
    </h2>
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px">
      <colgroup><col style="width:38%"><col style="width:62%"></colgroup>
      {rows}
    </table>"""


def compose_html(summary: Dict[str, Any]) -> str:
    """从结构化摘要生成 HTML 邮件正文。"""
    today = date.today().strftime("%Y-%m-%d")
    jobs = summary.get("jobs", {})
    data_date = summary.get("date", "N/A")
    if len(data_date) == 8:
        data_date = f"{data_date[:4]}-{data_date[4:6]}-{data_date[6:8]}"

    def j(key: str) -> Dict[str, Any]:
        return jobs.get(key, {})

    sections: list[str] = []

    # ── 1. 日K线数据 ──
    ud = j("update_daily")
    ud_rows = ""
    if not ud:
        ud_rows = '<tr><td colspan="2" style="color:#999">无数据</td></tr>'
    elif not ud.get("ok"):
        ud_rows = f'<tr><td colspan="2" style="color:#e74c3c">✗ {ud.get("error", "失败")}</td></tr>'
    else:
        mode = ud.get("mode", "unknown")
        if mode == "history":
            label = f"新增/覆盖 <strong>{_num(ud.get('records'), ' 条')}</strong>"
        elif mode == "skip":
            label = f"已有 <strong>{_num(ud.get('records'), ' 条')}</strong>（数据完整，跳过）"
        elif mode == "intraday":
            label = f"实时更新 <strong>{_num(ud.get('records'), ' 只')}</strong>"
        else:
            label = f"{_num(ud.get('records'), ' 条')}"
        qt = ud.get("qt_fallback")
        if qt:
            label += f"（qt 兜底 {qt:,} 只）"
        ud_rows = f"<tr><td>个股日线</td><td>{label}</td></tr>"

    sections.append(_build_section("📈", "日K线数据 & 指数", ud_rows))

    # 指数日线
    uid = j("update_index_daily")
    uid_rows = ""
    if uid and uid.get("ok"):
        mode = uid.get("mode", "unknown")
        if mode == "history":
            uid_rows = f"<tr><td>指数日线</td><td>新增/覆盖 <strong>{_num(uid.get('records'), ' 条')}</strong></td></tr>"
        elif mode == "skip":
            uid_rows = f"<tr><td>指数日线</td><td>已有 <strong>{_num(uid.get('records'), ' 条')}</strong>（数据完整）</td></tr>"
        elif mode == "intraday":
            uid_rows = f"<tr><td>指数日线</td><td>实时更新 <strong>{_num(uid.get('records'), ' 个')}</strong> 指数</td></tr>"
    if uid_rows:
        # Append to the same section table
        sections[-1] = sections[-1].replace("</table>", f"{uid_rows}</table>")

    # ── 2. 龙虎榜 ──
    dt = j("dragon_tiger")
    dt_rows = ""
    if dt and dt.get("ok"):
        count = dt.get("count")
        if count:
            dt_rows = f"<tr><td>上榜股票</td><td><strong>{_num(count, ' 只')}</strong></td></tr>"
        else:
            note = dt.get("note", "无数据")
            dt_rows = f'<tr><td>上榜股票</td><td><span style="color:#999">{note}</span></td></tr>'
    sections.append(_build_section("🐉", "龙虎榜", dt_rows))

    # ── 3. 估值数据 ──
    val = j("valuation")
    val_rows = ""
    if val and val.get("ok"):
        count = val.get("count")
        if count:
            val_rows = f"<tr><td>估值数据 PE/PB</td><td><strong>{_num(count, ' 条')}</strong></td></tr>"
        else:
            note = val.get("note", "")
            val_rows = f'<tr><td>估值数据 PE/PB</td><td><span style="color:#999">{note or "无数据"}</span></td></tr>'
    elif val and not val.get("ok"):
        val_rows = f'<tr><td>估值数据 PE/PB</td><td style="color:#e74c3c">✗ {val.get("error", "失败")}</td></tr>'
    sections.append(_build_section("📊", "估值数据", val_rows))

    # ── 4. 市场信号 ──
    md = j("market_data")
    mkt_rows = ""
    if md and md.get("ok"):
        if md.get("hot_stocks") is not None:
            nb = md.get("northbound", "N/A")
            if nb in ("no", "0", ""):
                nb_badge = '<span style="color:#999">无</span>'
            else:
                nb_badge = f'<span style="color:#27ae60">{nb}</span>'
            mkt_rows = f"""
            <tr><td>热点股票</td><td>{_num(md.get('hot_stocks'), ' 只')}</td></tr>
            <tr><td>热点主题</td><td>{_num(md.get('themes'), ' 个')}</td></tr>
            <tr><td>北向资金</td><td>{nb_badge}</td></tr>
            <tr><td>行业板块</td><td>{_num(md.get('industries'), ' 个')}</td></tr>
            <tr><td>概念板块</td><td>{_num(md.get('concepts'), ' 个')}</td></tr>"""
    sections.append(_build_section("🔥", "市场热点 & 资金流", mkt_rows))

    # ── 5. 个股资金流向 ──
    sff = j("stock_fund_flow")
    sff_rows = ""
    if sff and sff.get("ok"):
        saved = sff.get("saved")
        if saved:
            ok_b = sff.get("batches_ok", "?")
            fail_b = sff.get("batches_fail", 0)
            batch_info = f"{ok_b}/{ok_b + fail_b if isinstance(ok_b, int) and isinstance(fail_b, int) else ok_b} 批次"
            sff_rows = f"""
            <tr><td>成功写入</td><td><strong>{_num(saved, ' 条')}</strong></td></tr>
            <tr><td>批次</td><td>{batch_info}</td></tr>"""
    sections.append(_build_section("💧", "个股资金流向", sff_rows))

    # ── 6. 主力资金50指数 ──
    mf = j("mainflow_index")
    mf_rows = ""
    if mf and mf.get("ok"):
        status = mf.get("status", "unknown")
        if status == "updated":
            mf_rows = f"<tr><td>主力资金50</td><td>更新完成 — <strong>{_num(mf.get('count'), ' 只')}</strong> 成分股</td></tr>"
        elif status == "skipped":
            mf_rows = f'<tr><td>主力资金50</td><td><span style="color:#999">⏭ 非调仓日，已跳过</span></td></tr>'
    sections.append(_build_section("🏆", "主力资金50指数", mf_rows))

    # ── 7. 市场温度 ──
    mt = j("market_temperature")
    mt_rows = ""
    if mt and mt.get("ok") and mt.get("score") is not None:
        score = mt["score"]
        level = mt.get("level", "?")
        color = "#27ae60" if score < 30 else ("#e67e22" if score < 60 else "#e74c3c")
        details = mt.get("details", {})
        detail_str = ""
        if details:
            parts = []
            for k, v in details.items():
                label_map = {
                    "index_decline": "指数跌幅", "volatility": "波动率",
                    "limit_down": "跌停潮", "breadth": "下跌广度",
                    "northbound_outflow": "北向出逃",
                }
                parts.append(f"{label_map.get(k, k)}: {v}")
            detail_str = " / ".join(parts)
        mt_rows = f"""
        <tr><td>市场温度得分</td><td style="color:{color};font-size:18px"><strong>{score}° — {level}</strong></td></tr>
        <tr><td>细分</td><td style="font-size:12px;color:#666">{detail_str}</td></tr>"""
    sections.append(_build_section("🌡️", "市场温度", mt_rows))

    # ── 8. 日报发送状态 ──
    rpt = j("report")
    rpt_rows = ""
    if rpt and rpt.get("ok"):
        if rpt.get("email_sent"):
            rpt_rows = f'<tr><td>邮件发送</td><td style="color:#27ae60">✅ 已发送至 {_ok(rpt.get("email_to"), "?")}</td></tr>'
        else:
            rpt_rows = '<tr><td>邮件发送</td><td style="color:#e74c3c">✗ 未发送</td></tr>'

    # ── 总览 footer ──
    ok_count = summary.get("total_ok", 0)
    fail_count = summary.get("total_fail", 0)
    elapsed = summary.get("total_elapsed_s", 0)
    status_color = "#27ae60" if fail_count == 0 else "#e74c3c"
    status_text = "全部成功 ✅" if fail_count == 0 else f"{fail_count} 个失败 ⚠️"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, 'Segoe UI', sans-serif; background:#f5f6fa; padding:20px">
<div style="max-width:600px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.08)">

  <!-- Header -->
  <div style="background:#1a1a2e; color:#fff; padding:24px 32px; text-align:center">
    <h1 style="margin:0; font-size:22px">📊 AIpicking 数据同步日报</h1>
    <p style="margin:8px 0 0; opacity:0.7; font-size:13px">{today}（数据日期: {data_date}）</p>
  </div>

  <div style="padding:24px 32px">
    {''.join(sections)}

    <!-- 总览 -->
    <h2 style="font-size:16px; color:#1a1a2e; border-bottom:2px solid #999; padding-bottom:8px; margin-top:24px">
      📋 任务总览
    </h2>
    <table style="width:100%; border-collapse:collapse; margin-bottom:8px">
      <colgroup><col style="width:38%"><col style="width:62%"></colgroup>
      <tr><td>任务数</td><td>{ok_count + fail_count} 个（{ok_count} 成功 / {fail_count} 失败）</td></tr>
      <tr><td>状态</td><td style="color:{status_color}"><strong>{status_text}</strong></td></tr>
      <tr><td>总耗时</td><td>{elapsed:.0f}s</td></tr>
    </table>
    {rpt_rows}
  </div>

  <!-- Footer -->
  <div style="background:#f8f9fa; padding:16px 32px; text-align:center; font-size:12px; color:#999">
    AIpicking 自动日报 · 每个交易日盘后发送 · <a href="http://101.35.254.125/" style="color:#3498db">查看系统</a>
  </div>

</div>
</body>
</html>"""
    return html


# ═════════════════════════════════════════════════════════════════════════
# 邮件发送
# ═════════════════════════════════════════════════════════════════════════

def send_email(html_body, subject, to_addr, smtp_user, smtp_pass):
    """通过 QQ SMTP 发送邮件。"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_addr], msg.as_string())

    print(f"✅ 邮件已发送至 {to_addr}")


def main():
    load_env()

    parser = argparse.ArgumentParser(description="AIpicking 数据同步日报")
    parser.add_argument("--date", type=str, help="指定日期 YYYY-MM-DD / YYYYMMDD")
    parser.add_argument("--dry-run", action="store_true", help="只打印报告，不发邮件")
    parser.add_argument("--to", type=str, help="接收邮箱（默认 $REPORT_TO）")
    parser.add_argument("--smtp-user", type=str, help="发件邮箱（默认 $SMTP_USER）")
    parser.add_argument("--smtp-pass", type=str, help="SMTP 授权码（默认 $SMTP_PASS）")
    args = parser.parse_args()

    target_date = args.date
    if target_date:
        target_date = target_date.replace("-", "")

    # 1. 尝试读取结构化摘要 JSON
    print(f"📋 加载数据...")
    summary = load_summary(target_date)

    if summary:
        # ── 新版：从 JSON 摘要生成报告 ──
        jobs = summary.get("jobs", {})
        print(f"   数据来源: sync_summary.json")
        print(f"   日期: {summary.get('date', 'N/A')}")
        print(f"   任务: {summary.get('total_ok', 0)} 成功 / {summary.get('total_fail', 0)} 失败")
        for key, j in jobs.items():
            desc = j.get("desc", key)
            status = "✓" if j.get("ok") else "✗"
            print(f"     {status} {desc} ({j.get('elapsed_s', 0):.1f}s)")

        date_label = summary.get("date", "N/A")
        if len(date_label) == 8:
            date_label = f"{date_label[:4]}-{date_label[4:6]}-{date_label[6:8]}"
    else:
        # ── 旧版回退：解析原始日志 ──
        print(f"   数据来源: 日志文件（sync_summary.json 不存在）")
        daily = _parse_update_log(target_date)
        ingest = _parse_ingest_log(target_date)

        if "error" not in daily:
            print(f"   日线: {daily['date']} — {daily['records']:,} 条")
        else:
            print(f"   日线: ⚠️ {daily['error']}")

        if "error" not in ingest:
            print(f"   龙虎榜: {ingest.get('dragon_tiger', 'N/A')} 只")
            print(f"   市场数据: {ingest.get('hot_stocks', 'N/A')} 热点 / {ingest.get('themes', 'N/A')} 主题")

        # 构造兼容旧版的 summary 结构
        date_label = daily.get("date") or ingest.get("date") or "N/A"
        summary = {
            "date": date_label.replace("-", ""),
            "total_ok": 1 if "error" not in daily else 0,
            "total_fail": 0,
            "total_elapsed_s": 0,
            "jobs": {
                "update_daily": {"ok": "error" not in daily, "mode": "history",
                                 "records": daily.get("records", 0)},
                "dragon_tiger": {"ok": "error" not in ingest,
                                 "count": ingest.get("dragon_tiger")},
                "market_data": {"ok": "error" not in ingest,
                                "hot_stocks": ingest.get("hot_stocks"),
                                "themes": ingest.get("themes"),
                                "northbound": ingest.get("northbound"),
                                "industries": ingest.get("industries"),
                                "concepts": ingest.get("concepts")},
            },
        }

    # 生成 HTML
    html = compose_html(summary)
    subject = f"📊 AIpicking 数据同步日报 — {date_label}"

    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"  DRY RUN — 不发送邮件")
        print(f"{'='*60}")
        print(f"\n主题: {subject}")
        print(f"\n{html}")
        return

    # 发邮件
    to_addr = args.to or os.environ.get("REPORT_TO")
    smtp_user = args.smtp_user or os.environ.get("SMTP_USER")
    smtp_pass = args.smtp_pass or os.environ.get("SMTP_PASS")

    if not all([to_addr, smtp_user, smtp_pass]):
        print("\n❌ 缺少邮件配置！请设置以下环境变量或传参：")
        print("   SMTP_USER=你的QQ号@qq.com")
        print("   SMTP_PASS=QQ邮箱授权码")
        print("   REPORT_TO=接收报告的邮箱")
        print("\n   或创建 /opt/AIpicking/backend/.sync_report_env 文件：")
        print("   SMTP_USER=你的QQ号@qq.com")
        print("   SMTP_PASS=QQ邮箱授权码")
        print("   REPORT_TO=接收报告的邮箱")
        sys.exit(1)

    print(f"\n📧 发送邮件...")
    try:
        send_email(html, subject, to_addr, smtp_user, smtp_pass)
    except Exception as e:
        print(f"❌ 发送失败: {e}")
        sys.exit(1)

    print("✅ 完成！")


if __name__ == "__main__":
    main()
