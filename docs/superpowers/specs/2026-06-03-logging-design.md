# 应用层日志系统设计

**日期**: 2026-06-03
**范围**: FastAPI 后端应用层（数据采集脚本保持现状）

## 背景

当前 FastAPI 后端没有日志初始化，3 个服务模块（`auth_service`、`validator`、`education_service`）虽使用了 `logging.getLogger(__name__)`，但因 `main.py` 未调用 `basicConfig()`，日志仅依赖 uvicorn 默认行为输出到 stderr，格式不可控，重启即丢失。项目 `logs/` 目录已创建但为空。

## 目标

- 应用日志同时输出到终端和文件，终端方便开发，文件留存排查历史
- 文件按天滚动，自动清理过期日志
- 统一 uvicorn/SQLAlchemy 三方日志格式
- 通过现有 `DEBUG` 环境变量控制日志级别
- 零额外依赖，纯 Python 标准库 `logging`

## 设计

### 文件变更

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/logging_config.py` | 新增 | 日志初始化函数 |
| `backend/app/config.py` | 修改 | 新增 `LOG_DIR` 配置项 |
| `backend/app/main.py` | 修改 | 启动时调用 `setup_logging()` |

### `config.py` — 新增配置项

```python
self.LOG_DIR = os.getenv("LOG_DIR", str(Path(__file__).parent.parent / "logs"))
```

- 默认值：`backend/logs/`
- 可通过环境变量覆盖（生产环境可指向大容量日志分区）

### `logging_config.py` — 核心逻辑

```python
def setup_logging():
    # 1. 确保日志目录存在
    # 2. 创建 formatter：2026-06-03 14:30:01 [INFO] app.services.auth: message
    # 3. 创建两个 handler：
    #    - StreamHandler(sys.stdout)
    #    - TimedRotatingFileHandler(logs/app.log, when="midnight", backupCount=30)
    # 4. 级别控制：
    #    - DEBUG=True  → 应用 DEBUG，三方库 INFO
    #    - DEBUG=False → 全部 INFO
    # 5. 接管 uvicorn / uvicorn.access / sqlalchemy.engine 的日志
```

### `main.py` — 启动调用

在 `startup_event` 开头（所有业务逻辑之前）调用：

```python
from .logging_config import setup_logging
setup_logging()
```

## 日志格式

```
2026-06-03 14:30:01 [INFO] app.services.auth_service: 默认管理员账号已就绪
2026-06-03 14:30:02 [WARNING] app.services.validator: 策略代码缺少 handle_bar 方法
```

## 日志文件

- 路径：`logs/app.log`
- 切割：每天午夜 00:00
- 保留：30 天
- 命名：`logs/app.log.2026-06-02`（Python TimedRotatingFileHandler 默认后缀）

## 非目标

- 数据采集脚本（`sync_dragon_tiger.py`、`sync_market_data.py`）保持现状，不在本次范围
- 不引入结构化 JSON 日志，不做日志聚合平台对接
- 不做请求级别的 trace ID 注入（可后续迭代）

## 自检

- [x] 无 TBD/TODO
- [x] 配置项与现有 `Settings` 类风格一致
- [x] 范围明确，不涉及脚本层和前端
- [x] 零额外依赖
