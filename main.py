import time
import os
import json
from typing import Literal, Optional, Dict, List, Any
from datetime import datetime
from memory import memory
from token_counter import token_counter

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, EmailStr, field_validator
import openai
from dotenv import load_dotenv

from classifier import classify_intent, SYSTEM_PROMPTS
from tools import check_inventory, get_order_status, list_products


load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="AI Integration Bootcamp API", version="0.2.0")


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


# ADDED IN PHASE 2 DAY 7 
from database import init_db, insert_document, search_similar, get_document_count
from typing import List
import openai

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()

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
        {"role": "system", "content": "You are a helpful store assistant. Do use the available functions to help customers."},
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


