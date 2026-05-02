from fastapi import FastAPI
from pydantic import BaseModel
import openai
import os
from dotenv import load_dotenv

load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Cheapest for practice
            messages=[{"role": "user", "content": request.message}]
        )
        return {
            "answer": response.choices[0].message.content,
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens
            }
        }
    except openai.RateLimitError:
        return {"error": "Rate limited. Slow down."}
    except openai.APIError as e:
        return {"error": f"OpenAI error: {str(e)}"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai-integration-bootcamp"}

