#!/usr/bin/env python3
"""
数据同步报告脚本
解析 update_daily.log 和 ingest.log，汇总后通过 QQ 邮箱发送 HTML 报告。

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
from collections import defaultdict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent  # backend/
_LOCAL_LOG_DIR = _PROJECT_ROOT.parent / "logs"           # project-root/logs/

# 日志目录：环境变量 > 服务器路径（有实际日志文件）> 本地项目路径
def _find_log_dir() -> Path:
    if "AIPICKING_LOG_DIR" in os.environ:
        return Path(os.environ["AIPICKING_LOG_DIR"])
    # 检查服务器路径下是否有实际日志文件
    server_dir = Path("/var/log/aipicking")
    if (server_dir / "update_daily.log").exists() or (server_dir / "ingest.log").exists():
        return server_dir
    return _LOCAL_LOG_DIR

LOG_DIR = _find_log_dir()

UPDATE_LOG = LOG_DIR / "update_daily.log"
INGEST_LOG = LOG_DIR / "ingest.log"

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


def parse_update_log(target_date=None):
    """解析日线更新日志，返回最新的同步结果。"""
    if not UPDATE_LOG.exists():
        return {"error": f"日志文件不存在: {UPDATE_LOG}"}

    text = UPDATE_LOG.read_text()
    lines = text.splitlines()

    # 找所有 run 的边界
    # 支持多种日期标记行：
    #   📅 盘后更新今天(YYYYMMDD)        — update_index_daily.py / update_daily.py
    #   ✅ 今天(YYYYMMDD)已有             — 数据完整跳过（旧格式）
    #   ✅ 最近交易日(YYYYMMDD)已有        — 非交易日跳过（旧格式）
    #   📅 今天(YYYYMMDD)无数据            — update_daily.py
    #   📅 最近交易日(YYYYMMDD)无数据       — update_daily.py
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
                # 相同日期的连续行不新建 run（如 📅 + ✅ 同一天）
                if current_date == new_date and current_start is not None:
                    break
                if current_start is not None:
                    runs.append({
                        "date": current_date,
                        "start": current_start,
                        "end": i,
                    })
                current_start = i
                current_date = new_date
                break

    # 最后一个 run
    if current_start is not None:
        runs.append({
            "date": current_date,
            "start": current_start,
            "end": len(lines),
        })

    if not runs:
        return {"error": "未找到任何同步记录"}

    # 过滤目标日期
    if target_date:
        target = target_date.replace("-", "")
        runs = [r for r in runs if r["date"] == target]
        if not runs:
            return {"error": f"未找到 {target_date} 的同步记录"}

    # 取最新日期的所有 run（同一天可能有多个 run：个股 + 指数）
    latest_date = runs[-1]["date"]
    day_runs = [r for r in runs if r["date"] == latest_date]

    # 汇总
    total_records = 0
    details = []
    warnings = []
    errors = []

    for run in day_runs:
        run_lines = lines[run["start"]:run["end"]]
        for line in run_lines:
            # 完成行: "🎉 历史更新完成！新增/覆盖 X 条数据"
            m = re.search(r"🎉 历史更新完成！新增/覆盖 (\d+) 条", line)
            if m:
                total_records += int(m.group(1))
            # 警告/错误
            if "⚠️" in line or "ERROR" in line.upper():
                warnings.append(line.strip())
            if "❌" in line or "FATAL" in line:
                errors.append(line.strip())

        # 提取 run 类型（从完成行判断，更准确）
        run_type = "个股日线"
        for line in run_lines:
            if "指数数据" in line:
                run_type = "指数数据"
                break
            if "个股" in line:
                run_type = "个股日线"
        if run_type not in details:
            details.append(run_type)

    # 格式化日期
    display_date = f"{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:8]}"

    warning_count = len(warnings)
    return {
        "date": display_date,
        "records": total_records,
        "details": details,
        "warnings": warnings[-5:],  # 只保留最后 5 条详情
        "warning_count": warning_count,  # 真实警告总数
        "errors": errors,
    }


def parse_ingest_log(target_date=None):
    """解析 ingest.log（龙虎榜 + 市场数据），返回最新的同步结果。"""
    if not INGEST_LOG.exists():
        return {"error": f"日志文件不存在: {INGEST_LOG}"}

    text = INGEST_LOG.read_text()
    lines = text.splitlines()

    # 找所有的 "Sync YYYY-MM-DD complete:" 行来确定可用日期
    sync_dates = []
    for line in lines:
        m = re.search(r"Sync (\d{4}-\d{2}-\d{2}) complete:", line)
        if m:
            sync_dates.append(m.group(1))

    if not sync_dates:
        return {"error": "未找到市场数据同步记录"}

    # 确定目标日期
    if target_date:
        target = target_date
        if len(target) == 8:
            target = f"{target[:4]}-{target[4:6]}-{target[6:8]}"
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
        "top_industry": "",
        "top_concept": "",
        "errors": [],
    }

    # 提取龙虎榜数据: "Saved XX dragon tiger stocks for YYYY-MM-DD"
    dt_pattern = re.compile(
        rf"Saved (\d+) dragon tiger stocks for {target_date_str}"
    )
    for line in lines:
        m = dt_pattern.search(line)
        if m:
            result["dragon_tiger"] = int(m.group(1))

    # 提取市场数据 complete 行
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

    # 提取北向资金详情
    nb_pattern = re.compile(
        rf"Saved northbound: (.+)"
    )
    for line in lines:
        m = nb_pattern.search(line)
        if m and target_date_str in _get_context(lines, line):
            result["northbound"] = m.group(1)

    # 提取 top 板块
    top_ind = re.compile(r"Fetched \d+ industry sectors \(top: (.+)\)")
    top_con = re.compile(r"Fetched \d+ concept sectors \(top: (.+)\)")
    for line in lines:
        if target_date_str in _get_context(lines, line):
            m = top_ind.search(line)
            if m:
                result["top_industry"] = m.group(1)
            m = top_con.search(line)
            if m:
                result["top_concept"] = m.group(1)

    # 收集错误
    for line in lines:
        if target_date_str in _get_context(lines, line) and "ERROR" in line:
            result["errors"].append(line.strip())

    return result


def _get_context(lines, line, radius=2):
    """获取某行附近几行的日期上下文，用于判断行属于哪个日期。"""
    try:
        idx = lines.index(line) if isinstance(line, str) else next(
            i for i, l in enumerate(lines) if line in l
        )
    except StopIteration:
        return ""
    start = max(0, idx - radius)
    end = min(len(lines), idx + radius + 1)
    return "\n".join(lines[start:end])


def compose_html(daily, ingest):
    """生成 HTML 邮件正文。"""
    today = date.today().strftime("%Y-%m-%d")

    def ok_badge(val):
        if val is None:
            return '<span style="color:#999">N/A</span>'
        return str(val)

    def num(val, suffix=""):
        if val is None:
            return '<span style="color:#999">N/A</span>'
        return f"{val:,}{suffix}"

    # 日线部分
    daily_rows = ""
    if "error" in daily:
        daily_rows = f'<tr><td colspan="2" style="color:#e74c3c">{daily["error"]}</td></tr>'
    else:
        daily_rows = f"""
        <tr><td>同步日期</td><td><strong>{daily['date']}</strong></td></tr>
        <tr><td>新增/覆盖</td><td style="color:#27ae60;font-size:18px"><strong>{num(daily['records'], ' 条')}</strong></td></tr>
        <tr><td>类型</td><td>{', '.join(daily['details'])}</td></tr>
        """
        if daily.get("warnings"):
            wc = daily.get("warning_count", len(daily["warnings"]))
            daily_rows += f"""<tr><td>⚠️ 警告</td><td style="color:#e67e22">{wc} 条</td></tr>"""
        if daily.get("errors"):
            daily_rows += f"""<tr><td>❌ 错误</td><td style="color:#e74c3c">{len(daily['errors'])} 条</td></tr>"""

    # 龙虎榜
    dt_rows = ""
    if "error" not in ingest:
        dt_rows = f"""
        <tr><td>同步日期</td><td><strong>{ingest['date']}</strong></td></tr>
        <tr><td>上榜股票</td><td>{num(ingest.get('dragon_tiger'), ' 只')}</td></tr>
        """

    # 市场数据
    mkt_rows = ""
    if "error" not in ingest:
        mkt_rows = f"""
        <tr><td>热点股票</td><td>{num(ingest.get('hot_stocks'), ' 只')}</td></tr>
        <tr><td>热点主题</td><td>{num(ingest.get('themes'), ' 个')}</td></tr>
        <tr><td>北向资金</td><td>{ok_badge(ingest.get('northbound'))}</td></tr>
        <tr><td>行业板块</td><td>{num(ingest.get('industries'), ' 个')}{' — ' + ingest['top_industry'] if ingest.get('top_industry') else ''}</td></tr>
        <tr><td>概念板块</td><td>{num(ingest.get('concepts'), ' 个')}{' — ' + ingest['top_concept'] if ingest.get('top_concept') else ''}</td></tr>
        """
        if ingest.get("errors"):
            mkt_rows += f"""<tr><td>❌ 错误</td><td style="color:#e74c3c">{len(ingest['errors'])} 条</td></tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, 'Segoe UI', sans-serif; background:#f5f6fa; padding:20px">
<div style="max-width:600px; margin:0 auto; background:#fff; border-radius:12px; overflow:hidden; box-shadow:0 2px 12px rgba(0,0,0,0.08)">

  <!-- Header -->
  <div style="background:#1a1a2e; color:#fff; padding:24px 32px; text-align:center">
    <h1 style="margin:0; font-size:22px">📊 AIpicking 数据同步日报</h1>
    <p style="margin:8px 0 0; opacity:0.7; font-size:13px">{today}（数据日期: {daily.get('date', ingest.get('date', 'N/A'))}）</p>
  </div>

  <div style="padding:24px 32px">

    <!-- 日线数据 -->
    <h2 style="font-size:16px; color:#1a1a2e; border-bottom:2px solid #3498db; padding-bottom:8px">
      📈 日K线数据
    </h2>
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px">
      <colgroup><col style="width:35%"><col style="width:65%"></colgroup>
      {daily_rows}
    </table>

    <!-- 龙虎榜 -->
    <h2 style="font-size:16px; color:#1a1a2e; border-bottom:2px solid #e67e22; padding-bottom:8px">
      🐉 龙虎榜
    </h2>
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px">
      <colgroup><col style="width:35%"><col style="width:65%"></colgroup>
      {dt_rows if dt_rows else '<tr><td colspan="2" style="color:#e74c3c">' + ingest.get("error", "无数据") + '</td></tr>'}
    </table>

    <!-- 市场数据 -->
    <h2 style="font-size:16px; color:#1a1a2e; border-bottom:2px solid #27ae60; padding-bottom:8px">
      🔥 市场热点 & 资金流
    </h2>
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px">
      <colgroup><col style="width:35%"><col style="width:65%"></colgroup>
      {mkt_rows if mkt_rows else '<tr><td colspan="2" style="color:#e74c3c">' + ingest.get("error", "无数据") + '</td></tr>'}
    </table>

  </div>

  <!-- Footer -->
  <div style="background:#f8f9fa; padding:16px 32px; text-align:center; font-size:12px; color:#999">
    AIpicking 自动日报 · 每个交易日盘后发送 · <a href="http://101.35.254.125/" style="color:#3498db">查看系统</a>
  </div>

</div>
</body>
</html>"""
    return html


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

    # 解析日志
    print(f"📋 解析日志...")
    daily = parse_update_log(target_date)
    ingest = parse_ingest_log(target_date)

    # 打印摘要
    if "error" not in daily:
        print(f"   日线: {daily['date']} — 新增/覆盖 {daily['records']:,} 条")
    else:
        print(f"   日线: ⚠️ {daily['error']}")

    if "error" not in ingest:
        print(f"   龙虎榜: {ingest.get('dragon_tiger', 'N/A')} 只上榜")
        print(f"   市场数据: {ingest.get('hot_stocks', 'N/A')} 热点 / {ingest.get('themes', 'N/A')} 主题 / {ingest.get('industries', 'N/A')}+{ingest.get('concepts', 'N/A')} 板块")
    else:
        print(f"   市场数据: ⚠️ {ingest['error']}")

    # 生成 HTML
    date_label = daily.get("date") or ingest.get("date") or "N/A"
    html = compose_html(daily, ingest)
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
