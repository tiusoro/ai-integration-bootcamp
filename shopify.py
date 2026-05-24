from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import os

# -- MOCK SHOPIFY DATABASE (would be real API calls in production) --

SHOPIFY_PRODUCTS = {
    "prod-001": {
        "id": "prod-001",
        "title": "Wireless Noise-Cancelling Headphones",
        "vendor": "SoundMax",
        "product_type": "electronics",
        "price": 299.99,
        "compare_at_price": 349.99,
        "inventory_quantity": 47,
        "tags": ["audio", "wireless", "premium"],
        "description": "Premium headphones with active noise cancellation.",
        "image_url": "https://example.com/headphones.jpg",
        "created_at": "2026-01-15"
    },
    "prod-002": {
        "id": "prod-002",
        "title": "Running Shoes - Ultra Boost",
        "vendor": "Nike",
        "product_type": "footwear",
        "price": 129.99,
        "compare_at_price": 159.99,
        "inventory_quantity": 23,
        "tags": ["running", "sports", "breathable"],
        "description": "Lightweight running shoes with responsive cushioning.",
        "image_url": "https://example.com/shoes.jpg",
        "created_at": "2026-02-20"
    },
    "prod-003": {
        "id": "prod-003",
        "title": "Moisture-Wicking Athletic Socks (3-Pack)",
        "vendor": "UnderArmour",
        "product_type": "apparel",
        "price": 19.99,
        "compare_at_price": 24.99,
        "inventory_quantity": 150,
        "tags": ["running", "socks", "moisture-wicking"],
        "description": "Keep your feet dry during long runs.",
        "image_url": "https://example.com/socks.jpg",
        "created_at": "2026-03-10"
    },
    "prod-004": {
        "id": "prod-004",
        "title": "Portable Bluetooth Speaker",
        "vendor": "JBL",
        "product_type": "electronics",
        "price": 79.99,
        "compare_at_price": 99.99,
        "inventory_quantity": 8,
        "tags": ["audio", "portable", "waterproof"],
        "description": "Waterproof speaker with 12-hour battery.",
        "image_url": "https://example.com/speaker.jpg",
        "created_at": "2026-01-20"
    },
    "prod-005": {
        "id": "prod-005",
        "title": "Yoga Mat - Premium Non-Slip",
        "vendor": "Liforme",
        "product_type": "fitness",
        "price": 89.99,
        "compare_at_price": 109.99,
        "inventory_quantity": 34,
        "tags": ["yoga", "fitness", "non-slip"],
        "description": "Eco-friendly yoga mat with alignment markers.",
        "image_url": "https://example.com/yoga.jpg",
        "created_at": "2026-02-15"
    }
}

SHOPIFY_ORDERS = {
    "order-1001": {
        "id": "order-1001",
        "customer_email": "sarah@example.com",
        "line_items": ["prod-001", "prod-003"],
        "total_price": 319.98,
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "tracking_number": "1Z999AA10123456784",
        "created_at": "2026-05-20",
        "shipping_address": {"city": "New York", "country": "US"}
    },
    "order-1002": {
        "id": "order-1002",
        "customer_email": "marcus@example.com",
        "line_items": ["prod-002"],
        "total_price": 129.99,
        "financial_status": "paid",
        "fulfillment_status": "unfulfilled",
        "tracking_number": None,
        "created_at": "2026-05-22",
        "shipping_address": {"city": "Los Angeles", "country": "US"}
    }
}

SHOPIFY_CARTS = {
    "cart-abc123": {
        "customer_email": "sarah@example.com",
        "items": [{"product_id": "prod-002", "quantity": 1}],
        "abandoned_at": "2026-05-24T10:00:00",
        "total": 129.99
    },
    "cart-def456": {
        "customer_email": "john@example.com",
        "items": [{"product_id": "prod-001", "quantity": 1}, {"product_id": "prod-004", "quantity": 1}],
        "abandoned_at": "2026-05-24T09:30:00",
        "total": 379.98
    }
}

# -- PRODUCT RECOMMENDATION ENGINE --

class ProductRecommendation(BaseModel):
    product_id: str
    title: str
    price: float
    reason: str
    inventory_status: str
    discount_available: bool

class RecommendationRequest(BaseModel):
    customer_email: str = Field(..., description="For purchase history lookup")
    current_product_id: Optional[str] = None
    category_preference: Optional[str] = None
    max_recommendations: int = Field(3, ge=1, le=10)

class RecommendationResponse(BaseModel):
    customer_email: str
    recommendations: List[ProductRecommendation]
    based_on: str
    total_value: float
    cost_usd: float

def get_product_complementary_products(product_id: str) -> List[str]:
    """Find products that complement the given product."""
    complements = {
        "prod-001": ["prod-004"],  # Headphones -> Speaker
        "prod-002": ["prod-003", "prod-005"],  # Shoes -> Socks, Yoga Mat
        "prod-003": ["prod-002"],  # Socks -> Shoes
        "prod-004": ["prod-001"],  # Speaker -> Headphones
        "prod-005": ["prod-002"]   # Yoga Mat -> Shoes
    }
    return complements.get(product_id, [])

def get_customer_purchase_history(customer_email: str) -> List[str]:
    """Get products customer has already bought."""
    purchased = []
    for order in SHOPIFY_ORDERS.values():
        if order["customer_email"] == customer_email:
            purchased.extend(order["line_items"])
    return list(set(purchased))

def generate_recommendations(request: RecommendationRequest) -> RecommendationResponse:
    """Generate personalized product recommendations."""
    recommendations = []
    based_on = "general popularity"
    
    # Strategy 1: Complementary to current product
    if request.current_product_id:
        complements = get_product_complementary_products(request.current_product_id)
        for comp_id in complements:
            product = SHOPIFY_PRODUCTS.get(comp_id)
            if product and product["inventory_quantity"] > 0:
                recommendations.append(ProductRecommendation(
                    product_id=comp_id,
                    title=product["title"],
                    price=product["price"],
                    reason=f"Goes well with {SHOPIFY_PRODUCTS[request.current_product_id]['title']}",
                    inventory_status="in_stock" if product["inventory_quantity"] > 10 else "low_stock",
                    discount_available=product["compare_at_price"] > product["price"]
                ))
        based_on = f"complementary to {SHOPIFY_PRODUCTS[request.current_product_id]['title']}"
    
    # Strategy 2: Based on purchase history
    purchased = get_customer_purchase_history(request.customer_email)
    if purchased and len(recommendations) < request.max_recommendations:
        for prod_id in purchased:
            complements = get_product_complementary_products(prod_id)
            for comp_id in complements:
                if comp_id not in purchased and comp_id not in [r.product_id for r in recommendations]:
                    product = SHOPIFY_PRODUCTS.get(comp_id)
                    if product and product["inventory_quantity"] > 0:
                        recommendations.append(ProductRecommendation(
                            product_id=comp_id,
                            title=product["title"],
                            price=product["price"],
                            reason="Based on your previous purchases",
                            inventory_status="in_stock",
                            discount_available=product["compare_at_price"] > product["price"]
                        ))
                        if len(recommendations) >= request.max_recommendations:
                            break
            if len(recommendations) >= request.max_recommendations:
                break
        based_on = "your purchase history"
    
    # Strategy 3: Fill with popular items
    while len(recommendations) < request.max_recommendations:
        for prod_id, product in SHOPIFY_PRODUCTS.items():
            if (prod_id not in [r.product_id for r in recommendations] and 
                prod_id not in purchased and 
                product["inventory_quantity"] > 0):
                recommendations.append(ProductRecommendation(
                    product_id=prod_id,
                    title=product["title"],
                    price=product["price"],
                    reason="Popular among customers like you",
                    inventory_status="in_stock",
                    discount_available=product["compare_at_price"] > product["price"]
                ))
                break
    
    # Limit to max
    recommendations = recommendations[:request.max_recommendations]
    
    total_value = sum(r.price for r in recommendations)
    
    return RecommendationResponse(
        customer_email=request.customer_email,
        recommendations=recommendations,
        based_on=based_on,
        total_value=round(total_value, 2),
        cost_usd=0.0  # No AI call for recommendations (rule-based)
    )

# -- ABANDONED CART RECOVERY --

class CartRecoveryRequest(BaseModel):
    cart_id: str = Field(..., min_length=1)
    tone: Literal["friendly", "urgent", "personal"] = "friendly"
    include_discount: bool = False
    discount_percent: int = Field(10, ge=5, le=50)

class CartRecoveryResponse(BaseModel):
    cart_id: str
    customer_email: str
    subject: str
    email_body: str
    urgency_score: int  # 1-10
    discount_code: Optional[str]
    estimated_recovery_value: float
    cost_usd: float

def generate_recovery_email(cart: Dict, tone: str, include_discount: bool, discount_percent: int) -> Dict:
    """Generate personalized abandoned cart recovery email."""
    
    tone_instructions = {
        "friendly": "Warm and helpful. Remind them gently. No pressure.",
        "urgent": "Create FOMO. Limited stock, time-sensitive offer.",
        "personal": "Reference specific items they left. Personal touch."
    }
    
    items_text = "\n".join([
        f"- {SHOPIFY_PRODUCTS[item['product_id']]['title']} (${SHOPIFY_PRODUCTS[item['product_id']]['price']})"
        for item in cart["items"]
        if item["product_id"] in SHOPIFY_PRODUCTS
    ])
    
    system_prompt = f"""You are an e-commerce email specialist.
Write an abandoned cart recovery email.
TONE: {tone_instructions[tone]}
RULES:
1. Reference the specific items they left
2. Mention low stock if applicable
3. {'Include discount code' if include_discount else 'No discount mentioned'}
4. Clear, single call-to-action: Complete Purchase
5. Keep under 150 words"""
    
    user_content = f"""Customer left these items in cart:
{items_text}

Total: ${cart['total']}

Cart abandoned: {cart['abandoned_at']}"""
    
    return {
        "system_prompt": system_prompt,
        "user_content": user_content,
        "items_text": items_text
    }

