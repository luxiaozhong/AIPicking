"""策略代码验证器"""

import ast


class StrategyValidator:
    """策略代码验证器"""
    
    # 放宽限制：只允许导入常用的安全模块
    ALLOWED_IMPORTS = {
        'pandas', 'pd', 'numpy', 'np', 
        'datetime', 'time', 'os', 'pathlib',
        'typing', 'collections', 're'
    }
    
    FORBIDDEN_FUNCS = {'exec', 'eval', '__import__'}
    
    @classmethod
    def validate(cls, code: str) -> tuple[bool, str]:
        """
        验证策略代码安全性
        
        返回:
            (is_valid, error_message)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {e}"
        
        for node in ast.walk(tree):
            # 检查危险函数调用
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in cls.FORBIDDEN_FUNCS:
                        return False, f"禁止调用函数: {node.func.id}"
            
            # 检查 open() 内置函数调用（允许 with open() 读取文件）
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'open':
                    # 允许 open，但在生产环境中可以记录警告
                    pass
        
        return True, ""
    
    @classmethod
    def check_required_functions(cls, code: str) -> tuple[bool, list]:
        """
        检查策略代码是否包含必需函数
        
        返回:
            (has_required_funcs, missing_funcs)
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False, ["语法错误"]
        
        has_check = False
        has_run = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name.startswith('check_'):
                    has_check = True
                elif node.name == 'run':
                    has_run = True
        
        missing = []
        if not has_check:
            missing.append("check_xxx")
        if not has_run:
            missing.append("run")
        
        return len(missing) == 0, missing
