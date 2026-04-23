import base64
import json
import pandas as pd
import streamlit as st
from dw_engine import (
    process_user_question,
    process_predefined_query,
    get_predefined_queries
)


# =========================================================
# 1- PAGE CONFIG
# =========================================================
st.set_page_config(page_title="Sales DW Assistant", layout="wide")


# =========================================================
# 2- CUSTOM STYLE
# =========================================================
st.markdown(
    """
    <style>
    .main {
        background-color: white;
    }

    h1, h2, h3 {
        color: #0F81BF;
    }

    .custom-subtitle {
        text-align: center;
        color: #444;
        font-size: 18px;
        margin-top: -8px;
        margin-bottom: 24px;
    }

    /* =========================
       ALL NORMAL BUTTONS
    ========================= */
    div.stButton > button {
        background-color: #0F81BF !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.65rem 1rem !important;
        font-weight: 600 !important;
    }

    div.stButton > button:hover {
        background-color: #0c6fa3 !important;
        color: white !important;
        border: none !important;
    }

    div.stButton > button:focus,
    div.stButton > button:focus-visible,
    div.stButton > button:active {
        background-color: #0F81BF !important;
        color: white !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
    }

    /* =========================
       DOWNLOAD BUTTONS
    ========================= */
    div.stDownloadButton > button {
        background-color: #0F81BF !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.65rem 1rem !important;
        font-weight: 600 !important;
    }

    div.stDownloadButton > button:hover {
        background-color: #0c6fa3 !important;
        color: white !important;
        border: none !important;
    }

    div.stDownloadButton > button:focus,
    div.stDownloadButton > button:focus-visible,
    div.stDownloadButton > button:active {
        background-color: #0F81BF !important;
        color: white !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
    }

    /* =========================
       REAL TABS STYLE
    ========================= */
    div[data-baseweb="tab-list"] {
        justify-content: center !important;
        border-bottom: 1px solid #ddd !important;
        gap: 0 !important;
    }

    button[data-baseweb="tab"] {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        min-width: 240px !important;
        padding: 10px 28px !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        text-align: center !important;
        color: #444 !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        position: relative !important;
    }

    button[data-baseweb="tab"] p {
        color: #444 !important;
        font-size: 16px !important;
        font-weight: 500 !important;
        text-align: center !important;
        width: 100% !important;
        margin: 0 !important;
    }

    /* only one separator between the two tabs */
    button[data-baseweb="tab"]:first-child::after {
        content: "|" !important;
        position: absolute !important;
        right: -2px !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
        color: #bdbdbd !important;
        font-weight: 400 !important;
        font-size: 24px !important;
        line-height: 1 !important;
        pointer-events: none !important;
    }

    button[data-baseweb="tab"]:last-child::after {
        content: "" !important;
    }

    button[data-baseweb="tab"]:hover {
        color: #0F81BF !important;
    }

    button[data-baseweb="tab"]:hover p {
        color: #0F81BF !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        color: #0F81BF !important;
        font-weight: 600 !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #0F81BF !important;
        font-weight: 600 !important;
    }

    button[data-baseweb="tab"]:focus,
    button[data-baseweb="tab"]:focus-visible,
    button[data-baseweb="tab"]:active {
        background: transparent !important;
        outline: none !important;
        box-shadow: none !important;
        color: #0F81BF !important;
    }

    button[data-baseweb="tab"]:focus p,
    button[data-baseweb="tab"]:focus-visible p,
    button[data-baseweb="tab"]:active p {
        color: #0F81BF !important;
    }

    /* force the active underline to blue only */
    div[data-baseweb="tab-highlight"] {
        background-color: #0F81BF !important;
        background: #0F81BF !important;
        height: 3px !important;
        border-radius: 3px 3px 0 0 !important;
    }

    /* remove any possible red border/line on tab containers */
    div[data-baseweb="tab-border"] {
        background-color: transparent !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# 3- HELPERS
# =========================================================

# Reads an image file and converts it to base64 so it can be shown in HTML.
# This is used to display the logo at the top of the page.
def get_base64_image(path):
    with open(path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()


# Converts SQL result columns and rows into a pandas DataFrame.
# This makes the result easier to display and download.
def result_to_dataframe(columns, rows):
    return pd.DataFrame(rows, columns=columns)


# Builds a JSON string from summary, insight, and recommendation.
# This is used by the insights download button.
def build_insights_json(result):
    return json.dumps(
        {
            "summary": result["summary"],
            "insight": result["insight"],
            "recommendation": result["recommendation"]
        },
        indent=2,
        ensure_ascii=False
    )


# Displays the output in a clean layout with downloads.
# It shows the question, SQL, result table, summary, insight, and recommendation.
def show_result(result, show_question=False):
    if show_question and "question" in result:
        st.subheader("User Question")
        st.write(result["question"])

    st.subheader("Generated SQL")
    st.code(result["sql_query"], language="sql")

    st.subheader("Query Result")
    df = result_to_dataframe(result["columns"], result["rows"])

    if df.empty:
        st.info("No data returned for this query.")
    else:
        st.dataframe(df, use_container_width=True)

    st.subheader("Summary")
    st.write(result["summary"] or "-")

    st.subheader("Insight")
    st.write(result["insight"] or "-")

    st.subheader("Recommendation")
    st.write(result["recommendation"] or "-")

    col1, col2 = st.columns(2)

    with col1:
        if not df.empty:
            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Result as CSV",
                data=csv_data,
                file_name="query_result.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"csv_{result.get('title', result.get('question', 'result'))}"
            )

    with col2:
        insights_json = build_insights_json(result)
        st.download_button(
            label="Download Insights as JSON",
            data=insights_json,
            file_name="insights.json",
            mime="application/json",
            use_container_width=True,
            key=f"json_{result.get('title', result.get('question', 'result'))}"
        )


# =========================================================
# 4- LOGO + TITLE
# =========================================================
logo_path = "logo.png"

try:
    logo_base64 = get_base64_image(logo_path)
    st.markdown(
        f"""
        <div style="text-align: center; margin-top: 10px;">
            <img src="data:image/png;base64,{logo_base64}" width="120">
        </div>
        """,
        unsafe_allow_html=True
    )
except Exception:
    pass

st.markdown(
    "<h1 style='text-align: center; color:#0F81BF;'>Sales Data Warehouse Assistant</h1>",
    unsafe_allow_html=True
)

st.markdown(
    "<p class='custom-subtitle'>Ask business questions in natural language or run predefined OLAP queries.</p>",
    unsafe_allow_html=True
)


# =========================================================
# 5- TABS
# =========================================================
tab1, tab2 = st.tabs(["💬 Custom Question", "📊 Predefined Queries"])


# =========================================================
# 6- TAB 1
# =========================================================
with tab1:
    st.subheader("Ask a Custom Question")

    user_question = st.text_input(
        "Enter your business question",
        placeholder="Example: Show the total sales by month"
    )

    if st.button("Run Custom Question", use_container_width=True):
        if not user_question.strip():
            st.warning("Please enter a question.")
        else:
            try:
                result = process_user_question(user_question.strip())
                show_result(result, show_question=True)
            except Exception as e:
                st.error(f"Error: {str(e)}")


# =========================================================
# 7- TAB 2
# =========================================================
with tab2:
    st.subheader("Run a Predefined OLAP Query")

    queries = get_predefined_queries()
    titles = [q["title"] for q in queries]

    selected = st.selectbox("Choose query", titles)

    if st.button("Run Predefined Query", use_container_width=True):
        try:
            query = next(q for q in queries if q["title"] == selected)
            result = process_predefined_query(query)
            show_result(result)
        except Exception as e:
            st.error(f"Error: {str(e)}")