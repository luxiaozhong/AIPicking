---
title: "MACD 指标详解"
category: indicators
tags: ["macd", "动量", "入门"]
difficulty: 入门
order: 1
---

## MACD 是什么？

MACD（Moving Average Convergence Divergence，指数平滑异同移动平均线）是一种趋势跟踪动量指标，由 Gerald Appel 在 1970 年代提出。

## MACD 的构成

MACD 由三条线组成：

- **DIF（快线）**：12 日 EMA - 26 日 EMA
- **DEA（慢线/信号线）**：DIF 的 9 日 EMA
- **柱状图（MACD 柱）**：DIF - DEA

## 基本用法

### 金叉买入信号

当 DIF 线从下方向上穿过 DEA 线时，形成「金叉」，是买入信号。

### 死叉卖出信号

当 DIF 线从上方向下穿过 DEA 线时，形成「死叉」，是卖出信号。

### 背离信号

- **顶背离**：股价创新高，但 MACD 的 DIF 未创新高 → 卖出信号
- **底背离**：股价创新低，但 MACD 的 DIF 未创新低 → 买入信号

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| FAST | 快线周期 | 12 |
| SLOW | 慢线周期 | 26 |
| SIGNAL | 信号线周期 | 9 |
