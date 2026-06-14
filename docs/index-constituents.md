# 指数成分股数据

## 概述

提供指数成分股的本地存储和自动同步能力，为基于指数的选股策略提供数据基础。支持国证、中证等不同编制机构的指数，按调样日期区分成分股版本。

当前已入库：
- **国证成长100**（980080）：100 只成分股，最近生效日 2026-05-29

## 表结构

### index_info — 指数元数据

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 自增主键 |
| index_code | VARCHAR(20) UNIQUE | 指数代码，如 `980080` |
| index_name | VARCHAR(50) | 指数简称，如 `成长100` |
| full_name | VARCHAR(100) | 指数全称，如 `国证成长100` |
| publisher | VARCHAR(20) | 编制机构：`国证`/`中证`/`深证`/`上证` |
| constituent_count | INTEGER | 预期成分股数量 |
| data_source | VARCHAR(50) | 数据接口，如 `akshare.index_detail_cni` |
| last_sync_date | VARCHAR(10) | 最近同步日期 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

唯一约束：`index_code`

### index_constituents — 成分股明细

| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL PK | 自增主键 |
| index_code | VARCHAR(20) | 指数代码 |
| ts_code | VARCHAR(20) | 股票代码（原始格式，如 `000408`） |
| stock_name | VARCHAR(100) | 股票简称 |
| industry | VARCHAR(50) | 所属行业分类（来自指数编制方） |
| market_cap | DOUBLE PRECISION | 总市值（亿元） |
| weight | DOUBLE PRECISION | 权重（%） |
| eff_date | VARCHAR(10) | 生效日期 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

唯一约束：`(index_code, ts_code, eff_date)`
索引：`idx_ic_index_code`, `idx_ic_ts_code`, `idx_ic_eff_date`, `idx_ic_code_date(index_code, eff_date)`

## 同步脚本

```bash
cd backend

# 默认同步国证成长100
venv/bin/python scripts/sync_index_constituents.py

# 指定指数
venv/bin/python scripts/sync_index_constituents.py --index 980080

# 试运行（不写入数据库）
venv/bin/python scripts/sync_index_constituents.py --dry-run
```

### 定时同步

指数每季度（3/6/9/12月）调样，建议调样后运行同步：

```cron
0 4 1-5 * * cd /opt/AIpicking/backend && venv/bin/python scripts/sync_index_constituents.py >> /var/log/aipicking/ingest.log 2>&1
```

## 常用查询

### 获取最新成分股（按权重降序）

```sql
SELECT ts_code, stock_name, industry, weight
FROM index_constituents
WHERE index_code = '980080'
  AND eff_date = (SELECT MAX(eff_date) FROM index_constituents WHERE index_code = '980080')
ORDER BY weight DESC;
```

### 权重前 20

```sql
SELECT ts_code, stock_name, weight
FROM index_constituents
WHERE index_code = '980080'
ORDER BY weight DESC LIMIT 20;
```

### 行业分布

```sql
SELECT industry, COUNT(*) as cnt, SUM(weight) as total_weight
FROM index_constituents
WHERE index_code = '980080'
GROUP BY industry ORDER BY cnt DESC;
```

### 某只股票属于哪些指数

```sql
SELECT c.index_code, i.full_name, c.weight, c.eff_date
FROM index_constituents c
JOIN index_info i ON c.index_code = i.index_code
WHERE c.ts_code = '300308';
```

### 调样历史

```sql
SELECT eff_date, COUNT(*) as cnt
FROM index_constituents WHERE index_code = '980080'
GROUP BY eff_date ORDER BY eff_date DESC;
```

## 扩展指南

### 新增指数

1. 在 `backend/scripts/sync_index_constituents.py` 的 `KNOWN_INDICES` 中注册：

```python
KNOWN_INDICES = {
    "980080": {...},
    "399967": {
        "index_name": "中证军工",
        "full_name": "中证军工指数",
        "publisher": "中证",
        "constituent_count": 80,
        "data_source": "akshare.index_stock_cons_csindex",
    },
}
```

2. 如果数据源不同（非国证），在 `fetch_constituents()` 中增加分支做列名映射。

3. 运行 `venv/bin/python scripts/sync_index_constituents.py --index 399967`

### 在策略中使用

```python
from sqlalchemy import select, func
from app.models.index_tables import IndexConstituent

async def get_index_stocks(session, index_code: str) -> list[str]:
    """返回某指数最新成分股代码列表"""
    latest_date = (
        select(func.max(IndexConstituent.eff_date))
        .where(IndexConstituent.index_code == index_code)
        .scalar_subquery()
    )
    result = await session.execute(
        select(IndexConstituent.ts_code, IndexConstituent.weight)
        .where(
            IndexConstituent.index_code == index_code,
            IndexConstituent.eff_date == latest_date,
        )
        .order_by(IndexConstituent.weight.desc())
    )
    return [(row[0], row[1]) for row in result.fetchall()]
```

## 数据源

| 编制方 | akshare 接口 | 说明 |
|--------|-------------|------|
| 国证 | `index_detail_cni` | 含成分股、权重、行业 |
| 国证 | `index_all_cni` | 全指数列表 |
| 中证 | `index_stock_cons_csindex` | 中证成分股 |
| 申万 | `index_component_sw` | 申万指数成分股 |
