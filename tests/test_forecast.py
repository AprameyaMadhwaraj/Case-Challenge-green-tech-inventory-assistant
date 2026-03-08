"""
Tests for forecast: rule-based fallback (no API key in tests).
"""
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def no_gemini_key(monkeypatch):
    """Force rule-based fallback by making API key unavailable in tests."""
    monkeypatch.setenv("GEMINI_API_KEY", "")
    import src.forecast as forecast_mod
    monkeypatch.setattr(forecast_mod, "get_gemini_api_key", lambda: None)


def test_rule_based_forecast_with_history():
    """Happy path: consumption history yields days until runout and suggestion."""
    from src.forecast import _rule_based_forecast

    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-02", "2025-03-03"]),
        "quantity_used": [2.0, 2.0, 2.0],
    })
    result = _rule_based_forecast(current_stock=20.0, consumption_df=df, reorder_level=5.0)
    assert result["method"] == "rule_based"
    assert result["avg_daily_consumption"] == 2.0
    assert result["days_until_runout"] == 10.0
    assert "recommended_buy_qty" in result
    assert "waste_risk_score" in result
    assert result["waste_risk_level"] in {"green", "amber", "red"}
    assert 0 <= float(result["waste_risk_score"]) <= 100
    assert "suggestion" in result
    assert "reorder" in result["suggestion"].lower() or "day" in result["suggestion"].lower()


def test_rule_based_forecast_empty_history():
    """Edge case: no consumption history."""
    from src.forecast import _rule_based_forecast

    result = _rule_based_forecast(current_stock=10.0, consumption_df=pd.DataFrame(), reorder_level=2.0)
    assert result["method"] == "rule_based"
    assert result["avg_daily_consumption"] == 0.0
    assert "No consumption" in result["suggestion"] or "history" in result["suggestion"].lower()


def test_ai_chat_disabled_without_key():
    """AI chat helper should report disabled when no API key is available."""
    from src.forecast import get_ai_chat_response

    result = get_ai_chat_response(
        question="Should I reorder espresso beans?",
        inventory_snapshot="- Espresso Beans: 6.0 kg (reorder at 5.0)\n- Croissant: 20 pieces (reorder at 15)",
        usage_snapshot="Last 7 days usage: Espresso Beans 8.8 kg; Croissant 101 pieces.",
    )
    assert result["method"] == "disabled"
    assert "disabled" in result["answer"].lower() or "set gemini_api_key" in result["answer"].lower()


def test_dashboard_summary_forced_rule_based_when_ai_toggle_off(monkeypatch):
    """When AI is toggled off, API should not be called even if key exists."""
    import src.forecast as forecast_mod

    monkeypatch.setattr(forecast_mod, "get_gemini_api_key", lambda: "fake-key")

    def _should_not_call(*args, **kwargs):
        raise AssertionError("Gemini API should not be called when use_ai=False")

    monkeypatch.setattr(forecast_mod, "_call_gemini", _should_not_call)
    result = forecast_mod.get_ai_dashboard_summary(
        [{"name": "Espresso Beans", "current_stock": 2.0, "unit": "kg", "reorder_level": 5.0}],
        use_ai=False,
    )
    assert result["method"] == "rule_based"
    assert "set gemini_api_key" in result["summary"].lower() or "reorder" in result["summary"].lower()


def test_dashboard_paragraph_toggle_off_returns_short_bullets():
    """Fallback dashboard summary should be concise bullet points when AI is off."""
    from src.forecast import get_ai_dashboard_paragraph

    result = get_ai_dashboard_paragraph(
        last_7_usage="- Espresso Beans: 8.80\n- Croissant: 101.00",
        low_stock_lines="- Espresso Beans: 2.00 kg (reorder at 5.00)",
        by_time_usage="- 09:00: 35.40",
        use_ai=False,
    )
    assert result["method"] == "rule_based"
    lines = [line for line in result["summary"].splitlines() if line.strip()]
    assert 1 <= len(lines) <= 4


def test_get_forecast_includes_stock_and_risk_fields(monkeypatch):
    """Forecast payload should expose current stock and risk fields for UI decisions."""
    import src.forecast as forecast_mod
    import src.inventory_service as inv_mod

    monkeypatch.setattr(forecast_mod, "get_gemini_api_key", lambda: None)
    monkeypatch.setattr(inv_mod, "load_items", lambda: [
        {"id": "inv_001", "name": "Beans", "unit": "kg", "current_stock": 6.0, "reorder_level": 5.0, "shelf_life_days": 30}
    ])
    monkeypatch.setattr(forecast_mod, "load_items", inv_mod.load_items)
    monkeypatch.setattr(forecast_mod, "get_consumption_for_item", lambda _id: pd.DataFrame({
        "date": pd.to_datetime(["2025-03-01", "2025-03-02"]),
        "quantity_used": [1.0, 1.2],
    }))

    result = forecast_mod.get_forecast("inv_001", use_ai=False)
    assert result["current_stock"] == 6.0
    assert result["reorder_level"] == 5.0
    assert result["unit"] == "kg"
    assert 0 <= float(result["waste_risk_score"]) <= 100


def test_promo_intelligence_toggle_off_forces_rule_based(monkeypatch):
    """Promo intelligence should use fallback when AI is disabled."""
    import src.forecast as forecast_mod

    monkeypatch.setattr(forecast_mod, "get_gemini_api_key", lambda: "fake-key")

    def _should_not_call(*args, **kwargs):
        raise AssertionError("Gemini API should not be called when use_ai=False")

    monkeypatch.setattr(forecast_mod, "_call_gemini", _should_not_call)
    fallback = "- **Test fallback** promo line."
    result = forecast_mod.get_ai_promo_intelligence(
        top_item_lines="- Croissant: 100",
        overstock_lines="- Vanilla Syrup: stock 10, recent use 0.5",
        drinks_signal_line="- Paper cups used: 250",
        fallback_summary=fallback,
        use_ai=False,
    )
    assert result["method"] == "rule_based"
    assert result["summary"] == fallback
