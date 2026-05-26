"""
stripe_config.py
Subscription plans, feature gates, pricing tiers.
Central configuration for all billing logic.
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
# 1. PLAN DEFINITIONS
# ──────────────────────────────────────────────

PLANS = {
    "free": {
        "name": "Free",
        "description": "Get started with basic AI features",
        "price_monthly": 0,
        "price_yearly": 0,
        "currency": "usd",
        "features": {
            "chat_requests": 100,      # per month
            "rag_queries": 10,
            "agent_runs": 5,
            "api_keys": 0,
            "support": "community"
        },
        "stripe_price_id": None  # Free plan = no Stripe price
    },
    "pro": {
        "name": "Pro",
        "description": "For professionals and small teams",
        "price_monthly": 29,
        "price_yearly": 290,  # 2 months free
        "currency": "usd",
        "features": {
            "chat_requests": 1000,
            "rag_queries": 100,
            "agent_runs": 50,
            "api_keys": 3,
            "support": "email"
        },
        "stripe_price_id": "price_..."  # Replace with real Stripe Price ID
    },
    "enterprise": {
        "name": "Enterprise",
        "description": "Unlimited access for organizations",
        "price_monthly": 99,
        "price_yearly": 990,
        "currency": "usd",
        "features": {
            "chat_requests": -1,  # -1 = unlimited
            "rag_queries": -1,
            "agent_runs": -1,
            "api_keys": 10,
            "support": "priority"
        },
        "stripe_price_id": "price_..."  # Replace with real Stripe Price ID
    }
}

# ──────────────────────────────────────────────
# 2. FEATURE GATE CHECKER
# ──────────────────────────────────────────────

def check_feature_access(plan_id: str, feature: str, current_usage: int) -> Dict[str, Any]:
    """
    Check if user has access to a feature based on their plan and usage.
    Returns: {"allowed": bool, "limit": int, "remaining": int, "upgrade_required": bool}
    """
    plan = PLANS.get(plan_id, PLANS["free"])
    limit = plan["features"].get(feature, 0)
    
    # -1 = unlimited
    if limit == -1:
        return {
            "allowed": True,
            "limit": "unlimited",
            "remaining": "unlimited",
            "upgrade_required": False
        }
    
    remaining = max(0, limit - current_usage)
    allowed = current_usage < limit
    
    return {
        "allowed": allowed,
        "limit": limit,
        "remaining": remaining,
        "upgrade_required": not allowed
    }

def get_plan_features(plan_id: str) -> Dict[str, Any]:
    """Return all features for a plan."""
    plan = PLANS.get(plan_id, PLANS["free"])
    return {
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "features": plan["features"],
        "price_monthly": plan["price_monthly"],
        "price_yearly": plan["price_yearly"]
    }

# ──────────────────────────────────────────────
# 3. USAGE PRICING (Pay-as-you-go)
# ──────────────────────────────────────────────

OVERAGE_RATES = {
    "chat_request": 0.005,      # $0.005 per request over limit
    "rag_query": 0.02,          # $0.02 per RAG query over limit
    "agent_run": 0.10,          # $0.10 per agent run over limit
    "token": 0.0001             # $0.0001 per token (OpenAI cost + margin)
}

def calculate_overage(plan_id: str, feature: str, usage: int) -> float:
    """Calculate overage cost for exceeding plan limits."""
    plan = PLANS.get(plan_id, PLANS["free"])
    limit = plan["features"].get(feature, 0)
    
    if limit == -1 or limit == 0:
        return 0.0
    
    overage = max(0, usage - limit)
    rate = OVERAGE_RATES.get(feature, 0)
    
    return round(overage * rate, 4)

