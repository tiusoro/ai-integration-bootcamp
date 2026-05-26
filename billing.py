"""
billing.py
Stripe integration, subscription management, usage tracking, customer portal.
Uses PostgreSQL for subscription state and usage records.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

import stripe
from pydantic import BaseModel, Field
from fastapi import HTTPException, Header

from database import get_connection
from stripe_config import PLANS, check_feature_access, get_plan_features, calculate_overage

# Initialize Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# ──────────────────────────────────────────────
# 1. PYDANTIC MODELS
# ──────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan_id: str = Field(..., description="free, pro, or enterprise")
    billing_cycle: str = Field("monthly", description="monthly or yearly")

class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    plan_id: str

class SubscriptionStatus(BaseModel):
    plan_id: str
    status: str  # active, trialing, past_due, canceled
    current_period_start: str
    current_period_end: str
    cancel_at_period_end: bool

class UsageReport(BaseModel):
    user_id: str
    plan_id: str
    month: str
    chat_requests: int
    rag_queries: int
    agent_runs: int
    tokens_used: int
    overage_cost: float

# ──────────────────────────────────────────────
# 2. DATABASE INIT
# ──────────────────────────────────────────────

def init_billing_tables():
    """Create billing tables in PostgreSQL."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            stripe_customer_id VARCHAR(255),
            stripe_subscription_id VARCHAR(255),
            plan_id VARCHAR(50) DEFAULT 'free',
            status VARCHAR(50) DEFAULT 'active',
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            cancel_at_period_end BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_records (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL,
            feature VARCHAR(50) NOT NULL,
            quantity INT DEFAULT 1,
            cost_usd FLOAT DEFAULT 0,
            recorded_at TIMESTAMP DEFAULT NOW()
        );
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

# ──────────────────────────────────────────────
# 3. STRIPE CHECKOUT
# ──────────────────────────────────────────────

def create_checkout_session(user_id: str, plan_id: str, billing_cycle: str = "monthly") -> Dict[str, str]:
    """
    Create a Stripe Checkout session for subscription.
    Returns checkout URL and session ID.
    """
    if plan_id == "free":
        raise HTTPException(status_code=400, detail="Free plan doesn't require payment")
    
    plan = PLANS.get(plan_id)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid plan")
    
    if not plan.get("stripe_price_id"):
        raise HTTPException(status_code=500, detail="Stripe price not configured for this plan")
    
    # Get or create Stripe customer
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT stripe_customer_id FROM subscriptions WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    customer_id = result[0] if result else None
    
    if not customer_id:
        # Create new Stripe customer
        customer = stripe.Customer.create(
            metadata={"user_id": user_id}
        )
        customer_id = customer.id
    
    # Create checkout session
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{
            "price": plan["stripe_price_id"],
            "quantity": 1
        }],
        mode="subscription",
        success_url="https://your-domain.com/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://your-domain.com/cancel",
        subscription_data={
            "trial_period_days": 7 if plan_id == "pro" else 0
        }
    )
    
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "plan_id": plan_id
    }

# ──────────────────────────────────────────────
# 4. WEBHOOK HANDLER
# ──────────────────────────────────────────────

def handle_stripe_webhook(payload: bytes, signature: str) -> Dict[str, Any]:
    """
    Handle Stripe webhook events.
    Critical events: checkout.session.completed, invoice.paid, customer.subscription.deleted
    """
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    event_type = event["type"]
    data = event["data"]["object"]
    
    if event_type == "checkout.session.completed":
        _handle_checkout_completed(data)
    elif event_type == "invoice.paid":
        _handle_invoice_paid(data)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_cancelled(data)
    
    return {"status": "success", "event": event_type}

def _handle_checkout_completed(session: Dict[str, Any]):
    """Provision subscription after successful checkout."""
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    
    # Find user by customer ID
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM subscriptions WHERE stripe_customer_id = %s", (customer_id,))
    result = cursor.fetchone()
    
    if result:
        user_id = result[0]
        # Update subscription
        cursor.execute("""
            UPDATE subscriptions 
            SET stripe_subscription_id = %s, plan_id = %s, status = %s, updated_at = NOW()
            WHERE user_id = %s
        """, (subscription_id, "pro", "active", user_id))
        conn.commit()
    
    cursor.close()
    conn.close()

def _handle_invoice_paid(invoice: Dict[str, Any]):
    """Record successful payment."""
    # Could trigger email, update usage limits, etc.
    pass

def _handle_subscription_cancelled(subscription: Dict[str, Any]):
    """Downgrade to free plan on cancellation."""
    subscription_id = subscription.get("id")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE subscriptions 
        SET plan_id = %s, status = %s, cancel_at_period_end = FALSE, updated_at = NOW()
        WHERE stripe_subscription_id = %s
    """, ("free", "cancelled", subscription_id))
    conn.commit()
    cursor.close()
    conn.close()

# ──────────────────────────────────────────────
# 5. USAGE TRACKING
# ──────────────────────────────────────────────

def record_usage(user_id: str, feature: str, quantity: int = 1, cost: float = 0):
    """Record feature usage for billing."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO usage_records (user_id, feature, quantity, cost_usd)
        VALUES (%s, %s, %s, %s)
    """, (user_id, feature, quantity, cost))
    conn.commit()
    cursor.close()
    conn.close()

def get_monthly_usage(user_id: str, month: str = None) -> Dict[str, Any]:
    """Get usage report for a specific month."""
    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get plan
    cursor.execute("SELECT plan_id FROM subscriptions WHERE user_id = %s", (user_id,))
    plan_result = cursor.fetchone()
    plan_id = plan_result[0] if plan_result else "free"
    
    # Get usage by feature
    cursor.execute("""
        SELECT feature, SUM(quantity), SUM(cost_usd)
        FROM usage_records
        WHERE user_id = %s AND TO_CHAR(recorded_at, 'YYYY-MM') = %s
        GROUP BY feature
    """, (user_id, month))
    
    usage_rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    usage_by_feature = {row[0]: {"quantity": row[1], "cost": row[2]} for row in usage_rows}
    
    # Calculate overages
    total_overage = 0
    for feature, data in usage_by_feature.items():
        overage = calculate_overage(plan_id, feature, data["quantity"])
        total_overage += overage
    
    return {
        "user_id": user_id,
        "plan_id": plan_id,
        "month": month,
        "usage": usage_by_feature,
        "overage_cost": round(total_overage, 4),
        "total_cost": round(sum(d["cost"] for d in usage_by_feature.values()) + total_overage, 4)
    }

# ──────────────────────────────────────────────
# 6. CUSTOMER PORTAL
# ──────────────────────────────────────────────

def create_portal_session(user_id: str) -> str:
    """Create Stripe Customer Portal session for self-service billing."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT stripe_customer_id FROM subscriptions WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not result or not result[0]:
        raise HTTPException(status_code=400, detail="No Stripe customer found")
    
    session = stripe.billing_portal.Session.create(
        customer=result[0],
        return_url="https://your-domain.com/account"
    )
    
    return session.url

