# 应用层日志系统 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 FastAPI 后端搭建统一的日志系统：终端 + 文件双写，按天滚动，通过 DEBUG 环境变量控制级别，零额外依赖。

**Architecture:** 新增 `logging_config.py` 模块，在 `main.py` 启动时调用 `setup_logging()`，统一接管应用、uvicorn、sqlalchemy 三类 logger。`config.py` 新增 `LOG_DIR` 配置项。

**Tech Stack:** Python 标准库 `logging`、`TimedRotatingFileHandler`、`StreamHandler`

---

### Task 1: Config 新增 LOG_DIR 配置项

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 在 Settings.__init__ 末尾添加 LOG_DIR 配置**

在 `backend/app/config.py` 的 `Settings.__init__` 方法末尾（`self.DEEPSEEK_TIMEOUT` 行之后），`settings = Settings()` 行之前，添加：

```python
        # 日志配置
        self.LOG_DIR = os.getenv("LOG_DIR", str(_env_dir / "logs"))
```

完整修改后的 `__init__` 方法末尾：

```python
        # DeepSeek API 配置
        self.DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
        self.DEEPSEEK_BASE_URL = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.DEEPSEEK_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "120"))

        # 日志配置
        self.LOG_DIR = os.getenv("LOG_DIR", str(_env_dir / "logs"))
```

- [ ] **Step 2: 验证 import 可用**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -c "from app.config import settings; print('LOG_DIR:', settings.LOG_DIR)"
```

预期输出：`LOG_DIR: /Users/aklu/CodeBuddy/AIpicking/backend/logs`

- [ ] **Step 3: Commit**

```bash
cd /Users/aklu/CodeBuddy/AIpicking && git add backend/app/config.py && git commit -m "feat: add LOG_DIR config for logging system"
```

---

### Task 2: 创建 logging_config 模块

**Files:**
- Create: `backend/app/logging_config.py`

- [ ] **Step 1: 创建 logging_config.py**

创建 `/Users/aklu/CodeBuddy/AIpicking/backend/app/logging_config.py`，完整内容：

```python
"""统一日志配置 — 双写终端和文件，按天滚动"""

import logging
import os
from logging.handlers import TimedRotatingFileHandler

from .config import settings


def setup_logging() -> None:
    """初始化应用日志系统。

    - 日志同时输出到 stdout 和 logs/app.log
    - 文件按天午夜切割，保留 30 天
    - 开发环境 (DEBUG=True) 应用日志级别为 DEBUG，三方库保持 INFO
    - 生产环境 (DEBUG=False) 全部 INFO
    """
    # 1. 确保日志目录存在
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    # 2. 统一 Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 3. StreamHandler — 输出到终端
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # 4. TimedRotatingFileHandler — 输出到文件，每天午夜切割，保留 30 天
    log_file = os.path.join(settings.LOG_DIR, "app.log")
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # 5. 确定日志级别
    app_level = logging.DEBUG if settings.DEBUG else logging.INFO

    # 6. 接管三方库日志（uvicorn 和 sqlalchemy）
    #    三方库始终用 INFO 级别，避免 DEBUG 下太吵
    for lib_logger_name in ("uvicorn", "uvicorn.access", "sqlalchemy.engine"):
        lib_logger = logging.getLogger(lib_logger_name)
        lib_logger.handlers.clear()
        lib_logger.setLevel(logging.INFO)
        lib_logger.addHandler(stream_handler)
        lib_logger.addHandler(file_handler)
        lib_logger.propagate = False

    # 7. 配置根 logger（覆盖所有应用模块 logger）
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(app_level)
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -c "from app.logging_config import setup_logging; print('Module imported OK')"
```

预期输出：`Module imported OK`

- [ ] **Step 3: 验证 setup_logging 执行成功**

```bash
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -c "
from app.logging_config import setup_logging
setup_logging()
import logging
logger = logging.getLogger('test')
logger.info('test log message')
print('Log directory contents:')
import os
for f in os.listdir('logs'):
    print(' ', f)
"
```

预期输出：`test log message` 日志行 + `logs/` 目录下有 `app.log` 文件。

- [ ] **Step 4: Commit**

```bash
cd /Users/aklu/CodeBuddy/AIpicking && git add backend/app/logging_config.py && git commit -m "feat: add centralized logging config with stdout + file rotation"
```

---

### Task 3: main.py 启动时初始化日志

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 在 startup_event 开头调用 setup_logging**

修改 `/Users/aklu/CodeBuddy/AIpicking/backend/app/main.py`：

在第 26 行 `@app.on_event("startup")` 之后、`async def startup_event():` 之下，作为函数体**第一行**插入：

```python
    from .logging_config import setup_logging
    setup_logging()
```

同时，将文件中现有的 `print(...)` 调用替换为 `logging.getLogger(__name__).info(...)`：

在文件顶部 `from fastapi import FastAPI` 之后添加：
```python
import logging

logger = logging.getLogger(__name__)
```

然后替换两个 `print` 调用：

- 第 38 行：`print(f"默认管理员账号已就绪: {admin.username}")` →
  ```python
  logger.info("默认管理员账号已就绪: %s", admin.username)
  ```

- 第 51 行：`print("数据库已初始化")` →
  ```python
  logger.info("数据库已初始化")
  ```

完整修改后的 `startup_event`：

```python
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .database import init_db

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="A 股量化交易平台",
    version="0.1.0",
    debug=settings.DEBUG
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """应用启动时执行"""
    from .logging_config import setup_logging
    setup_logging()

    await init_db()

    # 创建默认管理员账号
    from .database import async_session
    from .services.auth_service import seed_default_admin
    session = await async_session()
    try:
        admin = await seed_default_admin(session)
        await session.commit()
        logger.info("默认管理员账号已就绪: %s", admin.username)
    finally:
        await session.close()

    # 预置内置策略
    from .seed_strategies import seed_strategies
    session = await async_session()
    try:
        await seed_strategies(session, admin_user_id=admin.id)
        await session.commit()
    finally:
        await session.close()

    logger.info("数据库已初始化")

    # 加载教育内容
    from .services.education_service import EducationService
    EducationService.instance().load()
```

注意：文件其余部分（`@app.get("/")`、`@app.get("/health")`、路由注册）保持不变。

- [ ] **Step 2: 重启后端验证启动日志**

```bash
# 先停掉正在运行的后端（如果有）
pkill -f "uvicorn app.main" || true
# 启动后端
cd /Users/aklu/CodeBuddy/AIpicking/backend && source venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
# 检查终端输出是否包含统一格式的日志行
# 检查日志文件
cat /Users/aklu/CodeBuddy/AIpicking/backend/logs/app.log
```

预期：
- 终端输出格式统一为 `2026-06-03 HH:MM:SS [INFO] ...`
- `logs/app.log` 文件包含相同内容
- 能看到 `uvicorn` 和 `app.main` 模块的日志行

- [ ] **Step 3: 清理并停止测试后端**

```bash
pkill -f "uvicorn app.main" || true
```

- [ ] **Step 4: Commit**

```bash
cd /Users/aklu/CodeBuddy/AIpicking && git add backend/app/main.py && git commit -m "feat: initialize logging on startup, replace print with logger"
```
