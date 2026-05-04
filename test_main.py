import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# ── HEALTH CHECK ──

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "models_available" in data

# ── BASIC CHAT ──

def test_chat_message_too_long():
    response = client.post("/chat", json={
        "message": "x" * 2001
    })
    assert response.status_code == 422
    assert "max_length" in str(response.json()["detail"])
    

def test_chat_basic():
    response = client.post("/chat", json={"message": "Say 'test passed'"})
    assert response.status_code == 200
    data = response.json()
    assert "test passed" in data["answer"].lower()
    assert "usage" in data
    assert data["usage"]["prompt_tokens"] > 0

def test_chat_with_model_selection():
    response = client.post("/chat", json={
        "message": "Hello",
        "model": "gpt-4o-mini",
        "temperature": 0.5,
        "max_tokens": 50
    })
    assert response.status_code == 200
    assert response.json()["model_used"] == "gpt-4o-mini-2024-07-18"

# ── VALIDATION ──

def test_chat_empty_message():
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422

def test_chat_whitespace_only():
    response = client.post("/chat", json={"message": "   "})
    assert response.status_code == 422

def test_chat_temperature_too_high():
    response = client.post("/chat", json={"message": "Hello", "temperature": 5.0})
    assert response.status_code == 422

def test_chat_invalid_model():
    response = client.post("/chat", json={"message": "Hello", "model": "gpt-3"})
    assert response.status_code == 422

# ── PRICING ──

def test_pricing_endpoint():
    response = client.get("/pricing")
    assert response.status_code == 200
    data = response.json()
    assert "gpt-4o-mini" in data["models"]
    assert "input_per_1m_tokens" in data["models"]["gpt-4o-mini"]

# ── MEMORY ──

def test_memory_chat():
    # First message
    r1 = client.post("/chat/memory", json={
        "message": "My name is TestUser",
        "user_id": "test-user-1"
    })
    assert r1.status_code == 200
    session_id = r1.json()["session_id"]
    assert len(session_id) == 12  # MD5 hash length
    
    # Recall
    r2 = client.post("/chat/memory", json={
        "message": "What is my name?",
        "user_id": "test-user-1"
    })
    assert r2.status_code == 200
    assert "TestUser" in r2.json()["answer"]
    assert r2.json()["history_length"] == 4  # 2 turns = 4 messages

def test_memory_isolation():
    # User A establishes memory
    client.post("/chat/memory", json={
        "message": "My name is Alice",
        "user_id": "user-a"
    })
    
    # User B asks same question
    r = client.post("/chat/memory", json={
        "message": "What is my name?",
        "user_id": "user-b"
    })
    assert "Alice" not in r.json()["answer"]

def test_memory_clear():
    r1 = client.post("/chat/memory", json={
        "message": "Hello",
        "user_id": "clear-test"
    })
    session_id = r1.json()["session_id"]
    
    # Clear
    r2 = client.delete(f"/chat/memory/{session_id}")
    assert r2.status_code == 200
    assert r2.json()["status"] == "cleared"
    
    # Verify cleared
    r3 = client.get(f"/chat/memory/{session_id}")
    assert r3.json()["session_info"]["message_count"] == 0

def test_memory_clear_404():
    r = client.delete("/chat/memory/nonexistent")
    assert r.status_code == 404

# ── BUDGET ──

def test_budget_under_limit():
    response = client.post("/chat/budget", json={
        "message": "Hello",
        "user_id": "budget-test",
        "max_budget_usd": 0.01,
        "max_tokens": 50
    })
    assert response.status_code == 200
    assert response.json()["budget_check"]["under_budget"] is True

def test_budget_exceeded():
    response = client.post("/chat/budget", json={
        "message": "Write a long essay",
        "user_id": "budget-test",
        "max_budget_usd": 0.001,
        "max_tokens": 4000,
        "model": "gpt-4o"
    })
    assert response.status_code == 402

# ── REGISTER ──

def test_register_valid():
    response = client.post("/register", json={
        "email": "test@example.com",
        "tier": "pro"
    })
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"

def test_register_invalid_email():
    response = client.post("/register", json={
        "email": "not-an-email",
        "tier": "pro"
    })
    assert response.status_code == 422

def test_support_billing():
    response = client.post("/support", json={
        "message": "I was charged twice",
        "user_id": "support-test-1",
        "customer_tier": "pro"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "billing"
    assert data["priority"] == 4
    assert data["escalation_needed"] is True

def test_support_technical():
    response = client.post("/support", json={
        "message": "App crashes on login",
        "user_id": "support-test-2",
        "customer_tier": "free"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["classification"] == "technical"
    assert data["priority"] == 2

def test_support_enterprise_priority():
    response = client.post("/support", json={
        "message": "Need help now",
        "user_id": "support-test-3",
        "customer_tier": "enterprise"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["priority"] == 5
    assert data["cost_usd"] > 0

