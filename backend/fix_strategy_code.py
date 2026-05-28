"""
修复策略代码 - 重新生成 strategy_id=4 的代码
"""
import sys
import os
import asyncio

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.strategy import Strategy
from app.services.code_generator import generate_strategy_code
from app.config import settings


async def fix_strategy(strategy_id: int):
    # 创建异步引擎和会话
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            # 查询策略
            result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
            strategy = result.scalar_one_or_none()

            if not strategy:
                print(f"策略 {strategy_id} 不存在")
                return

            print(f"正在修复策略: {strategy.name} (ID: {strategy.id})")
            print(f"因子配置: {strategy.factor_config}")

            # 解析 factor_config（可能是 JSON 字符串）
            import json
            if isinstance(strategy.factor_config, str):
                factor_config = json.loads(strategy.factor_config)
            else:
                factor_config = strategy.factor_config

            # 重新生成代码
            new_code = generate_strategy_code(strategy.name, factor_config)

            # 更新数据库
            strategy.generated_code = new_code
            await db.commit()

            # 更新文件
            code_file = os.path.join(os.path.dirname(__file__), "strategies", f"strategy_{strategy.id}.py")
            os.makedirs(os.path.dirname(code_file), exist_ok=True)
            with open(code_file, "w", encoding="utf-8") as f:
                f.write(new_code)

            print(f"✓ 代码已更新")
            print(f"✓ 数据库已更新")
            print(f"✓ 文件已更新: {code_file}")

            # 验证新代码是否有语法错误
            try:
                compile(new_code, f"strategy_{strategy.id}.py", "exec")
                print(f"✓ 代码语法验证通过")
            except SyntaxError as e:
                print(f"✗ 代码仍有语法错误: {e}")
                return

        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await db.close()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix_strategy(4))
