"""
Tests for inventory service: happy path and edge cases.
Uses a temporary directory for data to avoid mutating repo data.
"""
import json
import tempfile
from pathlib import Path

import pytest
import pandas as pd

# Patch config paths before importing service
import src.config as config


@pytest.fixture(autouse=True)
def temp_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    base = Path(tmp)
    (base / "data").mkdir(exist_ok=True)
    items_path = base / "data" / "inventory_items.json"
    consumption_path = base / "data" / "consumption.csv"
    monkeypatch.setattr(config, "ITEMS_PATH", items_path)
    monkeypatch.setattr(config, "CONSUMPTION_PATH", consumption_path)
    # inventory_service imports these from config at load time; patch the module that uses them
    import src.inventory_service as inv_mod
    monkeypatch.setattr(inv_mod, "ITEMS_PATH", items_path)
    monkeypatch.setattr(inv_mod, "CONSUMPTION_PATH", consumption_path)
    yield base


@pytest.fixture
def sample_items():
    return [
        {"id": "inv_001", "name": "Milk", "category": "Dairy", "unit": "L", "current_stock": 10.0, "reorder_level": 3.0},
        {"id": "inv_002", "name": "Beans", "category": "Coffee", "unit": "kg", "current_stock": 5.0, "reorder_level": 2.0},
    ]


def test_create_and_view_item(temp_data_dir, sample_items):
    """Happy path: create item then load and view it."""
    from src.inventory_service import create_item, load_items, get_item_by_id

    item = sample_items[0]
    created, errors = create_item(item)
    assert not errors
    assert created is not None
    assert created["name"] == "Milk"
    assert created["id"] == "inv_001"

    all_items = load_items()
    assert len(all_items) == 1
    found = get_item_by_id("inv_001")
    assert found["current_stock"] == 10.0


def test_create_item_generates_id_when_missing(temp_data_dir):
    """Happy path: create without id gets auto-generated id."""
    from src.inventory_service import create_item, load_items

    created, errors = create_item({
        "name": "Water", "category": "Beverages", "unit": "L",
        "current_stock": 100.0, "reorder_level": 20.0,
    })
    assert not errors
    assert created["id"].startswith("inv_")
    assert load_items()[0]["name"] == "Water"


def test_update_item(temp_data_dir, sample_items):
    """Happy path: update stock and reorder level."""
    from src.inventory_service import create_item, update_item, get_item_by_id

    create_item(sample_items[0])
    updated, errors = update_item("inv_001", {"current_stock": 2.0, "reorder_level": 5.0})
    assert not errors
    assert updated["current_stock"] == 2.0
    assert updated["reorder_level"] == 5.0
    assert get_item_by_id("inv_001")["current_stock"] == 2.0


def test_filter_items_low_stock(temp_data_dir, sample_items):
    """Happy path: filter by low stock."""
    from src.inventory_service import create_item, filter_items

    for i in sample_items:
        create_item(i)
    # inv_001: 10 > 3, inv_002: 5 > 2 -> none low
    low = filter_items(low_stock_only=True)
    assert len(low) == 0
    create_item({"name": "X", "category": "Y", "unit": "u", "current_stock": 1.0, "reorder_level": 5.0})
    low = filter_items(low_stock_only=True)
    assert len(low) == 1
    assert low[0]["current_stock"] == 1.0


def test_validate_item_rejects_negative_stock():
    """Edge case: negative current_stock is invalid."""
    from src.inventory_service import validate_item

    errors = validate_item({
        "name": "A", "category": "B", "unit": "u",
        "current_stock": -1, "reorder_level": 0,
    })
    assert any("negative" in e.lower() for e in errors)


def test_validate_item_rejects_missing_required():
    """Edge case: missing required fields."""
    from src.inventory_service import validate_item

    errors = validate_item({"name": "A"})
    assert len(errors) >= 1
    assert any("category" in e.lower() or "reorder" in e.lower() or "unit" in e.lower() for e in errors)


def test_update_nonexistent_item(temp_data_dir):
    """Edge case: update item that does not exist."""
    from src.inventory_service import update_item

    updated, errors = update_item("nonexistent", {"current_stock": 5.0})
    assert updated is None
    assert len(errors) >= 1
    assert "not found" in errors[0].lower()


def test_delete_item_success_and_not_found(temp_data_dir, sample_items):
    """Delete path: remove existing item then fail for missing id."""
    from src.inventory_service import create_item, delete_item, load_items

    create_item(sample_items[0])
    assert len(load_items()) == 1
    removed = delete_item("inv_001")
    assert removed is True
    assert len(load_items()) == 0
    removed_again = delete_item("inv_001")
    assert removed_again is False
