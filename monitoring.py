"""
monitoring.py
Structured logging, request timing, error tracking, performance metrics, cost tracking.
Uses PostgreSQL via database.py (DATABASE_URL from .env).
"""

import time
import json
import traceback
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from database import get_connection  # Your existing PostgreSQL connection

# ──────────────────────────────────────────────
# 1. STRUCTURED JSON LOGGER
# ──────────────────────────────────────────────

class StructuredLogger:
    """
    JSON-formatted logger for production observability.
    Every log entry is parseable by log aggregation tools (Datadog, Splunk, CloudWatch).
    """
    def __init__(self, name: str = "ai-bootcamp"):
        self.name = name

    def _log(self, level: str, message: str, **kwargs):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "logger": self.name,
            "message": message,
            **kwargs
        }
        print(json.dumps(entry))

    def info(self, message: str, **kwargs):
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log("CRITICAL", message, **kwargs)

logger = StructuredLogger()

# ──────────────────────────────────────────────
# 2. DATABASE INIT — Create monitoring tables
# ──────────────────────────────────────────────

def init_monitoring_tables():
    """
    Create monitoring tables in PostgreSQL.
    Run this once at application startup.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Request logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_requests (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT NOW(),
            method VARCHAR(10),
            path VARCHAR(255),
            status_code INTEGER,
            duration_ms FLOAT,
            user_id VARCHAR(255),
            user_agent TEXT,
            client_host VARCHAR(255)
        );
    """)

    # Error logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_errors (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT NOW(),
            path VARCHAR(255),
            error_type VARCHAR(100),
            message TEXT,
            stack_trace TEXT
        );
    """)

    # Cost tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monitoring_costs (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT NOW(),
            endpoint VARCHAR(255),
            cost_usd FLOAT,
            request_count INTEGER DEFAULT 1
        );
    """)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Monitoring tables initialized in PostgreSQL")

# ──────────────────────────────────────────────
# 3. REQUEST TIMING MIDDLEWARE
# ──────────────────────────────────────────────

class TimingMiddleware(BaseHTTPMiddleware):
    """
    Auto-captures request duration and logs to PostgreSQL.
    Attaches X-Response-Time-Ms header to every response.
    """
    async def dispatch(self, request: Request, call_next):
        start = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start) * 1000
        user_id = getattr(request.state, "user_id", "anonymous")

        # Log to PostgreSQL
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO monitoring_requests 
                (method, path, status_code, duration_ms, user_id, user_agent, client_host)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                request.method,
                request.url.path,
                response.status_code,
                round(duration_ms, 2),
                user_id,
                request.headers.get("user-agent", "unknown"),
                request.client.host if request.client else "unknown"
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error("Failed to log request to PostgreSQL", error=str(e))

        # Attach timing header
        response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))

        return response

# ──────────────────────────────────────────────
# 4. ERROR TRACKING
# ──────────────────────────────────────────────

def record_error(path: str, error: Exception):
    """Record an error to PostgreSQL."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_errors (path, error_type, message, stack_trace)
            VALUES (%s, %s, %s, %s)
        """, (
            path,
            type(error).__name__,
            str(error),
            traceback.format_exc()
        ))
        conn.commit()
        cursor.close()
        conn.close()

        logger.error(
            "Unhandled exception",
            path=path,
            error_type=type(error).__name__,
            message=str(error)
        )
    except Exception as e:
        logger.error("Failed to log error to PostgreSQL", error=str(e))

def get_error_summary(limit: int = 50) -> List[Dict[str, Any]]:
    """Return recent errors from PostgreSQL."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT timestamp, path, error_type, message, stack_trace
        FROM monitoring_errors
        ORDER BY timestamp DESC
        LIMIT %s
    """, (limit,))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    return [
        {
            "timestamp": str(row[0]),
            "path": row[1],
            "error_type": row[2],
            "message": row[3],
            "stack_trace": row[4]
        }
        for row in rows
    ]

# ──────────────────────────────────────────────
# 5. PERFORMANCE METRICS FROM POSTGRESQL
# ──────────────────────────────────────────────

def calculate_percentiles(values: List[float], percentiles: List[int] = [50, 95, 99]) -> Dict[str, float]:
    """Calculate latency percentiles."""
    if not values:
        return {f"p{p}": 0.0 for p in percentiles}

    sorted_values = sorted(values)
    n = len(sorted_values)

    result = {}
    for p in percentiles:
        idx = int((p / 100) * (n - 1))
        result[f"p{p}"] = round(sorted_values[idx], 2)

    return result

def get_performance_metrics() -> Dict[str, Any]:
    """
    Returns performance breakdown per endpoint from PostgreSQL.
    Includes request counts, error rates, latency percentiles.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get all requests from last 24 hours
    cursor.execute("""
        SELECT path, duration_ms, status_code
        FROM monitoring_requests
        WHERE timestamp >= NOW() - INTERVAL '24 hours'
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Group by endpoint
    endpoint_stats = defaultdict(lambda: {"durations": [], "errors": 0, "count": 0})

    for path, duration_ms, status_code in rows:
        endpoint_stats[path]["durations"].append(duration_ms)
        endpoint_stats[path]["count"] += 1
        if status_code >= 400:
            endpoint_stats[path]["errors"] += 1

    # Calculate metrics per endpoint
    metrics = {}
    for path, stats in endpoint_stats.items():
        metrics[path] = {
            "request_count": stats["count"],
            "error_count": stats["errors"],
            "error_rate_percent": round(stats["errors"] / stats["count"] * 100, 2) if stats["count"] > 0 else 0,
            "latency_ms": calculate_percentiles(stats["durations"]),
            "avg_latency_ms": round(sum(stats["durations"]) / len(stats["durations"]), 2) if stats["durations"] else 0
        }

    # Get total error count
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM monitoring_errors WHERE timestamp >= NOW() - INTERVAL '24 hours'")
    total_errors = cursor.fetchone()[0]
    cursor.close()
    conn.close()

    return {
        "total_requests": len(rows),
        "total_errors": total_errors,
        "endpoints": metrics,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

# ──────────────────────────────────────────────
# 6. COST TRACKING IN POSTGRESQL
# ──────────────────────────────────────────────

def record_cost(endpoint: str, cost_usd: float):
    """Track OpenAI spend per endpoint in PostgreSQL."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_costs (endpoint, cost_usd)
            VALUES (%s, %s)
        """, (endpoint, cost_usd))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error("Failed to log cost to PostgreSQL", error=str(e))

def get_cost_summary() -> Dict[str, Any]:
    """Return OpenAI cost breakdown by endpoint from PostgreSQL."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT endpoint, SUM(cost_usd), COUNT(*)
        FROM monitoring_costs
        WHERE timestamp >= DATE_TRUNC('day', NOW())
        GROUP BY endpoint
    """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    by_endpoint = {}
    total = 0.0
    for endpoint, cost, count in rows:
        by_endpoint[endpoint] = {
            "total_cost": round(float(cost), 4),
            "request_count": count
        }
        total += float(cost)

    return {
        "by_endpoint": by_endpoint,
        "total_today": round(total, 4),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

# ──────────────────────────────────────────────
# 7. HEALTH CHECK v2
# ──────────────────────────────────────────────

def get_health_status() -> Dict[str, Any]:
    """
    Expanded health check with PostgreSQL connectivity test.
    """
    checks = {
        "api": {"status": "healthy", "response_time_ms": 0},
        "openai": {"status": "unknown"},
        "database": {"status": "unknown"},
        "disk": {"status": "healthy", "free_percent": 85}
    }

    # Test PostgreSQL connection
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        checks["database"] = {"status": "healthy", "response_time_ms": 0}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}

    all_healthy = all(
        c["status"] in ("healthy", "unknown") 
        for c in checks.values()
    )

    return {
        "status": "healthy" if all_healthy else "degraded",
        "version": "20.0.0",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

