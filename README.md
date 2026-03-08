# Green-Tech Inventory Assistant

Case-study solution for *small cafes* to track perishable inventory, forecast reorder timing, improve decision-making with AI, and reduce waste.

---

## Submission Notes

- Candidate name: **Aprameya V. Madhwaraj**
- Time Spent: **~6 Hours**
- Video demo link: **[YouTube](https://www.youtube.com/watch?v=fW4YQ5cp-l8)**

---

## Scenario & Scope

- **Scenario chosen:** Green-Tech Inventory Assistant
- **Primary target:** Small cafes with perishable inventory
- **Core objective:** Reduce overstock/waste while avoiding stock-outs

Design decisions further elaborated in [DESIGN.md](DESIGN.md)

---

## Features Implemented

- Inventory lifecycle: **Add**, **View/Search**, **Update Stock**, **Delete**
- On-page filtering + compact table view
- Dashboard with:
  - AI summary in priority bullets
  - Low-stock alerts
  - Reorder recommendations
  - Promotional intelligence
  - Consumption visualizations
- Reorder Insights with:
  - Method-aware recommendations (AI vs rule-based)
  - Current stock with suggested buy quantity
  - Waste risk score (green/amber/red semantics)
- AI toggle at top (`AI Insights`) to switch AI on/off
- Floating “Ask me anything” assistant

---

## Tech Stack

- **Frontend:** Streamlit
- **Data:** JSON + CSV (synthetic)
- **AI:** Google Gemini (2.5 Flash Lite) via `google-genai` and API calls
- **Fallback:** Deterministic rule-based logic
- **Tests:** `pytest`

---

## Data Model

- `data/inventory_items.json`
  - Inventory master (id, name, category, unit, stock, reorder, shelf life, cost)
- `data/consumption.csv`
  - Timestamped usage (`date`, `time`, `item_id`, `quantity`, `day`)

No real customer data is used; all bundled data is synthetic (Google Gemini).

---

## AI Disclosure

- Did you use an AI assistant? - Yes (Cursor, Google Gemini)
- How did you verify the suggestions? 
  - All AI-generated suggestions were reviewed manually and validated against the application’s requirements before implementation
  - Core design and ideas are first designed by hand followed by prompts which are used for specific coding tasks (like UI changes, bug fixes, test cases)
  - The sample data used is fully AI generated (Google Gemini) which was achieved by providing strong prompts with clear defined parameters and patterns tailored for our case challenge.
- Give one example of a suggestion you rejected or changed:
  - An early AI suggestion recommended relying entirely on LLM-generated reorder recommendations. I modified this design so that the application always computes a deterministic rule-based reorder estimate first, and then optionally augments it with AI insights.  
  This ensures the application continues functioning even if the AI service fails or returns inconsistent output. Also provided a toggle suggestion to keep the service completely rule-based upon the user's discretion.
- All AI outputs are treated as advisory insights rather than decisions, and the system maintains deterministic fallback logic to ensure consistent operation.

---

## Setup & Run

### Prerequisites

- Python 3.11+ recommended (3.9+ works)
- pip

### Install and Launch

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

### Enable AI (optional)

1. Copy `.env.example` to `.env`
2. Set `GEMINI_API_KEY=...`
3. Use the `AI Insights` toggle in the app

---

## Test Instructions

Run all tests:

```bash
venv\Scripts\python -m pytest tests -q
```

Run verbose:

```bash
venv\Scripts\python -m pytest tests -vv
```

Coverage (optional future setup):

```bash
venv\Scripts\python -m pytest --cov=src --cov-report=term-missing
```

---

## Repository Structure


| Path                       | Purpose                                 |
| -------------------------- | --------------------------------------- |
| `app.py`                   | Streamlit UI + dashboard workflows      |
| `src/inventory_service.py` | CRUD + filtering + data load            |
| `src/forecast.py`          | AI/reorder/promo logic + fallback       |
| `src/config.py`            | Paths + env loading                     |
| `data/`                    | Synthetic inventory and consumption     |
| `tests/`                   | Unit tests for services and forecasting |
| `DESIGN.md`                | Architecture and design rationale       |


---

## Tradeoffs / Known Limitations

- Current persistence is local-file based (JSON/CSV), single-user friendly
- No authentication/authorization layer
- Forecasting is lightweight (fast, transparent) but not full time-series ML
- Given the time constraints; settled for a Streamlit frontend, with more time can be upgraded to a full suite React website

---

