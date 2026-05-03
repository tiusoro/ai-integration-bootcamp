from typing import Dict
from datetime import datetime, timedelta

class MonthlyBudgetTracker:
    """
    Track per-user spending across requests.
    Resets monthly. Production would use Redis/DB.
    """
    
    def __init__(self):
        self.spending: Dict[str, float] = {}
        self.months: Dict[str, str] = {}  # user_id -> "YYYY-MM"
    
    def _get_current_month(self) -> str:
        return datetime.now().strftime("%Y-%m")
    
    def _reset_if_new_month(self, user_id: str):
        current = self._get_current_month()
        if self.months.get(user_id) != current:
            self.spending[user_id] = 0.0
            self.months[user_id] = current
    
    def spend(self, user_id: str, amount: float):
        self._reset_if_new_month(user_id)
        self.spending[user_id] = self.spending.get(user_id, 0.0) + amount
        return self.spending[user_id]
    
    def get_spent(self, user_id: str) -> float:
        self._reset_if_new_month(user_id)
        return self.spending.get(user_id, 0.0)
    
    def check_budget(self, user_id: str, monthly_limit: float) -> dict:
        spent = self.get_spent(user_id)
        remaining = monthly_limit - spent
        return {
            "spent": round(spent, 6),
            "limit": monthly_limit,
            "remaining": round(remaining, 6),
            "exceeded": spent >= monthly_limit,
            "month": self._get_current_month()
        }

budget_tracker = MonthlyBudgetTracker()

