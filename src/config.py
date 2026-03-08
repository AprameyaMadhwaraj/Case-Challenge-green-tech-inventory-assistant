"""Configuration and paths. Uses synthetic data only."""
import os
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ITEMS_PATH = DATA_DIR / "inventory_items.json"
CONSUMPTION_PATH = DATA_DIR / "consumption.csv"


def get_gemini_api_key() -> Optional[str]:
    """Return Gemini API key from environment; never commit real keys."""
    # Ensure .env is loaded from project root (app may be run from different cwd)
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
        load_dotenv()  # cwd .env as fallback
    except ImportError:
        pass
    return os.getenv("GEMINI_API_KEY")
