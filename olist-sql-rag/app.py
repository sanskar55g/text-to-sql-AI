import streamlit as st
import pandas as pd
import json
from datetime import date, timedelta
from sql_generator import generate_sql
from database import DatabaseManager
from config import Config

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Olist Data Assistant",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .main .block-container { padding-top: 2rem; max-width: 1000px; }

    h1 { font-weight: 700; letter-spacing: -0.02em; }

    .subtitle { color: #6b7280; font-size: 1rem; margin-top: -0.6rem; margin-bottom: 1.5rem; }

    .status-pill {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600; margin-bottom: 0.5rem;
    }
    .status-ok { background: #dcfce7; color: #166534; }
    .status-bad { background: #fee2e2; color: #991b1b; }

    .clarify-box {
        background: #fffbeb; border: 1px solid #fde68a; border-radius: 10px;
        padding: 0.9rem 1.1rem; margin-bottom: 0.8rem;
    }
    .clarify-box b { color: #92400e; }

    div[data-testid="stChatMessage"] { padding: 0.4rem 0; }

    .stButton button {
        border-radius: 8px; font-weight: 500;
    }

    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Backend setup
# ---------------------------------------------------------------------------
@st.cache_resource
def get_db():
    return DatabaseManager()


db = get_db()
config_ok = Config.validate()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### System Status")
    if config_ok:
        st.markdown('<span class="status-pill status-ok">● Connected</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-pill status-bad">● Missing keys</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### About")
    st.caption(
        "Ask questions in plain English about orders, products, customers, and revenue. "
        "If a question is ambiguous (e.g. 'best', 'recent'), the assistant will ask you "
        "to clarify before running any query."
    )

    st.markdown("---")
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.display_log = []
        st.session_state.pending_clarification = None
        st.rerun()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
# chat_history: raw {"role", "content"} turns sent to the LLM for context
# display_log: rendered conversation entries (what the user actually sees)
# pending_clarification: the ai_response dict we're currently waiting on
defaults = {
    "chat_history": [],
    "display_log": [],
    "pending_clarification": None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🛒 Olist E-Commerce AI Assistant")
st.markdown(
    '<div class="subtitle">Ask any question about orders, products, or customers in plain English.</div>',
    unsafe_allow_html=True,
)

if not config_ok:
    st.error("Configuration is missing required keys. Check your .env / config before asking questions.")
    st.stop()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def run_query(user_message):
    """Call the AI with full context and append the raw turn to chat_history."""
    ai_response = generate_sql(user_message, history=st.session_state.chat_history)
    if ai_response.get("type") != "error":
        st.session_state.chat_history.append({"role": "user", "content": user_message})
        st.session_state.chat_history.append(
            {"role": "assistant", "content": json.dumps(ai_response)}
        )
    return ai_response


def execute_and_log(sql, explanation, label):
    """Runs SQL, stores a renderable result entry in display_log."""
    db_result = db.execute_query(sql)

    if "error" in db_result:
        st.session_state.display_log.append({
            "role": "assistant", "kind": "db_error",
            "label": label, "error": db_result["error"],
        })
        return

    st.session_state.display_log.append({
        "role": "assistant", "kind": "result",
        "label": label, "sql": sql, "explanation": explanation,
        "data": db_result["data"], "count": db_result["count"],
    })


# ---------------------------------------------------------------------------
# Smart chart-axis selection
# ---------------------------------------------------------------------------
# Column names that signal "this is an identifier/code, not a metric" even if
# it happens to be numeric (e.g. zip_code_prefix) or is a hash-like string
# (e.g. customer_id). We never want these as the Y-axis (value), and we
# deprioritize them as the X-axis (category) too.
_ID_LIKE_HINTS = ("_id", "id_", "_code", "code_", "zip", "prefix", "_key", "hash", "uuid")


def _looks_like_identifier(col_name, series):
    name = col_name.lower()
    if any(hint in name for hint in _ID_LIKE_HINTS) and name != "product_category_name":
        return True
    # High-cardinality columns (almost every row unique) behave like IDs even
    # if the name doesn't give it away — charting them produces unreadable axes.
    if len(series) > 3 and series.nunique() / len(series) > 0.9:
        return True
    return False


def pick_chart_columns(df):
    """
    Returns (category_col, value_col, candidate_value_cols) using heuristics:
    - value_col: numeric, not identifier-like, prefer names hinting at a real
      metric (count, sum, total, revenue, amount, price, avg, rate).
    - category_col: non-numeric (or low-cardinality numeric), not identifier-like.
    Falls back to (None, None, []) if nothing sensible is found.
    """
    numeric_cols = [c for c in df.select_dtypes(include=["number"]).columns
                     if not _looks_like_identifier(c, df[c])]
    other_cols = [c for c in df.columns if c not in numeric_cols
                  and not _looks_like_identifier(c, df[c])]

    if not numeric_cols or not other_cols:
        return None, None, numeric_cols

    metric_hints = ("count", "sum", "total", "revenue", "amount", "price",
                     "avg", "average", "rate", "value", "score", "qty", "quantity")
    ranked_numeric = sorted(
        numeric_cols,
        key=lambda c: (0 if any(h in c.lower() for h in metric_hints) else 1, c),
    )

    return other_cols[0], ranked_numeric[0], numeric_cols


def handle_ai_response(user_facing_label, ai_response):
    """Routes a fresh AI response into the display log / pending clarification state."""
    rtype = ai_response.get("type")

    if rtype == "error" or "error" in ai_response:
        st.session_state.display_log.append({
            "role": "assistant", "kind": "ai_error",
            "error": ai_response.get("error", "Unknown error"),
        })
        st.session_state.pending_clarification = None

    elif rtype == "clarification":
        st.session_state.display_log.append({
            "role": "assistant", "kind": "clarification",
            "clarification_type": ai_response.get("clarification_type"),
            "question": ai_response.get("question", ""),
            "options": ai_response.get("options", []),
        })
        st.session_state.pending_clarification = ai_response

    elif rtype == "sql":
        st.session_state.pending_clarification = None
        execute_and_log(ai_response["sql"], ai_response.get("explanation", ""), user_facing_label)

    else:
        st.session_state.display_log.append({
            "role": "assistant", "kind": "ai_error",
            "error": f"Unexpected response format: {ai_response}",
        })
        st.session_state.pending_clarification = None


# ---------------------------------------------------------------------------
# Render conversation so far
# ---------------------------------------------------------------------------
for entry in st.session_state.display_log:
    if entry["role"] == "user":
        with st.chat_message("user"):
            st.write(entry["text"])
        continue

    with st.chat_message("assistant"):
        kind = entry["kind"]

        if kind == "clarification":
            st.markdown(
                f'<div class="clarify-box"><b>Need a bit more detail:</b><br>{entry["question"]}</div>',
                unsafe_allow_html=True,
            )

        elif kind == "ai_error":
            st.error(f"AI Error: {entry['error']}")

        elif kind == "db_error":
            st.error(f"Database Error: {entry['error']}")

        elif kind == "result":
            with st.expander("View AI reasoning & SQL query", expanded=False):
                st.write(f"**Explanation:** {entry['explanation']}")
                st.code(entry["sql"], language="sql")

            count = entry["count"]
            if count == 0:
                st.warning("No results found for this query.")
            else:
                st.markdown(f"**Results — {count} row(s)**")
                df = pd.DataFrame(entry["data"])
                st.dataframe(df, use_container_width=True)

                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Download CSV",
                    data=csv,
                    file_name="query_results.csv",
                    mime="text/csv",
                    key=f"dl_{id(entry)}",
                )

                if len(df) > 1:
                    default_x, default_y, value_candidates = pick_chart_columns(df)

                    if default_x and default_y:
                        with st.expander("📊 Visual analysis", expanded=True):
                            category_candidates = [c for c in df.columns if c != default_y]

                            # Only show manual pickers if there's real choice to make;
                            # otherwise just render the sensible default silently.
                            if len(value_candidates) > 1 or len(category_candidates) > 1:
                                pcol1, pcol2 = st.columns(2)
                                x_choice = pcol1.selectbox(
                                    "Group by (X-axis)", category_candidates,
                                    index=category_candidates.index(default_x),
                                    key=f"x_{id(entry)}",
                                )
                                y_choice = pcol2.selectbox(
                                    "Metric (Y-axis)", value_candidates,
                                    index=value_candidates.index(default_y),
                                    key=f"y_{id(entry)}",
                                )
                            else:
                                x_choice, y_choice = default_x, default_y

                            # Aggregate so repeated category values don't produce
                            # one bar per row (e.g. many orders per city).
                            chart_df = (
                                df.groupby(x_choice, as_index=False)[y_choice]
                                .sum(numeric_only=True)
                                .sort_values(y_choice, ascending=False)
                                .head(25)
                            )
                            st.bar_chart(data=chart_df, x=x_choice, y=y_choice)
                    else:
                        st.caption(
                            "No suitable columns for a chart in this result "
                            "(only identifiers/codes present)."
                        )

# ---------------------------------------------------------------------------
# Pending clarification input widget (rendered after the log, live at the bottom)
# ---------------------------------------------------------------------------
clar = st.session_state.pending_clarification

if clar and clar.get("clarification_type") == "date_range":
    with st.container():
        st.markdown("**Pick a date range to continue:**")
        col1, col2, col3 = st.columns([1, 1, 0.6])
        with col1:
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=30))
        with col2:
            end_date = st.date_input("End date", value=date.today())
        with col3:
            st.write("")
            st.write("")
            submit_dates = st.button("Submit", use_container_width=True)

        if submit_dates:
            if start_date > end_date:
                st.error("Start date must be before end date.")
            else:
                answer = f"Date range answer: Start date: {start_date}, End date: {end_date}"
                st.session_state.display_log.append({"role": "user", "text": f"📅 {start_date} → {end_date}"})
                with st.spinner("Analyzing..."):
                    ai_response = run_query(answer)
                handle_ai_response(answer, ai_response)
                st.rerun()

elif clar and clar.get("clarification_type") == "options":
    options = clar.get("options", [])
    if options:
        st.markdown("**Choose an interpretation to continue:**")
        cols = st.columns(len(options))
        for i, opt in enumerate(options):
            if cols[i].button(opt, key=f"clarify_opt_{i}", use_container_width=True):
                answer = f"Chosen interpretation: {opt}"
                st.session_state.display_log.append({"role": "user", "text": opt})
                with st.spinner("Analyzing..."):
                    ai_response = run_query(answer)
                handle_ai_response(answer, ai_response)
                st.rerun()

# ---------------------------------------------------------------------------
# New question input (disabled while a clarification is pending, to avoid
# the user accidentally starting a second, unrelated thread mid-clarification)
# ---------------------------------------------------------------------------
st.markdown("---")
input_disabled = clar is not None
if input_disabled:
    st.caption("Please resolve the question above before asking something new.")

user_query = st.chat_input(
    "e.g., What are the top 5 cities by revenue?",
    disabled=input_disabled,
)

if user_query:
    st.session_state.display_log.append({"role": "user", "text": user_query})
    with st.spinner("Analyzing..."):
        ai_response = run_query(user_query)
    handle_ai_response(user_query, ai_response)
    st.rerun()