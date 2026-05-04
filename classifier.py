from typing import Literal
import openai
import os
from dotenv import load_dotenv

# Load environment variables BEFORE creating the client
load_dotenv()  # <-- ADD THIS LINE

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

CLASSIFICATION_PROMPT = """You are a support triage assistant. 
Classify the user's message into exactly one of these categories:
- billing: payment issues, refunds, invoices, subscriptions
- technical: bugs, errors, crashes, features not working
- sales: pricing questions, upgrades, demos, purchasing
- general: anything else

Respond with ONLY the category name, nothing else."""

SYSTEM_PROMPTS = {
    "billing": "You are a billing support specialist. Help with payments, refunds, and subscriptions.",
    "technical": "You are a technical support engineer. Troubleshoot bugs and errors step by step.",
    "sales": "You are a sales representative. Be persuasive but honest about pricing and features.",
    "general": "You are a helpful general support assistant."
}

def classify_intent(message: str) -> Literal["billing", "technical", "sales", "general"]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": CLASSIFICATION_PROMPT},
            {"role": "user", "content": message}
        ],
        temperature=0.0,  # Deterministic for classification
        max_tokens=10
    )
    result = response.choices[0].message.content.strip().lower()
    # Validate against allowed values
    if result not in ["billing", "technical", "sales", "general"]:
        return "general"
    return result
