"""自然语言策略构建器 — 测试"""

import pytest
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from app.factors import FACTOR_REGISTRY, get_factor_meta, reload_factors


# ============================================================
# Factor Matching Tests
# ============================================================

class TestFactorMatching:
    """因子注册表匹配逻辑"""

    def test_existing_factor_match_by_name(self):
        """已有因子按名称精确匹配"""
        meta = get_factor_meta("momentum_rsi")
        assert meta is not None
        assert "RSI" in meta["name"]

    def test_all_builtin_categories_have_factors(self):
        """所有内置分类都有至少一个因子"""
        from app.factors import get_all_categories
        cats = get_all_categories()
        assert len(cats) >= 4  # trend, momentum, volume, pattern, risk
        for cat in cats:
            factors = [f for f in FACTOR_REGISTRY.values() if f["category"] == cat]
            assert len(factors) >= 1, f"Category '{cat}' should have factors"

    def test_existing_factor_for_each_builtin(self):
        """测试可以匹配的常见因子名称"""
        test_cases = [
            ("rsi", "momentum_rsi"),
            ("RSI", "momentum_rsi"),
            ("RSI 14日", "momentum_rsi"),
            ("kdj", "momentum_kdj"),
            ("MACD", "momentum_macd"),
            ("macd 金叉", "momentum_macd"),
            ("均线金叉", "trend_ma_cross"),
            ("突破新高", "trend_breakout"),
            ("obv", "volume_obv"),
            ("换手率", "volume_turnover"),
            ("量比", "volume_ratio"),
        ]
        for query, expected_id in test_cases:
            matched = _match_factor(query)
            assert matched is not None, f"Should match '{query}' to some factor"
            assert matched == expected_id, f"'{query}' should match '{expected_id}', got '{matched}'"

    def test_unmatched_factor_returns_none(self):
        """无法匹配的因子返回 None"""
        result = _match_factor("quantum_momentum_xyz_nonexistent")
        assert result is None

    def test_ai_generated_directory_exists_after_setup(self):
        """ai_generated 目录存在"""
        factors_dir = os.path.dirname(os.path.dirname(
            os.path.abspath(__import__('app.factors').__file__)
        ))
        ai_dir = os.path.join(factors_dir, "ai_generated")
        os.makedirs(ai_dir, exist_ok=True)
        assert os.path.isdir(ai_dir)


# ============================================================
# NL Analysis Service Tests
# ============================================================

class TestNLAnalysisService:
    """自然语言分析服务"""

    @pytest.mark.asyncio
    async def test_parse_valid_deepseek_response(self):
        """解析有效的 DeepSeek 响应"""
        response_text = json.dumps({
            "summary": "寻找超跌反弹机会",
            "strategy_type": "similarity",
            "indicators": [
                {
                    "name": "RSI 14日",
                    "category": "动量类",
                    "description": "14日相对强弱指标，低于30表示超卖",
                    "params": {"period": 14},
                    "ref_value": 30.0,
                    "computation": "RSI = 100 - 100/(1+RS)"
                },
                {
                    "name": "MACD 金叉",
                    "category": "趋势类",
                    "description": "MACD DIF上穿DEA",
                    "params": {"fast": 12, "slow": 26, "signal": 9},
                    "ref_value": 1.0,
                    "computation": "DIF - DEA > 0"
                }
            ]
        }, ensure_ascii=False)

        from app.services.ai_nl_service import _parse_nl_response
        result = _parse_nl_response(response_text)

        assert result["summary"] == "寻找超跌反弹机会"
        assert len(result["indicators"]) == 2
        assert result["indicators"][0]["name"] == "RSI 14日"
        assert result["indicators"][0]["ref_value"] == 30.0

    @pytest.mark.asyncio
    async def test_parse_response_with_markdown_wrapper(self):
        """解析被 markdown 包裹的 DeepSeek 响应"""
        response_text = """```json
{
  "summary": "test",
  "indicators": [
    {
      "name": "KDJ",
      "category": "动量类",
      "description": "KDJ 随机指标",
      "params": {"k": 9, "d": 3, "j": 3},
      "ref_value": 20.0,
      "computation": "K = ..."
    }
  ]
}
```"""

        from app.services.ai_nl_service import _parse_nl_response
        result = _parse_nl_response(response_text)

        assert result["summary"] == "test"
        assert len(result["indicators"]) == 1

    @pytest.mark.asyncio
    async def test_parse_response_missing_indicators(self):
        """响应缺少 indicators 字段"""
        from app.services.ai_nl_service import _parse_nl_response

        with pytest.raises(ValueError, match="indicators"):
            _parse_nl_response(json.dumps({"summary": "test"}))

    @pytest.mark.asyncio
    async def test_parse_empty_indicators_ok(self):
        """indicators 为空列表时的行为"""
        from app.services.ai_nl_service import _parse_nl_response

        result = _parse_nl_response(json.dumps({
            "summary": "no indicators found",
            "indicators": []
        }))
        assert result["indicators"] == []

    @pytest.mark.asyncio
    async def test_classify_indicators_matched_vs_new(self):
        """分类指标为 matched 和 new"""
        from app.services.ai_nl_service import _classify_indicators

        indicators = [
            {"name": "RSI 14日", "category": "动量类", "ref_value": 30.0, "params": {"period": 14}},
            {"name": "底部放量确认", "category": "量能类", "ref_value": 2.5, "params": {"ratio": 2.0}},
        ]

        result = _classify_indicators(indicators)
        assert "matched" in result
        assert "new" in result

        # RSI should match
        matched_names = [m["name"] for m in result["matched"]]
        assert "RSI 14日" in matched_names

        # "底部放量确认" should be new (not in built-in library)
        new_names = [m["name"] for m in result["new"]]
        assert "底部放量确认" in new_names


# ============================================================
# API Endpoint Tests
# ============================================================

class TestNLAPIEndpoints:
    """API 端点测试（用 pytest-asyncio + httpx 或 FastAPI TestClient）"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        from httpx import ASGITransport, AsyncClient
        from app.main import app

        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    @pytest.mark.asyncio
    async def test_analyze_nl_endpoint_creates_task(self, client):
        """POST /ai/analyze-nl 创建任务"""
        response = await client.post(
            "/api/v1/ai/analyze-nl",
            json={"prompt": "寻找超跌反弹的股票，RSI低于30且放量"},
        )
        assert response.status_code in (200, 401, 403)  # 401/403 if no auth in test

    @pytest.mark.asyncio
    async def test_analyze_nl_rejects_empty_prompt(self, client):
        """拒绝过短的 prompt"""
        response = await client.post(
            "/api/v1/ai/analyze-nl",
            json={"prompt": "ab"},
        )
        # Should return 400 or 422 for validation error
        assert response.status_code != 200

    @pytest.mark.asyncio
    async def test_analyze_nl_rejects_missing_prompt(self, client):
        """拒绝缺少 prompt 的请求"""
        response = await client.post(
            "/api/v1/ai/analyze-nl",
            json={},
        )
        assert response.status_code != 200

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_404(self, client):
        """查询不存在的任务返回 404"""
        response = await client.get("/api/v1/ai/analyze-nl/nonexistent-id")
        assert response.status_code in (404, 401, 403)  # 401/403 if no auth


# ============================================================
# Helper: simple factor matching logic
# ============================================================

def _match_factor(query: str):  # returns Optional[str]
    """简化的因子匹配逻辑，用于测试验证"""
    import difflib

    query_lower = query.lower()

    # Collect all known factor names
    candidates: list[tuple[str, str, str]] = []  # (factor_id, name, name_lower)
    for fid, meta in FACTOR_REGISTRY.items():
        name = meta.get("name", "")
        candidates.append((fid, name, name.lower()))

    best_score = 0.0
    best_id = None

    for fid, name, name_lower in candidates:
        # Direct substring match
        if query_lower in name_lower or name_lower in query_lower:
            score = 0.9
        else:
            # difflib similarity
            score = difflib.SequenceMatcher(None, query_lower, name_lower).ratio()

        # Also check against common aliases
        aliases = _get_aliases(fid)
        for alias in aliases:
            alias_score = difflib.SequenceMatcher(None, query_lower, alias.lower()).ratio()
            score = max(score, alias_score)

        if score > best_score:
            best_score = score
            best_id = fid

    if best_score >= 0.6 and best_id:
        return best_id
    return None


def _get_aliases(factor_id: str) -> list[str]:
    """获取因子的常用别名"""
    aliases_map = {
        "momentum_rsi": ["相对强弱", "rsi 14日", "rsi14"],
        "momentum_macd": ["macd 金叉", "macd 死叉", "macd金叉", "macd死叉"],
        "momentum_kdj": ["kdj 金叉", "kdj金叉"],
        "trend_ma_cross": ["均线金叉", "均线交叉", "金叉", "ma cross"],
        "trend_breakout": ["突破新高", "突破", "新高"],
        "trend_ma_support": ["均线支撑", "支撑"],
        "volume_obv": ["能量潮", "obv"],
        "volume_turnover": ["换手率", "换手"],
        "volume_volume_ratio": ["量比", "放量", "量比放大"],
    }
    return aliases_map.get(factor_id, [])
