# MACD 交互学习页 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 MACD 文章详情页升级为交互式学习页面，支持预置案例/自选股票、参数滑块实时调参、Step-by-Step 引导、信号标注

**Architecture:** 前端新增 `indicators.ts` 工具库（EMA/MACD 计算 + 信号检测），4 个新组件（CaseSelector / MACDInteractiveChart / StepNavigator / ParameterPanel）由 `InteractiveMACDPage` 容器编排，后端新增案例配置 YAML + API 端点

**Tech Stack:** ECharts (echarts-for-react) for charting, YAML for case config, React state for parameter/interaction management

---

### Task 1: 指标计算工具库

**Files:**
- Create: `frontend/src/utils/indicators.ts`

- [ ] **Step 1: 实现 indicators.ts**

```typescript
/** 技术指标计算工具 */

export interface CrossPoint {
  index: number;
  date: string;
  type: 'golden' | 'death'; // 金叉 / 死叉
}

export interface DivergencePoint {
  index: number;
  date: string;
  type: 'top' | 'bottom'; // 顶背离 / 底背离
}

/** 计算 EMA 序列 */
export function calcEMA(data: number[], period: number): (number | null)[] {
  const result: (number | null)[] = [];
  if (data.length === 0) return result;
  const k = 2 / (period + 1);
  // 首个有效值为 SMA
  let sum = 0;
  for (let i = 0; i < period && i < data.length; i++) sum += data[i];
  let ema = sum / Math.min(period, data.length);
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else if (i === period - 1) {
      result.push(ema);
    } else {
      ema = data[i] * k + ema * (1 - k);
      result.push(ema);
    }
  }
  return result;
}

/** 计算 MACD */
export function calcMACD(
  closes: number[],
  fast: number,
  slow: number,
  signal: number
): { dif: (number | null)[]; dea: (number | null)[]; bar: (number | null)[] } {
  const emaFast = calcEMA(closes, fast);
  const emaSlow = calcEMA(closes, slow);
  const dif: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (emaFast[i] === null || emaSlow[i] === null) {
      dif.push(null);
    } else {
      dif.push(emaFast[i]! - emaSlow[i]!);
    }
  }
  // DIF 的有效数据起始索引 = Math.max(fast, slow) - 1
  const difStart = Math.max(fast, slow) - 1;
  const difValid: number[] = [];
  for (let i = difStart; i < dif.length; i++) {
    if (dif[i] !== null) difValid.push(dif[i]!);
  }
  const deaRaw = calcEMA(difValid, signal);
  const dea: (number | null)[] = new Array(difStart).fill(null);
  for (let i = 0; i < deaRaw.length; i++) {
    dea.push(deaRaw[i]);
  }
  // 补齐尾部
  while (dea.length < closes.length) dea.push(null);
  const bar: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (dif[i] !== null && dea[i] !== null) {
      bar.push(2 * (dif[i]! - dea[i]!));
    } else {
      bar.push(null);
    }
  }
  return { dif, dea, bar };
}

/** 检测金叉死叉 */
export function detectCrosses(dates: string[], dif: (number | null)[], dea: (number | null)[]): CrossPoint[] {
  const crosses: CrossPoint[] = [];
  for (let i = 1; i < dates.length; i++) {
    if (dif[i] === null || dea[i] === null || dif[i - 1] === null || dea[i - 1] === null) continue;
    if (dif[i - 1]! <= dea[i - 1]! && dif[i]! > dea[i]!) {
      crosses.push({ index: i, date: dates[i], type: 'golden' });
    } else if (dif[i - 1]! >= dea[i - 1]! && dif[i]! < dea[i]!) {
      crosses.push({ index: i, date: dates[i], type: 'death' });
    }
  }
  return crosses;
}

/** 检测背离（简单版：比较相邻极值点） */
export function detectDivergences(
  dates: string[],
  closes: number[],
  dif: (number | null)[],
  lookback: number = 60
): DivergencePoint[] {
  const divergences: DivergencePoint[] = [];
  // 简化实现：在局部窗口内比较价格极值与 DIF 极值的方向
  for (let i = lookback; i < dates.length; i++) {
    const windowCloses = closes.slice(i - lookback, i + 1);
    const windowDif = dif.slice(i - lookback, i + 1);
    const validDif = windowDif.filter((d): d is number => d !== null);
    if (validDif.length < lookback / 2) continue;
    const priceMax = Math.max(...windowCloses);
    const priceMin = Math.min(...windowCloses);
    const difMax = Math.max(...validDif);
    const difMin = Math.min(...validDif);
    const priceMaxIdx = windowCloses.lastIndexOf(priceMax);
    const priceMinIdx = windowCloses.lastIndexOf(priceMin);
    const difMaxIdx = validDif.lastIndexOf(difMax);
    const difMinIdx = validDif.lastIndexOf(difMin);
    // 顶背离：价格新高但 DIF 未新高
    if (priceMaxIdx > lookback * 0.5 && difMaxIdx < lookback * 0.5) {
      divergences.push({ index: i - lookback + priceMaxIdx, date: dates[i - lookback + priceMaxIdx], type: 'top' });
    }
    // 底背离：价格新低但 DIF 未新低
    if (priceMinIdx > lookback * 0.5 && difMinIdx < lookback * 0.5) {
      divergences.push({ index: i - lookback + priceMinIdx, date: dates[i - lookback + priceMinIdx], type: 'bottom' });
    }
  }
  return divergences;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/utils/indicators.ts
git commit -m "feat: add indicator calculation utilities (EMA, MACD, cross/divergence detection)"
```

---

### Task 2: 案例配置文件

**Files:**
- Create: `backend/content/education/macd-interactive/cases.yaml`
- Create: `backend/content/education/macd-interactive/steps/case-1-step-1.md`
- Create: `backend/content/education/macd-interactive/steps/case-1-step-2.md`
- Create: `backend/content/education/macd-interactive/steps/case-1-step-3.md`
- Create: `backend/content/education/macd-interactive/steps/case-1-step-4.md`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p backend/content/education/macd-interactive/steps
```

- [ ] **Step 2: 写入 cases.yaml**

File: `backend/content/education/macd-interactive/cases.yaml`

```yaml
default_params:
  fast: 12
  slow: 26
  signal: 9

cases:
  - id: "maotai-golden-cross"
    title: "贵州茅台 · 金叉买入信号"
    stock:
      ts_code: "600519.SH"
      name: "贵州茅台"
    date_range:
      start: "2020-01-01"
      end: "2020-06-30"
    annotations:
      - id: "gc1"
        date: "2020-03-20"
        type: "golden_cross"
        label: "金叉买入"
        desc: "DIF 从下方上穿 DEA，形成金叉买入信号"
    steps:
      - step: 1
        title: "观察默认 MACD 走势"
        content_file: "case-1-step-1.md"
        visible_annotations: []
        highlight_params: null
      - step: 2
        title: "发现金叉信号"
        content_file: "case-1-step-2.md"
        visible_annotations: ["gc1"]
        highlight_params: null
      - step: 3
        title: "调整参数观察灵敏度变化"
        content_file: "case-1-step-3.md"
        visible_annotations: ["gc1"]
        highlight_params: "fast"
      - step: 4
        title: "对比默认参数与自定义参数"
        content_file: "case-1-step-4.md"
        visible_annotations: ["gc1"]
        highlight_params: null

  - id: "ningde-top-divergence"
    title: "宁德时代 · 顶背离卖出信号"
    stock:
      ts_code: "300750.SZ"
      name: "宁德时代"
    date_range:
      start: "2021-09-01"
      end: "2022-03-31"
    annotations:
      - id: "td1"
        date: "2021-12-03"
        type: "top_divergence"
        label: "顶背离"
        desc: "股价创新高但 MACD DIF 未创新高，顶背离卖出信号"
    steps:
      - step: 1
        title: "观察股价与 MACD 的关系"
        content_file: "case-2-step-1.md"
        visible_annotations: []
        highlight_params: null
      - step: 2
        title: "识别顶背离信号"
        content_file: "case-2-step-2.md"
        visible_annotations: ["td1"]
        highlight_params: null
      - step: 3
        title: "调整慢线观察背离变化"
        content_file: "case-2-step-3.md"
        visible_annotations: ["td1"]
        highlight_params: "slow"
      - step: 4
        title: "总结背离交易策略"
        content_file: "case-2-step-4.md"
        visible_annotations: ["td1"]
        highlight_params: null

  - id: "byd-bottom-divergence"
    title: "比亚迪 · 底背离反弹信号"
    stock:
      ts_code: "002594.SZ"
      name: "比亚迪"
    date_range:
      start: "2022-03-01"
      end: "2022-08-31"
    annotations:
      - id: "bd1"
        date: "2022-04-27"
        type: "bottom_divergence"
        label: "底背离"
        desc: "股价创新低但 MACD DIF 未创新低，底背离反弹信号"
    steps:
      - step: 1
        title: "观察下跌趋势中的 MACD"
        content_file: "case-3-step-1.md"
        visible_annotations: []
        highlight_params: null
      - step: 2
        title: "发现底背离信号"
        content_file: "case-3-step-2.md"
        visible_annotations: ["bd1"]
        highlight_params: null
      - step: 3
        title: "调整快线观察信号灵敏度"
        content_file: "case-3-step-3.md"
        visible_annotations: ["bd1"]
        highlight_params: "fast"
      - step: 4
        title: "综合运用 MACD 信号"
        content_file: "case-3-step-4.md"
        visible_annotations: ["bd1"]
        highlight_params: null
```

- [ ] **Step 3: 写入步骤文案**

File: `backend/content/education/macd-interactive/steps/case-1-step-1.md`
```markdown
## 观察默认 MACD 走势

上图中 K 线是贵州茅台 2020 年上半年的走势。下方 MACD 面板中：

- **蓝色线是 DIF**（12日EMA - 26日EMA），代表短期与长期趋势的差值
- **橙色线是 DEA**（DIF 的 9日EMA），是 DIF 的平滑信号线
- **红绿柱**是 MACD 柱（2 × (DIF - DEA)），柱子在零轴上方为红色，下方为绿色

先观察 DIF 和 DEA 两条线的相对位置关系。当 DIF 在 DEA 上方时，短期趋势强于长期；反之则弱。

> 💡 试着用鼠标滚轮缩放图表，或拖拽下方的滑块选择时间范围。
```

File: `backend/content/education/macd-interactive/steps/case-1-step-2.md`
```markdown
## 发现金叉信号

注意图中标记的 **2020 年 3 月 20 日** 附近：DIF 线（蓝色）从下方上穿 DEA 线（橙色）。

这就是经典的 **「金叉」买入信号**。

### 金叉的含义
- DIF 上穿 DEA 意味着短期趋势开始强于长期趋势
- 市场从下跌/横盘转向上涨的概率增大
- 这是 MACD 最常用的买入信号

### 观察要点
- 金叉出现后，MACD 柱从绿色变为红色（从零轴下方翻到上方）
- 金叉后股价通常有一段上涨行情

> 🔍 在图中找到金叉标记的位置，观察金叉前后 K 线和 MACD 柱的变化。
```

File: `backend/content/education/macd-interactive/steps/case-1-step-3.md`
```markdown
## 调整参数观察灵敏度变化

现在试试调整右侧的 **快线 EMA 参数**。

### 尝试以下操作：

1. 把「快线 EMA」从 **12** 调到 **6**
2. 观察 DIF 线的变化——它变得更敏感了，金叉可能提前出现
3. 再把快线调到 **24**
4. 观察 DIF 线变平滑了，但金叉出现的时间也推迟了

### 思考
- 快线越小 → MACD 越敏感 → 信号更多但假信号也多
- 快线越大 → MACD 越平滑 → 信号更可靠但可能滞后
- 默认值 (12, 26, 9) 是经过长期实践检验的平衡值

> 💡 试着把三个参数都调一调，感受参数变化对金叉信号的影响。
```

File: `backend/content/education/macd-interactive/steps/case-1-step-4.md`
```markdown
## 总结：MACD 金叉交易策略

### 核心要点

| 要素 | 说明 |
|------|------|
| **信号** | DIF 上穿 DEA → 金叉买入 |
| **确认** | MACD 柱翻红（上穿零轴）增强信号可靠性 |
| **参数** | 默认 (12, 26, 9)，短线可调快，长线可调慢 |
| **止损** | 金叉后若 DIF 回穿 DEA（死叉），应考虑止损 |

### 注意事项
- 金叉在趋势市场中更可靠，震荡市中假信号较多
- 结合成交量放大可提高信号质量
- 金叉离零轴越远，趋势强度越大

> ✅ 完成！试试切换到其他案例，或搜索你感兴趣的股票自由探索。
```

File: `backend/content/education/macd-interactive/steps/case-2-step-1.md`
```markdown
## 观察股价与 MACD 的关系

宁德时代 2021 年 9 月至 2022 年 3 月的走势。注意观察：

- K 线图上的**价格高点**
- 下方 MACD 面板中 **DIF 线的高点**
- 两者是否同步变化？

当价格创新高时，DIF 是否也创了新高？如果不一致，就出现了背离。
```

File: `backend/content/education/macd-interactive/steps/case-2-step-2.md`
```markdown
## 识别顶背离信号

图中标记了 **2021 年 12 月 3 日** 附近的顶背离：

- 🔴 股价创了新高
- 🔵 但 MACD 的 DIF 线没有创出新高，反而在下降

这就是 **「顶背离」卖出信号**。

### 顶背离的含义
- 价格上涨的动能正在减弱
- 虽然价格还在涨，但买方力量已经不足
- 是趋势可能反转的预警信号
```

File: `backend/content/education/macd-interactive/steps/case-2-step-3.md`
```markdown
## 调整慢线观察背离变化

顶背离的识别受参数影响很大。试试调整「慢线 EMA」：

1. 把慢线从 **26** 调到 **50** → DIF 更平滑，背离更明显
2. 把慢线调到 **12** → DIF 更敏感，可能出现多次背离

### 思考
- 慢线越大，DIF 越平滑，背离信号越少但越可靠
- 慢线越小，DIF 越敏感，背离信号更多但可能有假信号
```

File: `backend/content/education/macd-interactive/steps/case-2-step-4.md`
```markdown
## 总结：MACD 背离交易策略

### 顶背离交易要点

| 要素 | 说明 |
|------|------|
| **识别** | 价格新高 + DIF 未新高 = 顶背离 |
| **信号** | 卖出/减仓预警 |
| **确认** | 后续出现死叉可确认卖出 |
| **周期** | 日线级别背离比小时级别更可靠 |

> ✅ 完成！切换到下一个案例学习底背离。
```

File: `backend/content/education/macd-interactive/steps/case-3-step-1.md`
```markdown
## 观察下跌趋势中的 MACD

比亚迪 2022 年 3 月至 8 月的走势。市场处于下跌趋势中。

观察 MACD 指标——当价格持续下跌时，DIF 和 DEA 通常位于零轴下方，柱状图呈现绿色。

注意寻找价格低点和 DIF 低点之间的不一致。
```

File: `backend/content/education/macd-interactive/steps/case-3-step-2.md`
```markdown
## 发现底背离信号

图中标记了 **2022 年 4 月 27 日** 的底背离：

- 🔴 股价创了新低
- 🔵 但 MACD 的 DIF 线没有创出新低，反而在回升

这就是 **「底背离」反弹信号**。

### 底背离的含义
- 价格下跌的动能正在减弱
- 虽然价格还在跌，但卖方力量已经不足
- 是趋势可能反转的预警信号
```

File: `backend/content/education/macd-interactive/steps/case-3-step-3.md`
```markdown
## 调整快线观察信号灵敏度

试试调整「快线 EMA」参数：

1. 把快线从 **12** 调到 **6** → 底背离信号可能更早出现
2. 把快线调到 **24** → 底背离信号可能延迟或消失

### 观察要点
- 底背离确认后，通常伴随金叉信号出现
- 结合成交量放大可增强买入信心
```

File: `backend/content/education/macd-interactive/steps/case-3-step-4.md`
```markdown
## 综合运用 MACD 信号

### MACD 三大信号总结

| 信号类型 | 识别方式 | 操作方向 |
|----------|----------|----------|
| **金叉** | DIF ↑ 穿 DEA | 买入 |
| **死叉** | DIF ↓ 穿 DEA | 卖出 |
| **顶背离** | 价格 ↑ + DIF ↓ | 卖出预警 |
| **底背离** | 价格 ↓ + DIF ↑ | 买入预警 |

### 最佳实践
- 多信号共振时可靠性更高（如底背离 + 金叉）
- 结合均线、成交量增强判断
- 不同市场环境调整参数

> ✅ 学习完成！试试右上角搜索你感兴趣的股票，自由探索 MACD 信号。
```

- [ ] **Step 4: Commit**

```bash
git add backend/content/education/macd-interactive/
git commit -m "feat: add MACD interactive case configs and step content"
```

---

### Task 3: 案例配置 API

**Files:**
- Modify: `backend/app/api/education.py`

- [ ] **Step 1: 添加案例配置端点**

在 `education.py` 末尾追加：

```python
import yaml
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent.parent.parent / "content" / "education" / "macd-interactive"


@router.get("/macd-interactive/cases")
async def get_macd_cases(
    current_user: User = Depends(get_current_user),
):
    """获取 MACD 交互学习案例配置"""
    cases_file = CASES_DIR / "cases.yaml"
    if not cases_file.exists():
        return {"code": 1, "message": "案例配置不存在", "data": None}
    try:
        data = yaml.safe_load(cases_file.read_text(encoding="utf-8"))
    except Exception:
        return {"code": 1, "message": "案例配置解析失败", "data": None}

    # 为每个步骤加载内容
    for case in data.get("cases", []):
        for step in case.get("steps", []):
            content_file = step.get("content_file", "")
            filepath = CASES_DIR / "steps" / content_file
            if filepath.exists():
                try:
                    step["content"] = filepath.read_text(encoding="utf-8")
                except Exception:
                    step["content"] = ""
            else:
                step["content"] = ""
    return {"code": 0, "message": "ok", "data": data}
```

需要在文件顶部添加 import（检查是否已有 `yaml` 和 `Path`）：

```python
# 如果 yaml 和 Path 尚未 import，在文件顶部添加
import yaml
from pathlib import Path
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/education.py
git commit -m "feat: add MACD interactive case config API endpoint"
```

---

### Task 4: educationService 扩展

**Files:**
- Modify: `frontend/src/services/educationService.ts`

- [ ] **Step 1: 添加类型和接口方法**

在 `educationService.ts` 中追加类型定义和新方法：

```typescript
// === MACD Interactive Types ===

export interface CaseAnnotation {
  id: string;
  date: string;
  type: 'golden_cross' | 'death_cross' | 'top_divergence' | 'bottom_divergence';
  label: string;
  desc: string;
}

export interface CaseStock {
  ts_code: string;
  name: string;
}

export interface CaseDateRange {
  start: string;
  end: string;
}

export interface CaseStep {
  step: number;
  title: string;
  content_file: string;
  content: string;
  visible_annotations: string[];
  highlight_params: string | null;
}

export interface MACDCase {
  id: string;
  title: string;
  stock: CaseStock;
  date_range: CaseDateRange;
  annotations: CaseAnnotation[];
  steps: CaseStep[] | null;
}

export interface MACDCasesData {
  default_params: { fast: number; slow: number; signal: number };
  cases: MACDCase[];
}

// === Append to educationService object ===

  async getMACDCases(): Promise<MACDCasesData> {
    const res = await api.get('/education/macd-interactive/cases');
    return res.data.data;
  },
```

- [ ] **Step 2: TypeScript 检查**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/educationService.ts
git commit -m "feat: add MACD interactive types and getMACDCases API method"
```

---

### Task 5: ParameterPanel 组件

**Files:**
- Create: `frontend/src/components/education/ParameterPanel.tsx`

- [ ] **Step 1: 实现 ParameterPanel**

```tsx
import React from 'react';
import { Button, Slider, Space } from 'antd';
import { UndoOutlined } from '@ant-design/icons';

export interface MACDParams {
  fast: number;
  slow: number;
  signal: number;
}

interface ParameterPanelProps {
  params: MACDParams;
  defaultParams: MACDParams;
  highlightParam: string | null; // 'fast' | 'slow' | 'signal' — 高亮提示哪个参数
  onChange: (params: MACDParams) => void;
}

const ParameterPanel: React.FC<ParameterPanelProps> = ({
  params,
  defaultParams,
  highlightParam,
  onChange,
}) => {
  const handleChange = (key: keyof MACDParams, value: number) => {
    onChange({ ...params, [key]: value });
  };

  const handleReset = () => {
    onChange({ ...defaultParams });
  };

  const sliderStyle = (key: string): React.CSSProperties => ({
    border: highlightParam === key ? '2px solid #1677ff' : '2px solid transparent',
    borderRadius: 6,
    padding: '4px 8px',
    transition: 'border 0.3s',
  });

  return (
    <div style={{ padding: '12px 0' }}>
      <h4 style={{ marginBottom: 16 }}>🎚️ 参数调节</h4>
      <div style={sliderStyle('fast')}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>快线 EMA</span>
          <strong>{params.fast}</strong>
        </div>
        <Slider
          min={2}
          max={50}
          value={params.fast}
          onChange={(v) => handleChange('fast', v)}
        />
      </div>
      <div style={{ ...sliderStyle('slow'), marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>慢线 EMA</span>
          <strong>{params.slow}</strong>
        </div>
        <Slider
          min={5}
          max={100}
          value={params.slow}
          onChange={(v) => handleChange('slow', v)}
        />
      </div>
      <div style={{ ...sliderStyle('signal'), marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
          <span>信号线 EMA</span>
          <strong>{params.signal}</strong>
        </div>
        <Slider
          min={2}
          max={30}
          value={params.signal}
          onChange={(v) => handleChange('signal', v)}
        />
      </div>
      <Button
        icon={<UndoOutlined />}
        onClick={handleReset}
        block
        style={{ marginTop: 16 }}
      >
        恢复默认 ({defaultParams.fast}, {defaultParams.slow}, {defaultParams.signal})
      </Button>
    </div>
  );
};

export default ParameterPanel;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/education/ParameterPanel.tsx
git commit -m "feat: add ParameterPanel component with MACD sliders"
```

---

### Task 6: CaseSelector 组件

**Files:**
- Create: `frontend/src/components/education/CaseSelector.tsx`

- [ ] **Step 1: 实现 CaseSelector**

```tsx
import React from 'react';
import { Select, AutoComplete, Button, Space } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { MACDCase } from '@/services/educationService';

interface CaseSelectorProps {
  cases: MACDCase[];
  activeCaseId: string | null;
  mode: 'preset' | 'free';
  onSelectCase: (caseId: string) => void;
  onSearchStock: (tsCode: string) => void;
}

const CaseSelector: React.FC<CaseSelectorProps> = ({
  cases,
  activeCaseId,
  mode,
  onSelectCase,
  onSearchStock,
}) => {
  const [searchValue, setSearchValue] = React.useState('');

  const handleSearch = () => {
    const trimmed = searchValue.trim();
    if (trimmed) onSearchStock(trimmed);
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0' }}>
      <span style={{ fontWeight: 'bold', fontSize: 13, whiteSpace: 'nowrap' }}>📋 案例</span>
      <Select
        style={{ minWidth: 240 }}
        value={mode === 'preset' ? activeCaseId : undefined}
        placeholder="选择预置案例..."
        onChange={onSelectCase}
        options={cases.map((c) => ({
          value: c.id,
          label: c.title,
        }))}
        allowClear={false}
      />
      <span style={{ color: '#999', fontSize: 12 }}>或</span>
      <AutoComplete
        style={{ width: 160 }}
        value={searchValue}
        onChange={setSearchValue}
        placeholder="输入股票代码..."
        options={[]}
      />
      <Button
        type="primary"
        icon={<SearchOutlined />}
        onClick={handleSearch}
        size="small"
      >
        查看
      </Button>
      {mode === 'free' && (
        <span style={{ fontSize: 11, color: '#fa8c16', marginLeft: 8 }}>
          自选模式 — 无步骤引导，自由探索
        </span>
      )}
    </div>
  );
};

export default CaseSelector;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/education/CaseSelector.tsx
git commit -m "feat: add CaseSelector with preset dropdown and free search"
```

---

### Task 7: StepNavigator 组件

**Files:**
- Create: `frontend/src/components/education/StepNavigator.tsx`

- [ ] **Step 1: 实现 StepNavigator**

```tsx
import React from 'react';
import { Button } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import type { CaseStep } from '@/services/educationService';

interface StepNavigatorProps {
  steps: CaseStep[];
  currentStep: number;
  onStepChange: (step: number) => void;
}

const StepNavigator: React.FC<StepNavigatorProps> = ({ steps, currentStep, onStepChange }) => {
  if (!steps || steps.length === 0) return null;

  const current = steps.find((s) => s.step === currentStep) || steps[0];

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 16px',
        background: '#fafafa',
        borderRadius: 8,
        marginTop: 12,
      }}
    >
      <span style={{ fontWeight: 'bold', fontSize: 13, whiteSpace: 'nowrap' }}>📍 学习步骤</span>
      <div style={{ display: 'flex', gap: 4 }}>
        {steps.map((s) => (
          <div
            key={s.step}
            onClick={() => onStepChange(s.step)}
            style={{
              width: 26,
              height: 26,
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 12,
              fontWeight: 'bold',
              cursor: 'pointer',
              color: s.step <= currentStep ? '#fff' : '#999',
              background:
                s.step === currentStep
                  ? '#1677ff'
                  : s.step < currentStep
                  ? '#91caff'
                  : '#f0f0f0',
              transition: 'all 0.2s',
            }}
          >
            {s.step}
          </div>
        ))}
      </div>
      <span style={{ flex: 1, fontSize: 12, color: '#333' }}>
        {current.title}
      </span>
      <Button
        size="small"
        icon={<LeftOutlined />}
        disabled={currentStep <= 1}
        onClick={() => onStepChange(currentStep - 1)}
      />
      <Button
        size="small"
        icon={<RightOutlined />}
        disabled={currentStep >= steps.length}
        onClick={() => onStepChange(currentStep + 1)}
      />
    </div>
  );
};

export default StepNavigator;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/education/StepNavigator.tsx
git commit -m "feat: add StepNavigator with step dots and prev/next"
```

---

### Task 8: MACDInteractiveChart 组件

**Files:**
- Create: `frontend/src/components/education/MACDInteractiveChart.tsx`

- [ ] **Step 1: 实现 MACDInteractiveChart**

```tsx
import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import EChartsWrapper from '@/components/charts/EChartsWrapper';
import type { KLineItem } from '@/types/stock';
import { calcMACD, detectCrosses, detectDivergences } from '@/utils/indicators';
import type { CrossPoint, DivergencePoint } from '@/utils/indicators';

export interface ChartAnnotation {
  id: string;
  date: string;
  type: 'golden_cross' | 'death_cross' | 'top_divergence' | 'bottom_divergence';
  label: string;
  desc: string;
}

interface MACDInteractiveChartProps {
  data: KLineItem[];
  fast: number;
  slow: number;
  signal: number;
  defaultFast: number;
  defaultSlow: number;
  defaultSignal: number;
  annotations: ChartAnnotation[];
  visibleAnnotationIds: string[];
  showComparison: boolean;
  height?: number;
}

export default function MACDInteractiveChart({
  data,
  fast,
  slow,
  signal,
  defaultFast,
  defaultSlow,
  defaultSignal,
  annotations,
  visibleAnnotationIds,
  showComparison,
  height = 550,
}: MACDInteractiveChartProps) {
  const option: EChartsOption = useMemo(() => {
    if (!data.length) return {};

    const dates = data.map((d) => d.trade_date.replace(/^(\d{4})(\d{2})(\d{2})$/, '$1-$2-$3'));
    const closes = data.map((d) => d.close);
    const ohlc = data.map((d) => [d.open, d.close, d.low, d.high]);
    const volumes = data.map((d) => d.vol);

    // 当前参数 MACD
    const macd = calcMACD(closes, fast, slow, signal);
    // 默认参数 MACD（对比用）
    const macdDefault = showComparison
      ? calcMACD(closes, defaultFast, defaultSlow, defaultSignal)
      : null;

    // 可见标注
    const visibleAnnotations = annotations.filter((a) => visibleAnnotationIds.includes(a.id));

    // 金叉死叉标注点
    const crosses = detectCrosses(dates, macd.dif, macd.dea);
    const crossMarkers = crosses
      .filter((c) => {
        // 只显示可见标注附近的交叉点，或全部显示
        if (visibleAnnotationIds.length === 0) return true;
        return visibleAnnotations.some(
          (a) => a.type === 'golden_cross' || a.type === 'death_cross'
        );
      })
      .map((c) => ({
        coord: [c.date, data[c.index].high],
        value: c.type === 'golden' ? '金叉' : '死叉',
        symbol: 'pin',
        symbolSize: 28,
        itemStyle: {
          color: c.type === 'golden' ? '#52c41a' : '#ff4d4f',
        },
        label: {
          show: true,
          formatter: c.type === 'golden' ? '金叉' : '死叉',
          fontSize: 10,
        },
      }));

    // 背离标注点
    const divergences = detectDivergences(dates, closes, macd.dif);
    const divergenceMarkers = divergences
      .filter((d) => {
        if (visibleAnnotationIds.length === 0) return true;
        return visibleAnnotations.some(
          (a) => a.type === 'top_divergence' || a.type === 'bottom_divergence'
        );
      })
      .map((d) => ({
        coord: [d.date, data[d.index].high],
        value: d.type === 'top' ? '顶背离' : '底背离',
        symbol: 'triangle',
        symbolSize: 20,
        itemStyle: {
          color: d.type === 'top' ? '#ff4d4f' : '#52c41a',
        },
        label: {
          show: true,
          formatter: d.type === 'top' ? '顶背离' : '底背离',
          fontSize: 10,
          position: 'top',
        },
      }));

    return {
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
      },
      grid: [
        { left: '5%', right: '3%', top: '5%', height: '58%' },
        { left: '5%', right: '3%', top: '68%', height: '20%' },
      ],
      xAxis: [
        {
          type: 'category',
          data: dates,
          gridIndex: 0,
          axisLabel: { show: false },
          axisLine: { onZero: false },
        },
        {
          type: 'category',
          data: dates,
          gridIndex: 1,
          axisLabel: { rotate: 0, formatter: (v: string) => v.slice(5) },
        },
      ],
      yAxis: [
        { scale: true, gridIndex: 0, axisLabel: { formatter: (v: number) => v.toFixed(1) } },
        { scale: true, gridIndex: 1, splitNumber: 3 },
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        { type: 'slider', xAxisIndex: [0, 1], start: 0, end: 100, height: 18, bottom: 0 },
      ],
      series: [
        // K 线
        {
          name: 'K 线',
          type: 'candlestick',
          data: ohlc,
          xAxisIndex: 0,
          yAxisIndex: 0,
          itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' },
          markPoint: { data: [...crossMarkers, ...divergenceMarkers], symbolOffset: [0, '-30%'] },
        },
        // DIF
        {
          name: `DIF(${fast},${slow})`,
          type: 'line',
          data: macd.dif,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          lineStyle: { color: '#1677ff', width: 1.5 },
        },
        // DEA
        {
          name: `DEA(${signal})`,
          type: 'line',
          data: macd.dea,
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbol: 'none',
          lineStyle: { color: '#fa8c16', width: 1.5 },
        },
        // MACD Bar
        {
          name: 'MACD 柱',
          type: 'bar',
          data: macd.bar.map((v, i) => (v !== null ? v : 0)),
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: {
            color: (params: { dataIndex: number }) => {
              const v = macd.bar[params.dataIndex];
              return v !== null && v >= 0 ? '#ef5350' : '#26a69a';
            },
          },
        },
        // 默认参数 DIF 虚线（对比）
        ...(macdDefault
          ? [
              {
                name: `DIF(${defaultFast},${defaultSlow}) 默认`,
                type: 'line' as const,
                data: macdDefault.dif,
                xAxisIndex: 1,
                yAxisIndex: 1,
                symbol: 'none',
                lineStyle: { color: '#1677ff', width: 1, type: 'dashed' as const, opacity: 0.4 },
              },
              {
                name: `DEA(${defaultSignal}) 默认`,
                type: 'line' as const,
                data: macdDefault.dea,
                xAxisIndex: 1,
                yAxisIndex: 1,
                symbol: 'none',
                lineStyle: { color: '#fa8c16', width: 1, type: 'dashed' as const, opacity: 0.4 },
              },
            ]
          : []),
      ],
    };
  }, [data, fast, slow, signal, showComparison, defaultFast, defaultSlow, defaultSignal, annotations, visibleAnnotationIds]);

  return <EChartsWrapper options={option} height={height} empty={!data.length} />;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/education/MACDInteractiveChart.tsx
git commit -m "feat: add MACDInteractiveChart with K-line, MACD panel, and signal annotations"
```

---

### Task 9: InteractiveMACDPage 容器

**Files:**
- Create: `frontend/src/pages/InteractiveMACDPage.tsx`

- [ ] **Step 1: 实现 InteractiveMACDPage**

```tsx
import React, { useEffect, useState, useCallback } from 'react';
import { Spin, Switch } from 'antd';
import educationService from '@/services/educationService';
import { stockService } from '@/services/stockService';
import type { MACDCase, MACDCasesData } from '@/services/educationService';
import type { KLineItem } from '@/types/stock';
import type { MACDParams } from '@/components/education/ParameterPanel';
import CaseSelector from '@/components/education/CaseSelector';
import MACDInteractiveChart from '@/components/education/MACDInteractiveChart';
import StepNavigator from '@/components/education/StepNavigator';
import ParameterPanel from '@/components/education/ParameterPanel';
import ReactMarkdown from 'react-markdown';

const InteractiveMACDPage: React.FC = () => {
  const [casesData, setCasesData] = useState<MACDCasesData | null>(null);
  const [loading, setLoading] = useState(true);

  // 状态
  const [mode, setMode] = useState<'preset' | 'free'>('preset');
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [klineData, setKlineData] = useState<KLineItem[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [params, setParams] = useState<MACDParams>({ fast: 12, slow: 26, signal: 9 });
  const [currentStep, setCurrentStep] = useState(1);
  const [showComparison, setShowComparison] = useState(false);

  // 加载案例配置
  useEffect(() => {
    educationService.getMACDCases().then((data) => {
      setCasesData(data);
      if (data.cases.length > 0) {
        setActiveCaseId(data.cases[0].id);
      }
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const activeCase: MACDCase | undefined = casesData?.cases.find((c) => c.id === activeCaseId);
  const defaultParams: MACDParams = casesData?.default_params
    ? { ...casesData.default_params }
    : { fast: 12, slow: 26, signal: 9 };

  // 加载 K 线数据
  const loadKline = useCallback(async (tsCode: string, start: string, end: string) => {
    setChartLoading(true);
    try {
      const startDate = start.replace(/-/g, '');
      const endDate = end.replace(/-/g, '');
      const days = Math.ceil(
        (new Date(end).getTime() - new Date(start).getTime()) / (86400000)
      ) + 30;
      const result = await stockService.getKLine(tsCode, Math.min(days, 365));
      const items = result.items || [];
      const filtered = items.filter(
        (item) => item.trade_date >= startDate && item.trade_date <= endDate
      );
      setKlineData(filtered.length > 0 ? filtered : items.slice(0, Math.min(days, items.length)));
    } finally {
      setChartLoading(false);
    }
  }, []);

  // 切换案例时加载数据 + 重置状态
  useEffect(() => {
    if (!activeCase) return;
    setParams({ ...defaultParams });
    setCurrentStep(1);
    setMode('preset');
    loadKline(
      activeCase.stock.ts_code,
      activeCase.date_range.start,
      activeCase.date_range.end
    );
  }, [activeCaseId]);

  const currentStepData = activeCase?.steps?.find((s) => s.step === currentStep);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;
  }

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <h2 style={{ marginBottom: 8 }}>MACD 交互学习</h2>

      {/* Zone 1: Case Selector */}
      <CaseSelector
        cases={casesData?.cases || []}
        activeCaseId={activeCaseId}
        mode={mode}
        onSelectCase={(id) => { setActiveCaseId(id); }}
        onSearchStock={(code) => {
          setMode('free');
          setActiveCaseId(null);
          setCurrentStep(1);
          const today = new Date();
          const start = new Date(today);
          start.setFullYear(start.getFullYear() - 1);
          const s = start.toISOString().slice(0, 10);
          const e = today.toISOString().slice(0, 10);
          loadKline(code, s, e);
        }}
      />

      {/* Zone 2: Interactive Chart */}
      <MACDInteractiveChart
        data={klineData}
        fast={params.fast}
        slow={params.slow}
        signal={params.signal}
        defaultFast={defaultParams.fast}
        defaultSlow={defaultParams.slow}
        defaultSignal={defaultParams.signal}
        annotations={activeCase?.annotations || []}
        visibleAnnotationIds={currentStepData?.visible_annotations || (mode === 'free' ? [] : [])}
        showComparison={showComparison}
        height={mode === 'free' ? 450 : 400}
      />

      {/* Zone 3: Step Navigator (only in preset mode) */}
      {mode === 'preset' && activeCase?.steps && (
        <StepNavigator
          steps={activeCase.steps}
          currentStep={currentStep}
          onStepChange={setCurrentStep}
        />
      )}

      {/* Zone 4: Content + Parameters */}
      <div style={{ display: 'flex', gap: 24, marginTop: 16 }}>
        {/* Zone 4a: Step Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {currentStepData?.content ? (
            <ReactMarkdown>{currentStepData.content}</ReactMarkdown>
          ) : mode === 'free' ? (
            <div style={{ color: '#666', fontSize: 13 }}>
              <p>🔍 <strong>自由探索模式</strong> — 图上标注了自动检测到的金叉/死叉/背离信号。</p>
              <p>调节右侧参数观察 MACD 变化，勾选下方对比开关查看与默认参数的差异。</p>
            </div>
          ) : null}
        </div>

        {/* Zone 4b: Parameter Panel */}
        <div style={{ width: 260, flexShrink: 0 }}>
          <ParameterPanel
            params={params}
            defaultParams={defaultParams}
            highlightParam={currentStepData?.highlight_params || null}
            onChange={setParams}
          />
          {/* Comparison Toggle */}
          <div style={{ marginTop: 12, padding: '8px 0', borderTop: '1px solid #f0f0f0' }}>
            <Switch
              checked={showComparison}
              onChange={setShowComparison}
              size="small"
            />{' '}
            <span style={{ fontSize: 12, color: '#666' }}>
              显示默认参数对比线
            </span>
            <div style={{ fontSize: 11, color: '#999', marginTop: 4 }}>
              虚线 = 默认参数 ({defaultParams.fast}, {defaultParams.slow}, {defaultParams.signal})
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InteractiveMACDPage;
```

- [ ] **Step 2: 检查 stockService 是否有 getKLine 导出**

```bash
grep "getKLine\|get_kline\|kline" frontend/src/services/stockService.ts
```

如果不存在，需要添加 `getKLine` 方法。假设已有，继续。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/InteractiveMACDPage.tsx
git commit -m "feat: add InteractiveMACDPage orchestrating chart, steps, and parameters"
```

---

### Task 10: EducationDetailPage 路由 MACD

**Files:**
- Modify: `frontend/src/pages/EducationDetailPage.tsx`

- [ ] **Step 1: 在 slug === 'macd' 时渲染 InteractiveMACDPage**

在 `EducationDetailPage.tsx` 顶部添加 import：

```tsx
import InteractiveMACDPage from '@/pages/InteractiveMACDPage';
```

在组件函数开头（`useParams` 之后）添加路由判断：

```tsx
const { category, slug } = useParams<{ category: string; slug: string }>();

// 当访问 MACD 文章时，渲染交互学习页面
if (category === 'indicators' && slug === 'macd') {
  return <InteractiveMACDPage />;
}

// ... 以下是原有的文章详情逻辑
```

注意：原有代码中 `useParams` 和后续的 `slug` 引用需保留不变，仅在组件返回前插入判断。

- [ ] **Step 2: TypeScript 检查**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/EducationDetailPage.tsx
git commit -m "feat: route MACD article to interactive learning page"
```

---

### Task 11: 测试

**Files:**
- Create: `frontend/src/utils/__tests__/indicators.test.ts`

- [ ] **Step 1: 实现指标计算测试**

```typescript
import { describe, it, expect } from 'vitest';
import { calcEMA, calcMACD, detectCrosses } from '../indicators';

describe('calcEMA', () => {
  it('calculates EMA for simple sequence', () => {
    const data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const result = calcEMA(data, 5);
    // 第 0-3 位为 null
    expect(result[0]).toBeNull();
    expect(result[4]).not.toBeNull(); // 第 5 个值开始有效
    expect(result[9]).not.toBeNull();
  });

  it('returns all null for empty input', () => {
    expect(calcEMA([], 5)).toEqual([]);
  });

  it('returns nulls for data shorter than period', () => {
    const result = calcEMA([1, 2, 3], 5);
    expect(result.length).toBe(3);
    expect(result.every((v) => v === null)).toBe(true);
  });
});

describe('calcMACD', () => {
  it('returns dif, dea, bar arrays of same length', () => {
    const closes = Array.from({ length: 100 }, (_, i) => 10 + Math.sin(i * 0.1) * 2);
    const { dif, dea, bar } = calcMACD(closes, 12, 26, 9);
    expect(dif.length).toBe(100);
    expect(dea.length).toBe(100);
    expect(bar.length).toBe(100);
  });

  it('has valid values after warm-up period', () => {
    const closes = Array.from({ length: 50 }, (_, i) => 10 + i * 0.1);
    const { dif, dea, bar } = calcMACD(closes, 12, 26, 9);
    // 慢线 26 日，前 25 个值应为 null
    expect(dif[25]).toBeNull();
    // 第 35 个左右应该有效
    const validStart = 34; // slow(26) + signal(9) - 1
    expect(dif[validStart]).not.toBeNull();
    expect(dea[validStart]).not.toBeNull();
    expect(bar[validStart]).not.toBeNull();
  });

  it('bar = 2 * (dif - dea)', () => {
    const closes = Array.from({ length: 100 }, (_, i) => 10 + Math.sin(i * 0.1) * 2);
    const { dif, dea, bar } = calcMACD(closes, 12, 26, 9);
    for (let i = 40; i < 100; i++) {
      if (dif[i] !== null && dea[i] !== null && bar[i] !== null) {
        expect(Math.abs(bar[i]! - 2 * (dif[i]! - dea[i]!))).toBeLessThan(0.001);
      }
    }
  });
});

describe('detectCrosses', () => {
  it('detects golden cross', () => {
    const dates = ['2020-01-01', '2020-01-02', '2020-01-03'];
    const dif = [null, -0.5, 0.5];
    const dea = [null, -0.2, -0.1];
    const crosses = detectCrosses(dates, dif, dea);
    expect(crosses.length).toBe(1);
    expect(crosses[0].type).toBe('golden');
    expect(crosses[0].date).toBe('2020-01-03');
  });

  it('detects death cross', () => {
    const dates = ['2020-01-01', '2020-01-02', '2020-01-03'];
    const dif = [null, 0.5, -0.5];
    const dea = [null, 0.2, 0.1];
    const crosses = detectCrosses(dates, dif, dea);
    expect(crosses.length).toBe(1);
    expect(crosses[0].type).toBe('death');
  });

  it('returns empty when no crosses', () => {
    const dates = ['2020-01-01', '2020-01-02', '2020-01-03'];
    const dif = [null, 1, 2];
    const dea = [null, 0.5, 1];
    const crosses = detectCrosses(dates, dif, dea);
    expect(crosses.length).toBe(0);
  });
});
```

- [ ] **Step 2: 运行测试**

```bash
cd frontend && npx vitest run src/utils/__tests__/indicators.test.ts
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/utils/__tests__/indicators.test.ts
git commit -m "test: add indicator calculation tests"
```

---

### Task 12: 前端验证

- [ ] **Step 1: TypeScript 编译检查**

```bash
cd frontend && npx tsc --noEmit
```

预期: 无错误

- [ ] **Step 2: 构建检查**

```bash
cd frontend && npm run build
```

预期: 构建成功

- [ ] **Step 3: 运行全部测试**

```bash
cd frontend && npx vitest run
```

预期: 所有测试通过

- [ ] **Step 4: 启动服务验证页面**

```bash
# 后端
cd backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
# 前端
cd frontend && npm run dev &
```

打开浏览器访问 `http://localhost:5173/education/indicators/macd`，验证：
- 案例下拉切换正常
- K 线图 + MACD 面板渲染
- 拖动参数滑块图表实时更新
- 步骤导航切换正常
- 对比开关生效
- 自选股票搜索正常
