import tiktoken
from typing import List, Dict

# ── PRICING DATA (moved here to avoid circular imports) ──
PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate API call cost in USD."""
    rates = PRICING.get(model, PRICING["gpt-4o-mini"])
    input_cost = (prompt_tokens / 1_000_000) * rates["input"]
    output_cost = (completion_tokens / 1_000_000) * rates["output"]
    return round(input_cost + output_cost, 6)


# ── TOKEN COUNTER ──
class TokenCounter:
    ENCODINGS = {
        "gpt-4o": "o200k_base",
        "gpt-4o-mini": "o200k_base",
        "gpt-4": "cl100k_base",
        "gpt-3.5-turbo": "cl100k_base",
    }
    
    def __init__(self):
        self._cache = {}
    
    def _get_encoding(self, model: str):
        encoding_name = self.ENCODINGS.get(model, "cl100k_base")
        if encoding_name not in self._cache:
            self._cache[encoding_name] = tiktoken.get_encoding(encoding_name)
        return self._cache[encoding_name]
    
    def count_tokens(self, text: str, model: str = "gpt-4o-mini") -> int:
        encoding = self._get_encoding(model)
        return len(encoding.encode(text))
    
    def count_message_tokens(self, messages: List[Dict[str, str]], model: str = "gpt-4o-mini") -> int:
        encoding = self._get_encoding(model)
        num_tokens = 0
        for message in messages:
            num_tokens += 3  # overhead per message
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
        num_tokens += 3  # reply priming
        return num_tokens
    
    def estimate_max_cost(self, messages: List[Dict[str, str]], model: str, max_tokens: int) -> dict:
        prompt_tokens = self.count_message_tokens(messages, model)
        total_tokens = prompt_tokens + max_tokens
        cost = calculate_cost(model, prompt_tokens, max_tokens)
        
        return {
            "estimated_prompt_tokens": prompt_tokens,
            "estimated_completion_tokens": max_tokens,
            "estimated_total_tokens": total_tokens,
            "estimated_max_cost_usd": cost,
            "model": model
        }


token_counter = TokenCounter()

