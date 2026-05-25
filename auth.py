"""
auth.py
Authentication & Authorization Engine for FastAPI.
JWT tokens, bcrypt password hashing, role-based access control, API key management.
Works with Day 18 analytics.py (mock data, no PostgreSQL required).
"""

import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from functools import wraps

import jwt
import bcrypt
from pydantic import BaseModel, Field, validator
from fastapi import HTTPException, Header, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

# Load .env BEFORE reading JWT_SECRET
load_dotenv()

# ──────────────────────────────────────────────
# 1. CONFIGURATION
# ──────────────────────────────────────────────

JWT_SECRET = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
API_KEY_PREFIX = "ak_"

# ──────────────────────────────────────────────
# 2. PYDANTIC MODELS
# ──────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=2)
    role: str = Field("user")

    @validator('role')
    def valid_role(cls, v):
        allowed = {"user", "admin", "read_only"}
        if v not in allowed:
            raise ValueError(f"Role must be one of: {allowed}")
        return v

    @validator('email')
    def valid_email(cls, v):
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email format")
        return v.lower()

class UserLoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class UserProfile(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str
    api_key_count: int

class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    rate_limit_per_minute: int = Field(60, ge=10, le=1000)

class APIKeyResponse(BaseModel):
    key_id: str
    name: str
    api_key: str
    prefix: str
    created_at: str
    rate_limit_per_minute: int
    is_active: bool

class APIKeyListItem(BaseModel):
    key_id: str
    name: str
    prefix: str
    created_at: str
    last_used: Optional[str]
    rate_limit_per_minute: int
    is_active: bool

# ──────────────────────────────────────────────
# 3. IN-MEMORY STORES (replace with PostgreSQL in production)
# ──────────────────────────────────────────────

MOCK_USERS: Dict[str, Dict[str, Any]] = {}
MOCK_API_KEYS: Dict[str, Dict[str, Any]] = {}

# ──────────────────────────────────────────────
# 4. PASSWORD HASHING
# ──────────────────────────────────────────────

def _hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def _verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )

def _generate_uuid() -> str:
    return str(uuid.uuid4())

def _generate_api_key() -> str:
    random_part = secrets.token_urlsafe(24)
    return f"{API_KEY_PREFIX}{random_part}"

def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()

# ──────────────────────────────────────────────
# 5. JWT ENGINE
# ──────────────────────────────────────────────

def create_access_token(user_id: str, email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=JWT_EXPIRATION_HOURS)

    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": _generate_uuid()
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token

def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

# ──────────────────────────────────────────────
# 6. FASTAPI DEPENDENCIES
# ──────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = credentials.credentials
    payload = decode_token(token)

    user_id = payload.get("sub")
    if user_id not in MOCK_USERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found. Token may be invalid."
        )

    return {
        "id": user_id,
        "email": payload.get("email"),
        "role": payload.get("role"),
        "token_payload": payload
    }

async def get_current_user_from_api_key(
    x_api_key: str = Header(None, alias="X-API-Key")
) -> Dict[str, Any]:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Provide X-API-Key header."
        )

    key_hash = _hash_api_key(x_api_key)
    key_data = MOCK_API_KEYS.get(key_hash)

    if not key_data or not key_data.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key."
        )

    key_data["last_used"] = datetime.now(timezone.utc).isoformat()

    user_id = key_data["user_id"]
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with API key not found."
        )

    return {
        "id": user_id,
        "email": user["email"],
        "role": user["role"],
        "api_key_id": key_data["id"],
        "rate_limit": key_data["rate_limit_per_minute"]
    }

async def get_current_user_or_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_api_key: str = Header(None, alias="X-API-Key")
) -> Dict[str, Any]:
    """Try JWT first, fall back to API key."""
    if credentials:
        try:
            return await get_current_user(credentials)
        except HTTPException:
            pass

    if x_api_key:
        try:
            return await get_current_user_from_api_key(x_api_key)
        except HTTPException:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"}
    )

# ──────────────────────────────────────────────
# 7. ROLE-BASED ACCESS CONTROL
# ──────────────────────────────────────────────

def require_role(allowed_roles: List[str]):
    async def role_checker(
        user: Dict[str, Any] = Depends(get_current_user_or_api_key)
    ) -> Dict[str, Any]:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {allowed_roles}. Your role: {user['role']}."
            )
        return user
    return role_checker

require_admin = require_role(["admin"])
require_admin_or_user = require_role(["admin", "user"])
require_any_role = require_role(["admin", "user", "read_only"])

# ──────────────────────────────────────────────
# 8. API KEY MANAGEMENT
# ──────────────────────────────────────────────

def create_api_key(user_id: str, name: str, rate_limit: int = 60) -> APIKeyResponse:
    api_key = _generate_api_key()
    key_hash = _hash_api_key(api_key)
    key_id = _generate_uuid()
    prefix = api_key[:8]
    now = datetime.now(timezone.utc).isoformat()

    MOCK_API_KEYS[key_hash] = {
        "id": key_id,
        "user_id": user_id,
        "name": name,
        "key_hash": key_hash,
        "prefix": prefix,
        "created_at": now,
        "last_used": None,
        "rate_limit_per_minute": rate_limit,
        "is_active": True
    }

    return APIKeyResponse(
        key_id=key_id,
        name=name,
        api_key=api_key,
        prefix=prefix,
        created_at=now,
        rate_limit_per_minute=rate_limit,
        is_active=True
    )

def list_api_keys(user_id: str, is_admin: bool = False) -> List[APIKeyListItem]:
    keys = []
    for key_data in MOCK_API_KEYS.values():
        if not is_admin and key_data["user_id"] != user_id:
            continue
        keys.append(APIKeyListItem(
            key_id=key_data["id"],
            name=key_data["name"],
            prefix=key_data["prefix"],
            created_at=key_data["created_at"],
            last_used=key_data.get("last_used"),
            rate_limit_per_minute=key_data["rate_limit_per_minute"],
            is_active=key_data["is_active"]
        ))
    return keys

def revoke_api_key(key_id: str, user_id: str, is_admin: bool = False) -> bool:
    for key_hash, key_data in MOCK_API_KEYS.items():
        if key_data["id"] == key_id:
            if not is_admin and key_data["user_id"] != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only revoke your own API keys."
                )
            key_data["is_active"] = False
            return True

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="API key not found."
    )

# ──────────────────────────────────────────────
# 9. USER REGISTRATION & AUTHENTICATION
# ──────────────────────────────────────────────

def register_user(request: UserRegisterRequest) -> Dict[str, Any]:
    for user in MOCK_USERS.values():
        if user["email"] == request.email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered."
            )

    user_id = _generate_uuid()
    now = datetime.now(timezone.utc).isoformat()

    MOCK_USERS[user_id] = {
        "id": user_id,
        "email": request.email,
        "password_hash": _hash_password(request.password),
        "name": request.name,
        "role": request.role,
        "created_at": now
    }

    return {
        "id": user_id,
        "email": request.email,
        "name": request.name,
        "role": request.role,
        "created_at": now
    }

def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    for user in MOCK_USERS.values():
        if user["email"] == email:
            if _verify_password(password, user["password_hash"]):
                return {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user["name"],
                    "role": user["role"],
                    "created_at": user["created_at"]
                }
            break

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password."
    )

def get_user_profile(user_id: str) -> UserProfile:
    user = MOCK_USERS.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    api_count = sum(
        1 for k in MOCK_API_KEYS.values()
        if k["user_id"] == user_id and k["is_active"]
    )

    return UserProfile(
        id=user_id,
        email=user["email"],
        name=user["name"],
        role=user["role"],
        created_at=user["created_at"],
        api_key_count=api_count
    )

