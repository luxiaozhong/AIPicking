# 策略发布、评分和评论 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为策略平台增加发布功能（一键公开策略）、五星评分和单层文字评论，同时修改回测可见性规则（已发布策略的回测所有人可见）。

**Architecture:** 后端新增 `is_published` 字段到 Strategy 模型 + 两张新表（ratings/comments），API 层增加发布/评分/评论端点。前端 StrategyList 增加 scope 筛选和发布状态/评分列，StrategyDetail 底部新增评分评论组件，非创建者隐藏代码。回测查询改为按策略发布状态驱动可见性。

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL · React 18 + TypeScript + Ant Design 6 + Zustand

---

## File Structure

```
新建:
  backend/migrate_add_publish.py          — 数据库迁移
  backend/app/models/strategy_rating.py    — 评分模型
  backend/app/models/strategy_comment.py   — 评论模型
  backend/app/schemas/rating.py            — 评分 schemas
  backend/app/schemas/comment.py           — 评论 schemas
  backend/app/api/ratings.py               — 评分路由
  backend/app/api/comments.py              — 评论路由
  backend/app/services/rating_service.py   — 评分服务
  backend/app/services/comment_service.py  — 评论服务
  backend/tests/test_publish.py            — 集成测试
  frontend/src/components/StrategyRating.tsx      — 评分组件
  frontend/src/components/StrategyComments.tsx    — 评论组件

修改:
  backend/app/models/strategy.py           — +is_published
  backend/app/models/__init__.py           — 注册新模型+关系
  backend/app/schemas/strategy.py          — 发布相关 schema
  backend/app/schemas/backtest.py          — +backtest_user_name
  backend/app/api/strategies.py            — publish/unpublish + scope
  backend/app/services/strategy_service.py — publish/unpublish + 权限 + scope
  backend/app/services/backtest_service.py — 回测可见性改策略驱动
  backend/app/main.py                      — 注册新路由
  frontend/src/types/strategy.ts           — 新类型
  frontend/src/services/strategyService.ts — 新 API 调用
  frontend/src/stores/strategyStore.ts     — 新 actions
  frontend/src/pages/StrategyList.tsx      — scope 筛选 + 列
  frontend/src/pages/StrategyDetail.tsx    — 权限 UI + 评分评论
```

---

### Task 1: 数据库迁移脚本

**Files:**
- Create: `backend/migrate_add_publish.py`

- [ ] **Step 1: 编写迁移脚本**

```python
"""迁移脚本：添加策略发布、评分、评论功能

运行方式：
    cd backend && source venv/bin/activate && python migrate_add_publish.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
from app.config import settings

def migrate():
    # 从 DATABASE_URL 解析连接参数
    sync_url = settings.SYNC_DATABASE_URL
    conn = psycopg2.connect(sync_url)
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # 1. strategies 表增加 is_published 列
        cursor.execute("""
            ALTER TABLE strategies
            ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT FALSE
        """)
        print("1. strategies.is_published 列已添加（或已存在）")

        # 2. 创建 strategy_ratings 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_ratings (
                id SERIAL PRIMARY KEY,
                strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE(strategy_id, user_id)
            )
        """)
        print("2. strategy_ratings 表已创建（或已存在）")

        # 3. 创建 strategy_ratings 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_ratings_strategy_id
            ON strategy_ratings(strategy_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_ratings_user_id
            ON strategy_ratings(user_id)
        """)
        print("3. strategy_ratings 索引已创建")

        # 4. 创建 strategy_comments 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_comments (
                id SERIAL PRIMARY KEY,
                strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """)
        print("4. strategy_comments 表已创建（或已存在）")

        # 5. 创建 strategy_comments 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_comments_strategy_id
            ON strategy_comments(strategy_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategy_comments_user_id
            ON strategy_comments(user_id)
        """)
        print("5. strategy_comments 索引已创建")

        # 6. 创建 is_published 索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_strategies_is_published
            ON strategies(is_published)
        """)
        print("6. strategies.is_published 索引已创建")

        conn.commit()
        print("\n迁移完成！")

    except Exception as e:
        conn.rollback()
        print(f"迁移失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrate()
```

- [ ] **Step 2: 运行迁移**

```bash
cd backend && source venv/bin/activate && python migrate_add_publish.py
```

Expected: 输出 "迁移完成！"

- [ ] **Step 3: 验证表结构**

```bash
cd backend && source venv/bin/activate && python -c "
import psycopg2
from app.config import settings
conn = psycopg2.connect(settings.SYNC_DATABASE_URL)
cur = conn.cursor()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name='strategies' AND column_name='is_published'\")
print('is_published:', cur.fetchone())
cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_name IN ('strategy_ratings','strategy_comments')\")
print('新表:', cur.fetchall())
conn.close()
"
```

Expected: `is_published: ('is_published',)` 和 `新表: [('strategy_comments',), ('strategy_ratings',)]`

- [ ] **Step 4: Commit**

```bash
git add backend/migrate_add_publish.py
git commit -m "feat: add migration for strategy publish, ratings, and comments"
```

---

### Task 2: 策略模型 — 新增 is_published 字段

**Files:**
- Modify: `backend/app/models/strategy.py:19`

- [ ] **Step 1: 修改 Strategy 模型**

在 `backend/app/models/strategy.py` 第 19 行（`version` 定义之后）新增：

```python
is_published = Column(Boolean, default=False, index=True)
```

并在文件顶部 import 加入 `Boolean`：

```python
from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean
```

最终 `backend/app/models/strategy.py` 完整内容：

```python
"""策略模型"""

from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .base import BaseModel


class Strategy(BaseModel):
    """策略表模型"""

    __tablename__ = "strategies"

    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text)
    file_path = Column(Text)
    params_schema = Column(Text)
    tags = Column(Text)
    status = Column(String(50), default="active", index=True)
    version = Column(Integer, default=1)
    factor_config = Column(Text)
    generated_code = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    is_published = Column(Boolean, default=False, index=True)
    owner = relationship("User", back_populates="strategies")

    @property
    def owner_name(self) -> str:
        return self.owner.username if self.owner else None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/strategy.py
git commit -m "feat: add is_published field to Strategy model"
```

---

### Task 3: 评分 & 评论模型

**Files:**
- Create: `backend/app/models/strategy_rating.py`
- Create: `backend/app/models/strategy_comment.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建评分模型**

```python
"""策略评分模型"""

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import BaseModel


class StrategyRating(BaseModel):
    """策略评分表"""

    __tablename__ = "strategy_ratings"

    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    score = Column(Integer, nullable=False)

    strategy = relationship("Strategy", back_populates="ratings")
    user = relationship("User", back_populates="ratings")

    __table_args__ = (
        UniqueConstraint("strategy_id", "user_id", name="uq_strategy_user_rating"),
    )
```

- [ ] **Step 2: 创建评论模型**

```python
"""策略评论模型"""

from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from .base import BaseModel


class StrategyComment(BaseModel):
    """策略评论表"""

    __tablename__ = "strategy_comments"

    strategy_id = Column(Integer, ForeignKey("strategies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)

    strategy = relationship("Strategy", back_populates="comments")
    user = relationship("User", back_populates="comments")

    @property
    def user_name(self) -> str:
        return self.user.username if self.user else None
```

- [ ] **Step 3: 修改模型注册文件**

修改 `backend/app/models/__init__.py`，新增导入和关系：

```python
"""Models package"""

from sqlalchemy.orm import relationship
from .base import Base, BaseModel
from .user import User
from .strategy import Strategy
from .backtest import BacktestReport, StrategyRun, BatchBacktestReport
from .ai_task import AIStrategyTask
from .ai_factor import AIFactor
from .strategy_rating import StrategyRating
from .strategy_comment import StrategyComment
from .stock_tables import (
    Stock, Daily, DailySectorFlow, StockTheme,
    DailyHotStock, DailyHotTheme, DailyNorthboundFlow,
    DailyDragonTiger, DailyDragonTigerSeat,
)

# 设置关系
Strategy.backtest_reports = relationship("BacktestReport", back_populates="strategy", cascade="all, delete-orphan")
Strategy.strategy_runs = relationship("StrategyRun", back_populates="strategy", cascade="all, delete-orphan")
Strategy.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="strategy", cascade="all, delete-orphan")
Strategy.owner = relationship("User", back_populates="strategies")
Strategy.ratings = relationship("StrategyRating", back_populates="strategy", cascade="all, delete-orphan")
Strategy.comments = relationship("StrategyComment", back_populates="strategy", cascade="all, delete-orphan")
BacktestReport.owner = relationship("User", back_populates="backtest_reports")
StrategyRun.owner = relationship("User", back_populates="strategy_runs")
BatchBacktestReport.owner = relationship("User", back_populates="batch_backtest_reports")
User.strategies = relationship("Strategy", back_populates="owner")
User.backtest_reports = relationship("BacktestReport", back_populates="owner")
User.strategy_runs = relationship("StrategyRun", back_populates="owner")
User.batch_backtest_reports = relationship("BatchBacktestReport", back_populates="owner")
User.ratings = relationship("StrategyRating", back_populates="user")
User.comments = relationship("StrategyComment", back_populates="user")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/strategy_rating.py backend/app/models/strategy_comment.py backend/app/models/__init__.py
git commit -m "feat: add StrategyRating and StrategyComment models"
```

---

### Task 4: 评分 & 评论 Schemas

**Files:**
- Create: `backend/app/schemas/rating.py`
- Create: `backend/app/schemas/comment.py`

- [ ] **Step 1: 创建评分 schemas**

```python
"""评分相关的 Pydantic schemas"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class RatingCreate(BaseModel):
    """提交/更新评分请求"""
    score: int = Field(..., ge=1, le=5, description="评分，1-5")


class RatingResponse(BaseModel):
    """单个评分响应"""
    id: int
    strategy_id: int
    user_id: int
    user_name: Optional[str] = None
    score: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RatingStats(BaseModel):
    """评分统计响应"""
    average: Optional[float] = Field(None, description="平均评分")
    count: int = Field(0, description="评分总人数")
    distribution: dict = Field(default_factory=dict, description="各星级人数 {1: n, 2: n, ...}")
    current_user_score: Optional[int] = Field(None, description="当前用户的评分")
```

- [ ] **Step 2: 创建评论 schemas**

```python
"""评论相关的 Pydantic schemas"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class CommentCreate(BaseModel):
    """发表评论请求"""
    content: str = Field(..., min_length=1, max_length=2000, description="评论内容")


class CommentResponse(BaseModel):
    """评论响应"""
    id: int
    strategy_id: int
    user_id: int
    user_name: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CommentListResponse(BaseModel):
    """评论列表响应"""
    items: List[CommentResponse]
    total: int
    page: int = 1
    limit: int = 20
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/rating.py backend/app/schemas/comment.py
git commit -m "feat: add rating and comment Pydantic schemas"
```

---

### Task 5: Strategy Schema 更新 — 发布相关

**Files:**
- Modify: `backend/app/schemas/strategy.py`

- [ ] **Step 1: 更新 StrategyResponse 和新增发布 schema**

在 `backend/app/schemas/strategy.py` 的 `StrategyResponse` 类中新增 `is_published` 字段，并添加 `PublishResponse`：

修改 `StrategyResponse`（在 `version` 之后添加 `is_published`）：

```python
class StrategyResponse(StrategyBase):
    """策略响应 schema"""
    id: int
    user_id: Optional[int] = None
    owner_name: Optional[str] = None
    status: str = "active"
    version: int = 1
    is_published: bool = False
    file_path: Optional[str] = None
    factor_config: Optional[Dict[str, Any]] = None
    generated_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # 评分统计（列表用）
    avg_score: Optional[float] = None
    rating_count: int = 0

    @field_validator('tags', mode='before')
    @classmethod
    def parse_tags(cls, v):
        if isinstance(v, str):
            return [t.strip() for t in v.split(',') if t.strip()]
        return v

    @field_validator('factor_config', mode='before')
    @classmethod
    def parse_factor_config(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    class Config:
        from_attributes = True
```

文件末尾新增 PublishResponse：

```python
class PublishResponse(BaseModel):
    """发布/取消发布响应"""
    code: int = 0
    message: str
    is_published: bool
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/strategy.py
git commit -m "feat: add is_published and avg_score to StrategyResponse"
```

---

### Task 6: Backtest Schema — 新增执行者名称

**Files:**
- Modify: `backend/app/schemas/backtest.py`

- [ ] **Step 1: 更新 BacktestResponse**

在 `BacktestResponse` 的 `summary` 字段之前新增 `user_name` 字段：

```python
class BacktestResponse(BaseModel):
    """回测报告响应 schema"""
    id: int
    strategy_id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    strategy_name: Optional[str] = None
    name: Optional[str] = None
    status: str = "pending"
    cutoff_date: str
    config: Optional[dict] = None
    recommendations: Optional[List[RecommendationItem]] = None
    summary: Optional[BacktestSummary] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # ... rest unchanged (field_validators and Config)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/backtest.py
git commit -m "feat: add user_id and user_name to BacktestResponse"
```

---

### Task 7: 策略服务层 — 发布/取消发布 + scope + 权限

**Files:**
- Modify: `backend/app/services/strategy_service.py:29-68` (get_strategies), `:71-95` (get_strategy)

- [ ] **Step 1: 修改 get_strategies — 添加 scope 和评分统计**

替换 `get_strategies` 方法（第 28-68 行）：

```python
@staticmethod
async def get_strategies(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
    scope: str = "all",
    user_id: Optional[int] = None,
    user_role: str = "user",
) -> Tuple[List[Strategy], int]:
    """获取策略列表"""
    from sqlalchemy import case
    from ..models.strategy_rating import StrategyRating

    query = select(
        Strategy,
        func.coalesce(func.avg(StrategyRating.score), 0).label("avg_score"),
        func.count(StrategyRating.id).label("rating_count"),
    ).options(
        selectinload(Strategy.owner)
    ).outerjoin(
        StrategyRating, StrategyRating.strategy_id == Strategy.id
    ).group_by(Strategy.id)

    # 权限筛选
    if user_role != "admin":
        if scope == "mine":
            query = query.where(Strategy.user_id == user_id)
        elif scope == "published":
            query = query.where(
                (Strategy.is_published == True) & (Strategy.user_id != user_id)
            )
        else:  # all
            query = query.where(
                (Strategy.user_id == user_id) | (Strategy.is_published == True)
            )

    # 通用筛选
    if search:
        query = query.where(Strategy.name.like(f"%{search}%"))
    if status:
        query = query.where(Strategy.status == status)

    # 排序
    query = query.order_by(Strategy.created_at.desc())

    # 计算总数
    count_query = select(func.count()).select_from(Strategy)
    if user_role != "admin":
        if scope == "mine":
            count_query = count_query.where(Strategy.user_id == user_id)
        elif scope == "published":
            count_query = count_query.where(
                (Strategy.is_published == True) & (Strategy.user_id != user_id)
            )
        else:
            count_query = count_query.where(
                (Strategy.user_id == user_id) | (Strategy.is_published == True)
            )
    if search:
        count_query = count_query.where(Strategy.name.like(f"%{search}%"))
    if status:
        count_query = count_query.where(Strategy.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    rows = result.all()

    # 组装：将 avg_score / rating_count 赋到 strategy 对象上
    strategies = []
    for row in rows:
        strategy = row[0]
        strategy._avg_score = float(row[1]) if row[1] else None
        strategy._rating_count = row[2] if row[2] else 0
        strategies.append(strategy)

    return strategies, total
```

- [ ] **Step 2: 修改 get_strategy — 允许非创建者访问已发布策略**

替换 `get_strategy` 方法（第 70-95 行）：

```python
@staticmethod
async def get_strategy(
    db: AsyncSession,
    strategy_id: int,
    user_id: Optional[int] = None,
    user_role: str = "user",
) -> Optional[Strategy]:
    """获取单个策略"""
    query = select(Strategy).options(selectinload(Strategy.owner)).where(Strategy.id == strategy_id)
    result = await db.execute(query)
    strategy = result.scalar_one_or_none()

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy with id {strategy_id} not found"
        )

    # 权限检查：admin 全通过；创建者全通过；已发布的策略其他人可查看
    is_owner = strategy.user_id == user_id
    if user_role != "admin" and not is_owner and not strategy.is_published:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此策略"
        )

    return strategy
```

- [ ] **Step 3: 新增 publish / unpublish 方法**

在 `StrategyService` 类末尾（`get_generated_code` 之后）新增：

```python
@staticmethod
async def publish_strategy(
    db: AsyncSession,
    strategy_id: int,
    user_id: int,
) -> dict:
    """发布策略"""
    query = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(query)
    strategy = result.scalar_one_or_none()

    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    if strategy.user_id != user_id:
        raise HTTPException(status_code=403, detail="只有策略创建者可以发布")

    strategy.is_published = True
    await db.commit()
    return {"code": 0, "message": "发布成功", "is_published": True}


@staticmethod
async def unpublish_strategy(
    db: AsyncSession,
    strategy_id: int,
    user_id: int,
) -> dict:
    """取消发布策略"""
    query = select(Strategy).where(Strategy.id == strategy_id)
    result = await db.execute(query)
    strategy = result.scalar_one_or_none()

    if not strategy:
        raise HTTPException(status_code=404, detail="策略不存在")
    if strategy.user_id != user_id:
        raise HTTPException(status_code=403, detail="只有策略创建者可以取消发布")

    strategy.is_published = False
    await db.commit()
    return {"code": 0, "message": "已取消发布", "is_published": False}
```

- [ ] **Step 4: 修改 update_strategy / delete_strategy 权限检查**

在 `update_strategy`（第 209 行附近）和 `delete_strategy`（第 235 行附近）中，确保只有创建者可操作。当前逻辑已通过 `get_strategy` 做权限检查。需要修改 `get_strategy` 调用让它不通过已发布绕过。新增参数 `allow_published=False`：

将 `get_strategy` 签名改为：

```python
@staticmethod
async def get_strategy(
    db: AsyncSession,
    strategy_id: int,
    user_id: Optional[int] = None,
    user_role: str = "user",
    require_owner: bool = False,
) -> Optional[Strategy]:
```

在权限检查处：

```python
    # 权限检查
    is_owner = strategy.user_id == user_id
    if require_owner:
        if not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有策略创建者可以执行此操作"
            )
    elif user_role != "admin" and not is_owner and not strategy.is_published:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此策略"
        )
```

然后修改 `update_strategy`、`delete_strategy`、`permanent_delete_strategy` 中调用 `get_strategy` 时传 `require_owner=True`。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/strategy_service.py
git commit -m "feat: add publish/unpublish, scope filtering, and owner-required permission checks"
```

---

### Task 8: 评分服务层

**Files:**
- Create: `backend/app/services/rating_service.py`

- [ ] **Step 1: 创建评分服务**

```python
"""评分业务逻辑层"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from ..models.strategy_rating import StrategyRating
from ..models.strategy import Strategy


class RatingService:
    """评分服务类"""

    @staticmethod
    async def upsert_rating(
        db: AsyncSession,
        strategy_id: int,
        user_id: int,
        score: int,
    ) -> StrategyRating:
        """提交或更新评分"""
        # 检查策略是否存在且可访问
        strategy = await db.get(Strategy, strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        # 查找已有评分
        result = await db.execute(
            select(StrategyRating).where(
                StrategyRating.strategy_id == strategy_id,
                StrategyRating.user_id == user_id,
            )
        )
        rating = result.scalar_one_or_none()

        if rating:
            rating.score = score
        else:
            rating = StrategyRating(
                strategy_id=strategy_id,
                user_id=user_id,
                score=score,
            )
            db.add(rating)

        await db.commit()
        await db.refresh(rating)
        return rating

    @staticmethod
    async def get_rating_stats(
        db: AsyncSession,
        strategy_id: int,
        current_user_id: Optional[int] = None,
    ) -> dict:
        """获取评分统计"""
        # 均分 & 总数
        result = await db.execute(
            select(
                func.avg(StrategyRating.score).label("avg"),
                func.count(StrategyRating.id).label("cnt"),
            ).where(StrategyRating.strategy_id == strategy_id)
        )
        row = result.one()
        avg = float(row[0]) if row[0] else None
        cnt = row[1] or 0

        # 分布
        dist_result = await db.execute(
            select(
                StrategyRating.score,
                func.count(StrategyRating.id),
            ).where(StrategyRating.strategy_id == strategy_id)
            .group_by(StrategyRating.score)
        )
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for score, count in dist_result.all():
            distribution[score] = count

        # 当前用户评分
        current_user_score = None
        if current_user_id:
            u_result = await db.execute(
                select(StrategyRating.score).where(
                    StrategyRating.strategy_id == strategy_id,
                    StrategyRating.user_id == current_user_id,
                )
            )
            score_row = u_result.scalar_one_or_none()
            current_user_score = score_row

        return {
            "average": avg,
            "count": cnt,
            "distribution": distribution,
            "current_user_score": current_user_score,
        }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/rating_service.py
git commit -m "feat: add RatingService with upsert and stats"
```

---

### Task 9: 评论服务层

**Files:**
- Create: `backend/app/services/comment_service.py`

- [ ] **Step 1: 创建评论服务**

```python
"""评论业务逻辑层"""

from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from ..models.strategy_comment import StrategyComment
from ..models.strategy import Strategy


class CommentService:
    """评论服务类"""

    @staticmethod
    async def create_comment(
        db: AsyncSession,
        strategy_id: int,
        user_id: int,
        content: str,
    ) -> StrategyComment:
        """发表评论"""
        strategy = await db.get(Strategy, strategy_id)
        if not strategy:
            raise HTTPException(status_code=404, detail="策略不存在")

        comment = StrategyComment(
            strategy_id=strategy_id,
            user_id=user_id,
            content=content,
        )
        db.add(comment)
        await db.commit()
        # 重新加载以获取 user 关系
        result = await db.execute(
            select(StrategyComment)
            .options(selectinload(StrategyComment.user))
            .where(StrategyComment.id == comment.id)
        )
        return result.scalar_one()

    @staticmethod
    async def get_comments(
        db: AsyncSession,
        strategy_id: int,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[StrategyComment], int]:
        """获取评论列表（按时间倒序）"""
        # 总数
        count_result = await db.execute(
            select(func.count()).select_from(StrategyComment)
            .where(StrategyComment.strategy_id == strategy_id)
        )
        total = count_result.scalar()

        # 分页
        offset = (page - 1) * limit
        result = await db.execute(
            select(StrategyComment)
            .options(selectinload(StrategyComment.user))
            .where(StrategyComment.strategy_id == strategy_id)
            .order_by(StrategyComment.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        comments = result.scalars().all()

        return comments, total

    @staticmethod
    async def delete_comment(
        db: AsyncSession,
        comment_id: int,
        user_id: int,
    ) -> None:
        """删除评论（评论作者或策略创建者）"""
        comment = await db.get(StrategyComment, comment_id)
        if not comment:
            raise HTTPException(status_code=404, detail="评论不存在")

        # 检查权限：评论作者或策略创建者
        strategy = await db.get(Strategy, comment.strategy_id)
        is_comment_author = comment.user_id == user_id
        is_strategy_owner = strategy and strategy.user_id == user_id

        if not is_comment_author and not is_strategy_owner:
            raise HTTPException(
                status_code=403,
                detail="无权删除此评论"
            )

        await db.delete(comment)
        await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/comment_service.py
git commit -m "feat: add CommentService with CRUD"
```

---

### Task 10: 策略 API — 发布/取消发布 + scope

**Files:**
- Modify: `backend/app/api/strategies.py`

- [ ] **Step 1: 更新 list_strategies 增加 scope 参数**

在 `list_strategies` 函数签名中增加 `scope` 参数，传给 service：

```python
@router.get("", response_model=StrategyListResponse)
async def list_strategies(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    scope: str = Query("all", description="筛选范围: all / mine / published"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略列表"""
    if not status:
        status = "active"

    strategies, total = await StrategyService.get_strategies(
        db, page, limit, search, status,
        scope=scope,
        user_id=current_user.id, user_role=current_user.role
    )

    return {
        "items": strategies,
        "total": total,
        "page": page,
        "limit": limit
    }
```

- [ ] **Step 2: 新增 publish / unpublish 端点**

在 `/strategies` 路由中添加（放在 `/code` 路由之前以避免匹配冲突）：

```python
@router.put("/{strategy_id}/publish")
async def publish_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发布策略（创建者操作）"""
    return await StrategyService.publish_strategy(
        db, strategy_id, user_id=current_user.id
    )


@router.put("/{strategy_id}/unpublish")
async def unpublish_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消发布策略（创建者操作）"""
    return await StrategyService.unpublish_strategy(
        db, strategy_id, user_id=current_user.id
    )
```

- [ ] **Step 3: 更新 update_strategy / delete_strategy 调用**

确保 `get_strategy` 调用使用 `require_owner=True`。在 `update_strategy`（第 126 行）和 `delete_strategy`（第 166 行）处，将 service 调用改为传入 `require_owner=True`：

```python
# update_strategy 中
return await StrategyService.update_strategy(
    db, strategy_id, strategy,
    user_id=current_user.id, user_role=current_user.role
)
```

同时确保 `StrategyService.update_strategy` 内部调用 `get_strategy` 时传 `require_owner=True`。

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/strategies.py
git commit -m "feat: add publish/unpublish endpoints and scope param to strategy list"
```

---

### Task 11: 评分 & 评论 API

**Files:**
- Create: `backend/app/api/ratings.py`
- Create: `backend/app/api/comments.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建评分路由**

```python
"""评分相关 API 路由"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.rating_service import RatingService
from ..schemas.rating import RatingCreate, RatingStats
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.post("/{strategy_id}/ratings")
async def rate_strategy(
    strategy_id: int,
    body: RatingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交或更新评分"""
    rating = await RatingService.upsert_rating(
        db, strategy_id, user_id=current_user.id, score=body.score
    )
    return {
        "code": 0,
        "message": "评分成功",
        "data": {"id": rating.id, "score": rating.score}
    }


@router.get("/{strategy_id}/ratings", response_model=RatingStats)
async def get_ratings(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取评分统计（含当前用户评分）"""
    return await RatingService.get_rating_stats(
        db, strategy_id, current_user_id=current_user.id
    )
```

- [ ] **Step 2: 创建评论路由**

```python
"""评论相关 API 路由"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.comment_service import CommentService
from ..schemas.comment import CommentCreate, CommentListResponse
from ..middleware.auth import get_current_user
from ..models.user import User

router = APIRouter()


@router.post("/{strategy_id}/comments")
async def create_comment(
    strategy_id: int,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发表评论"""
    comment = await CommentService.create_comment(
        db, strategy_id, user_id=current_user.id, content=body.content
    )
    return {
        "code": 0,
        "message": "评论成功",
        "data": {
            "id": comment.id,
            "content": comment.content,
            "user_name": comment.user.username if comment.user else None,
            "created_at": comment.created_at.isoformat(),
        }
    }


@router.get("/{strategy_id}/comments", response_model=CommentListResponse)
async def get_comments(
    strategy_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取评论列表"""
    comments, total = await CommentService.get_comments(db, strategy_id, page, limit)
    return {
        "items": comments,
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.delete("/{strategy_id}/comments/{comment_id}")
async def delete_comment(
    strategy_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除评论（评论作者或策略创建者）"""
    await CommentService.delete_comment(db, comment_id, user_id=current_user.id)
    return {"code": 0, "message": "删除成功"}
```

- [ ] **Step 3: 注册路由到 main.py**

修改 `backend/app/main.py`，在已有的 router 注册处新增：

```python
from .api.ratings import router as ratings_router
from .api.comments import router as comments_router

# 在 router 注册区域新增：
app.include_router(ratings_router, prefix="/api/v1/strategies", tags=["ratings"])
app.include_router(comments_router, prefix="/api/v1/strategies", tags=["comments"])
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/ratings.py backend/app/api/comments.py backend/app/main.py
git commit -m "feat: add rating and comment API endpoints"
```

---

### Task 12: 回测服务层 — 可见性改为策略驱动

**Files:**
- Modify: `backend/app/services/backtest_service.py:41-80` (get_backtests)

- [ ] **Step 1: 修改 get_backtests 查询逻辑**

将第 51-62 行的查询改为 JOIN Strategy 表按 `is_published` 判断可见性：

```python
@staticmethod
async def get_backtests(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    strategy_id: Optional[int] = None,
    status: Optional[str] = None,
    stock: Optional[str] = None,
    user_id: Optional[int] = None,
    user_role: str = "user",
) -> Tuple[List[BacktestReport], int]:
    """获取回测报告列表 — 可见性由关联策略的 is_published 决定"""
    from ..models.strategy import Strategy

    query = select(BacktestReport).options(
        selectinload(BacktestReport.strategy),
        selectinload(BacktestReport.owner),
    ).join(Strategy, BacktestReport.strategy_id == Strategy.id)

    if strategy_id:
        query = query.where(BacktestReport.strategy_id == strategy_id)
    if status:
        query = query.where(BacktestReport.status == status)
    if stock:
        query = query.where(BacktestReport.recommendations.like(f"%{stock}%"))
    if user_role != "admin":
        # 自己的回测 OR 关联策略已发布的回测
        query = query.where(
            (BacktestReport.user_id == user_id) |
            (Strategy.is_published == True)
        )

    # 计算总数
    count_query = select(func.count()).select_from(BacktestReport).join(
        Strategy, BacktestReport.strategy_id == Strategy.id
    )
    if strategy_id:
        count_query = count_query.where(BacktestReport.strategy_id == strategy_id)
    if status:
        count_query = count_query.where(BacktestReport.status == status)
    if stock:
        count_query = count_query.where(BacktestReport.recommendations.like(f"%{stock}%"))
    if user_role != "admin":
        count_query = count_query.where(
            (BacktestReport.user_id == user_id) |
            (Strategy.is_published == True)
        )
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit).order_by(BacktestReport.created_at.desc())

    result = await db.execute(query)
    backtests = result.scalars().all()

    return backtests, total
```

- [ ] **Step 2: 修改 get_backtest 权限检查**

找到 `get_backtest` 方法，同样 JOIN Strategy 判断可见性：

```python
@staticmethod
async def get_backtest(
    db: AsyncSession,
    backtest_id: int,
    user_id: Optional[int] = None,
    user_role: str = "user",
) -> BacktestReport:
    """获取单个回测报告"""
    from ..models.strategy import Strategy

    result = await db.execute(
        select(BacktestReport)
        .options(
            selectinload(BacktestReport.strategy),
            selectinload(BacktestReport.owner),
        )
        .join(Strategy, BacktestReport.strategy_id == Strategy.id)
        .where(BacktestReport.id == backtest_id)
    )
    backtest = result.scalar_one_or_none()

    if not backtest:
        raise HTTPException(status_code=404, detail="回测报告不存在")

    # 权限检查
    is_owner = backtest.user_id == user_id
    if user_role != "admin" and not is_owner and not backtest.strategy.is_published:
        raise HTTPException(status_code=403, detail="无权访问此回测报告")

    return backtest
```

- [ ] **Step 3: 确保 BacktestResponse 包含 user_name**

在 `get_backtests` 和 `get_backtest` 返回的数据中，`user_name` 通过 `BacktestReport.owner.username` 获取。`BacktestResponse` 的 `model_validate` 需要能解析此字段。在 `backend/app/api/backtests.py` 返回数据时增加 `user_name`：

```python
# 在 list_backtests 的返回值中为每个 item 增加 user_name
items = []
for bt in backtests:
    item = BacktestResponse.model_validate(bt).model_dump()
    item["user_name"] = bt.owner.username if bt.owner else None
    items.append(item)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/backtest_service.py backend/app/api/backtests.py
git commit -m "feat: make backtest visibility strategy-driven with user_name"
```

---

### Task 13: 后端集成测试

**Files:**
- Create: `backend/tests/test_publish.py`

- [ ] **Step 1: 编写测试**

```python
"""策略发布、评分、评论功能测试"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_db
from app.models import User, Strategy, StrategyRating, StrategyComment


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(test_db):
    """创建测试客户端"""
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _login(client, username, password):
    r = await client.post("/api/v1/auth/login", json={
        "username": username, "password": password
    })
    return r.json()["data"]["access_token"]


@pytest.fixture
async def user1_token(client, test_db):
    """创建 user1"""
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    u = User(username="testuser1", password_hash=pwd.hash("123456"), role="user")
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    return await _login(client, "testuser1", "123456")


@pytest.fixture
async def user2_token(client, test_db):
    """创建 user2"""
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    u = User(username="testuser2", password_hash=pwd.hash("123456"), role="user")
    test_db.add(u)
    await test_db.commit()
    await test_db.refresh(u)
    return await _login(client, "testuser2", "123456")


class TestStrategyPublish:
    """策略发布功能测试"""

    async def test_publish_strategy(self, client, user1_token, test_db):
        """创建者可以发布策略"""
        headers = {"Authorization": f"Bearer {user1_token}"}
        # 创建策略
        r = await client.post("/api/v1/strategies", json={
            "name": "test_publish",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers)
        sid = r.json()["data"]["id"]

        # 发布
        r = await client.put(f"/api/v1/strategies/{sid}/publish", headers=headers)
        assert r.json()["code"] == 0
        assert r.json()["is_published"] is True

    async def test_non_owner_cannot_publish(self, client, user1_token, user2_token, test_db):
        """非创建者不能发布"""
        headers1 = {"Authorization": f"Bearer {user1_token}"}
        headers2 = {"Authorization": f"Bearer {user2_token}"}
        r = await client.post("/api/v1/strategies", json={
            "name": "no_pub",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers1)
        sid = r.json()["data"]["id"]

        r = await client.put(f"/api/v1/strategies/{sid}/publish", headers=headers2)
        assert r.status_code == 403

    async def test_scope_all(self, client, user1_token, user2_token, test_db):
        """scope=all 返回自己的 + 别人已发布的"""
        headers1 = {"Authorization": f"Bearer {user1_token}"}
        headers2 = {"Authorization": f"Bearer {user2_token}"}

        # user1 创建并发布策略
        r = await client.post("/api/v1/strategies", json={
            "name": "published1",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers1)
        sid = r.json()["data"]["id"]
        await client.put(f"/api/v1/strategies/{sid}/publish", headers=headers1)

        # user2 查看 all
        r = await client.get("/api/v1/strategies?scope=all&status=", headers=headers2)
        items = r.json()["items"]
        assert any(s["id"] == sid for s in items)

    async def test_scope_mine(self, client, user1_token, user2_token, test_db):
        """scope=mine 仅返回自己的"""
        headers1 = {"Authorization": f"Bearer {user1_token}"}
        headers2 = {"Authorization": f"Bearer {user2_token}"}

        r = await client.post("/api/v1/strategies", json={
            "name": "mine_only",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers1)
        sid = r.json()["data"]["id"]

        r = await client.get("/api/v1/strategies?scope=mine&status=", headers=headers2)
        items = r.json()["items"]
        assert not any(s["id"] == sid for s in items)

    async def test_non_owner_hides_code(self, client, user1_token, user2_token, test_db):
        """非创建者看不到策略代码"""
        headers1 = {"Authorization": f"Bearer {user1_token}"}
        headers2 = {"Authorization": f"Bearer {user2_token}"}

        # user1 创建并发布策略
        r = await client.post("/api/v1/strategies", json={
            "name": "code_hidden",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers1)
        sid = r.json()["data"]["id"]
        await client.put(f"/api/v1/strategies/{sid}/publish", headers=headers1)

        # user2 查看详情 — 代码应隐藏
        r = await client.get(f"/api/v1/strategies/{sid}", headers=headers2)
        data = r.json()
        assert data["code"] == 0
        assert data["data"]["factor_config"] is not None  # 因子配置可见
        assert data["code_content"] == "" or data["code_content"] is None  # 代码隐藏


class TestRatings:
    """评分功能测试"""

    async def test_create_and_get_ratings(self, client, user1_token, user2_token, test_db):
        """评分和统计"""
        headers1 = {"Authorization": f"Bearer {user1_token}"}
        headers2 = {"Authorization": f"Bearer {user2_token}"}

        r = await client.post("/api/v1/strategies", json={
            "name": "rated",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers1)
        sid = r.json()["data"]["id"]

        # user2 评分
        await client.post(f"/api/v1/strategies/{sid}/ratings", json={"score": 4}, headers=headers2)
        await client.post(f"/api/v1/strategies/{sid}/ratings", json={"score": 5}, headers=headers1)

        # 统计
        r = await client.get(f"/api/v1/strategies/{sid}/ratings", headers=headers1)
        stats = r.json()
        assert stats["average"] == 4.5
        assert stats["count"] == 2

    async def test_single_rating_per_user(self, client, user1_token, test_db):
        """同一用户多次评分是更新而非新增"""
        headers = {"Authorization": f"Bearer {user1_token}"}
        r = await client.post("/api/v1/strategies", json={
            "name": "single_rating",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers)
        sid = r.json()["data"]["id"]

        await client.post(f"/api/v1/strategies/{sid}/ratings", json={"score": 2}, headers=headers)
        await client.post(f"/api/v1/strategies/{sid}/ratings", json={"score": 5}, headers=headers)

        r = await client.get(f"/api/v1/strategies/{sid}/ratings", headers=headers)
        stats = r.json()
        assert stats["count"] == 1
        assert stats["average"] == 5.0


class TestComments:
    """评论功能测试"""

    async def test_create_and_list_comments(self, client, user1_token, user2_token, test_db):
        """发表和列表"""
        headers1 = {"Authorization": f"Bearer {user1_token}"}
        headers2 = {"Authorization": f"Bearer {user2_token}"}

        r = await client.post("/api/v1/strategies", json={
            "name": "commented",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers1)
        sid = r.json()["data"]["id"]

        await client.post(f"/api/v1/strategies/{sid}/comments", json={"content": "不错"}, headers=headers2)
        await client.post(f"/api/v1/strategies/{sid}/comments", json={"content": "还行"}, headers=headers1)

        r = await client.get(f"/api/v1/strategies/{sid}/comments", headers=headers1)
        data = r.json()
        assert data["total"] == 2

    async def test_strategy_owner_can_delete_comment(self, client, user1_token, user2_token, test_db):
        """策略创建者可以删除他人评论"""
        headers1 = {"Authorization": f"Bearer {user1_token}"}
        headers2 = {"Authorization": f"Bearer {user2_token}"}

        r = await client.post("/api/v1/strategies", json={
            "name": "delete_comment",
            "description": "test",
            "factor_config": {
                "buy_signals": {"logic": "AND", "factors": []},
                "sell_signals": {"logic": "AND", "factors": []},
                "risk_factors": []
            }
        }, headers=headers1)
        sid = r.json()["data"]["id"]

        r = await client.post(f"/api/v1/strategies/{sid}/comments", json={"content": "spam"}, headers=headers2)
        cid = r.json()["data"]["id"]

        r = await client.delete(f"/api/v1/strategies/{sid}/comments/{cid}", headers=headers1)
        assert r.json()["code"] == 0
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && source venv/bin/activate && pytest tests/test_publish.py -v -x
```

Expected: 所有测试通过

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_publish.py
git commit -m "test: add integration tests for publish, ratings, and comments"
```

---

### Task 14: 前端类型定义

**Files:**
- Modify: `frontend/src/types/strategy.ts`

- [ ] **Step 1: 新增类型**

在 `frontend/src/types/strategy.ts` 末尾追加：

```typescript
// 发布相关
export interface PublishResponse {
  code: number;
  message: string;
  is_published: boolean;
}

// 评分相关
export interface RatingStats {
  average: number | null;
  count: number;
  distribution: Record<number, number>;
  current_user_score: number | null;
}

export interface RatingSubmitResponse {
  code: number;
  message: string;
  data: {
    id: number;
    score: number;
  };
}

// 评论相关
export interface CommentItem {
  id: number;
  strategy_id: number;
  user_id: number;
  user_name: string | null;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface CommentListResponse {
  items: CommentItem[];
  total: number;
  page: number;
  limit: number;
}

export interface CommentCreateResponse {
  code: number;
  message: string;
  data: {
    id: number;
    content: string;
    user_name: string | null;
    created_at: string;
  };
}
```

同时在 `Strategy` 接口中新增字段：

```typescript
export interface Strategy {
  // ... existing fields
  is_published: boolean;
  avg_score?: number | null;
  rating_count?: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/strategy.ts
git commit -m "feat: add publish, rating, and comment types"
```

---

### Task 15: 前端 Strategy Service — 新增 API 方法

**Files:**
- Modify: `frontend/src/services/strategyService.ts`

- [ ] **Step 1: 新增方法**

在 `strategyService` 对象内追加以下方法：

```typescript
  // 发布策略
  async publishStrategy(id: number) {
    const response = await api.put<{ code: number; message: string; is_published: boolean }>(`/strategies/${id}/publish`);
    return response.data;
  },

  // 取消发布策略
  async unpublishStrategy(id: number) {
    const response = await api.put<{ code: number; message: string; is_published: boolean }>(`/strategies/${id}/unpublish`);
    return response.data;
  },

  // 评分
  async rateStrategy(id: number, score: number) {
    const response = await api.post<{ code: number; message: string; data: { id: number; score: number } }>(`/strategies/${id}/ratings`, { score });
    return response.data;
  },

  // 获取评分统计
  async getStrategyRatings(id: number) {
    const response = await api.get<{ average: number | null; count: number; distribution: Record<number, number>; current_user_score: number | null }>(`/strategies/${id}/ratings`);
    return response.data;
  },

  // 发表评论
  async addComment(id: number, content: string) {
    const response = await api.post<{ code: number; message: string; data: { id: number; content: string; user_name: string | null; created_at: string } }>(`/strategies/${id}/comments`, { content });
    return response.data;
  },

  // 获取评论列表
  async getComments(id: number, page = 1, limit = 20) {
    const response = await api.get<{ items: import('@/types/strategy').CommentItem[]; total: number; page: number; limit: number }>(`/strategies/${id}/comments`, { params: { page, limit } });
    return response.data;
  },

  // 删除评论
  async deleteComment(strategyId: number, commentId: number) {
    const response = await api.delete<{ code: number; message: string }>(`/strategies/${strategyId}/comments/${commentId}`);
    return response.data;
  },
```

同时修改 `getStrategies` 方法，增加 `scope` 参数：

```typescript
  async getStrategies(params: {
    page?: number;
    limit?: number;
    search?: string;
    status?: string;
    scope?: string;
  } = {}) {
    const response = await api.get<StrategyListResponse>('/strategies', {
      params,
    });
    return response.data;
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/strategyService.ts
git commit -m "feat: add publish, rating, and comment API methods"
```

---

### Task 16: 前端 Strategy Store — 新增 Actions

**Files:**
- Modify: `frontend/src/stores/strategyStore.ts`

- [ ] **Step 1: 扩展接口和实现**

在 `StrategyState` 接口中新增 actions 类型声明：

```typescript
  publishStrategy: (id: number) => Promise<void>;
  unpublishStrategy: (id: number) => Promise<void>;
  rateStrategy: (id: number, score: number) => Promise<void>;
  fetchRatings: (id: number) => Promise<import('@/types/strategy').RatingStats | null>;
  addComment: (id: number, content: string) => Promise<void>;
  fetchComments: (id: number, page?: number) => Promise<import('@/types/strategy').CommentListResponse | null>;
  deleteComment: (strategyId: number, commentId: number) => Promise<void>;
```

在 `create` 回调的 return 对象中实现这些方法（在 `clearError` 之前）：

```typescript
  // 发布策略
  publishStrategy: async (id: number) => {
    set({ loading: true, error: null });
    try {
      await strategyService.publishStrategy(id);
      await get().fetchStrategies();
      if (get().currentStrategy?.id === id) {
        await get().fetchStrategy(id);
      }
      set({ loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.message || '发布失败' });
      throw error;
    }
  },

  // 取消发布
  unpublishStrategy: async (id: number) => {
    set({ loading: true, error: null });
    try {
      await strategyService.unpublishStrategy(id);
      await get().fetchStrategies();
      if (get().currentStrategy?.id === id) {
        await get().fetchStrategy(id);
      }
      set({ loading: false });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.message || '取消发布失败' });
      throw error;
    }
  },

  // 评分
  rateStrategy: async (id: number, score: number) => {
    try {
      await strategyService.rateStrategy(id, score);
    } catch (error: any) {
      set({ error: error.response?.data?.message || '评分失败' });
      throw error;
    }
  },

  // 获取评分统计
  fetchRatings: async (id: number) => {
    try {
      return await strategyService.getStrategyRatings(id);
    } catch {
      return null;
    }
  },

  // 发表评论
  addComment: async (id: number, content: string) => {
    try {
      await strategyService.addComment(id, content);
    } catch (error: any) {
      set({ error: error.response?.data?.message || '评论失败' });
      throw error;
    }
  },

  // 获取评论列表
  fetchComments: async (id: number, page = 1) => {
    try {
      return await strategyService.getComments(id, page);
    } catch {
      return null;
    }
  },

  // 删除评论
  deleteComment: async (strategyId: number, commentId: number) => {
    try {
      await strategyService.deleteComment(strategyId, commentId);
    } catch (error: any) {
      set({ error: error.response?.data?.message || '删除评论失败' });
      throw error;
    }
  },
```

同时修改 `fetchStrategies` 方法，在 params 中增加 `scope`：

```typescript
  fetchStrategies: async (params: { page?: number; limit?: number; search?: string; status?: string; scope?: string } = {}) => {
    set({ loading: true, error: null });
    try {
      const response = await strategyService.getStrategies({
        page: params.page || get().page,
        limit: params.limit || get().limit,
        search: params.search,
        status: params.status,
        scope: params.scope,
      });
      set({
        strategies: response.items,
        total: response.total,
        page: response.page,
        limit: response.limit,
        loading: false,
      });
    } catch (error: any) {
      set({ loading: false, error: error.response?.data?.message || '获取策略列表失败' });
    }
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/strategyStore.ts
git commit -m "feat: add publish, rating, and comment actions to strategy store"
```

---

### Task 17: 策略列表页改造

**Files:**
- Modify: `frontend/src/pages/StrategyList.tsx`

- [ ] **Step 1: 新增 scope 筛选器，改造列和操作**

完整替换 `frontend/src/pages/StrategyList.tsx`：

```tsx
import { useEffect, useMemo, useState } from 'react';
import { Card, Button, Table, Input, Select, Space, message, Popconfirm, Tag } from 'antd';
import { AppstoreOutlined, RobotOutlined, GlobalOutlined, LockOutlined, BarChartOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useStrategyStore } from '@/stores/strategyStore';
import { useAuthStore } from '@/stores/authStore';
import PageHeader from '@/components/shared/PageHeader';
import StatusTag from '@/components/shared/StatusTag';
import type { Strategy } from '@/types/strategy';

const { Search } = Input;

export default function StrategyList() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';
  const {
    strategies,
    total,
    page,
    limit,
    loading,
    error,
    fetchStrategies,
    deleteStrategy,
    updateStrategy,
    permanentDeleteStrategy,
    publishStrategy,
    unpublishStrategy,
    clearError,
  } = useStrategyStore();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [scopeFilter, setScopeFilter] = useState<string>('all');

  useEffect(() => {
    fetchStrategies({ scope: 'all' });
  }, [fetchStrategies]);

  useEffect(() => {
    if (error) {
      message.error(error);
      clearError();
    }
  }, [error, clearError]);

  const handleSearch = (value: string) => {
    setSearch(value);
    fetchStrategies({ page: 1, search: value || undefined, status: statusFilter, scope: scopeFilter });
  };

  const handleStatusFilter = (value: string | undefined) => {
    setStatusFilter(value);
    fetchStrategies({ page: 1, search: search || undefined, status: value, scope: scopeFilter });
  };

  const handleScopeFilter = (value: string) => {
    setScopeFilter(value);
    fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: value });
  };

  const handlePageChange = (newPage: number, newLimit: number) => {
    fetchStrategies({ page: newPage, limit: newLimit, search: search || undefined, status: statusFilter, scope: scopeFilter });
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteStrategy(id);
      message.success('删除成功');
      fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: scopeFilter });
    } catch {
      message.error('删除失败');
    }
  };

  const handleRestore = async (id: number) => {
    try {
      await updateStrategy(id, { status: 'active' });
      message.success('恢复成功');
      fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: scopeFilter });
    } catch {
      message.error('恢复失败');
    }
  };

  const handlePermanentDelete = async (id: number) => {
    try {
      await permanentDeleteStrategy(id);
      message.success('彻底删除成功');
      fetchStrategies({ page: 1, search: search || undefined, status: statusFilter, scope: scopeFilter });
    } catch {
      message.error('彻底删除失败');
    }
  };

  const handlePublish = async (id: number) => {
    try {
      await publishStrategy(id);
      message.success('已发布');
    } catch {
      message.error('发布失败');
    }
  };

  const handleUnpublish = async (id: number) => {
    try {
      await unpublishStrategy(id);
      message.success('已取消发布');
    } catch {
      message.error('取消发布失败');
    }
  };

  const columns = useMemo(() => {
    const cols: any[] = [
      {
        title: '策略名称',
        dataIndex: 'name',
        key: 'name',
        width: 180,
        render: (text: string, record: Strategy) => (
          <Button
            type="link"
            onClick={() => navigate(`/strategies/${record.id}`)}
            style={{ whiteSpace: 'normal', wordBreak: 'break-word', textAlign: 'left' }}
          >
            {text}
          </Button>
        ),
      },
      {
        title: '描述',
        dataIndex: 'description',
        key: 'description',
        ellipsis: true,
        width: 200,
      },
    ];

    if (isAdmin) {
      cols.push({
        title: '创建者',
        dataIndex: 'owner_name',
        key: 'owner_name',
        width: 110,
        render: (name: string) => name || '—',
      });
    }

    cols.push(
      {
        title: '发布状态',
        dataIndex: 'is_published',
        key: 'is_published',
        width: 90,
        render: (published: boolean) =>
          published ? (
            <Tag icon={<GlobalOutlined />} color="blue">已发布</Tag>
          ) : (
            <Tag icon={<LockOutlined />}>私密</Tag>
          ),
      },
      {
        title: '评分',
        dataIndex: 'avg_score',
        key: 'avg_score',
        width: 100,
        render: (score: number | null, record: Strategy) =>
          score ? (
            <span>⭐ {(score as number).toFixed(1)} ({record.rating_count})</span>
          ) : (
            <span style={{ color: '#ccc' }}>暂无</span>
          ),
      },
      {
        title: '标签',
        dataIndex: 'tags',
        key: 'tags',
        width: 160,
        render: (tags: string[]) =>
          tags?.length
            ? tags.map((tag: string) => <StatusTag key={tag} status={tag} />)
            : '—',
      },
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 90,
        render: (status: string) => <StatusTag status={status} />,
      },
      {
        title: '版本',
        dataIndex: 'version',
        key: 'version',
        width: 60,
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        width: 170,
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        key: 'updated_at',
        width: 170,
      },
      {
        title: '操作',
        key: 'action',
        width: 240,
        render: (_: unknown, record: Strategy) => {
          const isOwner = String(record.user_id) === String(user?.id);
          if (!isOwner && record.is_published) {
            // 非创建者查看已发布策略：只能查看 + 回测
            return (
              <Space size="small">
                <Button type="link" size="small" onClick={() => navigate(`/strategies/${record.id}`)}>
                  查看
                </Button>
                <Button
                  type="link"
                  size="small"
                  icon={<BarChartOutlined />}
                  onClick={() => navigate(`/strategies/${record.id}/backtest`)}
                >
                  回测
                </Button>
              </Space>
            );
          }

          // 创建者：完整操作
          return (
            <Space size="small">
              <Button type="link" size="small" onClick={() => navigate(`/strategies/${record.id}`)}>
                查看
              </Button>
              <Button type="link" size="small" onClick={() => navigate(`/strategies/${record.id}/edit`)}>
                编辑
              </Button>
              {record.status === 'deleted' ? (
                <>
                  <Popconfirm title="确定恢复此策略？" onConfirm={() => handleRestore(record.id)} okText="确定" cancelText="取消">
                    <Button type="link" size="small">恢复</Button>
                  </Popconfirm>
                  <Popconfirm title="彻底删除将同时删除所有关联的回测报告，不可恢复。确定继续？" onConfirm={() => handlePermanentDelete(record.id)} okText="确定" cancelText="取消">
                    <Button type="link" size="small" danger>彻底删除</Button>
                  </Popconfirm>
                </>
              ) : (
                <>
                  {record.is_published ? (
                    <Button type="link" size="small" onClick={() => handleUnpublish(record.id)}>取消发布</Button>
                  ) : (
                    <Button type="link" size="small" onClick={() => handlePublish(record.id)}>发布</Button>
                  )}
                  <Popconfirm title="确定删除此策略？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
                    <Button type="link" size="small" danger>删除</Button>
                  </Popconfirm>
                </>
              )}
            </Space>
          );
        },
      }
    );

    return cols;
  }, [isAdmin, navigate, user?.id, scopeFilter, statusFilter, search]);

  return (
    <>
      <PageHeader
        title="策略管理"
        breadcrumb={[{ title: '策略管理', path: '/strategies' }]}
        extra={
          <>
            <Button icon={<AppstoreOutlined />} onClick={() => navigate('/strategies/builder')} data-tour-id="btn-visual-builder">
              可视化构建
            </Button>
            <Button icon={<RobotOutlined />} onClick={() => navigate('/strategies/ai-builder')} data-tour-id="btn-ai-builder">
              AI 参考选股
            </Button>
          </>
        }
      />

      <Card>
        <div style={{ marginBottom: 16, display: 'flex', gap: 12 }}>
          <Search
            placeholder="搜索策略名称"
            onSearch={handleSearch}
            style={{ width: 300 }}
            allowClear
          />
          <Select
            placeholder="范围筛选"
            value={scopeFilter}
            onChange={handleScopeFilter}
            style={{ width: 130 }}
            options={[
              { label: '全部', value: 'all' },
              { label: '我的', value: 'mine' },
              { label: '已发布', value: 'published' },
            ]}
          />
          <Select
            placeholder="状态筛选"
            value={statusFilter}
            onChange={handleStatusFilter}
            style={{ width: 130 }}
            allowClear
            options={[
              { label: '活跃', value: 'active' },
              { label: '已归档', value: 'archived' },
              { label: '已删除', value: 'deleted' },
            ]}
          />
        </div>

        <Table
          rowKey="id"
          columns={columns}
          dataSource={strategies}
          loading={loading}
          scroll={{ x: 1300 }}
          pagination={{
            current: page,
            pageSize: limit,
            total,
            onChange: handlePageChange,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t: number) => `共 ${t} 条`,
          }}
        />
      </Card>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/StrategyList.tsx
git commit -m "feat: add scope filter, publish status, and rating columns to StrategyList"
```

---

### Task 18: 策略详情页改造 — 权限 UI

**Files:**
- Modify: `frontend/src/pages/StrategyDetail.tsx`

- [ ] **Step 1: 条件隐藏操作按钮和代码**

在 [StrategyDetail.tsx:89-115](frontend/src/pages/StrategyDetail.tsx#L89-L115) 的 `actions` 渲染中，根据是否为创建者决定显示哪些按钮：

```tsx
  const isOwner = currentStrategy?.user_id === undefined || String(currentStrategy.user_id) === String(user?.id);
  const { user } = useAuthStore();

  const actions = (
    <>
      {isOwner && (
        <>
          <Button icon={<EditOutlined />} onClick={() => navigate(`/strategies/${currentStrategy.id}/edit`)}>
            编辑
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleDownload}>
            下载
          </Button>
        </>
      )}
      <Button icon={<BarChartOutlined />} onClick={() => navigate(`/strategies/${currentStrategy.id}/backtest`)}>
        运行回测
      </Button>
      <StockSearchLookup
        value={stockCode}
        onChange={setStockCode}
        placeholder="股票代码（可选）"
        style={{ width: 200 }}
      />
      <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleExecute} loading={executeLoading}>
        执行策略
      </Button>
      {isOwner && (
        <Popconfirm title="确定删除？" onConfirm={handleDelete} okText="确定" cancelText="取消">
          <Button danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      )}
    </>
  );
```

- [ ] **Step 2: 代码 Tab 条件隐藏**

在 tabItems 的 `code` tab 中，非创建者条件渲染：

```tsx
    {
      key: 'code',
      label: '策略代码',
      children: isOwner ? (
        <CodeBlock code={codeContent} maxHeight={500} onCopy={() => message.success('已复制')} />
      ) : (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          <LockOutlined style={{ fontSize: 48, marginBottom: 16 }} />
          <p>代码仅对创建者可见</p>
        </div>
      ),
    },
```

需 import `LockOutlined` from `@ant-design/icons`。

- [ ] **Step 3: 新增评分评论 Tab**

在 `tabItems` 数组末尾新增：

```tsx
    {
      key: 'community',
      label: '评分评论',
      children: <StrategyCommunity strategyId={currentStrategy.id} isOwner={isOwner} />,
    },
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/StrategyDetail.tsx
git commit -m "feat: add permission-aware UI and community tab to StrategyDetail"
```

---

### Task 19: 评分评论组件

**Files:**
- Create: `frontend/src/components/StrategyRating.tsx`
- Create: `frontend/src/components/StrategyComments.tsx`

- [ ] **Step 1: 创建评分组件**

```tsx
// frontend/src/components/StrategyRating.tsx
import { useState, useEffect } from 'react';
import { Rate, message, Space, Typography } from 'antd';
import { useStrategyStore } from '@/stores/strategyStore';
import type { RatingStats } from '@/types/strategy';

const { Text } = Typography;

interface Props {
  strategyId: number;
}

export default function StrategyRating({ strategyId }: Props) {
  const { rateStrategy, fetchRatings } = useStrategyStore();
  const [stats, setStats] = useState<RatingStats | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchRatings(strategyId).then(setStats);
  }, [strategyId, fetchRatings]);

  const handleRate = async (value: number) => {
    setSubmitting(true);
    try {
      await rateStrategy(strategyId, value);
      message.success('评分成功');
      const fresh = await fetchRatings(strategyId);
      setStats(fresh);
    } catch {
      message.error('评分失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ textAlign: 'center', padding: '16px 0' }}>
      <Space direction="vertical" size={8}>
        <Text strong style={{ fontSize: 24 }}>
          {stats?.average ? `⭐ ${stats.average.toFixed(1)}` : '暂无评分'}
        </Text>
        <Text type="secondary">
          {stats?.count ? `${stats.count} 人评分` : '成为第一个评分的人'}
        </Text>
        <Rate
          value={stats?.current_user_score ?? 0}
          onChange={handleRate}
          disabled={submitting}
        />
      </Space>
    </div>
  );
}
```

- [ ] **Step 2: 创建评论组件**

```tsx
// frontend/src/components/StrategyComments.tsx
import { useState, useEffect } from 'react';
import { Button, Input, List, Typography, message, Popconfirm } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import { useStrategyStore } from '@/stores/strategyStore';
import type { CommentItem } from '@/types/strategy';

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

interface Props {
  strategyId: number;
  isOwner: boolean;
}

export default function StrategyComments({ strategyId, isOwner }: Props) {
  const { fetchComments, addComment, deleteComment } = useStrategyStore();
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [newComment, setNewComment] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const load = async (p = 1) => {
    const result = await fetchComments(strategyId, p);
    if (result) {
      setComments(result.items);
      setTotal(result.total);
      setPage(result.page);
    }
  };

  useEffect(() => {
    load(1);
  }, [strategyId]);

  const handleSubmit = async () => {
    if (!newComment.trim()) return;
    setSubmitting(true);
    try {
      await addComment(strategyId, newComment.trim());
      setNewComment('');
      message.success('评论成功');
      load(1);
    } catch {
      message.error('评论失败');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (commentId: number) => {
    try {
      await deleteComment(strategyId, commentId);
      message.success('删除成功');
      load(page);
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <div>
      <Text strong>评论 ({total})</Text>
      <div style={{ marginTop: 16, marginBottom: 16 }}>
        <TextArea
          rows={3}
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="分享你对这个策略的看法..."
          maxLength={2000}
          showCount
        />
        <Button
          type="primary"
          onClick={handleSubmit}
          loading={submitting}
          disabled={!newComment.trim()}
          style={{ marginTop: 8 }}
        >
          发表评论
        </Button>
      </div>
      <List
        dataSource={comments}
        pagination={{
          current: page,
          total,
          pageSize: 20,
          onChange: (p) => load(p),
        }}
        renderItem={(item: CommentItem) => (
          <List.Item
            actions={
              isOwner
                ? [
                    <Popconfirm
                      key="delete"
                      title="确定删除此评论？"
                      onConfirm={() => handleDelete(item.id)}
                      okText="确定"
                      cancelText="取消"
                    >
                      <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>,
                  ]
                : undefined
            }
          >
            <List.Item.Meta
              title={<Text strong>{item.user_name || '匿名用户'}</Text>}
              description={
                <>
                  <Paragraph style={{ marginBottom: 4 }}>{item.content}</Paragraph>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {new Date(item.created_at).toLocaleString()}
                  </Text>
                </>
              }
            />
          </List.Item>
        )}
      />
    </div>
  );
}
```

- [ ] **Step 3: 创建 StrategyCommunity 组装组件（消除重复 import）**

在 `frontend/src/components/StrategyCommunity.tsx` 中：

```tsx
// frontend/src/components/StrategyCommunity.tsx
import StrategyRating from './StrategyRating';
import StrategyComments from './StrategyComments';

interface Props {
  strategyId: number;
  isOwner: boolean;
}

export default function StrategyCommunity({ strategyId, isOwner }: Props) {
  return (
    <div>
      <StrategyRating strategyId={strategyId} />
      <div style={{ marginTop: 24 }}>
        <StrategyComments strategyId={strategyId} isOwner={isOwner} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/StrategyRating.tsx frontend/src/components/StrategyComments.tsx frontend/src/components/StrategyCommunity.tsx
git commit -m "feat: add rating, comment, and community components"
```

---

### Task 20: 前端 E2E 测试

**Files:**
- Create/Modify: `frontend/e2e/strategy-publish.spec.ts`

- [ ] **Step 1: 编写 E2E 测试**

```typescript
import { test, expect } from '@playwright/test';
import { loginAs, createStrategy } from './helpers';

test.describe('Strategy Publish Flow', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, 'testuser1', '123456');
  });

  test('scope filter switches correctly', async ({ page }) => {
    await page.goto('/strategies');
    await page.waitForLoadState('networkidle');

    // 默认范围是"全部"
    const scopeSelect = page.locator('.ant-select').filter({ hasText: /全部|我的|已发布/ });
    await expect(scopeSelect).toBeVisible();

    // 切换到"我的"
    await scopeSelect.click();
    await page.locator('.ant-select-item-option').filter({ hasText: '我的' }).click();
    await page.waitForLoadState('networkidle');
  });

  test('non-owner sees only view and backtest buttons for published strategy', async ({ page }) => {
    // user1 发布策略后退出
    // user2 登录后查看列表
    await page.goto('/strategies');
    await page.waitForLoadState('networkidle');

    // 切换 scope 为"已发布"以查看公开策略
    const scopeSelect = page.locator('.ant-select').filter({ hasText: /全部|我的|已发布/ });
    await scopeSelect.click();
    await page.locator('.ant-select-item-option').filter({ hasText: '已发布' }).click();
    await page.waitForLoadState('networkidle');
  });
});
```

- [ ] **Step 2: 运行 E2E 测试**

```bash
cd frontend && npx playwright test e2e/strategy-publish.spec.ts --project=chromium
```

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/strategy-publish.spec.ts
git commit -m "test: add E2E tests for strategy publish flow"
```

---

### Task 21: 最终验证

- [ ] **Step 1: 运行全部后端测试**

```bash
cd backend && source venv/bin/activate && pytest -v -x
```

Expected: 全部通过（包括新增的 test_publish.py）

- [ ] **Step 2: TypeScript 编译检查**

```bash
cd frontend && npm run build
```

Expected: 无类型错误

- [ ] **Step 3: 运行全部 E2E 测试**

```bash
cd frontend && npx playwright test
```

- [ ] **Step 4: 最终 Commit**

```bash
git add -A
git commit -m "feat: complete strategy publish, rating, and comment features"
```
