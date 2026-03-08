"""
Green-Tech Inventory Assistant — Streamlit dashboard for small cafes.
Core flow: Create, View, Update inventory + search/filter.
AI: Reorder forecast with rule-based fallback.
"""
import sys
import warnings
from pathlib import Path

# Reduce noise from third-party EOL warnings (e.g. Python 3.9 + google-auth)
warnings.filterwarnings("ignore", message=".*Python version 3.9 past its end of life.*", category=FutureWarning)

# Ensure src is on path when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load .env so GEMINI_API_KEY is available when set
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# Imports below require path and .env set first (see above).
import re  # noqa: E402
import streamlit as st  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402

from src.inventory_service import (  # noqa: E402
    load_items,
    get_item_by_id,
    create_item,
    update_item,
    delete_item,
    filter_items,
    load_consumption,
    get_consumption_for_item,
)
from src.forecast import (  # noqa: E402
    get_forecast,
    get_ai_dashboard_summary,
    get_ai_dashboard_paragraph,
    get_ai_chat_response,
    get_ai_promo_intelligence,
)
from src.config import get_gemini_api_key  # noqa: E402

st.set_page_config(
    page_title="Cafe Inventory & Reorder Assistant",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 60% Medium-style layout; glowbox for all AI; compact tables; floating chat
st.markdown("""
<style>
    /* Narrow centralized layout */
    div.block-container { max-width: min(56vw, 840px) !important; margin-left: auto; margin-right: auto; padding-top: 4.25rem; padding-bottom: 4rem; padding-left: 0.75rem !important; padding-right: 0.75rem !important; }
    .main-header { font-size: 4.4rem; font-weight: 900; margin-top: 0.2rem; margin-bottom: 0.55rem; color: inherit; letter-spacing: -0.03em; line-height: 1.12; display: block; }
    .sub-header { font-size: 1.1rem; font-weight: 450; margin-bottom: 1.25rem; color: inherit; opacity: 0.9; }
    .metric-card {
        padding: 0.75rem 1rem; border-radius: 8px; border-left: 4px solid #4ade80;
        margin: 0.5rem 0; background-color: rgba(74, 222, 128, 0.12); color: inherit;
    }
    .alert-low {
        border-left-color: #f87171 !important;
        background-color: rgba(248, 113, 113, 0.15) !important;
        color: inherit !important;
    }
    .stButton > button { border-radius: 6px; font-weight: 500; }
    div[data-testid="stMetricValue"] { font-weight: 600; }
    h3 { font-size: 1.15rem !important; font-weight: 600 !important; }
    /* Glowbox: same for all AI; label small, recommendations strong */
    .glowbox {
        padding: 1.25rem 1.5rem; border-radius: 12px; margin-bottom: 1.5rem;
        background: transparent; color: inherit; line-height: 1.65; font-size: 0.95rem;
        border: 2px solid rgba(0, 255, 255, 0.6);
        animation: neon-border 3s ease-in-out infinite;
        box-shadow: 0 0 15px rgba(0, 255, 255, 0.4), inset 0 0 15px transparent;
    }
    @keyframes neon-border {
        0%, 100% { border-color: rgba(0, 255, 255, 0.7); box-shadow: 0 0 15px rgba(0, 255, 255, 0.5), 0 0 30px rgba(0, 255, 255, 0.2); }
        33% { border-color: rgba(255, 0, 255, 0.7); box-shadow: 0 0 15px rgba(255, 0, 255, 0.5), 0 0 30px rgba(255, 0, 255, 0.2); }
        66% { border-color: rgba(0, 255, 200, 0.7); box-shadow: 0 0 15px rgba(0, 255, 200, 0.5), 0 0 30px rgba(0, 255, 200, 0.2); }
    }
    .glowbox .glowbox-label { font-size: 0.8rem; font-weight: 500; color: inherit; opacity: 0.9; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }
    .glowbox .glowbox-recs { font-size: 1.05rem; font-weight: 600; color: inherit; line-height: 1.6; }
    .glowbox strong { color: #7dd3fc; }
    .glowbox ul { margin: 0.4rem 0 0 1rem; padding-left: 0.5rem; }
    .glowbox li { margin: 0.35rem 0; }
    /* Compact centered table; no underscores in headers (handled in code) */
    .inventory-table-wrap { max-width: 100%; margin: 0.5rem auto; overflow-x: auto; }
    .inventory-table { margin: 0 auto; table-layout: auto; border-collapse: collapse; color: inherit; font-size: 0.9rem; }
    .inventory-table th, .inventory-table td { padding: 0.4rem 0.6rem; text-align: center; white-space: nowrap; border: 1px solid rgba(128,128,128,0.3); }
    .inventory-table th { font-weight: 600; }
    /* Delete item: neat grid */
    .item-detail-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem 1.5rem; margin: 0.75rem 0; font-size: 0.95rem; color: inherit; }
    .item-detail-grid .label { font-weight: 600; opacity: 0.9; }
    .item-detail-grid .value { font-weight: 500; }
    /* Fixed bottom-right floating AI chat launcher */
    div[data-testid="stPopover"] {
        position: fixed;
        right: 1.25rem;
        bottom: 1.25rem;
        width: min(360px, calc(100vw - 2rem));
        z-index: 999999;
        margin: 0 !important;
    }
</style>
""", unsafe_allow_html=True)


def main():
    api_key_present = bool(get_gemini_api_key() and get_gemini_api_key().strip())
    if "ai_enabled" not in st.session_state:
        st.session_state["ai_enabled"] = api_key_present

    title_col, toggle_col = st.columns([6, 2])
    with title_col:
        st.markdown('<p class="main-header">☕ CAFE INVENTORY & REORDER ASSISTANT</p>', unsafe_allow_html=True)
        st.markdown('<p class="sub-header">Track perishables, reduce waste, and prepare for upcoming days — built for small cafes.</p>', unsafe_allow_html=True)
    with toggle_col:
        ai_toggle = st.toggle("AI Insights", value=bool(st.session_state["ai_enabled"] and api_key_present), disabled=not api_key_present)
        st.session_state["ai_enabled"] = bool(ai_toggle and api_key_present)

    nav_options = ["Dashboard", "View & Search", "Add Item", "Update Stock", "Delete Item", "Consumption Trends", "Reorder Insights"]
    current_page = st.session_state.get("page", "Dashboard")
    page = st.sidebar.radio(
        "Navigate",
        nav_options,
        index=nav_options.index(current_page),
    )
    st.session_state["page"] = page

    if page == "Dashboard":
        render_dashboard()
    elif page == "View & Search":
        render_view_search()
    elif page == "Add Item":
        render_add_item()
    elif page == "Update Stock":
        render_update_stock()
    elif page == "Delete Item":
        render_delete_item()
    elif page == "Consumption Trends":
        render_consumption_trends()
    else:
        render_reorder_insights()

    # Floating collapsible chat (bottom-right style)
    render_floating_chat()


def _normalize_consumption(consumption_df):
    """Return a clean copy with date and quantity as proper types. Never mutate the original."""
    if consumption_df is None or consumption_df.empty:
        return pd.DataFrame(columns=["date", "time", "item_id", "quantity", "day"])
    df = consumption_df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(float)
    df = df.dropna(subset=["date"])
    return df


def _style_plotly(fig, height=None):
    """Use explicit styling so charts stay readable in older Streamlit dark mode setups."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb"),
        title_font=dict(size=18),
        legend=dict(font=dict(color="#e5e7eb")),
        hoverlabel=dict(font=dict(color="#e5e7eb")),
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(148,163,184,0.18)", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(148,163,184,0.18)", zeroline=False)
    if height is not None:
        fig.update_layout(height=height)
    return fig


def _fmt2(value):
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _ai_enabled():
    api_key = get_gemini_api_key()
    return bool(st.session_state.get("ai_enabled", False) and api_key and api_key.strip())


def _title_case_label(text):
    return str(text).replace("_", " ").title()


def _format_glowbox_html(text):
    safe = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", safe)
    lines = [line.strip() for line in safe.splitlines() if line.strip()]
    bullet_lines = [line[2:].strip() for line in lines if line.startswith("- ")]
    if bullet_lines and len(bullet_lines) == len(lines):
        return "<ul>" + "".join(f"<li>{line}</li>" for line in bullet_lines) + "</ul>"
    return "<p class=\"glowbox-recs\">" + "<br>".join(lines) + "</p>"


def _risk_color(level):
    if level == "green":
        return "#22c55e"
    if level == "red":
        return "#ef4444"
    return "#f59e0b"


def _build_inventory_snapshot(items):
    if not items:
        return "No inventory items."
    lines = []
    for i in items:
        lines.append(
            f"- {i.get('name')} ({i.get('category')}), stock: {i.get('current_stock')} {i.get('unit')}, "
            f"reorder at {i.get('reorder_level')}"
        )
    return "\n".join(lines)


def _build_usage_snapshot(consumption_df, id_to_name):
    if consumption_df is None or consumption_df.empty:
        return "No consumption data yet."
    # Last 7 days by item
    cutoff = consumption_df["date"].max() - pd.Timedelta(days=7)
    last_7 = consumption_df[consumption_df["date"] >= cutoff]
    by_item = last_7.groupby("item_id")["quantity"].sum()
    item_lines = [f"- {id_to_name.get(k, k)}: {by_item[k]}" for k in by_item.index]
    item_block = "Last 7 days by item:\n" + ("\n".join(item_lines) if item_lines else "No usage in last 7 days.")
    # By time slot
    time_block = "No time-of-day data."
    if "time" in consumption_df.columns:
        by_time = consumption_df.groupby("time")["quantity"].sum()
        time_lines = [f"- {t}: {by_time[t]}" for t in by_time.index]
        if time_lines:
            time_block = "Usage by time slot:\n" + "\n".join(time_lines)
    return item_block + "\n\n" + time_block


def render_dashboard():
    items = load_items()
    id_to_name = {i.get("id"): i.get("name", "") for i in items}
    consumption_raw = load_consumption()
    consumption_df = _normalize_consumption(consumption_raw)

    low_stock = [i for i in items if (i.get("current_stock") or 0) <= (i.get("reorder_level") or 0)]
    total_items = len(items)
    total_value = sum((i.get("current_stock") or 0) * (i.get("unit_cost") or 0) for i in items)

    # Build text summaries for AI paragraph (use normalized df)
    last_7_usage = "No consumption data yet."
    if not consumption_df.empty:
        cutoff = consumption_df["date"].max() - pd.Timedelta(days=7)
        last_7 = consumption_df[consumption_df["date"] >= cutoff]
        by_item_series = last_7.groupby("item_id")["quantity"].sum()
        last_7_usage = "\n".join([f"- {id_to_name.get(k, k)}: {_fmt2(by_item_series[k])}" for k in by_item_series.index]) or "No usage in last 7 days."
    low_stock_lines = "\n".join([f"- {i.get('name')}: {_fmt2(i.get('current_stock'))} {i.get('unit')} (reorder at {_fmt2(i.get('reorder_level'))})" for i in low_stock]) if low_stock else "None."
    by_time_usage = "No time breakdown."
    if not consumption_df.empty and "time" in consumption_df.columns:
        by_time_series = consumption_df.groupby("time")["quantity"].sum()
        by_time_usage = "\n".join([f"- {t}: {by_time_series[t]}" for t in by_time_series.index]) or "No data."

    # AI summary in glowbox: bullets in priority order, important words highlighted (markdown **)
    with st.spinner("Generating AI summary..."):
        paragraph_result = get_ai_dashboard_paragraph(last_7_usage, low_stock_lines, by_time_usage, use_ai=_ai_enabled())
    summary_text = paragraph_result.get("summary", "")
    is_ai = paragraph_result.get("method") == "ai"
    err = paragraph_result.get("error")
    title = "🤖 AI summary" if is_ai else "📋 Summary"
    st.markdown(
        f'<div class="glowbox"><span class="glowbox-label">{title}</span>{_format_glowbox_html(summary_text)}</div>',
        unsafe_allow_html=True,
    )
    if err and not is_ai:
        st.caption("Using rule-based summary because AI is off or unavailable.")

    # KPIs
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Total items", total_items)
    with c2:
        st.metric("Low stock alerts", len(low_stock), delta=None)
    with c3:
        st.metric("Inventory value (est.)", f"${total_value:,.0f}")

    st.markdown("### Prepare for upcoming days")
    if low_stock:
        for item in low_stock:
            st.markdown(f'<div class="metric-card alert-low"><b>{item.get("name")}</b> — Current: {_fmt2(item.get("current_stock"))} {item.get("unit")} (reorder at {_fmt2(item.get("reorder_level"))})</div>', unsafe_allow_html=True)
        with st.spinner("Getting recommendations..."):
            ai_result = get_ai_dashboard_summary(low_stock, use_ai=_ai_enabled())
        recs = ai_result.get("summary", "")
        rec_label = "Recommendations (AI)" if ai_result.get("method") == "ai" else "Recommendations (Rule-Based)"
        st.markdown('<div class="glowbox"><span class="glowbox-label">' + rec_label + '</span>' + _format_glowbox_html(recs) + '</div>', unsafe_allow_html=True)
        if ai_result.get("error") and ai_result.get("method") != "ai":
            st.caption(f"Fallback: {ai_result.get('error')}")
    else:
        st.info("No items below reorder level. Use **Consumption Trends** and **Reorder Insights** to plan ahead.")

    render_promo_intelligence(items, consumption_df, id_to_name)

    st.markdown("### Recent Consumption (Last 7 Days By Item)")
    if consumption_df.empty:
        st.caption("No consumption data yet. Data is loaded from synthetic CSV.")
    else:
        cutoff = consumption_df["date"].max() - pd.Timedelta(days=7)
        last_7 = consumption_df[consumption_df["date"] >= cutoff]
        # Build a simple list of dicts for the pie chart (no complex pandas ops that could break Plotly)
        sums = {}
        for _, row in last_7.iterrows():
            iid = row["item_id"]
            sums[iid] = sums.get(iid, 0.0) + float(row["quantity"])
        pie_data = [{"Item": id_to_name.get(k, k), "Quantity used": v} for k, v in sums.items() if v > 0 and k in id_to_name]
        if not pie_data:
            st.caption("No consumption in the last 7 days.")
        else:
            pie_df = pd.DataFrame(pie_data)
            fig = px.pie(pie_df, values="Quantity used", names="Item", title="Share Of Usage (Last 7 Days)", hole=0.4)
            fig.update_traces(textposition="inside", textinfo="label+percent")
            fig.update_layout(margin=dict(t=40, b=20, l=20, r=20), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.15))
            _style_plotly(fig)
            st.plotly_chart(fig, width="stretch")

    # Time-based insights — plain string sorting, no pd.Categorical (compatible with all Plotly versions)
    TIME_ORDER = ["07:00", "09:00", "12:00", "15:00", "18:00"]
    if not consumption_df.empty and "time" in consumption_df.columns:
        st.markdown("### Consumption By Time Of Day")
        time_sums = {}
        for _, row in consumption_df.iterrows():
            t = str(row["time"]).strip()
            time_sums[t] = time_sums.get(t, 0.0) + float(row["quantity"])
        time_list = [{"time": t, "quantity": time_sums.get(t, 0.0)} for t in TIME_ORDER if t in time_sums]
        if time_list:
            time_df = pd.DataFrame(time_list)
            max_q = float(time_df["quantity"].max()) if not time_df.empty else 0.0
            fig_time = px.line(time_df, x="time", y="quantity", title="Total Usage By Time Slot", markers=True)
            fig_time.update_traces(mode="lines+markers+text", text=time_df["quantity"].round(2), textposition="top center")
            fig_time.update_layout(xaxis_tickangle=-45, margin=dict(b=80), xaxis_title="Time", yaxis_title="Quantity")
            _style_plotly(fig_time, height=320)
            if max_q > 0:
                fig_time.update_yaxes(range=[0, max_q * 1.2])
            st.plotly_chart(fig_time, width="stretch")

        st.markdown("### Top Products By Time Slot")
        time_item_sums = {}
        for _, row in consumption_df.iterrows():
            t = str(row["time"]).strip()
            iid = row["item_id"]
            key = (t, iid)
            time_item_sums[key] = time_item_sums.get(key, 0.0) + float(row["quantity"])
        bar_data = []
        for (t, iid), q in time_item_sums.items():
            if t in TIME_ORDER and iid in id_to_name and q > 0:
                bar_data.append({"time": t, "Product": id_to_name[iid], "Quantity": q})
        if bar_data:
            bar_df = pd.DataFrame(bar_data)
            bar_df = bar_df.sort_values("time", key=lambda col: col.map({t: i for i, t in enumerate(TIME_ORDER)}))
            fig_bar = px.bar(bar_df, x="time", y="Quantity", color="Product", title="Usage By Time And Product", barmode="group")
            fig_bar.update_traces(texttemplate="%{y:.2f}", textposition="outside")
            fig_bar.update_layout(xaxis_tickangle=-45, margin=dict(b=100), xaxis_title="Time", yaxis_title="Quantity", legend=dict(orientation="h", yanchor="bottom", y=-0.35))
            _style_plotly(fig_bar, height=420)
            st.plotly_chart(fig_bar, width="stretch")


def render_promo_intelligence(items, consumption_df, id_to_name):
    """AI-first promo ideas from demand/stock with rule-based fallback."""
    st.markdown("### Promo Intelligence")
    if consumption_df.empty or not items:
        st.caption("Not enough data for promo ideas yet.")
        return

    id_to_item = {i.get("id"): i for i in items}
    cutoff = consumption_df["date"].max() - pd.Timedelta(days=7)
    last_7 = consumption_df[consumption_df["date"] >= cutoff]
    by_item = last_7.groupby("item_id", as_index=False).agg(total_qty=("quantity", "sum"))
    by_item["name"] = by_item["item_id"].map(id_to_name)
    by_item["category"] = by_item["item_id"].map(lambda iid: (id_to_item.get(iid) or {}).get("category", ""))
    by_item = by_item[by_item["name"].notna()].sort_values("total_qty", ascending=False)

    # Packaging and paper-cup lines are not hero items; they imply drinks demand.
    non_packaging = by_item[by_item["category"].str.lower() != "packaging"].copy()
    top_items = non_packaging.head(3).to_dict("records")
    paper_cups_row = by_item[by_item["name"].str.contains("paper cups", case=False, na=False)]
    paper_cups_qty = float(paper_cups_row.iloc[0]["total_qty"]) if not paper_cups_row.empty else 0.0

    item_usage = {row["item_id"]: float(row["total_qty"]) for _, row in by_item.iterrows()}
    overstocked = []
    for i in items:
        iid = i.get("id")
        used = item_usage.get(iid, 0.0)
        stock = float(i.get("current_stock") or 0.0)
        if stock > 0 and (used <= 0.5 or stock > (used * 3.0)):
            overstocked.append((i.get("name", iid), stock, used))
    overstocked = sorted(overstocked, key=lambda x: (x[2], -x[1]))[:2]

    promo_lines = []
    if top_items:
        hero = ", ".join([f"**{r['name']}** ({_fmt2(r['total_qty'])})" for r in top_items[:2]])
        promo_lines.append(f"- Push a **Morning Combo** around {hero} to maximize peak-hour demand.")
    if paper_cups_qty > 0:
        promo_lines.append(
            f"- **Drinks demand is strong** (paper cups used: {_fmt2(paper_cups_qty)}). Promote coffee/tea/hot chocolate bundles."
        )
    if overstocked:
        for name, stock, used in overstocked:
            promo_lines.append(
                f"- Run a limited **Bundle Offer** for **{name}** (Stock: {_fmt2(stock)}, 7-Day Use: {_fmt2(used)}) to reduce waste risk."
            )
    promo_lines.append("- Keep promos **time-boxed** (morning and lunch windows) and review every 2-3 days.")
    promo_text = "\n".join(promo_lines[:4])

    top_item_lines = "\n".join([f"- {r['name']}: {_fmt2(r['total_qty'])}" for r in top_items]) or "- None"
    overstock_lines = "\n".join(
        [f"- {name}: stock {_fmt2(stock)}, recent use {_fmt2(used)}" for name, stock, used in overstocked]
    ) or "- None"
    drinks_signal_line = f"- Paper cups used in last 7 days: {_fmt2(paper_cups_qty)}"

    promo_result = get_ai_promo_intelligence(
        top_item_lines=top_item_lines,
        overstock_lines=overstock_lines,
        drinks_signal_line=drinks_signal_line,
        fallback_summary=promo_text,
        use_ai=_ai_enabled(),
    )
    promo_label = "Recommendations (AI)" if promo_result.get("method") == "ai" else "Recommendations (Rule-Based)"
    st.markdown(
        '<div class="glowbox"><span class="glowbox-label">' + promo_label + '</span>'
        + _format_glowbox_html(promo_result.get("summary", promo_text))
        + '</div>',
        unsafe_allow_html=True,
    )


def render_view_search():
    st.subheader("View & Search inventory")
    flash_message = st.session_state.pop("flash_message", None)
    if flash_message:
        st.success(flash_message)
    items_all = load_items()
    categories = [""] + sorted({i.get("category") for i in items_all if i.get("category")})
    col1, col2, col3 = st.columns(3)
    with col1:
        filter_category = st.selectbox("Category", categories, key="vs_category")
    with col2:
        filter_low_stock = st.checkbox("Low stock only", value=False, key="vs_low_stock")
    with col3:
        filter_search = st.text_input("Search name or category", "", key="vs_search")
    items = filter_items(
        items=items_all,
        category=filter_category or None,
        low_stock_only=filter_low_stock,
        search_query=filter_search or None,
    )
    if not items:
        st.info("No items match the current filters.")
        return
    df = pd.DataFrame(items)
    cols = ["id", "name", "category", "unit", "current_stock", "reorder_level", "shelf_life_days"]
    df = df[[c for c in cols if c in df.columns]]
    def _esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    def _label(col):
        return _title_case_label(col)
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{_esc(row[c])}</td>" for c in df.columns) + "</tr>"
        for _, row in df.iterrows()
    )
    st.markdown(
        '<div class="inventory-table-wrap"><table class="inventory-table">'
        + "<thead><tr>" + "".join(f"<th>{_esc(_label(c))}</th>" for c in df.columns) + "</tr></thead><tbody>"
        + rows_html + "</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_add_item():
    st.subheader("Add new item")
    with st.form("add_item_form"):
        name = st.text_input("Name *", placeholder="e.g. Espresso Beans")
        category = st.text_input("Category *", placeholder="e.g. Coffee & Tea")
        unit = st.text_input("Unit *", placeholder="e.g. kg, L, pieces")
        current_stock = st.number_input("Current stock *", min_value=0.0, value=0.0, step=0.1)
        reorder_level = st.number_input("Reorder level *", min_value=0.0, value=0.0, step=0.1)
        shelf_life_days = st.number_input("Shelf life (days)", min_value=1, value=30, step=1)
        unit_cost = st.number_input("Unit cost (optional)", min_value=0.0, value=0.0, step=0.01)
        supplier_notes = st.text_area("Supplier notes (optional)", "")
        submitted = st.form_submit_button("Create item")
    if submitted:
        item = {
            "name": name,
            "category": category,
            "unit": unit,
            "current_stock": current_stock,
            "reorder_level": reorder_level,
            "shelf_life_days": shelf_life_days,
            "unit_cost": unit_cost,
            "supplier_notes": supplier_notes,
        }
        created, errors = create_item(item)
        if errors:
            for e in errors:
                st.error(e)
        else:
            st.session_state["flash_message"] = f"Added {created.get('name')} ({created.get('id')}) to inventory."
            st.session_state["page"] = "View & Search"
            st.rerun()


def render_update_stock():
    items = load_items()
    if not items:
        st.info("No items yet. Add an item first.")
        return
    item_ids = [i["id"] for i in items]
    options = [f"{i.get('name')} — {i.get('category')} ({i.get('id')})" for i in items]
    sel = st.selectbox("Select item to update", options)
    if not sel:
        return
    item_id = item_ids[options.index(sel)]
    item = get_item_by_id(item_id)
    if not item:
        st.error("Item not found.")
        return
    st.subheader(f"Update: {item.get('name')}")
    with st.form("update_stock_form"):
        new_stock = st.number_input("Current stock", min_value=0.0, value=float(item.get("current_stock", 0)), step=0.1)
        new_reorder = st.number_input("Reorder level", min_value=0.0, value=float(item.get("reorder_level", 0)), step=0.1)
        submitted = st.form_submit_button("Update")
    if submitted:
        updated, errors = update_item(item_id, {"current_stock": new_stock, "reorder_level": new_reorder})
        if errors:
            for e in errors:
                st.error(e)
        else:
            st.success("Stock updated.")


def render_delete_item():
    st.subheader("Delete an item")
    items = load_items()
    if not items:
        st.info("No items to delete.")
        return
    item_ids = [i["id"] for i in items]
    options = [f"{i.get('name')} — {i.get('category')} ({i.get('id')})" for i in items]
    sel = st.selectbox("Select item to delete", options)
    if not sel:
        return
    item_id = item_ids[options.index(sel)]
    item = get_item_by_id(item_id)
    if not item:
        st.error("Item not found.")
        return
    def _esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    st.markdown(
        '<div class="metric-card">'
        '<div class="item-detail-grid">'
        '<span class="label">Name</span><span class="value">' + _esc(item.get("name", "")) + '</span>'
        '<span class="label">Category</span><span class="value">' + _esc(item.get("category", "")) + '</span>'
        '<span class="label">Unit</span><span class="value">' + _esc(item.get("unit", "")) + '</span>'
        '<span class="label">Current stock</span><span class="value">' + _esc(str(item.get("current_stock", ""))) + '</span>'
        '<span class="label">Reorder level</span><span class="value">' + _esc(str(item.get("reorder_level", ""))) + '</span>'
        '<span class="label">Shelf life (days)</span><span class="value">' + _esc(str(item.get("shelf_life_days", ""))) + '</span>'
        '<span class="label">Unit cost</span><span class="value">$' + _esc(str(item.get("unit_cost", 0))) + '</span>'
        '<span class="label">ID</span><span class="value">' + _esc(item.get("id", "")) + '</span>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.warning("This action is irreversible. The item will be permanently removed from inventory.")
    if st.button("Delete this item"):
        removed = delete_item(item_id)
        if removed:
            st.session_state["flash_message"] = f"Deleted {item.get('name')} ({item_id}) from inventory."
            st.session_state["page"] = "View & Search"
            st.rerun()
        else:
            st.error("Failed to delete. Item may have already been removed.")


def render_consumption_trends():
    st.subheader("Day-Wise Consumption Trends")
    consumption_df = load_consumption()
    items = load_items()
    if consumption_df.empty or not items:
        st.info("No consumption or item data. Using synthetic data from repo.")
        return
    item_choices = {i["name"]: i["id"] for i in items}
    chosen_name = st.selectbox("Select item", list(item_choices.keys()))
    if not chosen_name:
        return
    item_id = item_choices[chosen_name]
    df = get_consumption_for_item(item_id, consumption_df)
    if df.empty:
        st.caption("No consumption history for this item.")
        return
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    max_q = float(df["quantity_used"].max()) if not df.empty else 0.0
    # Area chart for daily trend
    fig = px.area(df, x="date", y="quantity_used", title=f"Daily Consumption: {chosen_name}")
    fig.update_traces(fill="tozeroy", line=dict(width=2))
    fig.update_layout(xaxis_title="Date", yaxis_title="Quantity Used")
    _style_plotly(fig, height=320)
    if max_q > 0:
        fig.update_yaxes(range=[0, max_q * 1.15])
    st.plotly_chart(fig, width="stretch")
    # Day-of-week: horizontal bar for readability
    df["day_of_week"] = df["date"].dt.day_name()
    by_dow = df.groupby("day_of_week", as_index=False)["quantity_used"].mean()
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_dow["_sort"] = by_dow["day_of_week"].map({d: i for i, d in enumerate(day_order)})
    by_dow = by_dow.sort_values("_sort", ascending=False).drop(columns=["_sort"])  # Monday at top in horizontal bar
    fig2 = px.bar(by_dow, y="day_of_week", x="quantity_used", orientation="h", title="Average Usage By Day Of Week")
    fig2.update_traces(texttemplate="%{x:.2f}", textposition="outside")
    fig2.update_layout(xaxis_title="Average Quantity", yaxis_title="")
    _style_plotly(fig2, height=300)
    st.plotly_chart(fig2, width="stretch")
    # Time-of-day: area by time slot
    raw_consumption = _normalize_consumption(load_consumption())
    if not raw_consumption.empty and "time" in raw_consumption.columns:
        item_time = raw_consumption[raw_consumption["item_id"] == item_id]
        if not item_time.empty:
            st.markdown("#### Consumption By Time Of Day (This Item)")
            by_time = item_time.groupby("time", as_index=False)["quantity"].sum().sort_values("time")
            max_q2 = float(by_time["quantity"].max()) if not by_time.empty else 0.0
            fig3 = px.area(by_time, x="time", y="quantity", title=f"Usage By Time Slot: {chosen_name}")
            fig3.update_traces(fill="tozeroy", line=dict(width=2))
            fig3.update_layout(xaxis_title="Time", yaxis_title="Quantity")
            _style_plotly(fig3, height=280)
            if max_q2 > 0:
                fig3.update_yaxes(range=[0, max_q2 * 1.15])
            st.plotly_chart(fig3, width="stretch")
        else:
            st.caption("No time-split consumption for this item.")


def render_reorder_insights():
    st.subheader("Reorder Insights (AI + Fallback)")
    if _ai_enabled():
        st.caption("Using AI (Gemini) when available; rule-based fallback if the API is unavailable.")
    else:
        st.caption("AI is off or unavailable. Using rule-based forecast only.")
    items = load_items()
    if not items:
        st.info("No items. Add items and consumption data first.")
        return
    item_options = [f"{i.get('name')} — {i.get('category')} ({i.get('id')})" for i in items]
    item_ids = [i["id"] for i in items]
    chosen_label = st.selectbox("Select item for forecast", item_options)
    if not chosen_label:
        return
    item_id = item_ids[item_options.index(chosen_label)]
    if st.button("Get reorder insight"):
        with st.spinner("Computing..."):
            result = get_forecast(item_id, use_ai=_ai_enabled())
        if "error" in result:
            st.error(result["error"])
            return
        recs = result.get("suggestion", "")
        rec_method = result.get("method", "rule_based")
        current_stock = _fmt2(result.get("current_stock"))
        reorder_level = _fmt2(result.get("reorder_level"))
        unit = result.get("unit", "")
        buy_qty = _fmt2(result.get("recommended_buy_qty"))
        waste_score = _fmt2(result.get("waste_risk_score"))
        waste_level = result.get("waste_risk_level", "amber")
        waste_color = _risk_color(waste_level)
        recs_safe = recs.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        recs_safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", recs_safe)
        rec_label = "Recommendations (AI)" if rec_method == "ai" else "Recommendations (Rule-Based)"
        st.markdown(
            '<div class="glowbox">'
            f'<span class="glowbox-label">{rec_label}</span>'
            f'<p class="glowbox-recs"><strong>Current Stock:</strong> {current_stock} {unit} '
            f'| <strong>Reorder Level:</strong> {reorder_level} {unit}<br>'
            f'<strong>Suggested Buy Qty:</strong> {buy_qty} {unit} '
            f'| <strong>Waste Risk Score:</strong> <span style="color:{waste_color}; font-weight:700;">{waste_score}</span></p>'
            f'<p class="glowbox-recs">{recs_safe}</p></div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Avg. Daily Consumption", _fmt2(result.get("avg_daily_consumption")))
        with c2:
            st.metric("Days Until Run-Out", _fmt2(result.get("days_until_runout")))
        with c3:
            st.metric("Days Until Reorder", _fmt2(result.get("days_until_reorder")))


def render_floating_chat():
    """Fixed bottom-right floating AI chat launcher."""
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    if not _ai_enabled():
        st.button("💬 Ask Me Anything", disabled=True, key="chat_disabled", width="stretch")
        return

    with st.popover("💬 Ask Me Anything", use_container_width=True):
        st.markdown("**Data-Based Cafe Assistant**")
        if st.session_state["chat_history"]:
            for msg in st.session_state["chat_history"][-6:]:
                st.chat_message(msg.get("role", "assistant")).markdown(msg.get("content", ""))
        else:
            st.caption("Ask about inventory, demand peaks, reorder timing, or quick menu decisions.")

        question = st.text_input("Message", key="floating_chat_question", placeholder="What should I prepare most for the morning rush?")
        send = st.button("Send", key="floating_chat_send", width="stretch")

        if send and question.strip():
            user_input = question.strip()
            st.session_state["chat_history"].append({"role": "user", "content": user_input})
            items = load_items()
            inventory_snapshot = _build_inventory_snapshot(items)
            consumption_raw = load_consumption()
            consumption_df = _normalize_consumption(consumption_raw)
            id_to_name = {i.get("id"): i.get("name", "") for i in items}
            usage_snapshot = _build_usage_snapshot(consumption_df, id_to_name)
            with st.spinner("Thinking…"):
                result = get_ai_chat_response(
                    user_input,
                    inventory_snapshot=inventory_snapshot,
                    usage_snapshot=usage_snapshot,
                    use_ai=_ai_enabled(),
                )
            answer = result.get("answer", "") or "Unavailable. Try again."
            st.session_state["chat_history"].append({"role": "assistant", "content": answer})
            st.rerun()


if __name__ == "__main__":
    main()
