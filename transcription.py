from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import os
import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -- WHISPER API INTEGRATION --

class TranscriptionRequest(BaseModel):
    audio_url: Optional[str] = Field(None, description="URL to audio file (mp3, wav, m4a)")
    audio_text: Optional[str] = Field(None, description="Fallback: paste transcript text directly")
    language: str = Field("en", description="Audio language code")
    contact_id: str = Field(..., min_length=1, description="CRM contact to associate with")

class TranscriptionResponse(BaseModel):
    contact_id: str
    transcript: str
    transcript_length_seconds: Optional[int]
    meeting_summary: str
    key_decisions: List[str]
    action_items: List[Dict]
    sentiment: Literal["positive", "neutral", "negative"]
    follow_up_date: Optional[str]
    crm_updates: List[Dict]
    calendar_reminders: List[Dict]
    cost_usd: float
    processing_time_ms: float

def transcribe_audio(audio_url: str, language: str = "en") -> str:
    """Use OpenAI Whisper to transcribe audio file."""
    try:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=open(audio_url, "rb") if os.path.exists(audio_url) else None,
            language=language
        )
        return response.text
    except Exception as e:
        # Fallback for URL-based audio or errors
        return f"[Transcription error: {str(e)}]. Use audio_text fallback."

def extract_meeting_intelligence(transcript: str, contact_name: str, company: str) -> Dict:
    """Extract structured data from meeting transcript using GPT-4o-mini."""
    
    system_prompt = f"""You are a meeting intelligence assistant.
Analyze this meeting transcript and extract structured data.

CONTEXT: Meeting with {contact_name} from {company}

EXTRACT:
1. meeting_summary: 2-3 sentence summary
2. key_decisions: List of decisions made
3. action_items: List of {{owner, task, deadline}} objects
4. sentiment: "positive", "neutral", or "negative"
5. follow_up_date: Next meeting date if mentioned (YYYY-MM-DD format)
6. crm_updates: List of {{field, value}} updates needed for CRM
7. calendar_reminders: List of {{title, date, description}} reminders

RULES:
- Be specific about owners and deadlines
- If no deadline, use "TBD"
- CRM updates should be actionable field-value pairs
- Return ONLY valid JSON, no markdown"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcript}
        ],
        temperature=0.2,
        max_tokens=1500
    )
    
    try:
        result = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        # Fallback: wrap raw text
        result = {
            "meeting_summary": response.choices[0].message.content[:200],
            "key_decisions": [],
            "action_items": [],
            "sentiment": "neutral",
            "follow_up_date": None,
            "crm_updates": [],
            "calendar_reminders": []
        }
    
    return result

def generate_crm_updates(contact_id: str, intelligence: Dict) -> List[Dict]:
    """Generate CRM update operations from extracted intelligence."""
    updates = []
    
    # Update last contact date
    updates.append({
        "field": "last_contact",
        "value": datetime.now().strftime("%Y-%m-%d"),
        "reason": "Meeting completed today"
    })
    
    # Update status if action items indicate progress
    action_items = intelligence.get("action_items", [])
    if any("proposal" in str(item).lower() for item in action_items):
        updates.append({
            "field": "status",
            "value": "proposal_sent",
            "reason": "Proposal discussed in meeting"
        })
    elif any("demo" in str(item).lower() for item in action_items):
        updates.append({
            "field": "status",
            "value": "demo_scheduled",
            "reason": "Demo scheduled in meeting"
        })
    
    # Add meeting notes
    updates.append({
        "field": "notes",
        "value": intelligence.get("meeting_summary", ""),
        "reason": "Meeting summary"
    })
    
    # Track sentiment
    updates.append({
        "field": "last_sentiment",
        "value": intelligence.get("sentiment", "neutral"),
        "reason": "Meeting sentiment analysis"
    })
    
    return updates

def generate_calendar_reminders(intelligence: Dict, contact_name: str) -> List[Dict]:
    """Generate calendar reminder events from action items."""
    reminders = []
    
    # Follow-up date reminder
    follow_up = intelligence.get("follow_up_date")
    if follow_up:
        reminders.append({
            "title": f"Follow-up: {contact_name}",
            "date": follow_up,
            "description": f"Next meeting scheduled. Summary: {intelligence.get('meeting_summary', '')[:100]}"
        })
    
    # Action item deadlines
    for item in intelligence.get("action_items", []):
        deadline = item.get("deadline", "TBD")
        if deadline != "TBD":
            reminders.append({
                "title": f"Action: {item.get('task', 'Task')[:50]}",
                "date": deadline,
                "description": f"Owner: {item.get('owner', 'Unassigned')}. From meeting with {contact_name}."
            })
    
    return reminders
