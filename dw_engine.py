import json
import sqlite3
from groq import Groq
import os


# =========================================================
# 1- CONFIG
# =========================================================
DB_PATH = "Sales_DW.db"
MODEL_NAME = "llama-3.1-8b-instant"
MAX_ROWS_IN_PROMPT = 20

try:
    import streamlit as st
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
client = Groq(api_key=GROQ_API_KEY)


# =========================================================
# 2- DATABASE HELPERS
# =========================================================

# Opens and returns a new connection to the SQLite database.
def get_connection():
    return sqlite3.connect(DB_PATH)


# Creates the table used to store generated AI insights.
# This lets the app save summaries, insights, and recommendations.
def create_gpt_insights_table():
    conn = get_connection()
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

    conn.commit()
    conn.close()


# Saves one generated insight record into the database.
# This stores the query, prompt, and model output for later use.
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
    conn = get_connection()
    cursor = conn.cursor()

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

# Runs any SQL query and returns the column names and rows.
# It is used for both predefined queries and generated queries.
def run_query(query: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(query)
    columns = [desc[0] for desc in cursor.description] if cursor.description else []
    rows = cursor.fetchall()

    conn.close()
    return columns, rows


# =========================================================
# 3- SCHEMA FOR NL -> SQL
# =========================================================

# Returns the database schema and general SQL rules as text.
# This is sent to Groq so it can generate valid SQLite queries.
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


# =========================================================
# 4- RESULT HELPERS
# =========================================================

# Converts query rows into readable text for the model.
# It limits the number of rows so the prompt stays smaller and cleaner.
def rows_to_text(columns, rows, max_rows=MAX_ROWS_IN_PROMPT) -> str:
    if not rows:
        return "The query returned no rows."

    lines = []
    lines.append(f"The query returned {len(rows)} row(s).")
    lines.append("Columns: " + ", ".join(columns) + ".")
    lines.append("Result details:")

    for idx, row in enumerate(rows[:max_rows], start=1):
        row_text = ", ".join(f"{col} = {value}" for col, value in zip(columns, row))
        lines.append(f"Row {idx}: {row_text}.")

    if len(rows) > max_rows:
        lines.append(f"... and {len(rows) - max_rows} more row(s) not shown.")

    return "\n".join(lines)


# Builds the analysis prompt for a query result.
# It asks the model to return summary, insight, and recommendation as JSON.
def build_analysis_prompt(title: str, operation: str, columns, rows):
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
- summary: short and clear
- insight: meaningful interpretation or pattern
- recommendation: one practical action
- do not invent values not shown
- keep the answer concise
"""
    return prompt.strip(), result_text


# =========================================================
# 5- GROQ HELPERS
# =========================================================

# Sends a prompt to Groq and parses the answer as JSON.
# If parsing fails, it returns a safe fallback result.
def call_groq_json(prompt: str) -> dict:
    system_message = """
You are a business data analyst.
Always return valid JSON only.
Use exactly these keys:
summary
insight
recommendation
Do not use markdown.
""".strip()

    response = client.chat.completions.create(
        model=MODEL_NAME,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_message},
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


# Converts a natural-language question into one SQL query.
# It uses the schema description so Groq knows the database structure.
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
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
    return sql_query


# Analyzes the query result using Groq and converts it into business insights.
# It generates a summary, key insight, and recommendation based only on the data.
def explain_result(question: str, columns, rows) -> dict:
    result_text = rows_to_text(columns, rows)

    prompt = f"""
The user asked:
{question}

The SQL query result is:
{result_text}

Return valid JSON with exactly these keys:
{{
  "summary": "...",
  "insight": "...",
  "recommendation": "..."
}}

Rules:
- Base your answer only on the result above.
- Do not invent facts.
- Keep the answer clear and concise.
- Do not use markdown.
""".strip()

    return call_groq_json(prompt)


# =========================================================
# 6- PREDEFINED QUERIES
# =========================================================
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


# =========================================================
# 7- MAIN LOGIC FUNCTIONS
# =========================================================

# Processes one predefined query from start to finish.
# It runs the SQL, generates the insight, saves it, and returns the final result.
def process_predefined_query(query_info: dict):
    operation = query_info["operation"]
    title = query_info["title"]
    query = query_info["query"].strip()

    columns, rows = run_query(query)
    prompt, result_text = build_analysis_prompt(title, operation, columns, rows)
    insight_data = call_groq_json(prompt)

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


# Processes a user question by generating SQL, running it, and explaining the result.
# It also saves the generated insight into the database table.
def process_user_question(question: str):
    create_gpt_insights_table()

    sql_query = generate_sql_from_question(question)
    columns, rows = run_query(sql_query)
    result_text = rows_to_text(columns, rows)

    if not rows:
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

    insight_data = explain_result(question, columns, rows)

    prompt_used = f"""
User question:
{question}

Generated SQL:
{sql_query}

Result:
{result_text}
""".strip()

    save_gpt_insight(
        operation="NL_TO_SQL",
        query_title=question,
        query_text=sql_query,
        query_result_text=result_text,
        prompt=prompt_used,
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
# This helps the Streamlit app display titles without duplicating the logic file.
def get_predefined_queries():
    return OLAP_QUERIES