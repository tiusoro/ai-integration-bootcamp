"""
rate_limiter.py
Token bucket rate limiting per user/API key.
Prevents abuse and protects OpenAI API costs.
"""

import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
from fastapi import HTTPException, status

# ──────────────────────────────────────────────
# 1. TOKEN BUCKET IMPLEMENTATION
# ──────────────────────────────────────────────

class TokenBucket:
    """
    Token bucket algorithm: allows burst traffic while limiting sustained rate.
    
    How it works:
    - Bucket starts full (e.g., 60 tokens)
    - Each request consumes 1 token
    - Tokens refill at constant rate (e.g., 1 per second)
    - If bucket is empty, request is rejected (429 Too Many Requests)
    
    This is fairer than fixed window — allows bursts but prevents abuse.
    """
    def __init__(self, capacity: int, refill_rate_per_second: float):
        self.capacity = capacity
        self.tokens = float(capacity)  # Start full
        self.refill_rate = refill_rate_per_second
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens. Returns True if allowed, False if rate limited.
        """
        now = time.time()
        elapsed = now - self.last_refill
        
        # Refill tokens based on time elapsed
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.refill_rate)
        )
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def remaining(self) -> int:
        """Return approximate remaining tokens."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))
        return int(tokens)

# ──────────────────────────────────────────────
# 2. IN-MEMORY RATE LIMIT STORE
# ──────────────────────────────────────────────

"""
CRITICAL: In-memory store resets on server restart.
In production, use Redis: redis-py with EXPIRE for automatic cleanup.
"""

_rate_limit_buckets: Dict[str, TokenBucket] = {}

def get_bucket_key(identifier: str, endpoint: Optional[str] = None) -> str:
    """
    Create a unique key for rate limiting.
    Format: user_id:endpoint or api_key_hash:endpoint
    """
    if endpoint:
        return f"{identifier}:{endpoint}"
    return identifier

def check_rate_limit(
    identifier: str,
    max_requests_per_minute: int = 60,
    endpoint: Optional[str] = None
) -> Tuple[bool, int, int]:
    """
    Check if request is within rate limit.
    Returns: (is_allowed, remaining_requests, retry_after_seconds)
    
    identifier = user_id or api_key_hash
    """
    key = get_bucket_key(identifier, endpoint)
    
    if key not in _rate_limit_buckets:
        # Create new bucket: capacity = max_requests, refill = max_requests/60 per second
        _rate_limit_buckets[key] = TokenBucket(
            capacity=max_requests_per_minute,
            refill_rate_per_second=max_requests_per_minute / 60.0
        )
    
    bucket = _rate_limit_buckets[key]
    allowed = bucket.consume(1)
    remaining = bucket.remaining()
    
    if not allowed:
        # Calculate retry after (time until 1 token is available)
        retry_after = int(60 / max_requests_per_minute) + 1
        return False, 0, retry_after
    
    return True, remaining, 0

def rate_limit_dependency(
    max_requests_per_minute: int = 60,
    endpoint: Optional[str] = None
):
    """
    FastAPI dependency factory for rate limiting.
    Usage: Depends(rate_limit_dependency(60, "chat"))
    
    Automatically extracts user ID from auth dependency.
    """
    from fastapi import Depends
    from auth import get_current_user
    
    async def _check_limit(user: Dict = Depends(get_current_user)):
        identifier = user.get("id", "anonymous")
        allowed, remaining, retry_after = check_rate_limit(
            identifier, max_requests_per_minute, endpoint
        )
        
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after), "X-RateLimit-Remaining": "0"}
            )
        
        # Add rate limit headers to response (FastAPI handles this via middleware or response)
        return {"user": user, "rate_limit_remaining": remaining}
    
    return _check_limit

# ──────────────────────────────────────────────
# 3. COST PROTECTION — Endpoint-Specific Limits
# ──────────────────────────────────────────────

ENDPOINT_COSTS = {
    "chat": 1,           # Standard chat
    "rag": 2,            # RAG with embedding search
    "database_query": 3,  # NL-to-SQL + execution
    "image": 5,          # Vision API
    "transcription": 4,   # Whisper audio
    "stream": 1,         # Streaming (same cost, different delivery)
}

def check_cost_budget(
    user_id: str,
    endpoint: str,
    monthly_budget: float = 50.0  # $50/month default
) -> bool:
    """
    Check if user has budget remaining for this endpoint.
    In production, track actual OpenAI costs per user in PostgreSQL.
    """
    cost = ENDPOINT_COSTS.get(endpoint, 1)
    # Mock: always allow for bootcamp (implement real tracking in production)
    return True


