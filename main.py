import time
import os
import json
import time
from typing import Literal, Optional, Dict, List, Any
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from memory import memory
from token_counter import token_counter

from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field, EmailStr, field_validator
import openai
from dotenv import load_dotenv

from classifier import classify_intent, SYSTEM_PROMPTS
from tools import check_inventory, get_order_status, list_products

from crm import (
    calculate_lead_score, LeadScore,
    build_email_context, EmailDraftRequest, EmailDraftResponse,
    CRM_CONTACTS,
    MeetingTranscribeRequest
)

from transcription import (
    TranscriptionRequest, TranscriptionResponse,
    transcribe_audio, extract_meeting_intelligence,
    generate_crm_updates, generate_calendar_reminders
)

from shopify import (
    SHOPIFY_PRODUCTS, SHOPIFY_ORDERS, SHOPIFY_CARTS,
    RecommendationRequest, RecommendationResponse,
    CartRecoveryRequest, CartRecoveryResponse,
    generate_recommendations, generate_recovery_email
)

from analytics import (
    NLQueryRequest, NLQueryResponse,
    DashboardMetrics,
    generate_sql, validate_sql, execute_mock_sql,
    calculate_dashboard_metrics,
    DashboardMetrics, calculate_dashboard_metrics,
    DATABASE_SCHEMA,MOCK_USERS
)

from auth import (
    UserRegisterRequest, UserLoginRequest, TokenResponse, UserProfile,
    APIKeyCreateRequest, APIKeyResponse, APIKeyListItem,
    register_user, authenticate_user, create_access_token,
    get_current_user, get_current_user_or_api_key,
    require_role, require_admin, require_admin_or_user, require_any_role,
    create_api_key, list_api_keys, revoke_api_key,
    get_user_profile
)


from rate_limiter import rate_limit_dependency, check_rate_limit
from fastapi import FastAPI, HTTPException, Depends, status 
from typing import Dict, Any, List, Optional  
from analytics import DashboardMetrics, calculate_dashboard_metrics

# Day 20 imports
from monitoring import (
    TimingMiddleware, logger, record_error, record_cost,
    get_performance_metrics, get_error_summary, get_cost_summary, get_health_status,
    init_monitoring_tables
)
from alerting import send_alert

# Day 21 imports
from tenant import (
    TenantCreateRequest, TenantResponse, TenantUserAssignRequest, TenantSwitchRequest,
    get_current_tenant, init_tenant_tables, _get_tenant_with_membership, 
    create_tenant, list_tenants, assign_user_to_tenant, switch_user_tenant,
    get_tenant_usage, set_tenant_context
)

# Day 22 imports
from agent_engine import (
    AgentRunRequest, AgentApprovalRequest, AgentStatusResponse,
    AgentState, init_agent_tables, create_agent_run, get_agent_status,
    run_agent_workflow, approve_and_continue, WORKFLOWS
)
# At the top of main.py, ensure this import exists:
from database import get_connection



load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


app = FastAPI(
    title="AI Integration Bootcamp API",
    description="Days 1-19: Chat, RAG, CRM, E-commerce, Analytics, Auth",
    version="19.0.0"
)

# Add timing middleware
# Initialize monitoring tables on startup
init_monitoring_tables()
app.add_middleware(TimingMiddleware)

# Initialize tenant tables on startup
init_tenant_tables()

# Initialize agent tables on startup
init_agent_tables()


# ───────────────────────────────────────────────
# REQUEST MODELS (what clients send us)
# ───────────────────────────────────────────────

class SupportRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    customer_tier: Literal["free", "pro", "enterprise"] = "free"
    user_id: str = Field(..., min_length=1)

class SupportResponse(BaseModel):
    classification: str
    priority: int  # 1-5
    answer: str
    escalation_needed: bool
    cost_usd: float
    response_time_ms: float

@app.post("/support", response_model=SupportResponse)
async def support(request: SupportRequest):
    start_time = time.time()
    
    # Classify intent
    classification = classify_intent(request.message)
    
    # Determine priority based on tier + classification
    priority_map = {
        "free": {"billing": 3, "technical": 2, "sales": 1, "general": 1},
        "pro": {"billing": 4, "technical": 3, "sales": 2, "general": 2},
        "enterprise": {"billing": 5, "technical": 5, "sales": 4, "general": 3}
    }
    priority = priority_map[request.customer_tier][classification]
    
    # Build specialized prompt
    system_prompt = SYSTEM_PROMPTS[classification]
    if request.customer_tier == "enterprise":
        system_prompt += " This is an enterprise customer. Provide detailed, immediate solutions."
    
    # Call AI with specialized context
    response = call_openai_with_retry(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.message}
        ],
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=500
    )
    
    answer = response.choices[0].message.content
    cost = calculate_cost("gpt-4o-mini", response.usage.prompt_tokens, response.usage.completion_tokens)
    escalation_needed = priority >= 4
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return SupportResponse(
        classification=classification,
        priority=priority,
        answer=answer,
        escalation_needed=escalation_needed,
        cost_usd=cost,
        response_time_ms=elapsed_ms
    )


class BudgetChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(..., min_length=1)
    max_budget_usd: float = Field(0.01, ge=0.001, le=1.0, description="Max $ per request")
    model: Literal["gpt-4o-mini", "gpt-4o"] = "gpt-4o-mini"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(500, ge=1, le=4096)
    system_prompt: Optional[str] = "You are a helpful assistant."


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The message to send to the AI"
    )
    model: Literal["gpt-4o-mini", "gpt-4o"] = Field(
        default="gpt-4o-mini",
        description="Which model to use"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Creativity: 0 = deterministic, 2 = maximum randomness"
    )
    max_tokens: int = Field(
        default=500,
        ge=1,
        le=4096,
        description="Maximum tokens in the response"
    )
    system_prompt: Optional[str] = Field(
        default="You are a helpful assistant.",
        max_length=2000,
        description="Override the default system behavior"
    )

    @field_validator("message")
    @classmethod
    def no_empty_strings(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be whitespace only")
        return v.strip()

class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class UserRegistration(BaseModel):
    email: EmailStr
    tier: Literal["free", "pro", "enterprise"] = "free"
    company: Optional[str] = Field(default=None, max_length=100)

class ChatWithMemoryRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(..., min_length=1, description="Unique user identifier")
    session_id: Optional[str] = Field(default=None, description="Override auto-generated session")
    system_prompt: Optional[str] = "You are a helpful assistant with perfect memory."
    model: Literal["gpt-4o-mini", "gpt-4o"] = "gpt-4o-mini"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(500, ge=1, le=4096)


class ChatWithMemoryResponse(BaseModel):
    answer: str
    session_id: str
    history_length: int
    model_used: str
    usage: UsageInfo
    response_time_ms: float

# Added on Day 8
class RAGChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    max_context_chunks: int = Field(3, ge=1, le=5)
    model: Literal["gpt-4o-mini", "gpt-4o"] = "gpt-4o-mini"

class RAGChatResponse(BaseModel):
    answer: str
    sources: List[Dict]
    context_used: bool
    tokens_used: int
    cost_usd: float
    response_time_ms: float

@app.post("/chat/rag", response_model=RAGChatResponse)
async def chat_rag(request: RAGChatRequest):
    start_time = time.time()
    
    # Step 1: Generate embedding for the question
    query_embedding = generate_embedding(request.message)
    
    # Step 2: Search vector database for relevant chunks
    relevant_docs = search_similar(
        embedding=query_embedding,
        limit=request.max_context_chunks,
        min_similarity=0.5
    )
    
    context_used = len(relevant_docs) > 0
    
    # Step 3: Build context from retrieved documents
    if context_used:
        context = "\n\n".join([
            f"Source: {doc['title']}\n{doc['content']}"
            for doc in relevant_docs
        ])
        system_prompt = f"""You are a knowledge base assistant. You have access to the following documents:

{context}

INSTRUCTIONS:
1. Answer using ONLY the information in these documents.
2. Cite the source document title in your answer.
3. If the documents do not contain the answer, say: "I don't have that information in my knowledge base."
4. NEVER use outside knowledge. If it's not in the documents above, you don't know it."""
    else:
        # NO RELEVANT DOCUMENTS FOUND
        system_prompt = """You are a knowledge base assistant. 

STATUS: No relevant documents found in the knowledge base for this question.

INSTRUCTIONS:
1. You MUST say: "I don't have that information in my knowledge base."
2. Do NOT answer from your training data.
3. Do NOT guess or make up information."""
    
    # Step 4: Call AI with context
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.message}
    ]
    
    response = call_openai_with_retry(
        messages=messages,
        model=request.model,
        temperature=0.0,  # ZERO temperature for strict compliance
        max_tokens=100    # Short response to prevent rambling
    )
    
    answer = response.choices[0].message.content
    
    # ... rest of your code ...
    
    # Step 5: Calculate cost
    cost = calculate_cost(
        request.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens
    )
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return RAGChatResponse(
        answer=answer,
        sources=[
            {
                "title": doc["title"],
                "similarity": round(doc["similarity"], 4),
                "content_preview": doc["content"][:100] + "..."
            }
            for doc in relevant_docs
        ],
        context_used=context_used,
        tokens_used=response.usage.total_tokens,
        cost_usd=cost,
        response_time_ms=elapsed_ms
    )

# Added on Day 9
class FunctionChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(..., min_length=1)
    model: Literal["gpt-4o-mini", "gpt-4o"] = "gpt-4o-mini"

class FunctionChatResponse(BaseModel):
    answer: str
    function_called: Optional[str] = None
    function_result: Optional[Any] = None
    cost_usd: float
    response_time_ms: float


# ───────────────────────────────────────────────
# RESPONSE MODELS (what we guarantee to clients)
# ───────────────────────────────────────────────

class ChatResponse(BaseModel):
    answer: str
    model_used: str
    usage: UsageInfo
    response_time_ms: float
    timestamp: str


class ErrorResponse(BaseModel):
    error: str
    error_code: str
    suggestion: Optional[str] = None


# ───────────────────────────────────────────────
# PRICING ENGINE
# ───────────────────────────────────────────────

PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = PRICING.get(model, PRICING["gpt-4o-mini"])
    input_cost = (prompt_tokens / 1_000_000) * rates["input"]
    output_cost = (completion_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


# ───────────────────────────────────────────────
# OPENAI CLIENT WITH RETRY
# ───────────────────────────────────────────────

def call_openai_with_retry(
    messages: list,
    model: str,
    temperature: float,
    max_tokens: int,
    max_retries: int = 3
):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        except openai.RateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
        except openai.APIError:
            raise


# ───────────────────────────────────────────────
# ENDPOINTS
# ───────────────────────────────────────────────

@app.get("/health", response_model=dict)
async def health():
    return {
        "status": "ok",
        "service": "ai-integration-bootcamp",
        "version": "0.2.0",
        "models_available": list(PRICING.keys())
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    start_time = time.time()
    
    messages = [
        {"role": "system", "content": request.system_prompt},
        {"role": "user", "content": request.message}
    ]
    
    try:
        response = call_openai_with_retry(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
    except openai.RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please retry in 60 seconds."
        )
    except openai.APIError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI service error: {str(e)}"
        )
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return ChatResponse(
        answer=response.choices[0].message.content,
        model_used=response.model,
        usage=UsageInfo(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            estimated_cost_usd=calculate_cost(
                request.model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )
        ),
        response_time_ms=elapsed_ms,
        timestamp=datetime.utcnow().isoformat()
    )


@app.post("/register", response_model=UserRegistration)
async def register(user: UserRegistration):
    # In real app: hash password, store in DB, send email
    return {
        "email": user.email,
        "tier": user.tier,
        "company": user.company,
        "registered_at": datetime.utcnow().isoformat()
    }


@app.get("/pricing")
async def pricing():
    return {
        "models": {
            model: {
                "input_per_1m_tokens": rates["input"],
                "output_per_1m_tokens": rates["output"]
            }
            for model, rates in PRICING.items()
        },
        "note": "Costs are estimates. Actual billing may vary."
    }

@app.post("/chat/memory", response_model=ChatWithMemoryResponse)
async def chat_with_memory(request: ChatWithMemoryRequest):
    start_time = time.time()
    
    # Generate or use provided session ID
    session_id = request.session_id or memory._generate_session_id(request.user_id, "default")
    
    # Build message list with history
    messages = [{"role": "system", "content": request.system_prompt}]
    messages.extend(memory.get_history(session_id))
    messages.append({"role": "user", "content": request.message})
    
    try:
        response = call_openai_with_retry(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except openai.APIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    
    answer = response.choices[0].message.content
    
    # Store both user message and AI response
    memory.add_message(session_id, "user", request.message)
    memory.add_message(session_id, "assistant", answer)
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return ChatWithMemoryResponse(
        answer=answer,
        session_id=session_id,
        history_length=len(memory.get_history(session_id)),
        model_used=response.model,
        usage=UsageInfo(
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            estimated_cost_usd=calculate_cost(
                request.model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )
        ),
        response_time_ms=elapsed_ms
    )


@app.get("/chat/memory/{session_id}")
async def get_memory(session_id: str):
    """Retrieve full conversation history for a session."""
    history = memory.get_history(session_id)
    info = memory.get_session_info(session_id)
    return {
        "session_info": info,
        "history": history
    }


@app.delete("/chat/memory/{session_id}")
async def clear_memory(session_id: str):
    """Clear a conversation session."""
    cleared = memory.clear_session(session_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "cleared", "session_id": session_id}


@app.get("/chat/memory")
async def list_sessions():
    """List all active sessions (dev only — remove in production)."""
    return {
        "active_sessions": len(memory.sessions),
        "sessions": [
            {
                "session_id": sid,
                "message_count": len(msgs),
                "last_message": msgs[-1]["content"][:50] + "..." if msgs else None
            }
            for sid, msgs in memory.sessions.items()
        ]
    }

@app.post("/chat/budget")
async def chat_with_budget(request: BudgetChatRequest):
    """
    Chat endpoint with pre-flight cost estimation.
    Rejects request if estimated cost exceeds budget.
    """
    start_time = time.time()
    
    # Build messages
    messages = [
        {"role": "system", "content": request.system_prompt},
        {"role": "user", "content": request.message}
    ]
    
    # PRE-FLIGHT: Estimate cost before API call
    estimate = token_counter.estimate_max_cost(
        messages=messages,
        model=request.model,
        max_tokens=request.max_tokens
    )
    
    if estimate["estimated_max_cost_usd"] > request.max_budget_usd:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "Budget exceeded",
                "estimated_cost": estimate["estimated_max_cost_usd"],
                "budget": request.max_budget_usd,
                "suggestion": "Reduce max_tokens or increase budget"
            }
        )
    
    # Call API
    try:
        response = call_openai_with_retry(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except openai.APIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    
    # POST-FLIGHT: Compare estimate vs actual
    actual_cost = calculate_cost(
        request.model,
        response.usage.prompt_tokens,
        response.usage.completion_tokens
    )
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return {
        "answer": response.choices[0].message.content,
        "budget_check": {
            "estimated_max_cost": estimate["estimated_max_cost_usd"],
            "actual_cost": actual_cost,
            "budget": request.max_budget_usd,
            "under_budget": actual_cost <= request.max_budget_usd
        },
        "token_accuracy": {
            "estimated_prompt_tokens": estimate["estimated_prompt_tokens"],
            "actual_prompt_tokens": response.usage.prompt_tokens,
            "difference": response.usage.prompt_tokens - estimate["estimated_prompt_tokens"]
        },
        "usage": {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens
        },
        "response_time_ms": elapsed_ms
    }

# Added on Day 10
from starlette.responses import StreamingResponse
import asyncio

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream tokens as they're generated by the AI."""
    stream = client.chat.completions.create(
        model=request.model,
        messages=[
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.message}
        ],
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=True  # Enable streaming
    )
    
    async def generate():
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield f"data: {json.dumps({'token': chunk.choices[0].delta.content})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


# ADDED IN DAY 7 
from database import init_db, insert_document, search_similar, get_document_count
from typing import List
import openai

# Initialize database on startup
@asynccontextmanager  # NEW, correct
async def lifespan(app: FastAPI):
    print("🚀 Starting up... Initializing database")
    init_db()
    yield


# Request/Response models
class DocumentIngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1, max_length=10000)
    metadata: Optional[Dict] = {}

class DocumentIngestResponse(BaseModel):
    id: int
    title: str
    chunks_stored: int
    status: str

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    limit: int = Field(5, ge=1, le=20)
    min_similarity: float = Field(0.5, ge=0.0, le=1.0)

class SearchResult(BaseModel):
    id: int
    title: str
    content: str
    similarity: float

class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_found: int

# Generate embedding for text
def generate_embedding(text: str) -> List[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding

# Chunk long text into smaller pieces
def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks for better search."""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap  # Overlap for context continuity
    
    return chunks

# Ingest endpoint
@app.post("/documents/ingest", response_model=DocumentIngestResponse)
async def ingest_document(request: DocumentIngestRequest):
    start_time = time.time()
    
    # Chunk the content
    chunks = chunk_text(request.content)
    
    # Store each chunk with its embedding
    stored_ids = []
    for i, chunk in enumerate(chunks):
        embedding = generate_embedding(chunk)
        
        # Create metadata with chunk info
        chunk_metadata = {
            **request.metadata,
            "chunk_index": i,
            "total_chunks": len(chunks),
            "chunk_size": len(chunk)
        }
        
        doc_id = insert_document(
            title=f"{request.title} (chunk {i+1}/{len(chunks)})",
            content=chunk,
            embedding=embedding,
            metadata=chunk_metadata
        )
        stored_ids.append(doc_id)
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return DocumentIngestResponse(
        id=stored_ids[0],  # Return first chunk ID
        title=request.title,
        chunks_stored=len(stored_ids),
        status=f"Stored {len(stored_ids)} chunks in {elapsed_ms}ms"
    )

# Search endpoint
@app.post("/documents/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    # Generate embedding for the query
    query_embedding = generate_embedding(request.query)
    
    # Search database
    results = search_similar(
        embedding=query_embedding,
        limit=request.limit,
        min_similarity=request.min_similarity
    )
    
    return SearchResponse(
        query=request.query,
        results=[
            SearchResult(
                id=r["id"],
                title=r["title"],
                content=r["content"],
                similarity=round(r["similarity"], 4)
            )
            for r in results
        ],
        total_found=len(results)
    )

# Stats endpoint
@app.get("/documents/stats")
async def document_stats():
    return {
        "total_documents": get_document_count(),
        "database": "postgresql_with_pgvector"
    }

# Added on Day 9
AVAILABLE_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "Check if a product is in stock and get pricing",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "Product identifier (e.g., 'iphone-15', 'macbook-air')"
                    }
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Get the shipping status and tracking info for an order",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order identifier (e.g., 'order-123')"
                    }
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_products",
            "description": "List all available products with prices and stock status",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]


@app.post("/chat/functions", response_model=FunctionChatResponse)
async def chat_with_functions(request: FunctionChatRequest):
    start_time = time.time()
    
    messages = [
        {"role": "system", "content": "You are a helpful store assistant. Use the available functions to help customers."},
        {"role": "user", "content": request.message}
    ]
    
    response = client.chat.completions.create(
        model=request.model,
        messages=messages,
        tools=AVAILABLE_FUNCTIONS,
        tool_choice="auto",
        temperature=0.3
    )
    
    message = response.choices[0].message
    
    if message.tool_calls:
        tool_call = message.tool_calls[0]
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)
        
        if function_name == "check_inventory":
            result = check_inventory(**arguments)
        elif function_name == "get_order_status":
            result = get_order_status(**arguments)
        elif function_name == "list_products":
            result = list_products()
        else:
            result = {"error": f"Unknown function: {function_name}"}
        
        messages.append(message)
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result)
        })
        
        final_response = client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=0.7
        )
        
        answer = final_response.choices[0].message.content
        cost = calculate_cost(request.model, 
            response.usage.prompt_tokens + final_response.usage.prompt_tokens,
            response.usage.completion_tokens + final_response.usage.completion_tokens
        )
    else:
        answer = message.content
        cost = calculate_cost(request.model, response.usage.prompt_tokens, response.usage.completion_tokens)
        result = None
        function_name = None
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return FunctionChatResponse(
        answer=answer,
        function_called=function_name,
        function_result=result,
        cost_usd=cost,
        response_time_ms=elapsed_ms
    )

class ImageAnalysisRequest(BaseModel):
    image_url: str = Field(..., description="URL of image to analyze")
    question: str = Field(..., description="What to ask about the image")

class ImageAnalysisResponse(BaseModel):
    answer: str
    model_used: str
    cost_usd: float

@app.post("/chat/image", response_model=ImageAnalysisResponse)
async def analyze_image(request: ImageAnalysisRequest):
    start_time = time.time()
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": request.question},
                    {
                        "type": "image_url",
                        "image_url": {"url": request.image_url}
                    }
                ]
            }
        ],
        max_tokens=500
    )
    
    answer = response.choices[0].message.content
    cost = calculate_cost("gpt-4o-mini", response.usage.prompt_tokens, response.usage.completion_tokens)
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return ImageAnalysisResponse(
        answer=answer,
        model_used=response.model,
        cost_usd=cost
    )

#====================Day 15==============================================================

@app.get("/crm/leads/{lead_id}/score", response_model=LeadScore)
async def get_lead_score(lead_id: str):
    """Get AI-calculated lead quality score with actionable recommendation."""
    return calculate_lead_score(lead_id)

@app.post("/crm/leads/{lead_id}/email", response_model=EmailDraftResponse)
async def draft_email(lead_id: str, request: EmailDraftRequest):
    """Generate personalized email using lead context and AI."""
    start_time = time.time()
    
    # Build context from CRM
    context = build_email_context(lead_id)
    contact = CRM_CONTACTS.get(lead_id)
    
    # Build system prompt based on email type
    email_prompts = {
        "follow_up": "You are a sales follow-up specialist. Write a warm, personalized follow-up email.",
        "cold_outreach": "You are a B2B sales development rep. Write a compelling cold email that gets a response.",
        "demo_request": "You are a solutions consultant. Write an email to schedule a product demo.",
        "proposal": "You are an account executive. Write an email presenting a tailored proposal."
    }
    
    tone_instructions = {
        "professional": "Use formal business language. Clear, concise, respectful.",
        "friendly": "Use warm, conversational tone. Build rapport.",
        "urgent": "Create gentle urgency. Limited time offer or competitive pressure."
    }
    
    system_prompt = f"""{email_prompts[request.email_type]}
TONE: {tone_instructions[request.tone]}
RULES:
1. Reference specific pain points from the lead profile
2. Mention recent activity (page views, downloads) naturally
3. Keep under {request.max_length_words} words
4. {'Include clear call-to-action' if request.include_cta else 'No call-to-action, just value'}
5. Subject line should be compelling and specific"""
    
    # Generate email with AI
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Write an email to this lead:\n\n{context}"}
    ]
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=800
    )
    
    email_text = response.choices[0].message.content
    
    # Extract subject line (first line if it starts with "Subject:")
    lines = email_text.split('\n')
    subject = "Follow-up"
    body = email_text
    for line in lines:
        if line.lower().startswith('subject:'):
            subject = line.replace('Subject:', '').strip()
            body = '\n'.join(lines[lines.index(line)+1:]).strip()
            break
    
    # Identify personalization signals used
    personalization = []
    if any(pain in email_text.lower() for pain in contact["pain_points"]):
        personalization.append("referenced pain points")
    if contact["company"] in email_text:
        personalization.append("mentioned company name")
    if contact["interactions"] and any(i["date"] in email_text for i in contact["interactions"]):
        personalization.append("referenced recent activity")
    
    cost = calculate_cost("gpt-4o-mini", response.usage.prompt_tokens, response.usage.completion_tokens)
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return EmailDraftResponse(
        lead_id=lead_id,
        recipient={"name": contact["name"], "email": contact["email"], "company": contact["company"]},
        subject=subject,
        body=body,
        tone=request.tone,
        word_count=len(email_text.split()),
        personalization_signals=personalization,
        cost_usd=cost,
        generated_at=datetime.now().isoformat()
    )

@app.get("/crm/leads")
async def list_leads():
    """List all leads with basic info and scores."""
    results = []
    for lead_id, contact in CRM_CONTACTS.items():
        score = calculate_lead_score(lead_id)
        results.append({
            "lead_id": lead_id,
            "name": contact["name"],
            "company": contact["company"],
            "status": contact["status"],
            "score": score.score,
            "priority": score.priority,
            "last_contact": contact["last_contact"]
        })
    return {"leads": results, "total": len(results)}

@app.post("/crm/meeting/transcribe")
async def transcribe_meeting(request: MeetingTranscribeRequest):
    """Mock meeting transcription → extract action items → CRM update suggestions."""
    start_time = time.time()
    
    system_prompt = """You are a meeting intelligence assistant.
Extract from this meeting transcript:
1. Key decisions made
2. Action items with owners
3. Follow-up dates
4. Sentiment (positive/neutral/negative)
5. CRM updates needed

Return as structured JSON."""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.meeting_text}
        ],
        temperature=0.3,
        max_tokens=1000
    )
    
    # Parse AI response
    try:
        result = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        result = {
            "raw_analysis": response.choices[0].message.content,
            "note": "AI returned non-JSON. Parse manually."
        }
    
    cost = calculate_cost("gpt-4o-mini", response.usage.prompt_tokens, response.usage.completion_tokens)
    
    return {
        "transcript_length": len(request.meeting_text),
        "analysis": result,
        "crm_updates_suggested": result.get("crm_updates_needed", []),
        "cost_usd": cost,
        "processing_time_ms": round((time.time() - start_time) * 1000, 2)
    }

# ==========================Day 16==================================================

@app.post("/crm/meeting/process", response_model=TranscriptionResponse)
async def process_meeting(request: TranscriptionRequest):
    """Full pipeline: audio/text -> transcript -> intelligence -> CRM updates -> reminders."""
    start_time = time.time()
    
    # Step 1: Get transcript (audio or text)
    if request.audio_url and os.path.exists(request.audio_url):
        transcript = transcribe_audio(request.audio_url, request.language)
        audio_seconds = None
    elif request.audio_text:
        transcript = request.audio_text
        audio_seconds = None
    else:
        raise HTTPException(status_code=400, detail="Provide audio_url or audio_text")
    
    # Step 2: Get contact info
    contact = CRM_CONTACTS.get(request.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact {request.contact_id} not found")
    
    # Step 3: Extract intelligence
    intelligence = extract_meeting_intelligence(
        transcript=transcript,
        contact_name=contact["name"],
        company=contact["company"]
    )
    
    # Step 4: Generate CRM updates
    crm_updates = generate_crm_updates(request.contact_id, intelligence)
    
    # Step 5: Generate calendar reminders
    calendar_reminders = generate_calendar_reminders(intelligence, contact["name"])
    
    # Calculate costs
    extraction_cost = calculate_cost(
        "gpt-4o-mini",
        len(transcript.split()) // 4,
        len(str(intelligence).split()) // 4
    )
    total_cost = round(extraction_cost, 6)
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    return TranscriptionResponse(
        contact_id=request.contact_id,
        transcript=transcript,
        transcript_length_seconds=audio_seconds,
        meeting_summary=intelligence.get("meeting_summary", ""),
        key_decisions=intelligence.get("key_decisions", []),
        action_items=intelligence.get("action_items", []),
        sentiment=intelligence.get("sentiment", "neutral"),
        follow_up_date=intelligence.get("follow_up_date"),
        crm_updates=crm_updates,
        calendar_reminders=calendar_reminders,
        cost_usd=total_cost,
        processing_time_ms=elapsed_ms
    )

@app.get("/crm/meeting/{contact_id}/history")
async def get_meeting_history(contact_id: str):
    """Get all processed meetings for a contact."""
    contact = CRM_CONTACTS.get(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    return {
        "contact_id": contact_id,
        "contact_name": contact["name"],
        "meetings_processed": 1,
        "last_meeting": contact.get("last_contact"),
        "note": "In production, this queries a meetings database table"
    }


# =====================Day 17======================================================
# -- PRODUCT ENDPOINTS --

@app.get("/shopify/products")
async def list_products():
    """List all Shopify products with inventory status."""
    products = []
    for prod_id, product in SHOPIFY_PRODUCTS.items():
        products.append({
            "id": prod_id,
            "title": product["title"],
            "price": product["price"],
            "compare_at_price": product["compare_at_price"],
            "inventory": product["inventory_quantity"],
            "status": "in_stock" if product["inventory_quantity"] > 0 else "out_of_stock",
            "tags": product["tags"]
        })
    return {"products": products, "total": len(products)}

@app.get("/shopify/products/{product_id}")
async def get_product(product_id: str):
    """Get single product details."""
    product = SHOPIFY_PRODUCTS.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.post("/shopify/recommend", response_model=RecommendationResponse)
async def get_recommendations(request: RecommendationRequest):
    """Get personalized product recommendations."""
    return generate_recommendations(request)

# -- ORDER TRACKING --

@app.get("/shopify/orders/{order_id}")
async def track_order(order_id: str):
    """Track order status and shipping."""
    order = SHOPIFY_ORDERS.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Calculate delivery estimate
    created = datetime.strptime(order["created_at"], "%Y-%m-%d")
    if order["fulfillment_status"] == "fulfilled":
        delivery_estimate = "Delivered or in transit"
    else:
        delivery_estimate = "Processing - ships within 2 business days"
    
    return {
        "order_id": order_id,
        "status": order["fulfillment_status"],
        "financial_status": order["financial_status"],
        "total": order["total_price"],
        "items": [SHOPIFY_PRODUCTS.get(item_id, {"title": "Unknown"})["title"] for item_id in order["line_items"]],
        "tracking_number": order["tracking_number"],
        "delivery_estimate": delivery_estimate,
        "shipping_to": order["shipping_address"]
    }

# -- ABANDONED CART RECOVERY --

@app.post("/shopify/cart/recover", response_model=CartRecoveryResponse)
async def recover_cart(request: CartRecoveryRequest):
    """Generate abandoned cart recovery email."""
    start_time = time.time()
    
    cart = SHOPIFY_CARTS.get(request.cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    # Generate email content
    email_data = generate_recovery_email(cart, request.tone, request.include_discount, request.discount_percent)
    
    # Call AI for email generation
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": email_data["system_prompt"]},
            {"role": "user", "content": email_data["user_content"]}
        ],
        temperature=0.7,
        max_tokens=500
    )
    
    email_text = response.choices[0].message.content
    
    # Extract subject (first line if starts with Subject:)
    lines = email_text.split('\n')
    subject = "You left something behind..."
    body = email_text
    for line in lines:
        if line.lower().startswith('subject:'):
            subject = line.replace('Subject:', '').strip()
            body = '\n'.join(lines[lines.index(line)+1:]).strip()
            break
    
    # Calculate urgency
    abandoned_time = datetime.fromisoformat(cart["abandoned_at"].replace('Z', '+00:00'))
    hours_abandoned = (datetime.now() - abandoned_time).total_seconds() / 3600
    urgency_score = min(10, int(hours_abandoned / 2) + 3)
    
    # Generate discount code if requested
    discount_code = None
    if request.include_discount:
        discount_code = f"SAVE{request.discount_percent}-{request.cart_id[:4].upper()}"
    
    cost = calculate_cost("gpt-4o-mini", response.usage.prompt_tokens, response.usage.completion_tokens)
    
    return CartRecoveryResponse(
        cart_id=request.cart_id,
        customer_email=cart["customer_email"],
        subject=subject,
        email_body=body,
        urgency_score=urgency_score,
        discount_code=discount_code,
        estimated_recovery_value=cart["total"],
        cost_usd=cost
    )

# =====================Day 18 ===================================================

# ═══════════════════════════════════════════════
# HEALTH CHECK (Day 1)
# ═══════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "19.0.0", "days_completed": 19}

# ═══════════════════════════════════════════════
# DAY 18: SaaS Analytics (PROTECTED)
# ═══════════════════════════════════════════════

@app.post("/analytics/query", response_model=NLQueryResponse, tags=["Analytics"])
async def natural_language_query(
    request: NLQueryRequest,
    user: Dict[str, Any] = Depends(require_any_role)
):
    """Convert natural language to SQL, validate, execute with permissions."""
    import time
    start_time = time.time()

    # Override request role with actual auth role for security
    effective_role = user["role"]
    effective_user_id = request.user_id if effective_role == "admin" else int(user["id"])

    # Step 1: Generate SQL from natural language
    sql = generate_sql(request.question, DATABASE_SCHEMA, effective_role)

    # Step 2: Validate SQL safety
    is_safe, warning = validate_sql(sql)
    if not is_safe:
        return NLQueryResponse(
            question=request.question,
            generated_sql=sql,
            sql_safe=False,
            results=[],
            result_count=0,
            execution_time_ms=0,
            cost_usd=0,
            warning=warning
        )

    # Step 3: Execute with permission filtering
    results = execute_mock_sql(sql, effective_user_id, effective_role)

    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    return NLQueryResponse(
        question=request.question,
        generated_sql=sql,
        sql_safe=True,
        results=results,
        result_count=len(results),
        execution_time_ms=elapsed_ms,
        cost_usd=0.0001,
        warning=None
    )

@app.get("/analytics/dashboard", response_model=DashboardMetrics, tags=["Analytics"])
async def get_dashboard(user: Dict[str, Any] = Depends(require_admin)):
    """Get admin dashboard metrics. ADMIN ONLY."""
    return calculate_dashboard_metrics()

@app.get("/analytics/dashboard/chart/{metric}", tags=["Analytics"])
async def get_chart_data(metric: str, user: Dict[str, Any] = Depends(require_admin)):
    """Get chart-ready data for specific metric. ADMIN ONLY."""
    if metric == "revenue_by_month":
        data = execute_mock_sql(
            "SELECT strftime('%Y-%m', created_at) as month, SUM(amount) as total FROM orders GROUP BY month",
            user_id=None,
            user_role="admin"
        )
        return {"chart_type": "bar", "data": data, "x_key": "month", "y_key": "total"}
    elif metric == "user_growth":
        data = execute_mock_sql(
            "SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count FROM users GROUP BY month",
            user_id=None,
            user_role="admin"
        )
        return {"chart_type": "line", "data": data, "x_key": "month", "y_key": "count"}
    elif metric == "subscription_distribution":
        tiers = {}
        for u in MOCK_USERS:
            tier = u["subscription_tier"]
            tiers[tier] = tiers.get(tier, 0) + 1
        data = [{"tier": k, "count": v} for k, v in tiers.items()]
        return {"chart_type": "pie", "data": data, "label_key": "tier", "value_key": "count"}
    else:
        raise HTTPException(status_code=404, detail="Metric not found")

# ═══════════════════════════════════════════════
# DAY 19: Authentication & Authorization
# ═══════════════════════════════════════════════

@app.post("/auth/register", response_model=Dict[str, Any], tags=["Authentication"])
async def register(request: UserRegisterRequest):
    """Register a new user. Password hashed with bcrypt."""
    user = register_user(request)
    return {"message": "Registration successful", "user": user}

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login(request: UserLoginRequest):
    """Authenticate and receive JWT access token."""
    user = authenticate_user(request.email, request.password)
    token = create_access_token(user["id"], user["email"], user["role"])

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=24 * 3600,
        user=user
    )

@app.get("/auth/me", response_model=UserProfile, tags=["Authentication"])
async def me(user: Dict[str, Any] = Depends(get_current_user_or_api_key)):
    """Get current user profile from JWT token OR API key."""
    return get_user_profile(user["id"])

@app.post("/auth/api-keys", response_model=APIKeyResponse, tags=["API Keys"])
async def generate_api_key(
    request: APIKeyCreateRequest,
    user: Dict[str, Any] = Depends(require_admin_or_user)
):
    """Generate API key for integrations. Key shown ONCE."""
    return create_api_key(user["id"], request.name, request.rate_limit_per_minute)

@app.get("/auth/api-keys", response_model=List[APIKeyListItem], tags=["API Keys"])
async def get_api_keys(user: Dict[str, Any] = Depends(require_admin_or_user)):
    """List API keys (metadata only)."""
    is_admin = user["role"] == "admin"
    return list_api_keys(user["id"], is_admin)

@app.delete("/auth/api-keys/{key_id}", tags=["API Keys"])
async def delete_api_key(
    key_id: str,
    user: Dict[str, Any] = Depends(require_admin_or_user)
):
    """Revoke an API key."""
    is_admin = user["role"] == "admin"
    revoke_api_key(key_id, user["id"], is_admin)
    return {"message": "API key revoked successfully"}

@app.get("/auth/rate-limit", tags=["Authentication"])
async def rate_limit_status(user: Dict[str, Any] = Depends(get_current_user_or_api_key)):
    """Check current rate limit status."""
    return {
        "remaining_requests": 60,
        "reset_in_seconds": 60,
        "user_id": user["id"]
    }

# Test route (remove after verification)
@app.get("/auth/test", tags=["Authentication"])
async def auth_test():
    return {"status": "auth routes are working"}

# ====================================Day20=============================================
@app.get("/health", tags=["Monitoring"])
async def health_check():
    return get_health_status()

# ═══════════════════════════════════════════════
# DAY 20: Monitoring & Logging
# ═══════════════════════════════════════════════

@app.get("/monitoring/performance", tags=["Monitoring"])
async def performance_metrics(user: Dict[str, Any] = Depends(require_admin)):
    return get_performance_metrics()

@app.get("/monitoring/errors", tags=["Monitoring"])
async def error_logs(limit: int = 50, user: Dict[str, Any] = Depends(require_admin)):
    return {
        "errors": get_error_summary(limit),
        "total_recorded": len(get_error_summary(10000)),
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

@app.get("/monitoring/costs", tags=["Monitoring"])
async def cost_metrics(user: Dict[str, Any] = Depends(require_admin)):
    return get_cost_summary()

@app.post("/monitoring/alert", tags=["Monitoring"])
async def test_alert(
    message: str = "Test alert from AI Bootcamp",
    user: Dict[str, Any] = Depends(require_admin)
):
    results = send_alert(message, details={"source": "test_endpoint", "user": user["email"]})
    return {
        "message": message,
        "channels_attempted": results,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ===========================Day 21======================================================
# ═══════════════════════════════════════════════
# DAY 21: Multi-Tenant Architecture
# ═══════════════════════════════════════════════

@app.post("/tenants", response_model=Dict[str, Any], tags=["Tenants"])
async def create_new_tenant(
    request: TenantCreateRequest,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Create a new tenant (organization/workspace).
    Creator is automatically assigned as admin.
    """
    tenant = create_tenant(request, user["id"])
    return {
        "message": "Tenant created successfully",
        "tenant": tenant
    }

@app.get("/tenants", response_model=List[TenantResponse], tags=["Tenants"])
async def get_tenants(
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    List tenants you belong to. Admins see all tenants.
    """
    is_admin = user["role"] == "admin"
    return list_tenants(user["id"], is_admin)

@app.get("/tenants/me", tags=["Tenants"])
async def get_my_tenant(
    tenant: Dict[str, Any] = Depends(get_current_tenant)
):
    """
    Get current tenant context.
    """
    return tenant

@app.post("/tenants/{tenant_id}/users", tags=["Tenants"])
async def add_user_to_tenant(
    tenant_id: str,
    request: TenantUserAssignRequest,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Assign a user to a tenant. Only tenant admins can do this.
    """
    # Verify caller is admin of this tenant
    tenant = _get_tenant_with_membership(tenant_id, user["id"])
    if not tenant or tenant["user_role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tenant admins can add users."
        )
    
    assign_user_to_tenant(tenant_id, request.user_id, request.role)
    return {
        "message": "User assigned to tenant successfully",
        "tenant_id": tenant_id,
        "user_id": request.user_id,
        "role": request.role
    }

@app.post("/tenants/switch", tags=["Tenants"])
async def switch_tenant(
    request: TenantSwitchRequest,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Switch to a different tenant.
    """
    return switch_user_tenant(user["id"], request.tenant_id)

@app.get("/tenants/{tenant_id}/usage", tags=["Tenants"])
async def tenant_usage(
    tenant_id: str,
    days: int = 30,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Get usage metrics for billing (request count, cost, active users).
    """
    # Verify membership
    tenant = _get_tenant_with_membership(tenant_id, user["id"])
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this tenant."
        )
    
    return get_tenant_usage(tenant_id, days)



# ==================================Day22===================================================
# ═══════════════════════════════════════════════
# DAY 22: Agent Architecture
# ═══════════════════════════════════════════════

@app.post("/agents/run", response_model=Dict[str, Any], tags=["Agents"])
async def start_agent(
    request: AgentRunRequest,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Start a multi-step agent workflow.
    
    Example: {"workflow_name": "content_creation", "input_data": {"topic": "AI in healthcare"}}
    """
    if request.workflow_name not in WORKFLOWS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown workflow. Available: {list(WORKFLOWS.keys())}"
        )
    
    run_id = create_agent_run(request.workflow_name, request.input_data, user["id"])
    
    # Run workflow (synchronous for bootcamp; async background task in production)
    run_agent_workflow(run_id)
    
    status = get_agent_status(run_id)
    
    return {
        "message": "Agent workflow started",
        "run_id": run_id,
        "workflow_name": request.workflow_name,
        "state": status["state"],
        "current_step": status["current_step"]
    }

@app.get("/agents/{run_id}/status", response_model=AgentStatusResponse, tags=["Agents"])
async def get_agent_status_endpoint(
    run_id: str,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Check current status of an agent run.
    """
    status = get_agent_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Agent run not found")
    
    return AgentStatusResponse(
        run_id=status["run_id"],
        workflow_name=status["workflow_name"],
        state=status["state"],
        current_step=status["current_step"],
        completed_steps=status["completed_steps"],
        failed_steps=status["failed_steps"],
        results=status["results"],
        started_at=status["started_at"],
        updated_at=status["updated_at"],
        waiting_for_approval=status["waiting_for_approval"]
    )

@app.post("/agents/{run_id}/approve", tags=["Agents"])
async def approve_agent_step(
    run_id: str,
    request: AgentApprovalRequest,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Approve or reject a paused agent step.
    True = continue, False = cancel.
    """
    try:
        result = approve_and_continue(run_id, request.approved, request.feedback)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/agents/{run_id}/cancel", tags=["Agents"])
async def cancel_agent(
    run_id: str,
    user: Dict[str, Any] = Depends(get_current_user_or_api_key)
):
    """
    Cancel a running or paused agent.
    """
    from database import get_connection  # Local import as fallback
    
    status = get_agent_status(run_id)
    if not status:
        raise HTTPException(status_code=404, detail="Agent run not found")
    
    if status["state"] not in ["running", "paused", "idle"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel agent in state: {status['state']}")
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        UPDATE agent_runs SET state = %s, updated_at = %s, current_step = NULL
        WHERE id = %s
    """, ("cancelled", now, run_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    return {"message": "Agent run cancelled", "run_id": run_id}


@app.get("/agents/workflows", tags=["Agents"])
async def list_workflows():
    """
    List available predefined workflows and their steps.
    """
    return {
        "workflows": {
            name: [
                {
                    "name": step.name,
                    "description": step.description,
                    "requires_approval": step.requires_approval
                }
                for step in steps
            ]
            for name, steps in WORKFLOWS.items()
        }
    }


