"""策略代码验证器"""

import ast
import logging

logger = logging.getLogger(__name__)


class StrategyValidator:
    """策略代码验证器"""
    
    # 禁止导入的模块
    FORBIDDEN_IMPORTS = {'os', 'sys', 'subprocess', 'builtins', 'shutil', 'socket'}
    
    # 禁止调用的函数
    FORBIDDEN_FUNCS = {'exec', 'eval', 'open', '__import__', 'compile', 'getattr', 'setattr', 'delattr'}
    
    @classmethod
    def validate(cls, code: str) -> tuple[bool, str]:
        """
        验证策略代码安全性
        返回: (is_valid, error_message)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e.msg} (第 {e.lineno} 行)"
        
        for node in ast.walk(tree):
            # 检查 import 语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in cls.FORBIDDEN_IMPORTS or alias.name.startswith('os.'):
                        return False, f"禁止导入模块: {alias.name} (第 {node.lineno} 行)"
            
            # 检查 from ... import 语句
            if isinstance(node, ast.ImportFrom):
                if node.module in cls.FORBIDDEN_IMPORTS:
                    return False, f"禁止导入模块: {node.module} (第 {node.lineno} 行)"
            
            # 检查函数调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in cls.FORBIDDEN_FUNCS:
                        return False, f"禁止调用函数: {node.func.id} (第 {node.lineno} 行)"
                elif isinstance(node.func, ast.Attribute):
                    # 检查 attribute access like os.system
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id in cls.FORBIDDEN_IMPORTS:
                            return False, f"禁止访问模块: {node.func.value.id} (第 {node.lineno} 行)"
        
        # 检查是否定义了 Strategy 类
        has_strategy_class = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # 检查类是否包含 required 方法
                method_names = [item.name for item in node.body if isinstance(item, ast.FunctionDef)]
                # 不强制要求特定方法，但建议包含 handle_bar
                if 'handle_bar' in method_names:
                    has_strategy_class = True
        
        if not has_strategy_class:
            logger.warning("策略代码可能未定义 handle_bar 方法")
        
        return True, ""
    
    @classmethod
    def validate_strategy_interface(cls, code: str) -> tuple[bool, str]:
        """
        验证策略是否实现了 required 接口
        返回: (is_valid, error_message)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        
        # 查找所有类定义
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        
        if not classes:
            return False, "未找到类定义"
        
        # 检查是否有 handle_bar 方法
        for cls in classes:
            method_names = [item.name for item in cls.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if 'handle_bar' in method_names:
                return True, ""
        
        return False, "策略类未实现 handle_bar 方法"
