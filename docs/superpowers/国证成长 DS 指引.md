# 指数成分股同步指引

覆盖国证/中证/深证三大指数家族，通过 `sync_index_constituents.py` 一键拉取成分股到 `index_info` + `index_constituents` 两张表。

---

## 一、快速操作

```bash
cd backend && source venv/bin/activate

# 同步单个指数（示例）
python scripts/sync_index_constituents.py --index 980080     # 国证成长100
python scripts/sync_index_constituents.py --index 931643     # 科创创业50（中证）
python scripts/sync_index_constituents.py --index 399673     # 创业板50（深证）

# Dry-run 预览（不写入数据库）
python scripts/sync_index_constituents.py --index 931643 --dry-run

# 指定数据库连接
python scripts/sync_index_constituents.py --index 399750 --pg-url postgresql://user:pass@host/db
```

---

## 二、如何新增一个指数

只需要两步：

### Step 1：在 `sync_index_constituents.py` 的 `KNOWN_INDICES` 中注册

```python
"<指数代码>": {
    "index_name": "<简称>",
    "full_name": "<全称>",
    "publisher": "国证|中证|深证",
    "constituent_count": <预期成分股数量>,
    "data_source": "<数据源标识>",   # 见下方对照表
},
```

### Step 2：运行同步命令

```bash
cd backend && source venv/bin/activate
python scripts/sync_index_constituents.py --index <指数代码>
```

### 数据源标识对照

| data_source | 适用指数家族 | 有权重 | 有行业 | 有市值 | 示例代码 |
|-------------|-------------|--------|--------|--------|---------|
| `akshare.index_detail_cni` | 国证 (980xxx/480xxx) | ✅ | ✅ | ✅ | 980080 |
| `akshare.index_stock_cons_weight_csindex` | 中证 (000xxx/930xxx/950xxx) | ✅ | ❌ | ❌ | 931643, 950180 |
| `akshare.index_stock_cons` | 深证 (399xxx) | ❌ | ❌ | ❌ | 399673, 399667 |

---

## 三、已注册指数一览

| 指数代码 | 简称 | 全称 | 编制方 | 数量 | 有权重 | 最近同步 |
|----------|------|------|--------|------|--------|----------|
| 980080 | 成长100 | 国证成长100 | 国证 | 100 | ✅ | 2026-06-14 |
| 480080 | 成长100R | 国证成长100R | 国证 | 100 | ✅ | — |
| 931643 | 科创创业50 | 中证科创创业50 | 中证 | 50 | ✅ | 2026-06-16 |
| 950180 | 科创AI | 上证科创板人工智能 | 中证 | 30 | ✅ | 2026-06-16 |
| 399673 | 创业板50 | 深证创业板50 | 深证 | 50 | ❌ | 2026-06-16 |
| 399667 | 创业板成长 | 深证创业板成长 | 深证 | 50 | ❌ | 2026-06-16 |
| 399750 | 深主板50 | 深证主板50 | 深证 | 50 | ❌ | 2026-06-16 |

---

## 四、数据库表结构

### index_info（指数元数据）

| 列 | 类型 | 说明 |
|----|------|------|
| index_code | VARCHAR(20) | 指数代码（唯一） |
| index_name | VARCHAR(50) | 指数简称 |
| full_name | VARCHAR(100) | 指数全称 |
| publisher | VARCHAR(20) | 编制机构：国证/中证/深证 |
| constituent_count | INTEGER | 预期成分股数量 |
| data_source | VARCHAR(50) | 数据获取接口标识 |
| last_sync_date | VARCHAR(10) | 最近同步日期 |

### index_constituents（成分股明细）

| 列 | 类型 | 说明 |
|----|------|------|
| index_code | VARCHAR(20) | 指数代码 |
| ts_code | VARCHAR(20) | 股票代码 |
| stock_name | VARCHAR(100) | 股票简称 |
| industry | VARCHAR(50) | 行业分类（仅国证有） |
| market_cap | FLOAT | 总市值亿元（仅国证有） |
| weight | FLOAT | 权重%（国证/中证有，深证无） |
| eff_date | VARCHAR(10) | 生效日期 |

唯一约束：`(index_code, ts_code, eff_date)` — 同指数同股票同生效日不重复，幂等可重跑。

---

## 五、指数数据源详情

### 5.1 国证指数（akshare.index_detail_cni）

- **适用代码段**：980xxx（成长系列等）、480xxx（R系列）
- **接口**：`akshare.index_detail_cni(index_code)`
- **返回字段**：日期、样本代码、样本简称、所属行业、总市值、权重
- **官网**：http://www.cnindex.com.cn
- **数据最全**：有权重 + 行业 + 市值

### 5.2 中证指数（akshare.index_stock_cons_weight_csindex）

- **适用代码段**：000xxx（沪深300等）、930xxx（中证系列）、950xxx（上证科创系列）
- **接口**：`akshare.index_stock_cons_weight_csindex(symbol)`
- **底层 URL**：`https://oss-ch.csindex.com.cn/.../closeweight/{symbol}closeweight.xls`
- **返回字段**：日期、成分券代码、成分券名称、交易所、权重
- **官网**：https://www.csindex.com.cn
- **注意**：950252（科创AI 债券指数）非股票指数，科创AI 股票指数代码为 950180

### 5.3 深证指数（akshare.index_stock_cons）

- **适用代码段**：399xxx（深证系列）
- **接口**：`akshare.index_stock_cons(symbol)`
- **底层**：新浪财经 `vip.stock.finance.sina.com.cn`
- **返回字段**：品种代码、品种名称、纳入日期（每只股票各自加入指数的日期）
- **限制**：无权重/行业/市值，仅成分股名单
- **特点**：各股票 eff_date 分散在不同日期（各自纳入日），而非统一调样日

### 5.4 数据源选择优先级

```
有权重需求 → 优先国证/中证
仅需名单   → 深证（新浪）即可
国证指数   → 数据最全，优先推荐
```

---

## 六、常见问题

**Q: 深证指数为什么看不到权重？**
A: 新浪财经接口仅提供成分股名单，不含权重。如需深证指数权重，需从深交所官网或付费数据源获取。

**Q: 指数调样后需要重新同步吗？**
A: 需要。指数通常每季度调样（3/6/9/12月），请在调样生效后重新运行 sync 命令。旧数据保留（不同 eff_date），不影响回测。

**Q: 如何确认指数代码是否正确？**
A: 
- 国证：http://www.cnindex.com.cn 搜索
- 中证：https://www.csindex.com.cn 搜索
- 深证：http://www.szse.cn 搜索
- 或用 `akshare.index_stock_info()` 遍历所有已知指数

**Q: 同步脚本能在服务器上跑吗？**
A: 可以。本地同步后数据在 PostgreSQL 中，服务器如有相同数据库可直接访问。如需在服务器上跑，用 `--pg-url` 指定连接。

---

## 七、原始参考（国证成长100）

以下整理了国证成长100指数成分股的获取方法（2026年6月确认）。

### 截至2026年6月已确认的部分成分股

**前十大权重股（2026年6月12日数据，合计权重约50.63%）**

| 证券代码 | 股票简称 | 权重 | 所属行业 |
|----------|----------|------|----------|
| 300308 | 中际旭创 | 11.87% | 通信 |
| 002384 | 东山精密 | 9.92% | 电子 |
| 688498 | 源杰科技 | 8.16% | 电子 |
| 600487 | 亨通光电 | 6.24% | 通信 |
| 600150 | 中国船舶 | 6.07% | 国防军工 |
| 688072 | 拓荆科技 | 3.61% | 电子 |
| 600183 | 生益科技 | 3.47% | 电子 |
| 002851 | 麦格米特 | 2.45% | 电力设备 |
| — | 德福科技 | 2.19% | — |
| 002738 | 中矿资源 | 2.16% | 有色金属 |

**通过成分股日报可确认的其余成分股**

| 证券代码 | 股票简称 |
|----------|----------|
| 600988 | 赤峰黄金 |
| 301308 | 江波龙 |
| 002709 | 天赐材料 |
| 000408 | 藏格矿业 |
| 000792 | 盐湖股份 |
| 002916 | 深南电路 |
| 002202 | 金风科技 |
| 300450 | 先导智能 |
| 688388 | 嘉元科技 |
| 688700 | 东威科技 |
| 002466 | 天齐锂业 |
| 600869 | 远东股份 |
| 002812 | 恩捷股份 |
| 002756 | 永兴材料 |
| 688456 | 有研粉材 |
| 300747 | 锐科激光 |
| 301345 | 涛涛车业 |
| 002281 | 光迅科技 |
| 688200 | 华峰测控 |
| 688668 | 鼎通科技 |
| 000893 | 亚钾国际 |
| 300568 | 星源材质 |
| 603083 | 剑桥科技 |
| 601138 | 工业富联 |
| 688183 | 生益电子 |
| 688182 | 灿勤科技 |
| 300666 | 江丰电子 |
| 600389 | 江山股份 |
| 301338 | 凯格精机 |
| 835640 | 富士达（北交所） |

部分成分股来自易方达国证成长100ETF（159259）2026年一季报公开持仓及近期的指数日报披露。

### 编程自动获取（Python方案）

#### 方案一：AkShare（完全免费，推荐）

```python
import akshare as ak

# 获取国证指数所有列表
index_df = ak.index_cni_all()

# 获取国证成长100（980080）的历史样本详情
constituents = ak.index_cni_hist(index='980080')
print(constituents)
```

#### 方案二：tushare 或其他开源库

```python
import tushare as ts
ts.set_token('your_token')
df = ts.index_member(index_code='980080')
print(df)
```

> tushare免费版有调用次数限制。

### 替代查询方法

1. **查阅易方达国证成长100ETF（159259）持仓报告**：天天基金网、同花顺基金F10、好买基金
2. **理杏仁（Lixinger）**：www.lixinger.com，可免费查看前十大权重
