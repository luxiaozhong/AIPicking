#!/usr/bin/env python3
"""
资金流 Backfill 监控 — 收集四条线进度，发 HTML 邮件。
Usage:
    python scripts/monitor_backfill.py          # 打印 + 发邮件
    python scripts/monitor_backfill.py --dry-run  # 只打印
    python scripts/monitor_backfill.py --once   # 只执行一次（不发邮件）
"""

from __future__ import annotations

import os
import re
import smtplib
import subprocess
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def ssh_output(cmd: str) -> str:
    """Run command on prod server via SSH, return stdout."""
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", "root@101.35.254.125", cmd],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def parse_log(path: str, is_remote: bool = False) -> dict:
    """Parse a backfill log and return progress dict.

    Supports three formats:
      A: [N/TOTAL] DATE — ✓ 完成 (Xs)  /  [N/TOTAL] DATE — 开始 (HH:MM)  /  [N/TOTAL] DATE — ⏭ 跳过
      B: [N/TOTAL] 同步 DATE ... HH:MM:SS  (120-day script)
      C: Completion summary line: "回填完成: X 成功, Y 跳过, Z 失败"
    """
    if is_remote:
        out = ssh_output(f'tail -500 "{path}" 2>/dev/null')
    else:
        try:
            with open(path) as f:
                file_lines = f.readlines()
            out = "".join(file_lines[-500:])
        except FileNotFoundError:
            out = ""

    lines = out.strip().split("\n") if out.strip() else []

    result = {
        "raw": out,
        "current": None,
        "total": None,
        "done": None,
        "skipped": None,
        "current_date": None,
        "last_duration": None,
        "pct": None,
        "status": "未知",
    }

    # Detect "全部完成" summary line
    done_summary = re.search(r'回填完成[：:]\s*(\d+)\s*成功[，,\s]*(\d+)\s*跳过[，,\s]*(\d+)\s*失败', out)
    if done_summary:
        ok = int(done_summary.group(1))
        skip = int(done_summary.group(2))
        fail = int(done_summary.group(3))
        # Also try to extract total from the log
        total_m = re.search(r'(\d+)\s*个交易日', out)
        result["total"] = int(total_m.group(1)) if total_m else (ok + skip + fail)
        result["current"] = result["total"]
        result["done"] = ok + fail  # actually processed
        result["skipped"] = skip
        result["pct"] = 100.0
        result["status"] = "✅ 全部完成"
        return result

    # Count skip lines
    skip_count = len(re.findall(r'⏭\s*跳过', out))

    # Try format A: "[N/TOTAL] DATE — ✓ 完成 (Xs)" or "[N/TOTAL] DATE — 开始" or "[N/TOTAL] DATE — ⏭ 跳过"
    fmt_a = re.findall(r'^\[(\d+)/(\d+)\]\s+(\S+)\s+—\s+(.*)', out, re.MULTILINE)

    # Try format B: "[N/TOTAL] 同步 DATE ... HH:MM:SS"
    fmt_b = re.findall(r'^\[(\d+)/(\d+)\]\s+同步\s+(\S+)', out, re.MULTILINE)

    if fmt_a:
        result["current"] = int(fmt_a[-1][0])
        result["total"] = int(fmt_a[-1][1])
        result["pct"] = round(result["current"] / result["total"] * 100, 1)
        result["current_date"] = fmt_a[-1][2]
        action = fmt_a[-1][3]

        # Count done and skipped lines
        done_matches = re.findall(r'\[(\d+)/(\d+)\]\s+(\S+)\s+—\s+✓\s+完成\s+\((\d+)s\)', out)
        if done_matches:
            result["done"] = int(done_matches[-1][0])
            result["last_duration"] = int(done_matches[-1][3])

        if skip_count > 0:
            result["skipped"] = skip_count

        # Determine status
        if "全部完成" in out or (result["current"] == result["total"] and "完成" in out):
            result["status"] = "✅ 全部完成"
        elif "完成" in action:
            result["status"] = "🟢 运行中"
        elif "开始" in action:
            result["status"] = "🟢 运行中"
        elif "跳过" in action:
            result["status"] = "🟢 运行中" if result["current"] < result["total"] else "✅ 全部完成"
        elif "失败" in action:
            result["status"] = "🔴 失败"

    elif fmt_b:
        result["total"] = int(fmt_b[0][1])
        last = fmt_b[-1]
        result["current"] = int(last[0])
        result["current_date"] = last[2]
        result["pct"] = round(result["current"] / result["total"] * 100, 1)
        # Count done (non-skip lines — format B has no explicit "完成" per line)
        skip_count_b = len(re.findall(r'⏭\s*跳过', out))
        result["done"] = result["current"] - 1 - skip_count_b
        if skip_count_b > 0:
            result["skipped"] = skip_count_b

        # Check for completion summary
        if "回填完成" in out:
            result["status"] = "✅ 全部完成"
            result["done"] = result["total"]
            result["current"] = result["total"]
            result["pct"] = 100.0
        elif result["current"] >= result["total"]:
            result["status"] = "✅ 完成"
        else:
            result["status"] = "🟢 运行中"

    else:
        result["status"] = "⚠️ 无进度数据"

    return result


def fmt_duration(sec: int | None) -> str:
    if sec is None:
        return "—"
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec//60}m{sec%60}s"
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h}h{m}m"


def compose_html(lines: list[dict]) -> str:
    """Generate HTML email body."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = ""
    for l in lines:
        pct = f"{l['pct']}%" if l['pct'] is not None else "—"
        dur = fmt_duration(l["last_duration"])
        cur = l["current_date"] or "—"
        # Build progress cell: "done/total" + skip info
        progress = f"{l['done'] or '—'}/{l['total'] or '—'}"
        if l.get("skipped"):
            progress += f"<br><span style='font-size:11px;color:#999'>(跳{l['skipped']})</span>"
        rows += f"""
        <tr>
            <td>{l['name']}</td>
            <td style="text-align:center">{progress}</td>
            <td style="text-align:center;font-weight:bold">{pct}</td>
            <td style="text-align:center">{cur}</td>
            <td style="text-align:center">{dur}</td>
            <td style="text-align:center">{l['status']}</td>
        </tr>"""

    # Progress bars
    bars = ""
    for l in lines:
        if l['pct'] is not None:
            bar_color = l.get('color', '#3498db')
            # Use green for completed lines
            if l['pct'] >= 100:
                bar_color = '#27ae60'
            bars += f"""
            <div style="margin-bottom:8px">
                <div style="font-size:12px;color:#666;margin-bottom:2px">{l['name']} — {l['pct']}%</div>
                <div style="background:#eee;border-radius:4px;height:6px">
                    <div style="background:{bar_color};border-radius:4px;height:6px;width:{min(l['pct'],100)}%"></div>
                </div>
            </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,'Segoe UI',sans-serif;background:#f5f6fa;padding:20px">
<div style="max-width:650px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)">

  <div style="background:#1a1a2e;color:#fff;padding:24px 32px;text-align:center">
    <h1 style="margin:0;font-size:20px">💰 资金流 Backfill 进度</h1>
    <p style="margin:8px 0 0;opacity:0.7;font-size:13px">{now}</p>
  </div>

  <div style="padding:24px 32px">

    <!-- Progress Bars -->
    {bars}

    <!-- Table -->
    <table style="width:100%;border-collapse:collapse;margin-top:16px;font-size:13px">
      <thead>
        <tr style="background:#f8f9fa;border-bottom:2px solid #dee2e6">
          <th style="padding:8px;text-align:left">线路</th>
          <th style="padding:8px;text-align:center">进度</th>
          <th style="padding:8px;text-align:center">完成%</th>
          <th style="padding:8px;text-align:center">当前日期</th>
          <th style="padding:8px;text-align:center">上日耗时</th>
          <th style="padding:8px;text-align:center">状态</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>

  </div>

  <div style="background:#f8f9fa;padding:16px 32px;text-align:center;font-size:12px;color:#999">
    AIpicking 自动监控 · 每30分钟 · <a href="http://101.35.254.125/" style="color:#3498db">查看系统</a>
  </div>

</div>
</body>
</html>"""
    return html


def send_email(html_body: str, subject: str):
    """Send via QQ SMTP."""
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("REPORT_TO")

    if not all([smtp_user, smtp_pass, to_addr]):
        print("❌ 缺少 SMTP 配置 (SMTP_USER, SMTP_PASS, REPORT_TO)")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_addr], msg.as_string())

    print(f"✅ 邮件已发送至 {to_addr}")
    return True


def collect_all() -> list[dict]:
    """Collect progress from all 4 backfill lines (2 local + 2 prod)."""
    lines = []

    # ① Local 120天线
    l1 = parse_log("/tmp/backfill_fund_flow_120d_dev.log")
    l1["name"] = "① 本地 120天线"
    l1["color"] = "#3498db"
    lines.append(l1)

    # ② Local 2025线
    l2 = parse_log("/tmp/backfill_fund_flow_2025_dev.log")
    l2["name"] = "② 本地 2025线"
    l2["color"] = "#e67e22"
    lines.append(l2)

    # ③ Prod 2025线
    l3 = parse_log("/tmp/backfill_fund_flow_2025.log", is_remote=True)
    l3["name"] = "③ Prod 2025线"
    l3["color"] = "#9b59b6"
    lines.append(l3)

    # ④ Prod 120天线
    l4 = parse_log("/var/log/aipicking/fund_flow_backfill.log", is_remote=True)
    l4["name"] = "④ Prod 120天线"
    l4["color"] = "#27ae60"
    lines.append(l4)

    return lines


def load_env():
    """Load SMTP env from .sync_report_env if exists."""
    env_file = os.path.join(os.path.dirname(__file__), os.pardir, ".sync_report_env")
    env_file = os.path.abspath(env_file)
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key, val)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="资金流 Backfill 监控")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发邮件")
    parser.add_argument("--force", action="store_true", help="忽略完成检测，强制发邮件")
    args = parser.parse_args()

    load_env()

    print(f"📊 收集 backfill 进度... ({datetime.now().strftime('%H:%M:%S')})")
    lines = collect_all()

    # Print summary
    all_done = True
    for l in lines:
        pct = f"{l['pct']}%" if l['pct'] is not None else "—"
        dur = fmt_duration(l["last_duration"])
        skip_info = f" 跳{l['skipped']}" if l.get("skipped") else ""
        print(f"  {l['name']}: {l['done']}/{l['total']} ({pct}){skip_info} | {l['current_date'] or '—'} | {dur} | {l['status']}")
        if "全部完成" not in l["status"] and "完成" not in l["status"]:
            all_done = False
        if "无进度" in l["status"]:
            all_done = False

    if all_done and not args.force:
        print("\n✅ 全部回填已完成，跳过发送邮件")
        return

    html = compose_html(lines)
    subject = f"💰 资金流 Backfill — {datetime.now().strftime('%m-%d %H:%M')}"

    if args.dry_run:
        print("\n[DRY RUN] 不发送邮件")
        return

    if all_done:
        subject = f"✅ 资金流 Backfill 全部完成！— {datetime.now().strftime('%m-%d %H:%M')}"
        print("\n🎉 全部完成，发送最终通知...")

    send_email(html, subject)


if __name__ == "__main__":
    main()
