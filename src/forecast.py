"""
Reorder / run-out forecasting: AI (Gemini) with rule-based fallback.
Fits case study requirement: one AI capability (Forecast) + fallback when AI unavailable.
"""
from typing import Optional

import pandas as pd

from .config import get_gemini_api_key
from .inventory_service import get_consumption_for_item, load_items


def _extract_text_from_gemini_response(response) -> str:
    """
    Extract only plain text from the response, ignoring non-text parts (e.g. thought_signature)
    that can truncate or corrupt the returned string. Works with both google.genai and
    google.generativeai response shapes.
    """
    text_parts = []
    try:
        candidates = getattr(response, "candidates", None)
        if candidates and len(candidates) > 0:
            content = getattr(candidates[0], "content", None)
            if content is not None:
                parts = getattr(content, "parts", None) or []
                for part in parts:
                    raw = getattr(part, "text", None)
                    if isinstance(raw, str) and raw.strip():
                        text_parts.append(raw.strip())
    except (IndexError, AttributeError, TypeError, KeyError):
        pass
    if text_parts:
        return " ".join(text_parts).strip()
    fallback = getattr(response, "text", None)
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return ""


def _call_gemini(prompt: str, max_tokens: int = 200, temperature: float = 0.3) -> str:
    """Call Gemini API; raises on failure or empty response. Bulletproof text extraction."""
    api_key = get_gemini_api_key()
    if not api_key or not api_key.strip():
        raise ValueError("API key not set")

    response = None
    # Prefer google.genai (new SDK); fall back to google.generativeai (legacy) if needed
    try:
        from google.genai import Client
        from google.genai.types import GenerateContentConfig
        client = Client(api_key=api_key)
        try:
            config = GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception:
            config = None
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=config,
        )
    except ImportError:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.5-flash-lite")
            response = model.generate_content(
                prompt,
                generation_config=dict(max_output_tokens=max_tokens, temperature=temperature),
            )
        except Exception as e:
            raise ValueError(f"Gemini API failed: {e}") from e

    if response is None:
        raise ValueError("No response from API")
    text = _extract_text_from_gemini_response(response)
    if not text:
        raise ValueError("Empty AI response")
    return text


def _rule_based_forecast(
    current_stock: float,
    consumption_df: pd.DataFrame,
    reorder_level: float,
    shelf_life_days: int = 30,
) -> dict:
    """
    Fallback: use average daily consumption to estimate days until run-out
    and days until reorder.
    """
    if consumption_df.empty or consumption_df["quantity_used"].sum() == 0:
        avg_daily = 0.0
    else:
        days_with_data = max(1, (consumption_df["date"].max() - consumption_df["date"].min()).days + 1)
        total_used = consumption_df["quantity_used"].sum()
        avg_daily = total_used / days_with_data

    days_until_runout = None  # type: Optional[float]
    days_until_reorder = None  # type: Optional[float]
    if avg_daily > 0:
        days_until_runout = current_stock / avg_daily
        if current_stock > reorder_level and reorder_level >= 0:
            stock_above_reorder = current_stock - reorder_level
            days_until_reorder = stock_above_reorder / avg_daily
        else:
            days_until_reorder = 0.0
    else:
        days_until_runout = 999.0  # no usage
        days_until_reorder = 999.0

    recommended_buy_qty = 0.0
    if avg_daily > 0:
        target_days_cover = min(7.0, max(2.0, float(shelf_life_days) * 0.6))
        desired_stock = max(reorder_level + (avg_daily * 2.0), avg_daily * target_days_cover)
        recommended_buy_qty = max(0.0, desired_stock - current_stock)
    elif current_stock <= reorder_level:
        recommended_buy_qty = max(0.0, reorder_level - current_stock)

    # Waste risk score (0 good -> 100 high waste risk), based on days of cover vs shelf life
    if avg_daily <= 0:
        waste_risk_score = 85.0 if current_stock > 0 else 10.0
    else:
        projected_days_cover = (current_stock + recommended_buy_qty) / avg_daily if avg_daily > 0 else 999.0
        shelf = max(1.0, float(shelf_life_days))
        ratio = projected_days_cover / shelf
        if ratio <= 0.6:
            waste_risk_score = 15.0
        elif ratio <= 0.9:
            waste_risk_score = 30.0
        elif ratio <= 1.1:
            waste_risk_score = 55.0
        elif ratio <= 1.4:
            waste_risk_score = 75.0
        else:
            waste_risk_score = 90.0

    if waste_risk_score <= 35:
        waste_risk_level = "green"
    elif waste_risk_score <= 65:
        waste_risk_level = "amber"
    else:
        waste_risk_level = "red"

    return {
        "method": "rule_based",
        "avg_daily_consumption": round(avg_daily, 4),
        "days_until_runout": round(days_until_runout, 1) if days_until_runout is not None else None,
        "days_until_reorder": round(days_until_reorder, 1) if days_until_reorder is not None else None,
        "suggestion": _format_fallback_suggestion(
            avg_daily, days_until_runout, days_until_reorder, current_stock, reorder_level
        ),
        "recommended_buy_qty": round(recommended_buy_qty, 2),
        "waste_risk_score": round(waste_risk_score, 2),
        "waste_risk_level": waste_risk_level,
    }


def _format_fallback_suggestion(
    avg_daily: float,
    days_until_runout: Optional[float],
    days_until_reorder: Optional[float],
    current_stock: float,
    reorder_level: float,
) -> str:
    if avg_daily <= 0:
        return "No consumption history yet. Add daily usage to get reorder predictions."
    if days_until_runout is not None and days_until_runout <= 0:
        return "Stock is depleted. Reorder immediately."
    if days_until_reorder is not None and days_until_reorder <= 0:
        return "Stock at or below reorder level. Reorder soon to avoid run-out."
    if days_until_runout is not None and days_until_runout < 7:
        return f"Low stock: about {int(days_until_runout)} days until run-out. Consider reordering."
    return f"Stock OK for ~{int(days_until_runout or 0)} days. Reorder in ~{int(days_until_reorder or 0)} days to stay above reorder level."


def _build_consumption_summary(consumption_df: pd.DataFrame) -> str:
    """Build a short text summary of consumption for the AI prompt."""
    if consumption_df.empty:
        return "No consumption history."
    consumption_df = consumption_df.sort_values("date")
    lines = []
    for _, row in consumption_df.tail(14).iterrows():  # last 2 weeks
        lines.append(f"  {row['date'].strftime('%Y-%m-%d')} ({row.get('day_of_week', '')}): {row['quantity_used']}")
    return "Recent daily usage:\n" + "\n".join(lines)


def ai_forecast(
    item_id: str,
    item_name: str,
    unit: str,
    current_stock: float,
    reorder_level: float,
    consumption_df: pd.DataFrame,
    shelf_life_days: int = 30,
    use_ai: bool = True,
) -> dict:
    """
    Use Gemini to generate a short reorder insight (Forecast).
    On any failure (no key, API error, invalid response), falls back to rule-based.
    """
    if not use_ai or not get_gemini_api_key() or not get_gemini_api_key().strip():
        return _rule_based_forecast(current_stock, consumption_df, reorder_level, shelf_life_days=shelf_life_days)

    consumption_summary = _build_consumption_summary(consumption_df)
    prompt = f"""You are an inventory assistant for a small cafe. Based on the data below, give a very short reorder insight (1-2 sentences). Be specific: mention approximate days until run-out or reorder if possible.
Treat paper cups as packaging only (a proxy for drink demand), never as a consumed hero item.

Item: {item_name}
Unit: {unit}
Current stock: {current_stock}
Reorder level: {reorder_level}

{consumption_summary}

Reply with only the short suggestion, no preamble."""

    try:
        suggestion = _call_gemini(prompt, max_tokens=150, temperature=0.3)
        fallback = _rule_based_forecast(current_stock, consumption_df, reorder_level, shelf_life_days=shelf_life_days)
        return {
            "method": "ai",
            "avg_daily_consumption": fallback["avg_daily_consumption"],
            "days_until_runout": fallback["days_until_runout"],
            "days_until_reorder": fallback["days_until_reorder"],
            "suggestion": suggestion,
            "recommended_buy_qty": fallback["recommended_buy_qty"],
            "waste_risk_score": fallback["waste_risk_score"],
            "waste_risk_level": fallback["waste_risk_level"],
        }
    except Exception:
        return _rule_based_forecast(current_stock, consumption_df, reorder_level, shelf_life_days=shelf_life_days)


def get_forecast(item_id: str, use_ai: bool = True) -> dict:
    """
    Get reorder/run-out forecast for an item. Uses AI when available, else rule-based.
    """
    items = load_items()
    item = next((i for i in items if i.get("id") == item_id), None)
    if not item:
        return {"error": f"Item not found: {item_id}"}
    consumption_df = get_consumption_for_item(item_id)
    result = ai_forecast(
        item_id=item_id,
        item_name=item.get("name", ""),
        unit=item.get("unit", ""),
        current_stock=float(item.get("current_stock", 0)),
        reorder_level=float(item.get("reorder_level", 0)),
        consumption_df=consumption_df,
        shelf_life_days=int(item.get("shelf_life_days") or 30),
        use_ai=use_ai,
    )
    result["current_stock"] = float(item.get("current_stock", 0))
    result["reorder_level"] = float(item.get("reorder_level", 0))
    result["unit"] = item.get("unit", "")
    result["item_name"] = item.get("name", "")
    result["shelf_life_days"] = int(item.get("shelf_life_days") or 30)
    return result


def get_ai_chat_response(question: str, inventory_snapshot: str, usage_snapshot: str, use_ai: bool = True) -> dict:
    """
    General-purpose AI chat for the app.
    - Strictly data-based: the model only sees inventory + usage summaries we pass in.
    - Returns {"method": "ai"|"disabled"|"error", "answer": str, "error": Optional[str]}.
    """
    if not use_ai or not get_gemini_api_key() or not get_gemini_api_key().strip():
        return {
            "method": "disabled",
            "answer": "AI chat is disabled. Set GEMINI_API_KEY in .env to enable data-driven answers.",
            "error": "API key not set",
        }

    prompt = f"""You are an inventory and operations assistant for a small cafe.
You must base your answers on the data provided below, but you MAY infer likely menu items
and sensible new menu ideas from the inventory and usage patterns. It is OK to compute simple
aggregates or averages from the data you see.

Data snapshot (current cafe state):

Inventory:
{inventory_snapshot}

Usage and trends:
{usage_snapshot}

User question:
{question}

Guidelines:
- Focus on fast, actionable decision-making (what to reorder, what to prepare more/less of, time-of-day focus, etc.).
- If a question asks for a FACT (for example, an exact stock level), answer only from the data. If it asks for IDEAS
  (for example, “what would be a popular addition to the menu?”), propose reasonable options that are consistent with the data.
- When you infer or suggest, make it clear that these are suggestions based on current inventory and usage, not confirmed history.
- Keep answers short and to the point (2-5 sentences).
- Do not talk about being an AI model; just answer as the cafe assistant.
- Treat commodities like milk as ingredients, not standalone menu items. Heavy use of espresso beans + milk implies strong coffee demand.
- Paper cups are packaging; they imply drinks demand (coffee/tea/hot chocolate). Never present paper cups as a consumed hero product.
- When asked “what’s on the menu” or “what does this cafe offer”, give a concise menu-style list based on pastries and drinks
  implied by the data (for example, coffee drinks, croissants, muffins), and ignore pure ingredients or packaging in the list.
- When asked for recommendations for the menu, provide a small list (3–5) of plausible additions that align with existing patterns
  and sustainability, such as seasonal drinks or complementary pastries, and avoid specific prices.
- Always strive for sustainability and reduce waste.
"""

    try:
        answer = _call_gemini(prompt, max_tokens=260, temperature=0.35)
        return {"method": "ai", "answer": answer, "error": None}
    except Exception as e:
        return {
            "method": "error",
            "answer": "AI chat is temporarily unavailable. Try again later or use the dashboard panels for guidance.",
            "error": str(e),
        }


def get_ai_dashboard_summary(low_stock_items: list, use_ai: bool = True) -> dict:
    """
    Call Gemini to generate a short reorder summary for the dashboard (mandatory AI use).
    Returns {"method": "ai"|"rule_based", "summary": str, "error": str|None}. Fallback if no key or API error.
    """
    if not use_ai or not get_gemini_api_key() or not get_gemini_api_key().strip():
        return {
            "method": "rule_based",
            "summary": "Set GEMINI_API_KEY in .env to see AI-generated reorder suggestions here.",
            "error": "API key not set",
        }
    if not low_stock_items:
        return {"method": "rule_based", "summary": "No low-stock items. Inventory levels look healthy.", "error": None}
    lines = [f"- {i.get('name')}: {i.get('current_stock')} {i.get('unit')} (reorder at {i.get('reorder_level')})" for i in low_stock_items]
    prompt = f"""You are an inventory assistant for a small cafe. Below are items at or below reorder level. Reply with one short, to-the-point sentence: what to do (e.g. reorder soonest first). Use ** around the most important word or two. Be concise.
If paper cups appear, refer to them as packaging/support stock for drinks, not as a consumed hero product.

Items:
{chr(10).join(lines)}

Reply with only that one sentence, no preamble."""

    try:
        summary = _call_gemini(prompt, max_tokens=120, temperature=0.3)
        return {"method": "ai", "summary": summary, "error": None}
    except Exception as e:
        return {
            "method": "rule_based",
            "summary": "Reorder the low-stock items above soon. Use **Reorder Insights** for per-item forecasts.",
            "error": str(e),
        }


def get_ai_dashboard_paragraph(
    last_7_usage: str,
    low_stock_lines: str,
    by_time_usage: str,
    use_ai: bool = True,
) -> dict:
    """
    Call Gemini to generate one paragraph summarizing trends, usage, and preparations for the dashboard.
    Returns {"method": "ai"|"rule_based", "summary": str, "error": str|None}. Always tries API when key is set.
    """
    if not use_ai or not get_gemini_api_key() or not get_gemini_api_key().strip():
        fallback = (
            "- **Review** inventory and reorder items at or below reorder level.\n"
            "- Use **Consumption Trends** for usage patterns.\n"
            "- Set **GEMINI_API_KEY** in .env for AI insights."
        )
        return {"method": "rule_based", "summary": fallback, "error": "API key not set"}

    prompt = f"""You are an inventory assistant for a small cafe. Using ONLY the data below, reply with a short dashboard summary in this exact format:

- Use bullet points only, in priority order (most urgent first).
- Put 3 to 4 bullets maximum: recent usage trends (what is selling most), items needing attention (low stock), and concrete preparations (what to order or watch).
- Wrap the most important words in each bullet with double asterisks, e.g. **reorder soon** or **Croissant** or **12:00 peak**. One or two bold phrases per bullet is enough.
- Be specific and use numbers from the data. No decimals for whole numbers. Milk is an ingredient and paper cups are packaging; stress coffee/drinks and pastries where the data shows high use.
- Never present paper cups as a top consumed hero item. If paper cups are high, interpret this as high drinks demand.
- Do not invent data. No heading or preamble.

Data:

Last 7 days usage (by item):
{last_7_usage}

Items at or below reorder level:
{low_stock_lines}

Usage by time of day (if available):
{by_time_usage}

Reply with only the bullet list (markdown: - and **)."""

    try:
        summary = _call_gemini(prompt, max_tokens=280, temperature=0.4)
        return {"method": "ai", "summary": summary, "error": None}
    except Exception as e:
        fallback = (
            "- **Reorder** items at or below reorder level.\n"
            "- Use **Consumption Trends** and **Reorder Insights** for detailed forecasts."
        )
        return {"method": "rule_based", "summary": fallback, "error": str(e)}


def get_ai_promo_intelligence(
    top_item_lines: str,
    overstock_lines: str,
    drinks_signal_line: str,
    fallback_summary: str,
    use_ai: bool = True,
) -> dict:
    """
    AI-first promo intelligence with rule-based fallback.
    Returns {"method": "ai"|"rule_based", "summary": str, "error": str|None}.
    """
    if not use_ai or not get_gemini_api_key() or not get_gemini_api_key().strip():
        return {"method": "rule_based", "summary": fallback_summary, "error": "API key not set or AI disabled"}

    prompt = f"""You are an inventory + growth assistant for a small cafe.
Create concise promo intelligence in 3 to 4 bullet points using ONLY the data below.

Rules:
- Focus on actionable promo ideas that increase sales and reduce waste.
- Use **bold** around important words.
- Never treat paper cups as a hero sold item. Paper cups are packaging and only imply drinks demand.
- Prefer beverage and pastry promos over ingredient-level promos.
- Do not invent products or numbers.

Top moving non-packaging items:
{top_item_lines}

Potential overstock/slow movement:
{overstock_lines}

Drinks demand proxy:
{drinks_signal_line}

Reply with bullet points only (markdown '- '), no heading."""

    try:
        summary = _call_gemini(prompt, max_tokens=220, temperature=0.35)
        return {"method": "ai", "summary": summary, "error": None}
    except Exception as e:
        return {"method": "rule_based", "summary": fallback_summary, "error": str(e)}
