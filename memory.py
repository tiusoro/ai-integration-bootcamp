from typing import List, Dict, Optional
from datetime import datetime, timedelta
import hashlib

class ConversationMemory:
    """
    In-memory conversation store with TTL cleanup.
    Production would use Redis or PostgreSQL.
    """
    
    def __init__(self, max_messages: int = 10, ttl_minutes: int = 30):
        self.sessions: Dict[str, List[dict]] = {}
        self.timestamps: Dict[str, datetime] = {}
        self.max_messages = max_messages
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def _generate_session_id(self, user_id: str, seed: str = "") -> str:
        """Deterministic session ID from user_id + optional seed."""
        hash_input = f"{user_id}:{seed}".encode()
        return hashlib.md5(hash_input).hexdigest()[:12]
    
    def get_history(self, session_id: str) -> List[dict]:
        self._cleanup(session_id)
        if session_id not in self.sessions:
            return []
        # Return only role/content for OpenAI API
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.sessions[session_id]
        ]
    
    def add_message(self, session_id: str, role: str, content: str) -> None:
        if session_id not in self.sessions:
            self.sessions[session_id] = []
            self.timestamps[session_id] = datetime.now()
        
        self.sessions[session_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # FIFO: keep only last N messages
        if len(self.sessions[session_id]) > self.max_messages:
            self.sessions[session_id] = self.sessions[session_id][-self.max_messages:]
    
    def get_session_info(self, session_id: str) -> dict:
        self._cleanup(session_id)
        history = self.sessions.get(session_id, [])
        return {
            "session_id": session_id,
            "message_count": len(history),
            "created_at": self.timestamps.get(session_id, datetime.now()).isoformat(),
            "ttl_minutes": self.ttl.total_seconds() / 60
        }
    
    def clear_session(self, session_id: str) -> bool:
        """Returns True if session existed and was cleared."""
        existed = session_id in self.sessions
        self.sessions.pop(session_id, None)
        self.timestamps.pop(session_id, None)
        return existed
    
    def _cleanup(self, session_id: str) -> None:
        """Remove expired sessions."""
        if session_id in self.timestamps:
            if datetime.now() - self.timestamps[session_id] > self.ttl:
                del self.sessions[session_id]
                del self.timestamps[session_id]

# Global instance (singleton for this bootcamp)
memory = ConversationMemory(max_messages=10, ttl_minutes=30)

