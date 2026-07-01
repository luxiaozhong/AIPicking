# 量价动量轮动策略 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现量价动量轮动策略——多指数成分股池，横截面 Z-score 排名（价格动量 + 成交量），返回 top N。

**Architecture:** 独立策略文件 `momentum_rotation.py`（仿 `grow_with_money.py` 模式），`run(data)` 接口，仅依赖日线 K 线数据 + 指数成分股。所有参数通过 `params_schema` 暴露。

**Tech Stack:** Python, pandas, numpy, 策略 AST 沙箱环境

## Global Constraints

- 遵循 `run(data)` 接口，返回 `list[dict]`，每项含 `ts_code`, `name`, `score`, `signal`
- `REQUIRED_DATA = ["index_constituents"]` 声明数据依赖
- `params_schema` JSON 格式，type 仅支持 `int` / `float` / `string`（前端渲染限制）
- `index_codes` 用逗号分隔字符串（如 `"399006,000300"`），前端 Input 输入
- 多指数去重：同一 raw_code（前 6 位）只保留首次匹配的 ts_code
- 空 `index_codes` 不走指数过滤，由引擎板块过滤决定股票池

---

### Task 1: 创建策略文件 `momentum_rotation.py`

**Files:**
- Create: `backend/app/strategies/examples/momentum_rotation.py`

**Interfaces:**
- Produces: `run(data: dict) -> list[dict]` — 策略入口函数，回测引擎调用
- Produces: `REQUIRED_DATA = ["index_constituents"]` — 数据依赖声明

- [ ] **Step 1: 创建策略文件**

```python
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
```

- [ ] **Step 2: 验证语法**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -c "
import ast
with open('app/strategies/examples/momentum_rotation.py') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```

- [ ] **Step 3: 验证策略可被引擎加载（dry run）**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -c "
from app.services.backtest_engine import BacktestEngine
with open('app/strategies/examples/momentum_rotation.py') as f:
    code = f.read()
engine = BacktestEngine(code, {})
print('REQUIRED_DATA:', engine.required_data)
print('Strategy loaded OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/strategies/examples/momentum_rotation.py
git commit -m "feat: add momentum_rotation strategy — price momentum + volume cross-sectional ranking"
```

---

### Task 2: 注册策略到 seed

**Files:**
- Modify: `backend/app/seed_strategies.py` — 在 `BUILTIN_STRATEGIES` 列表末尾添加

**Interfaces:**
- Consumes: `momentum_rotation.py` 策略文件（Task 1）
- Produces: 数据库 seed 条目，后端启动时自动注册

- [ ] **Step 1: 在 BUILTIN_STRATEGIES 末尾（`]` 之前）添加策略条目**

在 `backend/app/seed_strategies.py` 的 `BUILTIN_STRATEGIES` 列表中，最后一个条目 `grow_with_money_all` 的 `}` 之后、`]` 之前，插入：

```python
    {
        "name": "动量轮动",
        "description": "量价动量轮动：多指数成分股池，按价格动量（多周期加权）+成交量（量比）横截面Z-score排名，选取top N",
        "file_path": "app/strategies/examples/momentum_rotation.py",
        "tags": "动量,量能,轮动,排名,指数成分股",
        "params_schema": json.dumps({
            "index_codes": {
                "type": "string",
                "default": "",
                "label": "指数代码",
                "description": "逗号分隔，如 399006,000300。留空则全市场选股",
            },
            "N": {
                "type": "int",
                "default": 10,
                "label": "推荐数量 N",
                "description": "选取 top N 只",
                "min": 1,
                "max": 50,
            },
            "mom_fast": {
                "type": "int",
                "default": 20,
                "label": "短周期动量窗口",
                "description": "短周期收益率窗口（交易日）",
                "min": 5,
                "max": 120,
            },
            "mom_slow": {
                "type": "int",
                "default": 60,
                "label": "长周期动量窗口",
                "description": "长周期收益率窗口（交易日）",
                "min": 10,
                "max": 250,
            },
            "mom_fast_weight": {
                "type": "float",
                "default": 0.6,
                "label": "短周期权重",
                "description": "短周期收益率权重，1-此值=长周期权重",
                "min": 0.1,
                "max": 0.9,
            },
            "vol_short": {
                "type": "int",
                "default": 5,
                "label": "短期均量窗口",
                "description": "短期均量窗口（交易日）",
                "min": 3,
                "max": 30,
            },
            "vol_long": {
                "type": "int",
                "default": 20,
                "label": "长期均量窗口",
                "description": "长期均量窗口（交易日）",
                "min": 5,
                "max": 60,
            },
            "volume_weight": {
                "type": "float",
                "default": 0.4,
                "label": "成交量权重",
                "description": "成交量在总分中的权重，1-此值=动量权重",
                "min": 0.1,
                "max": 0.9,
            },
        }, ensure_ascii=False),
    },
```

- [ ] **Step 2: 验证 Python 语法**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -c "
import ast
with open('app/seed_strategies.py') as f:
    ast.parse(f.read())
print('Syntax OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/seed_strategies.py
git commit -m "feat: register momentum_rotation strategy in seed data"
```

---

### Task 3: 端到端验证

**Files:**
- (No new/modified files — verification only)

- [ ] **Step 1: 启动后端验证 seed 注册不报错**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && timeout 5 python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 || true
# 确认日志中出现 "已预置 X 个策略" 或启动无报错
```

- [ ] **Step 2: 用模拟数据做单元级验证**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -c "
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))
sys.path.insert(0, '.')

# 模拟策略加载
from app.services.backtest_engine import BacktestEngine

with open('app/strategies/examples/momentum_rotation.py') as f:
    code = f.read()

engine = BacktestEngine(code, {'index_codes': '', 'N': 5})
print('REQUIRED_DATA:', engine.required_data)

# 用假数据测试 run 逻辑
import numpy as np

# 构造模拟 daily 数据（2 只股票，各 80 条）
np.random.seed(42)
daily = {}
for i, code in enumerate(['000001.SZ', '000002.SZ']):
    base_price = 10 + i * 5
    closes = base_price + np.cumsum(np.random.randn(80) * 0.2)
    vols = np.abs(np.random.randn(80) * 1000000 + 5000000)
    rows = []
    for j in range(80):
        rows.append({
            'trade_date': f'2026-{(j//20)+1:02d}-{(j%20)+1:02d}',
            'open': float(closes[j]),
            'high': float(closes[j] * 1.02),
            'low': float(closes[j] * 0.98),
            'close': float(closes[j]),
            'vol': float(vols[j]),
        })
    daily[code] = rows

mock_data = {
    'cutoff_date': '20260630',
    'stocks': [
        {'ts_code': '000001.SZ', 'name': '平安银行'},
        {'ts_code': '000002.SZ', 'name': '万科A'},
    ],
    'daily': daily,
    'index_constituents': [],
    'config': {'index_codes': '', 'N': 5},
}

result = engine.strategy_func(mock_data)
print(f'Got {len(result)} recommendations:')
for r in result:
    print(f'  {r[\"ts_code\"]} {r[\"name\"]} score={r[\"score\"]} signal={r[\"signal\"]}')
print('OK — strategy runs without error')
"
```

- [ ] **Step 3: Commit (if any fixes)**

```bash
# Only if changes were needed after verification
git add -A && git commit -m "fix: verification fixes for momentum_rotation"
```
