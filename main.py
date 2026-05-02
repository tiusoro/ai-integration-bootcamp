import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import os
from dotenv import load_dotenv

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

def call_openai_with_retry(message: str, max_retries: int = 3):
    """Retry with exponential backoff on rate limits."""
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": message}]
            )
        except openai.RateLimitError:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait_time)
            else:
                raise
        except openai.APIError:
            raise

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        response = call_openai_with_retry(request.message)
        return {
            "answer": response.choices[0].message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens
            }
        }
    except openai.RateLimitError:
        return {"error": "Rate limited. Try Again in 60 seconds."}
    except openai.APIError as e:
        return {"error": f"OpenAI error: {str(e)}"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-integration-bootcamp"}
