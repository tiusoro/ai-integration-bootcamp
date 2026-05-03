import time
import os
from typing import Literal, Optional
from datetime import datetime
from memory import memory

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, EmailStr, field_validator
import openai
from dotenv import load_dotenv

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI(title="AI Integration Bootcamp API", version="0.2.0")


# ───────────────────────────────────────────────
# REQUEST MODELS (what clients send us)
# ───────────────────────────────────────────────

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



