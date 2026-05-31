# 预存测试失败记录

**日期:** 2026-05-31  
**分支:** feature/strategy-publish（main 分支同样存在）

## 失败 (9)

| 测试 | 错误 |
|------|------|
| test_create_backtest | AttributeError: 'async_generator' object has no attribute 'post' |
| test_get_backtest_list | 同上 |
| test_get_backtest_detail | 同上 |
| test_delete_backtest | 同上 |
| test_create_strategy | 同上 |
| test_get_strategies_list | 同上 |
| test_get_strategy_detail | 同上 |
| test_update_strategy | 同上 |
| test_delete_strategy | 同上 |

**根因:** 测试使用 `@pytest.mark.asyncio` 但 `client` fixture 是 `async_generator`，应改为 `@pytest.mark.anyio` + `async with client as ac:`。

## 错误 (6)

| 测试 | 错误 |
|------|------|
| test_permanent_delete_user_success | ModuleNotFoundError |
| test_permanent_delete_nonexistent_user | 同上 |
| test_permanent_delete_self | 同上 |
| test_permanent_delete_default_admin | 同上 |
| test_permanent_delete_with_cascade | 同上 |
| test_permanent_delete_requires_admin | 同上 |

**根因:** `tests/test_users.py` 导入了不存在的模块。

## 通过 (23)

所有其他测试正常通过。
