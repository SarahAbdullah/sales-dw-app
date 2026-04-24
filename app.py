import base64
import csv
import io
import pandas as pd
import streamlit as st

from dw_engine import (
    process_user_question,
    process_predefined_query,
    get_predefined_queries
)


st.set_page_config(page_title="Sales DW Assistant", layout="wide")


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

    div.stButton > button,
    div.stDownloadButton > button {
        background-color: #0F81BF !important;
        color: white !important;
        border: none !important;
        border-radius: 10px !important;
        padding: 0.65rem 1rem !important;
        font-weight: 600 !important;
    }

    div.stButton > button:hover,
    div.stDownloadButton > button:hover {
        background-color: #0c6fa3 !important;
        color: white !important;
        border: none !important;
    }

    div.stButton > button:focus,
    div.stButton > button:focus-visible,
    div.stButton > button:active,
    div.stDownloadButton > button:focus,
    div.stDownloadButton > button:focus-visible,
    div.stDownloadButton > button:active {
        background-color: #0F81BF !important;
        color: white !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
    }

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

    button[data-baseweb="tab"]:hover,
    button[data-baseweb="tab"]:hover p,
    button[data-baseweb="tab"][aria-selected="true"],
    button[data-baseweb="tab"][aria-selected="true"] p {
        color: #0F81BF !important;
        font-weight: 600 !important;
    }

    div[data-baseweb="tab-highlight"] {
        background-color: #0F81BF !important;
        height: 3px !important;
        border-radius: 3px 3px 0 0 !important;
    }

    div[data-baseweb="tab-border"] {
        background-color: transparent !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# Reads the logo image and converts it to base64.
# This allows the image to be displayed using HTML.
def get_base64_image(path):
    with open(path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()


# Converts query columns and rows into a Pandas DataFrame.
# This is used to display the SQL result in Streamlit.
def result_to_dataframe(columns, rows):
    return pd.DataFrame(rows, columns=columns)


# Builds one CSV file that contains the query information,
# query result, summary, insight, and recommendation.
def build_combined_csv(result):
    lines = []

    lines.append(["Query Info"])
    lines.append(["Title", result.get("title", "")])

    if result.get("question", ""):
        lines.append(["Question", result.get("question", "")])

    lines.append(["SQL Query", result.get("sql_query", "")])
    lines.append(["Currency Note", "All monetary values are in Saudi Riyal (SAR)."])
    lines.append([])

    lines.append(["Query Result"])

    if result["columns"] and result["rows"]:
        lines.append(result["columns"])

        for row in result["rows"]:
            lines.append(list(row))
    else:
        lines.append(["No data returned"])

    lines.append([])

    lines.append(["Generated Insights"])
    lines.append(["Summary", result.get("summary", "")])
    lines.append(["Insight", result.get("insight", "")])
    lines.append(["Recommendation", result.get("recommendation", "")])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(lines)

    return output.getvalue().encode("utf-8-sig")


# Displays the SQL query, result table, and generated insights.
# Also provides one CSV download containing both result and insights.
def show_result(result, show_question=False):
    if show_question and "question" in result:
        st.subheader("User Question")
        st.write(result["question"])

    st.subheader("Generated SQL")
    st.code(result["sql_query"], language="sql")

    st.subheader("Query Result")
    st.caption("All monetary values are in Saudi Riyal (SAR).")

    df = result_to_dataframe(result["columns"], result["rows"])

    if df.empty:
        st.info("No data returned for this query.")
    else:
        st.dataframe(df, use_container_width=True)

    st.subheader("Generated Insights")

    st.markdown("**Summary**")
    st.write(result.get("summary", "") or "-")

    st.markdown("**Insight**")
    st.write(result.get("insight", "") or "-")

    st.markdown("**Recommendation**")
    st.write(result.get("recommendation", "") or "-")

    csv_data = build_combined_csv(result)

    file_name = result.get("title", result.get("question", "result"))
    file_name = file_name.lower().replace(" ", "_").replace("/", "_")

    st.download_button(
        label="Download Result and Insights as CSV",
        data=csv_data,
        file_name=f"{file_name}_result_and_insights.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"combined_{file_name}"
    )


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


tab1, tab2 = st.tabs(["💬 Custom Question", "📊 Predefined Queries"])


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
