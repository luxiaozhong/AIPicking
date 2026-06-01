"""
因子注册表 - 自动发现并注册所有因子
"""
import os
import importlib
import inspect
from typing import Dict, List, Optional

# 因子元数据注册表
FACTOR_REGISTRY: Dict[str, dict] = {}
FACTOR_MODULES: Dict[str, object] = {}


def register_factor(meta: dict, module: object):
    """注册一个因子"""
    factor_id = meta["id"]
    FACTOR_REGISTRY[factor_id] = meta
    FACTOR_MODULES[factor_id] = module


def get_factor_meta(factor_id: str) -> Optional[dict]:
    """获取因子元数据"""
    return FACTOR_REGISTRY.get(factor_id)


def get_factor_module(factor_id: str) -> Optional[object]:
    """获取因子模块"""
    return FACTOR_MODULES.get(factor_id)


def list_factors(category: Optional[str] = None) -> List[dict]:
    """列出所有因子元数据，可选按分类过滤"""
    factors = list(FACTOR_REGISTRY.values())
    if category:
        factors = [f for f in factors if f["category"] == category]
    return sorted(factors, key=lambda x: (x["category"], x["name"]))


def get_all_categories() -> List[str]:
    """获取所有因子分类"""
    categories = set(f["category"] for f in FACTOR_REGISTRY.values())
    return sorted(categories)


def compute_factor(factor_id: str, df, params: dict):
    """调用因子的 compute 函数"""
    module = FACTOR_MODULES.get(factor_id)
    if module is None:
        raise ValueError(f"因子不存在: {factor_id}")
    if not hasattr(module, "compute"):
        raise ValueError(f"因子 {factor_id} 没有 compute 函数")
    return module.compute(df, params)


# 自动发现并导入所有因子模块
_factor_dir = os.path.dirname(__file__)
_subdirs = ["trend", "momentum", "volume", "pattern", "risk", "ai_generated", "fundamental"]


def _discover_and_register():
    """扫描并注册所有因子模块"""
    for _subdir in _subdirs:
        _subdir_path = os.path.join(_factor_dir, _subdir)
        if not os.path.isdir(_subdir_path):
            continue
        for _filename in os.listdir(_subdir_path):
            if _filename.endswith(".py") and not _filename.startswith("__"):
                _module_name = f"app.factors.{_subdir}.{_filename[:-3]}"
                try:
                    _module = importlib.import_module(_module_name)
                    if hasattr(_module, "FACTOR_META"):
                        register_factor(_module.FACTOR_META, _module)
                except Exception as e:
                    print(f"加载因子失败 {_module_name}: {e}")


def reload_factors():
    """重新加载所有因子（AI 生成新因子后热加载）"""
    FACTOR_REGISTRY.clear()
    FACTOR_MODULES.clear()
    for _subdir in _subdirs:
        _subdir_path = os.path.join(_factor_dir, _subdir)
        if not os.path.isdir(_subdir_path):
            continue
        for _filename in os.listdir(_subdir_path):
            if _filename.endswith(".py") and not _filename.startswith("__"):
                _module_name = f"app.factors.{_subdir}.{_filename[:-3]}"
                try:
                    _module = importlib.import_module(_module_name)
                    try:
                        importlib.reload(_module)
                    except Exception:
                        pass
                    if hasattr(_module, "FACTOR_META"):
                        register_factor(_module.FACTOR_META, _module)
                except Exception as e:
                    print(f"加载因子失败 {_module_name}: {e}")


# 初始加载
_discover_and_register()
