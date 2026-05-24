from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json

# -- MOCK CRM DATABASE (HubSpot/GoHighLevel style) --

CRM_CONTACTS = {
    "lead-001": {
        "name": "Sarah Chen",
        "email": "sarah.chen@techcorp.com",
        "company": "TechCorp Industries",
        "title": "VP of Operations",
        "industry": "manufacturing",
        "company_size": "200-500",
        "last_contact": "2026-05-20",
        "interactions": [
            {"type": "page_view", "page": "pricing", "date": "2026-05-18"},
            {"type": "page_view", "page": "pricing", "date": "2026-05-19"},
            {"type": "page_view", "page": "features", "date": "2026-05-20"},
            {"type": "email_open", "subject": "Product Update", "date": "2026-05-21"},
        ],
        "pain_points": ["inventory tracking", "supplier delays"],
        "budget_indication": "high",
        "status": "qualified"
    },
    "lead-002": {
        "name": "Marcus Johnson",
        "email": "marcus@retailplus.io",
        "company": "RetailPlus",
        "title": "CTO",
        "industry": "e-commerce",
        "company_size": "50-200",
        "last_contact": "2026-05-15",
        "interactions": [
            {"type": "page_view", "page": "blog", "date": "2026-05-10"},
            {"type": "demo_request", "date": "2026-05-12"},
        ],
        "pain_points": ["scaling support", "high cart abandonment"],
        "budget_indication": "medium",
        "status": "new"
    },
    "lead-003": {
        "name": "Elena Rodriguez",
        "email": "elena@healthfirst.org",
        "company": "HealthFirst Medical",
        "title": "Director of IT",
        "industry": "healthcare",
        "company_size": "500+",
        "last_contact": "2026-05-22",
        "interactions": [
            {"type": "page_view", "page": "enterprise", "date": "2026-05-22"},
            {"type": "whitepaper_download", "topic": "HIPAA Compliance", "date": "2026-05-22"},
        ],
        "pain_points": ["HIPAA compliance", "patient data security"],
        "budget_indication": "enterprise",
        "status": "hot"
    }
}

# -- LEAD SCORING ENGINE --

class MeetingTranscribeRequest(BaseModel):
    meeting_text: str = Field(..., min_length=10, description="Raw meeting transcript text")

class LeadScore(BaseModel):
    lead_id: str
    name: str
    company: str
    score: int = Field(..., ge=1, le=100)
    score_breakdown: Dict[str, int]
    priority: Literal["hot", "warm", "cold"]
    recommended_action: str
    last_updated: str

def calculate_lead_score(lead_id: str) -> LeadScore:
    """Calculate lead quality score based on behavior signals."""
    contact = CRM_CONTACTS.get(lead_id)
    if not contact:
        raise ValueError(f"Lead {lead_id} not found")
    
    score_breakdown = {}
    
    # 1. Interaction frequency (max 30 points)
    interaction_count = len(contact["interactions"])
    score_breakdown["interaction_frequency"] = min(interaction_count * 10, 30)
    
    # 2. Recency (max 25 points)
    last_contact = datetime.strptime(contact["last_contact"], "%Y-%m-%d")
    days_since_contact = (datetime.now() - last_contact).days
    if days_since_contact <= 2:
        score_breakdown["recency"] = 25
    elif days_since_contact <= 7:
        score_breakdown["recency"] = 15
    elif days_since_contact <= 14:
        score_breakdown["recency"] = 5
    else:
        score_breakdown["recency"] = 0
    
    # 3. Intent signals (max 25 points)
    intent_score = 0
    for interaction in contact["interactions"]:
        if interaction["type"] == "demo_request":
            intent_score += 25
        elif interaction["type"] == "whitepaper_download":
            intent_score += 20
        elif interaction["type"] == "page_view" and interaction.get("page") == "pricing":
            intent_score += 15
        elif interaction["type"] == "email_open":
            intent_score += 5
    score_breakdown["intent_signals"] = min(intent_score, 25)
    
    # 4. Budget indication (max 20 points)
    budget_map = {"low": 5, "medium": 10, "high": 15, "enterprise": 20}
    score_breakdown["budget_fit"] = budget_map.get(contact["budget_indication"], 10)
    
    # Total score
    total_score = sum(score_breakdown.values())
    
    # Priority classification
    if total_score >= 75:
        priority = "hot"
        recommended_action = "Call within 24 hours. High intent + budget."
    elif total_score >= 50:
        priority = "warm"
        recommended_action = "Send personalized email + schedule demo."
    else:
        priority = "cold"
        recommended_action = "Nurture with educational content."
    
    return LeadScore(
        lead_id=lead_id,
        name=contact["name"],
        company=contact["company"],
        score=total_score,
        score_breakdown=score_breakdown,
        priority=priority,
        recommended_action=recommended_action,
        last_updated=datetime.now().isoformat()
    )

# -- EMAIL DRAFTING ENGINE --

class EmailDraftRequest(BaseModel):
    lead_id: str = Field(..., min_length=1)
    email_type: Literal["follow_up", "cold_outreach", "demo_request", "proposal"] = "follow_up"
    tone: Literal["professional", "friendly", "urgent"] = "professional"
    max_length_words: int = Field(200, ge=50, le=500)
    include_cta: bool = True

class EmailDraftResponse(BaseModel):
    lead_id: str
    recipient: Dict
    subject: str
    body: str
    tone: str
    word_count: int
    personalization_signals: List[str]
    cost_usd: float
    generated_at: str

def build_email_context(lead_id: str) -> str:
    """Build rich context string from CRM data for AI email generation."""
    contact = CRM_CONTACTS.get(lead_id)
    if not contact:
        raise ValueError(f"Lead {lead_id} not found")
    
    # Format interaction history
    interactions = []
    for i in contact["interactions"][-5:]:  # Last 5 interactions
        if i["type"] == "page_view":
            interactions.append(f"Viewed {i['page']} page on {i['date']}")
        elif i["type"] == "email_open":
            interactions.append(f"Opened email '{i['subject']}' on {i['date']}")
        elif i["type"] == "demo_request":
            interactions.append(f"Requested demo on {i['date']}")
        elif i["type"] == "whitepaper_download":
            interactions.append(f"Downloaded whitepaper '{i['topic']}' on {i['date']}")
    
    context = f"""LEAD PROFILE:
Name: {contact['name']}
Title: {contact['title']}
Company: {contact['company']}
Industry: {contact['industry']}
Company Size: {contact['company_size']}

PAIN POINTS: {', '.join(contact['pain_points'])}

RECENT ACTIVITY:
{chr(10).join(interactions)}

BUDGET INDICATION: {contact['budget_indication']}
STATUS: {contact['status']}
LAST CONTACT: {contact['last_contact']}"""
    
    return context

