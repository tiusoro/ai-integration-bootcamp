from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import re
import os
import openai
from dotenv import load_dotenv

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -- MOCK SAAS DATABASE SCHEMA --

DATABASE_SCHEMA = {
    "users": {
        "columns": ["id", "email", "name", "role", "created_at", "last_login", "subscription_tier"],
        "description": "User accounts and profiles"
    },
    "orders": {
        "columns": ["id", "user_id", "amount", "status", "created_at", "product_id"],
        "description": "Purchase orders and transactions"
    },
    "products": {
        "columns": ["id", "name", "category", "price", "created_at"],
        "description": "Product catalog"
    },
    "subscriptions": {
        "columns": ["id", "user_id", "plan", "status", "started_at", "ended_at", "mrr"],
        "description": "Subscription records and MRR"
    }
}

# -- MOCK DATA FOR QUERY EXECUTION --

MOCK_USERS = [
    {"id": 1, "email": "sarah@techcorp.com", "name": "Sarah Chen", "role": "admin", "created_at": "2026-01-15", "last_login": "2026-05-20", "subscription_tier": "enterprise"},
    {"id": 2, "email": "marcus@retailplus.io", "name": "Marcus Johnson", "role": "user", "created_at": "2026-02-10", "last_login": "2026-05-18", "subscription_tier": "pro"},
    {"id": 3, "email": "elena@healthfirst.org", "name": "Elena Rodriguez", "role": "user", "created_at": "2026-03-05", "last_login": "2026-05-22", "subscription_tier": "enterprise"},
    {"id": 4, "email": "john@startup.io", "name": "John Smith", "role": "user", "created_at": "2026-04-01", "last_login": "2026-05-15", "subscription_tier": "free"},
]

MOCK_ORDERS = [
    {"id": 101, "user_id": 1, "amount": 299.99, "status": "completed", "created_at": "2026-05-01", "product_id": "prod-001"},
    {"id": 102, "user_id": 1, "amount": 129.99, "status": "completed", "created_at": "2026-05-10", "product_id": "prod-002"},
    {"id": 103, "user_id": 2, "amount": 79.99, "status": "pending", "created_at": "2026-05-15", "product_id": "prod-004"},
    {"id": 104, "user_id": 3, "amount": 499.99, "status": "completed", "created_at": "2026-05-18", "product_id": "prod-005"},
    {"id": 105, "user_id": 2, "amount": 199.99, "status": "completed", "created_at": "2026-05-20", "product_id": "prod-001"},
]

MOCK_SUBSCRIPTIONS = [
    {"id": 501, "user_id": 1, "plan": "enterprise", "status": "active", "started_at": "2026-01-15", "ended_at": None, "mrr": 499.99},
    {"id": 502, "user_id": 2, "plan": "pro", "status": "active", "started_at": "2026-02-10", "ended_at": None, "mrr": 99.99},
    {"id": 503, "user_id": 3, "plan": "enterprise", "status": "active", "started_at": "2026-03-05", "ended_at": None, "mrr": 499.99},
    {"id": 504, "user_id": 4, "plan": "free", "status": "cancelled", "started_at": "2026-04-01", "ended_at": "2026-05-01", "mrr": 0.00},
]

# -- SQL GENERATION & VALIDATION --

class NLQueryRequest(BaseModel):
    question: str = Field(..., min_length=5, description="Natural language question about data")
    user_id: Optional[int] = Field(None, description="For permission filtering")
    user_role: Literal["admin", "user"] = "user"
    max_results: int = Field(100, ge=1, le=1000)

class NLQueryResponse(BaseModel):
    question: str
    generated_sql: str
    sql_safe: bool
    results: List[Dict]
    result_count: int
    execution_time_ms: float
    cost_usd: float
    warning: Optional[str] = None

def validate_sql(sql: str) -> tuple[bool, Optional[str]]:
    """Validate SQL for safety. Block destructive operations."""
    dangerous_keywords = ["DELETE ", "DROP ", "TRUNCATE ", "ALTER ", "INSERT ", "UPDATE ", "CREATE ", "EXEC ", "EXECUTE "]
    sql_upper = sql.upper()
    
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return False, f"Destructive operation detected: {keyword.strip()}"
    
    # Must be a SELECT query
    if not sql_upper.strip().startswith("SELECT"):
        return False, "Only SELECT queries are allowed"
    
    return True, None

def generate_sql(question: str, schema: Dict, user_role: str) -> str:
    """Generate SQL from natural language using GPT-4o-mini."""
    
    schema_text = "\n".join([
        f"Table: {table}\nColumns: {', '.join(info['columns'])}\nDescription: {info['description']}"
        for table, info in schema.items()
    ])
    
    system_prompt = f"""You are a SQL expert. Convert natural language questions to safe, read-only SQL queries.
    
DATABASE SCHEMA:
{schema_text}

RULES:
1. ONLY generate SELECT queries
2. NEVER use CREATE, DROP, ALTER, INSERT, UPDATE, DELETE, TRUNCATE
3. Use proper JOINs when needed
4. Add appropriate WHERE, GROUP BY, ORDER BY
5. Use date functions for time-based queries
6. For aggregations, use clear column aliases
7. If user_role is "user" (not "admin"), add WHERE user_id = current_user_id for user-owned tables
8. Return ONLY the SQL query, no markdown, no explanation"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Question: {question}\nUser role: {user_role}"}
        ],
        temperature=0.1,
        max_tokens=500
    )
    
    sql = response.choices[0].message.content.strip()
    # Remove markdown code blocks if present
    sql = sql.replace("```sql", "").replace("```", "").strip()
    
    return sql

def execute_mock_sql(sql: str, user_id: Optional[int], user_role: str) -> List[Dict]:
    """Execute SQL against mock data with permission filtering."""
    
    # Simple SQL parser for mock execution
    sql_lower = sql.lower()
    results = []
    
    # Determine which table
    if "from orders" in sql_lower:
        data = MOCK_ORDERS.copy()
        # Permission filter for non-admin users
        if user_role != "admin" and user_id:
            data = [row for row in data if row["user_id"] == user_id]
    elif "from users" in sql_lower:
        data = MOCK_USERS.copy()
        # Users can only see themselves
        if user_role != "admin" and user_id:
            data = [row for row in data if row["id"] == user_id]
    elif "from subscriptions" in sql_lower:
        data = MOCK_SUBSCRIPTIONS.copy()
        if user_role != "admin" and user_id:
            data = [row for row in data if row["user_id"] == user_id]
    else:
        data = []
    
    # Simple aggregation detection
    if "sum(" in sql_lower and "group by" in sql_lower:
        # Group by month simulation
        from collections import defaultdict
        grouped = defaultdict(float)
        for row in data:
            month = row["created_at"][:7] if "created_at" in row else "unknown"
            grouped[month] += row.get("amount", 0) or row.get("mrr", 0)
        results = [{"month": k, "total": round(v, 2)} for k, v in sorted(grouped.items())]
    elif "count(" in sql_lower:
        results = [{"count": len(data)}]
    elif "sum(" in sql_lower:
        total = sum(row.get("amount", 0) or row.get("mrr", 0) for row in data)
        results = [{"total": round(total, 2)}]
    else:
        results = data
    
    # Apply LIMIT if specified
    limit_match = re.search(r'limit\s+(\d+)', sql_lower)
    if limit_match:
        limit = int(limit_match.group(1))
        results = results[:limit]
    
    return results

# -- ADMIN DASHBOARD METRICS --

class DashboardMetrics(BaseModel):
    total_users: int
    active_users_7d: int
    total_revenue: float
    mrr: float
    churn_rate: float
    top_products: List[Dict]
    recent_signups: List[Dict]
    generated_at: str

def calculate_dashboard_metrics() -> DashboardMetrics:
    """Calculate admin dashboard metrics from mock data."""
    
    total_users = len(MOCK_USERS)
    active_users_7d = len([u for u in MOCK_USERS if u["last_login"] >= "2026-05-17"])
    
    total_revenue = sum(o["amount"] for o in MOCK_ORDERS if o["status"] == "completed")
    mrr = sum(s["mrr"] for s in MOCK_SUBSCRIPTIONS if s["status"] == "active")
    
    # Churn: cancelled subscriptions / total subscriptions
    total_subs = len(MOCK_SUBSCRIPTIONS)
    cancelled_subs = len([s for s in MOCK_SUBSCRIPTIONS if s["status"] == "cancelled"])
    churn_rate = round(cancelled_subs / total_subs * 100, 1) if total_subs > 0 else 0
    
    # Top products by revenue
    product_revenue = {}
    for order in MOCK_ORDERS:
        if order["status"] == "completed":
            pid = order["product_id"]
            product_revenue[pid] = product_revenue.get(pid, 0) + order["amount"]
    
    top_products = sorted(
        [{"product_id": k, "revenue": round(v, 2)} for k, v in product_revenue.items()],
        key=lambda x: x["revenue"],
        reverse=True
    )[:5]
    
    # Recent signups (last 30 days)
    recent_signups = [
        {"id": u["id"], "name": u["name"], "email": u["email"], "tier": u["subscription_tier"]}
        for u in MOCK_USERS
        if u["created_at"] >= "2026-04-24"
    ]
    
    return DashboardMetrics(
        total_users=total_users,
        active_users_7d=active_users_7d,
        total_revenue=round(total_revenue, 2),
        mrr=round(mrr, 2),
        churn_rate=churn_rate,
        top_products=top_products,
        recent_signups=recent_signups,
        generated_at=datetime.now().isoformat()
    )

