import json
import sqlite3
import os
from groq import Groq


DB_PATH = "Sales_DW.db"
MODEL_NAME = "llama-3.1-8b-instant"
MAX_ROWS_IN_PROMPT = 20

try:
    import streamlit as st
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


client = Groq(api_key=GROQ_API_KEY)


# Runs a SQL query on the SQLite database.
# Returns the column names and result rows.
def run_query(query: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = cursor.fetchall()

    conn.close()
    return columns, rows


# Converts SQL result rows into readable text.
# Limits the number of rows sent to Groq.
def rows_to_text(columns, rows, max_rows=MAX_ROWS_IN_PROMPT) -> str:
    if not rows:
        return "The query returned no rows."

    lines = [
        f"The query returned {len(rows)} row(s).",
        "Columns: " + ", ".join(columns) + ".",
        "Result details:"
    ]

    for idx, row in enumerate(rows[:max_rows], start=1):
        row_text = ", ".join(f"{col} = {value}" for col, value in zip(columns, row))
        lines.append(f"Row {idx}: {row_text}.")

    if len(rows) > max_rows:
        lines.append(f"... and {len(rows) - max_rows} more row(s) not shown.")

    return "\n".join(lines)


# Sends a prompt to Groq and expects a JSON response.
# Returns summary, insight, and recommendation.
def call_groq_json(prompt: str) -> dict:
    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": """
You are a business data analyst.
Always return valid JSON only.
Use exactly these keys:
summary
insight
recommendation
Do not use markdown.
""".strip()
            },
            {"role": "user", "content": prompt}
        ]
    )

    content = response.choices[0].message.content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = {
            "summary": content,
            "insight": "",
            "recommendation": ""
        }

    return {
        "summary": str(data.get("summary", "")).strip(),
        "insight": str(data.get("insight", "")).strip(),
        "recommendation": str(data.get("recommendation", "")).strip()
    }


# Saves the generated AI insight into the database.
# Also creates the gpt_insights table if it does not exist.
def save_gpt_insight(
    operation: str,
    query_title: str,
    query_text: str,
    query_result_text: str,
    prompt: str,
    summary: str,
    insight: str,
    recommendation: str
):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gpt_insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation TEXT,
        query_title TEXT,
        query_text TEXT,
        query_result_text TEXT,
        prompt TEXT,
        summary TEXT,
        insight TEXT,
        recommendation TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    INSERT INTO gpt_insights (
        operation,
        query_title,
        query_text,
        query_result_text,
        prompt,
        summary,
        insight,
        recommendation
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        operation,
        query_title,
        query_text,
        query_result_text,
        prompt,
        summary,
        insight,
        recommendation
    ))

    conn.commit()
    conn.close()


# Describes the database schema for Groq.
# Used when converting a user question into SQL.
def get_schema_description() -> str:
    return """
Database: Sales Data Warehouse

Tables:

1) customer_dim
- CustomerID (INTEGER, PRIMARY KEY)
- FirstName (TEXT)
- LastName (TEXT)
- Email (TEXT)
- City (TEXT)
- Country (TEXT)

2) product_dim
- ProductID (INTEGER, PRIMARY KEY)
- ProductName (TEXT)
- Category (TEXT)
- Brand (TEXT)
- Supplier (TEXT)
- Price (REAL)

3) store_dim
- StoreID (INTEGER, PRIMARY KEY)
- StoreName (TEXT)
- Location (TEXT)
- ManagerName (TEXT)

4) date_dim
- DateID (INTEGER, PRIMARY KEY)
- Date (TEXT)
- Year (INTEGER)
- Quarter (INTEGER)
- Month (INTEGER)
- Day (INTEGER)

5) sales_fact
- SaleID (INTEGER, PRIMARY KEY)
- CustomerID (INTEGER, FOREIGN KEY -> customer_dim.CustomerID)
- ProductID (INTEGER, FOREIGN KEY -> product_dim.ProductID)
- StoreID (INTEGER, FOREIGN KEY -> store_dim.StoreID)
- DateID (INTEGER, FOREIGN KEY -> date_dim.DateID)
- Quantity (INTEGER)
- TotalSales (REAL)

Join relationships:
- sales_fact.CustomerID = customer_dim.CustomerID
- sales_fact.ProductID = product_dim.ProductID
- sales_fact.StoreID = store_dim.StoreID
- sales_fact.DateID = date_dim.DateID

Rules:
- Use SQLite SQL syntax only.
- Use only the tables and columns above.
- Return only one SQL query.
- Do not use markdown fences.
- Use the join relationships provided when data is needed from multiple tables.
- Use aggregation functions such as SUM, COUNT, AVG, MIN, and MAX when required by the question.
- Use GROUP BY when the question asks for summarized results.
"""


# Converts a natural-language question into SQL.
# Uses Groq and the database schema description.
def generate_sql_from_question(question: str) -> str:
    prompt = f"""
Schema:
{get_schema_description()}

User question:
{question}
""".strip()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are an expert SQLite SQL generator. Return only one valid SQL query. Do not use markdown."
            },
            {"role": "user", "content": prompt}
        ]
    )

    sql_query = response.choices[0].message.content.strip()
    return sql_query.replace("```sql", "").replace("```", "").strip()


# Analyzes SQL query results using Groq.
# Generates summary, insight, and recommendation.
def analyze_result(title: str, operation: str, columns, rows):
    result_text = rows_to_text(columns, rows)

    prompt = f"""
You are analyzing query results from a Sales Data Warehouse.

Query title: {title}
Operation: {operation}

{result_text}

Return valid JSON with exactly these keys:
{{
  "summary": "...",
  "insight": "...",
  "recommendation": "..."
}}

Requirements:
- Base your answer only on the provided data.
- Write a medium-length answer: not too short and not too detailed.
- Each field should be around 2 clear sentences.
- mention important values from the data when useful
- do not invent values not shown in the result
- avoid one-sentence or generic answers
- avoid long explanations
- All monetary values are in Saudi Riyal (SAR).
- Do NOT use the dollar symbol ($).
- Always refer to currency as SAR.
""".strip()

    insight_data = call_groq_json(prompt)
    return insight_data, prompt, result_text


OLAP_QUERIES = [
    {
        "operation": "Slice",
        "title": "Electronics sales by month",
        "query": """
        SELECT d.Month, ROUND(SUM(f.TotalSales), 2) AS TotalSales
        FROM sales_fact f
        JOIN date_dim d ON f.DateID = d.DateID
        JOIN product_dim p ON f.ProductID = p.ProductID
        WHERE p.Category = 'Electronics'
        GROUP BY d.Month
        ORDER BY d.Month;
        """
    },
    {
        "operation": "Dice",
        "title": "Electronics sales in Riyadh and Jeddah during Quarter 1 by product",
        "query": """
        SELECT p.ProductName, s.Location, ROUND(SUM(f.TotalSales), 2) AS TotalSales
        FROM sales_fact f
        JOIN product_dim p ON f.ProductID = p.ProductID
        JOIN store_dim s ON f.StoreID = s.StoreID
        JOIN date_dim d ON f.DateID = d.DateID
        WHERE p.Category = 'Electronics'
          AND s.Location IN ('Riyadh', 'Jeddah')
          AND d.Quarter = 1
        GROUP BY p.ProductName, s.Location
        ORDER BY TotalSales DESC;
        """
    },
    {
        "operation": "Roll-Up",
        "title": "Quarterly total sales",
        "query": """
        SELECT d.Quarter, ROUND(SUM(f.TotalSales), 2) AS TotalSales
        FROM sales_fact f
        JOIN date_dim d ON f.DateID = d.DateID
        GROUP BY d.Quarter
        ORDER BY d.Quarter;
        """
    },
    {
        "operation": "Drill-Down",
        "title": "Monthly total sales within each quarter",
        "query": """
        SELECT d.Quarter, d.Month, ROUND(SUM(f.TotalSales), 2) AS TotalSales
        FROM sales_fact f
        JOIN date_dim d ON f.DateID = d.DateID
        GROUP BY d.Quarter, d.Month
        ORDER BY d.Quarter, d.Month;
        """
    },
    {
        "operation": "SQL Analysis",
        "title": "Top 5 customers by total purchases",
        "query": """
        SELECT
            c.CustomerID,
            c.FirstName || ' ' || c.LastName AS CustomerName,
            ROUND(SUM(f.TotalSales), 2) AS TotalPurchases
        FROM sales_fact f
        JOIN customer_dim c ON f.CustomerID = c.CustomerID
        GROUP BY c.CustomerID, CustomerName
        ORDER BY TotalPurchases DESC
        LIMIT 5;
        """
    },
    {
        "operation": "SQL Analysis",
        "title": "Total sales by product category",
        "query": """
        SELECT
            p.Category,
            ROUND(SUM(f.TotalSales), 2) AS TotalSales
        FROM sales_fact f
        JOIN product_dim p ON f.ProductID = p.ProductID
        GROUP BY p.Category
        ORDER BY TotalSales DESC;
        """
    },
    {
        "operation": "SQL Analysis",
        "title": "Monthly revenue trend",
        "query": """
        SELECT
            d.Month,
            ROUND(SUM(f.TotalSales), 2) AS TotalSales
        FROM sales_fact f
        JOIN date_dim d ON f.DateID = d.DateID
        GROUP BY d.Month
        ORDER BY d.Month;
        """
    }
]


# Runs one predefined OLAP query.
# Generates and saves the AI insight for that result.
def process_predefined_query(query_info: dict):
    operation = query_info["operation"]
    title = query_info["title"]
    query = query_info["query"].strip()

    columns, rows = run_query(query)
    insight_data, prompt, result_text = analyze_result(title, operation, columns, rows)

    save_gpt_insight(
        operation=operation,
        query_title=title,
        query_text=query,
        query_result_text=result_text,
        prompt=prompt,
        summary=insight_data["summary"],
        insight=insight_data["insight"],
        recommendation=insight_data["recommendation"]
    )

    return {
        "operation": operation,
        "title": title,
        "sql_query": query,
        "columns": columns,
        "rows": rows,
        "query_result_text": result_text,
        "summary": insight_data["summary"],
        "insight": insight_data["insight"],
        "recommendation": insight_data["recommendation"]
    }


# Handles a user question from start to finish.
# Generates SQL, runs it, analyzes the result, and saves the insight.
def process_user_question(question: str):
    sql_query = generate_sql_from_question(question)
    columns, rows = run_query(sql_query)

    if not rows:
        result_text = rows_to_text(columns, rows)

        return {
            "question": question,
            "sql_query": sql_query,
            "columns": columns,
            "rows": rows,
            "query_result_text": result_text,
            "summary": "No data returned.",
            "insight": "",
            "recommendation": ""
        }

    insight_data, prompt, result_text = analyze_result(question, "NL_TO_SQL", columns, rows)

    save_gpt_insight(
        operation="NL_TO_SQL",
        query_title=question,
        query_text=sql_query,
        query_result_text=result_text,
        prompt=prompt,
        summary=insight_data["summary"],
        insight=insight_data["insight"],
        recommendation=insight_data["recommendation"]
    )

    return {
        "question": question,
        "sql_query": sql_query,
        "columns": columns,
        "rows": rows,
        "query_result_text": result_text,
        "summary": insight_data["summary"],
        "insight": insight_data["insight"],
        "recommendation": insight_data["recommendation"]
    }


# Returns the list of predefined OLAP queries.
# Used by the Streamlit app to display available queries.
def get_predefined_queries():
    return OLAP_QUERIES
