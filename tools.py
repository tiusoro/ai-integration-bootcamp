from typing import Dict, List
from datetime import datetime

# Mock inventory database
INVENTORY = {
    "iphone-15": {"name": "iPhone 15", "stock": 47, "price": 799.00},
    "iphone-15-pro": {"name": "iPhone 15 Pro", "stock": 12, "price": 999.00},
    "macbook-air": {"name": "MacBook Air M3", "stock": 0, "price": 1099.00},
    "airpods-pro": {"name": "AirPods Pro 2", "stock": 150, "price": 249.00},
}

# Mock orders database
ORDERS = {
    "order-123": {
        "customer_id": "user-1",
        "items": ["iphone-15", "airpods-pro"],
        "total": 1048.00,
        "status": "shipped",
        "tracking": "1Z999AA10123456784",
        "date": "2026-04-15"
    },
    "order-456": {
        "customer_id": "user-2",
        "items": ["macbook-air"],
        "total": 1099.00,
        "status": "pending",
        "tracking": None,
        "date": "2026-05-01"
    }
}

def check_inventory(product_id: str) -> Dict:
    """Check if a product is in stock."""
    product = INVENTORY.get(product_id)
    if not product:
        return {"error": f"Product '{product_id}' not found"}
    
    return {
        "product": product["name"],
        "in_stock": product["stock"] > 0,
        "stock_count": product["stock"],
        "price": product["price"]
    }

def get_order_status(order_id: str) -> Dict:
    """Get the status of a customer order."""
    order = ORDERS.get(order_id)
    if not order:
        return {"error": f"Order '{order_id}' not found"}
    
    return {
        "order_id": order_id,
        "status": order["status"],
        "items": [INVENTORY[item]["name"] for item in order["items"] if item in INVENTORY],
        "total": order["total"],
        "tracking": order["tracking"],
        "date": order["date"]
    }

def list_products() -> List[Dict]:
    """List all available products."""
    return [
        {
            "id": pid,
            "name": p["name"],
            "price": p["price"],
            "in_stock": p["stock"] > 0
        }
        for pid, p in INVENTORY.items()
    ]

