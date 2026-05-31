# 重构规格：合并两个 Validator 实现

**版本**: 1.0
**状态**: 草稿
**创建日期**: 2026-05-30
**最后更新**: 2026-05-30
**作者**: AI Assistant (基于 Code Review)
**优先级**: 🟡 P1 — 消除代码重复和潜在 Bug

---

## 1. 背景与动机

项目存在两个 validator 实现，功能重叠但实现不同：

| 文件 | 用途 | 实现方式 |
|------|------|----------|
| `backend/app/services/validator.py` | 策略代码安全校验 | `ValidatorFactory` + AST 沙箱 + 允许名单 |
| `backend/app/utils/validator.py` | 策略上传时的函数接口校验 | `ValidatorFactory` + 函数名检查 + 参数验证 |

两个 `ValidatorFactory` 类名完全相同，各自定义在不同的模块中：
- `services/validator.py` 的 `ValidatorFactory` 关注**安全**（阻止 os/sys/exec 等危险导入）
- `utils/validator.py` 的 `ValidatorFactory` 关注**接口合规**（检查是否包含 run/check_xxx 函数）

### 问题

1. **同名冲突**：两个 `ValidatorFactory` 容易混淆
2. **重复代码**：两处都有 AST 解析逻辑，可以复用
3. **调用分散**：`strategy_service.py` 调用 `utils/validator.py`，`backtest_engine.py` 调用 `services/validator.py`，各自为政
4. **维护负担**：修改校验规则时需要改两个地方

---

## 2. 现状分析

### 2.1 `services/validator.py` — 安全校检器

```python
class ValidatorFactory:
    """策略代码沙箱验证器"""
    @staticmethod
    def validate(code: str) -> tuple[bool, str]:
        # 1. ast.parse 语法检查
        # 2. 遍历 AST 节点，检查危险操作：
        #    - 危险导入：os, sys, subprocess, shutil, socket, pickle, importlib
        #    - 危险函数：exec, eval, compile, open, __import__, globals, locals
        #    - 危险属性：__class__, __bases__, __subclasses__, __dict__, __globals__
        # 3. 返回 (valid, error_message)
```

**被调用方**: `backtest_engine.py` 在执行策略前进行安全校验

### 2.2 `utils/validator.py` — 接口合规校验器

```python
class ValidatorFactory:
    """策略接口验证器"""
    @staticmethod
    def validate_interface(code: str) -> dict:
        # 1. ast.parse 语法检查
        # 2. 遍历顶级函数定义
        # 3. 检查是否存在 check_ 前缀函数 + run 函数
        # 4. 检查 run 函数的参数签名
        # 5. 返回 {valid, errors, warnings, functions}
```

**被调用方**: `strategy_service.py` 在上传策略时进行接口检查

---

## 3. 目标架构

### 3.1 合并后的单一 Validator

```
backend/app/services/validator.py  (唯一保留)
│
├── validate_safety(code: str) → (bool, str)
│   安全校验：阻止危险导入、函数调用、属性访问
│
├── validate_interface(code: str) → InterfaceResult
│   接口校验：检查必需函数、参数签名
│
└── validate(code: str) → ValidationResult  (组合调用)
    一次性执行安全 + 接口校验，返回完整结果
```

### 3.2 删除

```
backend/app/utils/validator.py  → ✂️ 删除
```

### 3.3 数据结构

```python
from dataclasses import dataclass

@dataclass
class InterfaceResult:
    valid: bool
    has_run: bool           # 是否有 run 函数
    has_check: bool         # 是否有 check_ 前缀函数
    check_functions: list[str]  # 找到的 check_ 函数名列表
    errors: list[str]
    warnings: list[str]

@dataclass
class ValidationResult:
    valid: bool
    safety: tuple[bool, str]    # (passed, error_message)
    interface: InterfaceResult
    errors: list[str]
```

### 3.4 统一的 `ValidatorFactory`

```python
class ValidatorFactory:
    """策略代码统一验证器 — 安全 + 接口合规"""

    DANGEROUS_IMPORTS = {'os', 'sys', 'subprocess', 'shutil', 'socket', 'pickle', 'importlib'}
    DANGEROUS_FUNCTIONS = {'exec', 'eval', 'compile', 'open', '__import__'}
    DANGEROUS_ATTRS = {'__class__', '__bases__', '__subclasses__', '__dict__', '__globals__'}
    REQUIRED_FUNCTIONS = ('run',)  # check_ 前缀函数至少一个
    MAX_CODE_SIZE = 10 * 1024 * 1024  # 10MB

    @classmethod
    def validate_safety(cls, code: str) -> tuple[bool, str]:
        """纯安全校验"""
        ...

    @classmethod
    def validate_interface(cls, code: str) -> InterfaceResult:
        """纯接口校验"""
        ...

    @classmethod
    def validate(cls, code: str) -> ValidationResult:
        """组合校验（推荐外部直接调用此方法）"""
        ...
```

---

## 4. 实施步骤

### Step 1: 合并代码到 `services/validator.py`

- 将 `utils/validator.py` 的 `validate_interface` 逻辑移入 `services/validator.py`
- 统一两个 `ValidatorFactory` 为一个类
- 引入 `ValidationResult` / `InterfaceResult` dataclass
- 保留所有现有校验规则，不改变校验结果

**预估**: 30 分钟

### Step 2: 更新调用方

- `backtest_engine.py`: `ValidatorFactory.validate(code)` → `ValidatorFactory.validate_safety(code)`（只需安全检查）
- `strategy_service.py`: `from app.utils.validator import ValidatorFactory` → `from app.services.validator import ValidatorFactory`

**预估**: 10 分钟

### Step 3: 删除 `utils/validator.py`

- 确认无其他 import 引用后删除
- 搜索 `utils.validator` 或 `utils/validator` 确保无残留引用

**预估**: 5 分钟

### Step 4: 添加单元测试

- 新增 `backend/tests/test_validator.py`
- 覆盖：合法代码通过、危险导入拦截、危险函数拦截、缺少必需函数、参数签名错误

**预估**: 20 分钟

---

## 5. 验收标准

- [ ] `backend/app/utils/validator.py` 已删除
- [ ] `backend/app/services/validator.py` 包含安全 + 接口两种校验
- [ ] `backtest_engine.py` 调用 `validate_safety()` 且行为不变
- [ ] `strategy_service.py` 调用 `validate_interface()` 且行为不变
- [ ] 全局只有一个 `ValidatorFactory` 类定义
- [ ] 新增 validator 单元测试通过（`pytest tests/test_validator.py -v`）
- [ ] 现有测试全部通过（`pytest`）

---

## 6. 风险与注意事项

- **校验行为不变**：合并只是代码重组，不修改任何校验规则。被拦截的代码仍然被拦截，通过的仍然通过
- **import 路径兼容**：如果其他文件（如 debug 脚本、migration 脚本）引用了 `utils/validator.py`，需同步更新。先搜索再删除
- **`__init__.py` 检查**：确认 `backend/app/utils/__init__.py` 是否有重导出

---

**变更日志**:
- 2026-05-30: 初始版本创建（基于 Code Review 发现）
