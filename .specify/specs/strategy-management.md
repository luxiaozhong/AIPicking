# 功能规格：策略管理 (Strategy Management)

**版本**: 2.0  
**状态**: 草稿  
**创建日期**: 2026-05-24  
**最后更新**: 2026-05-24  
**作者**: AI Assistant

---

## 1. 概述

允许用户通过 Web UI 上传、管理量化交易策略脚本。策略以 Python 脚本文件形式上传，系统自动解析并适配为统一接口，支持回测执行和报告生成。

---

## 2. 用户故事

### US-001: 上传策略脚本
**作为** 量化交易者，  
**我希望** 能够上传本地的策略脚本文件，  
**以便** 我可以快速将现有策略集成到平台进行回测。

**验收标准**:
- [ ] 支持拖拽或点击上传 Python 脚本文件（.py）
- [ ] 系统自动解析脚本，检查是否包含必需函数（`check_xxx`, `run`）
- [ ] 解析成功后显示策略名称、描述、参数配置
- [ ] 支持手动编辑策略名称和描述
- [ ] 上传成功后保存到数据库，并跳转到策略列表

### US-002: 编辑策略脚本
**作为** 量化交易者，  
**我希望** 能够在线编辑已上传的策略脚本，  
**以便** 我可以优化策略逻辑或修复错误。

**验收标准**:
- [ ] 在策略列表点击策略可进入编辑页面
- [ ] 提供代码编辑器（Monaco Editor）用于编辑策略脚本
- [ ] 编辑时实时语法检查（Python 语法）
- [ ] 保存时自动验证策略接口（检查必需函数）
- [ ] 保存成功后显示成功提示

### US-003: 查看策略列表
**作为** 量化交易者，  
**我希望** 能够查看所有已上传的策略，  
**以便** 我可以快速找到并管理我的策略。

**验收标准**:
- [ ] 以表格或卡片形式展示策略列表
- [ ] 显示策略名称、描述、创建时间、最后修改时间、状态
- [ ] 支持按名称搜索策略
- [ ] 支持按标签筛选策略
- [ ] 支持分页或无限滚动（> 50 个策略时）

### US-004: 删除策略
**作为** 量化交易者，  
**我希望** 能够删除不需要的策略，  
**以便** 保持策略库的整洁。

**验收标准**:
- [ ] 删除前弹出确认对话框
- [ ] 删除后策略从列表消失
- [ ] 关联回测报告可选择保留或一并删除
- [ ] 提供"归档"替代删除（软删除）

### US-005: 下载策略脚本
**作为** 量化交易者，  
**我希望** 能够下载已上传的策略脚本，  
**以便** 我可以在本地备份或修改。

**验收标准**:
- [ ] 在策略详情页提供"下载"按钮
- [ ] 下载的文件保持原始格式（.py）
- [ ] 下载的文件可直接运行（包含完整代码）

---

## 3. 功能需求

### 3.1 策略脚本标准接口

每个策略脚本必须实现以下函数：

```python
# strategy_template.py

def check_xxx(df: pd.DataFrame, pick_dt: str) -> dict:
    """
    形态识别函数
    
    参数:
        df: 股票历史数据 DataFrame（包含 OHLC、成交量等）
        pick_dt: 选股日期（格式：YYYY-MM-DD）
    
    返回:
        {
            "passed": bool,       # 是否通过筛选
            "score": int,         # 综合得分 (0-100)
            "details": dict,      # 详细指标（如均线、MACD、RSI 等）
            "breakdown": dict     # 各项得分明细
        }
    """
    pass


def run(pick_date: str, all_data: dict, meta_df: pd.DataFrame) -> list:
    """
    选股函数
    
    参数:
        pick_date: 选股日期（格式：YYYY-MM-DD）
        all_data: 所有股票的数据（{ts_code: DataFrame}）
        meta_df: 股票元数据 DataFrame（包含代码、名称、行业等）
    
    返回:
        [
            {
                "ts_code": "600236.SH",
                "code": "600236",
                "name": "桂冠电力",
                "score": 96,              # 得分
                "pick_close": 11.94,      # 选股日收盘价
                "details": {...}           # 详细指标
            },
            ...
        ]
    """
    pass


def backtest(start_date: str, end_date: str) -> dict:
    """
    回测函数（可选，由后端统一回测引擎执行）
    
    参数:
        start_date: 回测起始日期（格式：YYYY-MM-DD）
        end_date: 回测结束日期（格式：YYYY-MM-DD）
    
    返回:
        {
            "summary": {...},   # 汇总统计
            "results": [...]    # 逐日结果
        }
    """
    pass
```

### 3.2 策略脚本上传流程

```
用户上传 .py 文件
  ↓
后端接收文件，保存到临时目录
  ↓
解析脚本（使用 ast 模块）
  ↓
检查是否包含必需函数（check_xxx, run）
  ↓
如果通过验证：
  - 保存到数据库（strategies 表）
  - 保存脚本文件到 strategies/ 目录
  - 返回成功响应
如果验证失败：
  - 返回错误信息（缺少哪些函数）
  - 删除临时文件
```

### 3.3 策略脚本验证规则

| 检查项 | 说明 |
|--------|------|
| **语法检查** | 使用 `ast.parse()` 检查 Python 语法是否正确 |
| **必需函数检查** | 必须包含 `check_` 开头函数和 `run` 函数 |
| **安全检查** | 禁止导入 `os`、`sys`、`subprocess` 等危险模块 |
| **函数签名检查** | 检查函数参数是否符合规范 |

### 3.4 策略参数配置

策略脚本支持参数配置（通过 JSON 配置文件或脚本内的全局变量）：

```python
# 策略脚本内的参数定义（可选）
PARAMS_SCHEMA = {
    "short_window": {
        "type": "integer",
        "title": "短期均线周期",
        "default": 5,
        "minimum": 1,
        "maximum": 60
    },
    "long_window": {
        "type": "integer",
        "title": "长期均线周期",
        "default": 20,
        "minimum": 10,
        "maximum": 250
    }
}
```

### 3.5 前端组件

1. **策略列表页** (`/strategies`)
   - 策略卡片/表格组件
   - 搜索栏和筛选器
   - "上传策略"按钮

2. **策略上传页** (`/strategies/upload`)
   - 文件上传组件（拖拽或点击）
   - 策略信息表单（名称、描述、标签）
   - 上传进度显示

3. **策略编辑器页** (`/strategies/:id/edit`)
   - Monaco Editor（代码编辑）
   - 参数配置表单（基于 JSON Schema 动态生成）
   - 保存/取消按钮

4. **策略详情页** (`/strategies/:id`)
   - 策略代码展示（只读模式）
   - 参数列表
   - 关联回测报告列表
   - 操作按钮（编辑、删除、下载、运行回测）

---

## 4. 数据模型

### 4.1 数据库表结构 (SQLite)

```sql
-- 策略表
CREATE TABLE strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    file_path TEXT NOT NULL,  -- 策略脚本文件路径（相对路径）
    params_schema TEXT,  -- 参数 JSON Schema 字符串（可选）
    tags TEXT,  -- 逗号分隔的标签
    status VARCHAR(50) DEFAULT 'active',  -- active, archived, deleted
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1
);

-- 策略参数实例表（每次运行回测时的参数）
CREATE TABLE strategy_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    params TEXT NOT NULL,  -- 实际使用的参数 JSON
    backtest_id INTEGER,  -- 关联的回测报告 ID
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);
```

### 4.2 策略脚本存储

策略脚本文件存储在 `backend/app/strategies/examples/` 目录下，文件名格式：`{strategy_id}_{strategy_name}.py`

---

## 5. API 接口设计

### 5.1 策略管理 API

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/strategies` | 获取策略列表（支持分页、搜索、筛选） |
| POST | `/api/v1/strategies/upload` | 上传策略脚本 |
| GET | `/api/v1/strategies/:id` | 获取单个策略详情 |
| GET | `/api/v1/strategies/:id/download` | 下载策略脚本 |
| PUT | `/api/v1/strategies/:id` | 更新策略（元数据） |
| PUT | `/api/v1/strategies/:id/code` | 更新策略代码（上传新文件或在线编辑） |
| DELETE | `/api/v1/strategies/:id` | 删除策略（软删除） |

### 5.2 请求/响应示例

**上传策略 - POST /api/v1/strategies/upload**

请求体（multipart/form-data）:
```
file: strategy.py  (策略脚本文件)
name: "老鸭头策略"  (策略名称)
description: "..."  (策略描述)
tags: ["均线", "趋势跟踪"]  (标签)
```

响应（成功）:
```json
{
  "code": 0,
  "message": "策略上传成功",
  "data": {
    "id": 1,
    "name": "老鸭头策略",
    "description": "...",
    "file_path": "strategies/examples/1_老鸭头策略.py",
    "status": "active",
    "created_at": "2026-05-24T17:00:00Z",
    "updated_at": "2026-05-24T17:00:00Z",
    "version": 1
  }
}
```

响应（失败 - 验证错误）:
```json
{
  "code": 40001,
  "message": "策略脚本验证失败",
  "errors": [
    "缺少必需函数: check_old_duck_head",
    "缺少必需函数: run"
  ]
}
```

**下载策略 - GET /api/v1/strategies/:id/download**

响应：
- Content-Type: `application/octet-stream`
- Content-Disposition: `attachment; filename="strategy_name.py"`
- Body: 策略脚本文件内容

---

## 6. 非功能需求

### 6.1 性能
- 策略列表加载时间 < 1 秒（100 条记录内）
- 策略脚本上传时间 < 3 秒（包含验证）
- 策略脚本下载时间 < 1 秒
- 代码编辑器打开时间 < 2 秒

### 6.2 安全性
- 策略脚本沙箱执行（防止恶意代码）
- 文件上传大小限制（最大 10MB）
- 文件类型检查（仅允许 .py 文件）
- API 请求频率限制（防止滥用）

### 6.3 可用性
- 代码编辑器支持语法高亮、自动补全
- 上传失败时显示详细错误信息
- 支持策略导入/导出（.py 文件）
- 支持策略版本控制（保存历史版本）

---

## 7. 依赖和约束

### 7.1 前端依赖
- React 18+
- Ant Design 5+
- Monaco Editor (或 CodeMirror 6)
- React Router 6+
- Axios (HTTP 客户端)
- Zustand (状态管理)
- react-dropzone (文件上传)

### 7.2 后端依赖
- FastAPI
- Python 3.11+
- SQLite 3
- Pydantic (数据验证)
- AST (Python 代码解析)
- pandas (数据处理)

### 7.3 约束
- 策略脚本必须是有效的 Python 语法
- 策略必须实现规定的接口方法（`check_xxx`, `run`）
- 不支持多线程/多进程策略（初期）
- 文件上传大小限制（最大 10MB）

---

## 8. 开放问题

- [ ] 是否支持策略版本控制（Git 集成）？
- [ ] 是否支持策略共享/导入功能？
- [ ] 代码编辑器选择 Monaco Editor 还是 CodeMirror？
- [ ] 策略参数配置是否支持高级类型（日期、股票代码选择器）？
- [ ] 是否支持策略模板库（内置示例策略）？

---

## 9. 验收标准总结

- [x] **US-001**: 上传策略脚本
- [x] **US-002**: 编辑策略脚本
- [x] **US-003**: 查看策略列表
- [x] **US-004**: 删除策略
- [x] **US-005**: 下载策略脚本

---

**变更日志**:
- 2026-05-24: 初始版本创建
- 2026-05-24: 版本 2.0 - 调整为策略脚本上传模式（参考 WorkBuddy 项目）
