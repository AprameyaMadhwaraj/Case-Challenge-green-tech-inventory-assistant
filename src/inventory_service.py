"""
Inventory data layer: load/save items and daily consumption.
Synthetic data only; supports Create, View, Update, and search/filter.
"""
import json
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd

from .config import ITEMS_PATH, CONSUMPTION_PATH


# --- Validation ---
def validate_item(data: dict) -> List[str]:
    """Validate inventory item. Returns list of error messages (empty if valid)."""
    errors = []
    required = ("name", "category", "unit", "current_stock", "reorder_level")
    for field in required:
        if field not in data or data[field] is None:
            errors.append(f"Missing required field: {field}")
    if "current_stock" in data and not isinstance(data["current_stock"], (int, float)):
        try:
            float(data["current_stock"])
        except (TypeError, ValueError):
            errors.append("current_stock must be a number")
    if "reorder_level" in data and not isinstance(data["reorder_level"], (int, float)):
        try:
            float(data["reorder_level"])
        except (TypeError, ValueError):
            errors.append("reorder_level must be a number")
    if data.get("current_stock") is not None and (data.get("current_stock") or 0) < 0:
        errors.append("current_stock cannot be negative")
    if data.get("reorder_level") is not None and (data.get("reorder_level") or 0) < 0:
        errors.append("reorder_level cannot be negative")
    return errors


def _ensure_data_dir() -> None:
    ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_items() -> List[dict]:
    """Load inventory items from JSON. Returns list of item dicts."""
    if not ITEMS_PATH.exists():
        return []
    with open(ITEMS_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_items(items: List[dict]) -> None:
    """Persist inventory items to JSON."""
    _ensure_data_dir()
    with open(ITEMS_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def get_item_by_id(item_id: str) -> Optional[dict]:
    """Get a single item by id."""
    for item in load_items():
        if item.get("id") == item_id:
            return item
    return None


def create_item(item: dict) -> tuple:
    """
    Create a new inventory item. Generates id if missing.
    Returns (created_item, errors). If errors non-empty, item is None.
    """
    errors = validate_item(item)
    if errors:
        return None, errors
    items = load_items()
    existing_ids = {i.get("id") for i in items if i.get("id")}
    new_id = item.get("id")
    if not new_id or new_id in existing_ids:
        prefix = "inv"
        n = 1
        while f"{prefix}_{n:03d}" in existing_ids:
            n += 1
        new_id = f"{prefix}_{n:03d}"
    normalized = {
        "id": new_id,
        "name": str(item["name"]).strip(),
        "category": str(item["category"]).strip(),
        "unit": str(item["unit"]).strip(),
        "current_stock": float(item["current_stock"]) if isinstance(item["current_stock"], str) else item["current_stock"],
        "reorder_level": float(item["reorder_level"]) if isinstance(item["reorder_level"], str) else item["reorder_level"],
        "shelf_life_days": int(item.get("shelf_life_days") or 30),
        "unit_cost": float(item.get("unit_cost") or 0),
        "supplier_notes": str(item.get("supplier_notes") or "").strip(),
    }
    items.append(normalized)
    save_items(items)
    return normalized, []


def update_item(item_id: str, updates: dict) -> tuple:
    """
    Update an existing item by id. Only provided fields are updated.
    Returns (updated_item, errors). If not found or validation fails, item is None.
    """
    items = load_items()
    idx = next((i for i, x in enumerate(items) if x.get("id") == item_id), None)
    if idx is None:
        return None, [f"Item not found: {item_id}"]
    merged = {**items[idx], **updates}
    errors = validate_item(merged)
    if errors:
        return None, errors
    merged["current_stock"] = float(merged["current_stock"]) if isinstance(merged["current_stock"], str) else merged["current_stock"]
    merged["reorder_level"] = float(merged["reorder_level"]) if isinstance(merged["reorder_level"], str) else merged["reorder_level"]
    if "shelf_life_days" in merged:
        merged["shelf_life_days"] = int(merged["shelf_life_days"])
    if "unit_cost" in merged:
        merged["unit_cost"] = float(merged["unit_cost"])
    items[idx] = merged
    save_items(items)
    return merged, []


def delete_item(item_id: str) -> bool:
    """Remove item by id. Returns True if removed."""
    items = load_items()
    new_items = [i for i in items if i.get("id") != item_id]
    if len(new_items) == len(items):
        return False
    save_items(new_items)
    return True


def filter_items(
    items: Optional[List[dict]] = None,
    category: Optional[str] = None,
    low_stock_only: bool = False,
    search_query: Optional[str] = None,
) -> List[dict]:
    """Filter items by category, low stock, or text search on name/category."""
    if items is None:
        items = load_items()
    if category:
        items = [i for i in items if (i.get("category") or "").lower() == category.lower()]
    if low_stock_only:
        items = [i for i in items if (i.get("current_stock") or 0) <= (i.get("reorder_level") or 0)]
    if search_query:
        q = search_query.lower().strip()
        if q:
            items = [
                i for i in items
                if q in (i.get("name") or "").lower() or q in (i.get("category") or "").lower()
            ]
    return items


def load_consumption() -> pd.DataFrame:
    """Load single consumption CSV. Columns: date, time, item_id, quantity, day."""
    if not CONSUMPTION_PATH.exists():
        return pd.DataFrame(columns=["date", "time", "item_id", "quantity", "day"])
    df = pd.read_csv(CONSUMPTION_PATH)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def get_consumption_for_item(item_id: str, df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Get daily consumption for one item (aggregated by date), sorted by date. For forecasting."""
    if df is None:
        df = load_consumption()
    out = df[df["item_id"] == item_id].copy()
    if out.empty:
        return out
    agg = out.groupby("date", as_index=False).agg({"quantity": "sum", "day": "first"})
    agg = agg.rename(columns={"quantity": "quantity_used", "day": "day_of_week"})
    return agg.sort_values("date").reset_index(drop=True)


def add_consumption_record(date: str, item_id: str, quantity_used: float, time: str = "12:00") -> None:
    """Append one consumption record (for demo/simulated use)."""
    _ensure_data_dir()
    df = load_consumption()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dt = pd.to_datetime(date)
    day_of_week = day_names[dt.weekday()]
    new_row = pd.DataFrame([{"date": date, "time": time, "item_id": item_id, "quantity": quantity_used, "day": day_of_week}])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CONSUMPTION_PATH, index=False)
