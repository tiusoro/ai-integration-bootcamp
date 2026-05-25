"""
tenant.py
Multi-Tenant Architecture Engine for FastAPI + PostgreSQL.
Tenant identification, row-level security, tenant-aware queries, tenant management.
Uses PostgreSQL via database.py (DATABASE_URL from .env).
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from functools import wraps

from pydantic import BaseModel, Field, validator
from fastapi import HTTPException, Header, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import get_connection  # Your existing PostgreSQL connection
from auth import get_current_user_or_api_key  # Reuse combined auth from Day 19

# ──────────────────────────────────────────────
# 1. PYDANTIC MODELS
# ──────────────────────────────────────────────

class TenantCreateRequest(BaseModel):
    """Create a new tenant (organization/workspace)."""
    name: str = Field(..., min_length=2, max_length=100, description="Tenant/company name")
    slug: str = Field(..., min_length=2, max_length=50, description="URL-friendly identifier")
    plan: str = Field("free", description="free, pro, enterprise")
    
    @validator('slug')
    def valid_slug(cls, v):
        if not v.isalnum() and '-' not in v:
            raise ValueError("Slug must be alphanumeric with hyphens only")
        return v.lower()
    
    @validator('plan')
    def valid_plan(cls, v):
        allowed = {"free", "pro", "enterprise"}
        if v not in allowed:
            raise ValueError(f"Plan must be one of: {allowed}")
        return v

class TenantResponse(BaseModel):
    """Tenant data returned to clients."""
    id: str
    name: str
    slug: str
    plan: str
    created_at: str
    user_count: int
    is_active: bool

class TenantUserAssignRequest(BaseModel):
    """Assign a user to a tenant with a specific role."""
    user_id: str
    role: str = Field("member", description="admin, member, viewer")

class TenantSwitchRequest(BaseModel):
    """Switch current user to a different tenant."""
    tenant_id: str

# ──────────────────────────────────────────────
# 2. TENANT DATABASE TABLES
# ──────────────────────────────────────────────

def init_tenant_tables():
    """
    Create tenant tables in PostgreSQL.
    Run once at application startup.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tenants table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(50) UNIQUE NOT NULL,
            plan VARCHAR(20) DEFAULT 'free',
            created_at TIMESTAMP DEFAULT NOW(),
            is_active BOOLEAN DEFAULT TRUE,
            settings JSONB DEFAULT '{}'
        );
    """)
    
    # Tenant-user memberships (many-to-many)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
            user_id VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(tenant_id, user_id)
        );
    """)
    
    # Add tenant_id to existing tables for RLS
    # These are ALTER statements — safe to run multiple times
    tables_to_alter = [
        "monitoring_requests",
        "monitoring_errors", 
        "monitoring_costs"
    ]
    
    for table in tables_to_alter:
        try:
            cursor.execute(f"""
                ALTER TABLE {table} 
                ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
            """)
        except Exception:
            pass  # Column might already exist or table might not exist
    
    conn.commit()
    cursor.close()
    conn.close()
    
    # Create RLS policies
    _create_rls_policies()

def _create_rls_policies():
    """Create Row-Level Security policies for tenant isolation."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Enable RLS on tables
    for table in ["monitoring_requests", "monitoring_errors", "monitoring_costs"]:
        try:
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
            
            # Drop existing policy if exists (idempotent)
            cursor.execute(f"""
                DROP POLICY IF EXISTS tenant_isolation_policy ON {table};
            """)
            
            # Create policy: users only see their tenant's data
            cursor.execute(f"""
                CREATE POLICY tenant_isolation_policy ON {table}
                FOR ALL
                USING (tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID);
            """)
        except Exception as e:
            print(f"RLS setup note for {table}: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()

# ──────────────────────────────────────────────
# 3. TENANT MIDDLEWARE
# ──────────────────────────────────────────────

async def get_current_tenant(
    request: Request,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
) -> Dict[str, Any]:
    """
    Extract tenant from:
    1. X-Tenant-ID header (explicit)
    2. User's JWT token (tenant_id claim)
    3. User's primary tenant (first tenant in membership)
    
    Attaches tenant info to request.state for downstream use.
    """
    tenant_id = None
    
    # Priority 1: Explicit header
    if x_tenant_id:
        tenant_id = x_tenant_id
    
    # Priority 2: JWT claim
    elif user.get("token_payload", {}).get("tenant_id"):
        tenant_id = user["token_payload"]["tenant_id"]
    
    # Priority 3: User's primary tenant from database
    else:
        tenant_id = _get_user_primary_tenant(user["id"])
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant specified. Provide X-Tenant-ID header or join a tenant."
        )
    
    # Validate tenant exists and user is member
    tenant = _get_tenant_with_membership(tenant_id, user["id"])
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this tenant."
        )
    
    # Attach to request state for middleware
    request.state.tenant_id = tenant_id
    request.state.user_id = user["id"]
    
    return tenant

def _get_user_primary_tenant(user_id: str) -> Optional[str]:
    """Get user's first/primary tenant from database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT tenant_id FROM tenant_users 
        WHERE user_id = %s 
        ORDER BY joined_at ASC 
        LIMIT 1
    """, (user_id,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return str(result[0]) if result else None

def _get_tenant_with_membership(tenant_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Verify tenant exists and user is a member."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.id, t.name, t.slug, t.plan, t.created_at, t.is_active, tu.role
        FROM tenants t
        JOIN tenant_users tu ON t.id = tu.tenant_id
        WHERE t.id = %s AND tu.user_id = %s AND t.is_active = TRUE
    """, (tenant_id, user_id))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not result:
        return None
    
    return {
        "id": str(result[0]),
        "name": result[1],
        "slug": result[2],
        "plan": result[3],
        "created_at": str(result[4]),
        "is_active": result[5],
        "user_role": result[6]
    }

# ──────────────────────────────────────────────
# 4. TENANT-AWARE QUERY WRAPPER
# ──────────────────────────────────────────────

def set_tenant_context(tenant_id: str):
    """
    Set PostgreSQL session variable for RLS.
    Must be called before every tenant-aware query.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SET app.current_tenant_id = %s;", (tenant_id,))
    except Exception:
        # Fallback: some PostgreSQL versions don't support custom settings
        pass
    
    cursor.close()
    conn.close()

def execute_tenant_query(sql: str, params: tuple = (), tenant_id: str = None):
    """
    Execute SQL with tenant context set for RLS.
    """
    if tenant_id:
        set_tenant_context(tenant_id)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    
    # For SELECT queries
    if sql.strip().upper().startswith("SELECT"):
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return results
    
    # For INSERT/UPDATE/DELETE
    conn.commit()
    cursor.close()
    conn.close()
    return None

# ──────────────────────────────────────────────
# 5. TENANT MANAGEMENT
# ──────────────────────────────────────────────

def create_tenant(request: TenantCreateRequest, creator_user_id: str) -> Dict[str, Any]:
    """Create new tenant and assign creator as admin."""
    conn = get_connection()
    cursor = conn.cursor()
    
    tenant_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Insert tenant
    cursor.execute("""
        INSERT INTO tenants (id, name, slug, plan, created_at, is_active)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id;
    """, (tenant_id, request.name, request.slug, request.plan, now, True))
    
    # Assign creator as admin
    cursor.execute("""
        INSERT INTO tenant_users (tenant_id, user_id, role, joined_at)
        VALUES (%s, %s, %s, %s);
    """, (tenant_id, creator_user_id, "admin", now))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        "id": tenant_id,
        "name": request.name,
        "slug": request.slug,
        "plan": request.plan,
        "created_at": now,
        "is_active": True,
        "user_role": "admin"
    }

def list_tenants(user_id: str, is_admin: bool = False) -> List[Dict[str, Any]]:
    """List tenants user belongs to. Admins see all."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if is_admin:
        cursor.execute("""
            SELECT id, name, slug, plan, created_at, is_active,
                   (SELECT COUNT(*) FROM tenant_users WHERE tenant_id = t.id) as user_count
            FROM tenants t
            WHERE is_active = TRUE
            ORDER BY created_at DESC;
        """)
    else:
        cursor.execute("""
            SELECT t.id, t.name, t.slug, t.plan, t.created_at, t.is_active,
                   (SELECT COUNT(*) FROM tenant_users WHERE tenant_id = t.id) as user_count
            FROM tenants t
            JOIN tenant_users tu ON t.id = tu.tenant_id
            WHERE tu.user_id = %s AND t.is_active = TRUE
            ORDER BY t.created_at DESC;
        """, (user_id,))
    
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return [
        {
            "id": str(row[0]),
            "name": row[1],
            "slug": row[2],
            "plan": row[3],
            "created_at": str(row[4]),
            "is_active": row[5],
            "user_count": row[6]
        }
        for row in rows
    ]

def assign_user_to_tenant(tenant_id: str, user_id: str, role: str = "member") -> bool:
    """Assign a user to a tenant."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO tenant_users (tenant_id, user_id, role, joined_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, user_id) DO UPDATE SET role = %s;
        """, (tenant_id, user_id, role, datetime.now(timezone.utc).isoformat(), role))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        cursor.close()
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to assign user: {str(e)}"
        )

def switch_user_tenant(user_id: str, tenant_id: str) -> Dict[str, Any]:
    """Switch user's active tenant (updates JWT claim on next login)."""
    # Verify membership
    tenant = _get_tenant_with_membership(tenant_id, user_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this tenant."
        )
    
    # In production, update user's default tenant in users table
    # For bootcamp, just return confirmation
    return {
        "message": "Tenant switched successfully",
        "tenant": tenant,
        "note": "Login again to get updated JWT with new tenant claim"
    }

# ──────────────────────────────────────────────
# 6. TENANT BILLING TRACKER
# ──────────────────────────────────────────────

def get_tenant_usage(tenant_id: str, days: int = 30) -> Dict[str, Any]:
    """
    Get usage metrics for billing/invoicing.
    Returns request count, cost, active users.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Request count
    cursor.execute("""
        SELECT COUNT(*) FROM monitoring_requests
        WHERE tenant_id = %s AND timestamp >= NOW() - INTERVAL '%s days'
    """, (tenant_id, days))
    request_count = cursor.fetchone()[0]
    
    # Cost
    cursor.execute("""
        SELECT COALESCE(SUM(cost_usd), 0) FROM monitoring_costs
        WHERE tenant_id = %s AND timestamp >= NOW() - INTERVAL '%s days'
    """, (tenant_id, days))
    total_cost = float(cursor.fetchone()[0])
    
    # Active users
    cursor.execute("""
        SELECT COUNT(DISTINCT user_id) FROM monitoring_requests
        WHERE tenant_id = %s AND timestamp >= NOW() - INTERVAL '%s days'
    """, (tenant_id, days))
    active_users = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return {
        "tenant_id": tenant_id,
        "period_days": days,
        "request_count": request_count,
        "total_cost_usd": round(total_cost, 4),
        "active_users": active_users,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

