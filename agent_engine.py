"""
agent_engine.py
Multi-Step AI Agent Architecture for FastAPI.
State machine, step registry, tool chaining, human-in-the-loop, error recovery.
Uses PostgreSQL for state persistence (via database.py).
"""

import os
import uuid
import json
import time
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
from functools import wraps

from pydantic import BaseModel, Field
from openai import OpenAI
from database import get_connection  # Your existing PostgreSQL connection

# Load .env for OpenAI key
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ──────────────────────────────────────────────
# 1. AGENT STATE ENUM
# ──────────────────────────────────────────────

class AgentState(str, Enum):
    """Possible states for an agent run."""
    IDLE = "idle"           # Not started
    RUNNING = "running"     # Currently executing a step
    PAUSED = "paused"       # Waiting for human approval
    COMPLETED = "completed" # All steps finished successfully
    FAILED = "failed"       # Step failed, no recovery possible
    CANCELLED = "cancelled" # Manually stopped

# ──────────────────────────────────────────────
# 2. PYDANTIC MODELS
# ──────────────────────────────────────────────

class AgentStepConfig(BaseModel):
    """Configuration for a single step in the agent workflow."""
    name: str = Field(..., description="Step identifier")
    description: str = Field(..., description="What this step does")
    function_name: str = Field(..., description="Name of function to call")
    next_step: Optional[str] = Field(None, description="Next step name, or None if final")
    requires_approval: bool = Field(False, description="Pause for human approval")
    max_retries: int = Field(2, ge=0, le=5, description="Retry attempts on failure")
    timeout_seconds: int = Field(60, ge=10, le=300)

class AgentRunRequest(BaseModel):
    """Start a new agent workflow."""
    workflow_name: str = Field(..., description="Name of predefined workflow")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="Initial data for step 1")
    user_id: Optional[str] = Field(None, description="For attribution")

class AgentApprovalRequest(BaseModel):
    """Human approval/rejection for a paused step."""
    approved: bool = Field(..., description="True to continue, False to cancel")
    feedback: Optional[str] = Field(None, description="Human feedback/notes")

class AgentStatusResponse(BaseModel):
    """Current status of an agent run."""
    run_id: str
    workflow_name: str
    state: str
    current_step: Optional[str]
    completed_steps: List[str]
    failed_steps: List[Dict[str, Any]]
    results: Dict[str, Any]
    started_at: str
    updated_at: str
    waiting_for_approval: bool

# ──────────────────────────────────────────────
# 3. STEP REGISTRY — Define Reusable Agent Steps
# ──────────────────────────────────────────────

"""
STEP FUNCTIONS: Each takes (input_data, context) and returns (output_data, status)
Status: "success", "needs_review", "failed"
"""

def step_research_topic(input_data: Dict, context: Dict) -> tuple[Dict, str]:
    """
    Step 1: Research a topic using OpenAI.
    Input: {"topic": "AI in healthcare"}
    Output: {"research_notes": "...", "sources": [...]}
    """
    topic = input_data.get("topic", "general topic")
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {"role": "system", "content": "You are a research assistant. Provide comprehensive research notes with key findings."},
            {"role": "user", "content": f"Research this topic thoroughly: {topic}"}
        ],
        max_tokens=1000
    )
    
    research = response.choices[0].message.content
    
    return {
        "research_notes": research,
        "topic": topic,
        "word_count": len(research.split())
    }, "success"

def step_draft_content(input_data: Dict, context: Dict) -> tuple[Dict, str]:
    """
    Step 2: Draft content based on research.
    Input: {"research_notes": "...", "topic": "..."}
    Output: {"draft": "...", "format": "markdown"}
    """
    research = input_data.get("research_notes", "")
    topic = input_data.get("topic", "")
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[
            {"role": "system", "content": "You are a content writer. Create a well-structured draft based on research notes."},
            {"role": "user", "content": f"Write a draft about '{topic}' based on this research:\n\n{research}"}
        ],
        max_tokens=1500
    )
    
    draft = response.choices[0].message.content
    
    return {
        "draft": draft,
        "format": "markdown",
        "char_count": len(draft)
    }, "success"

def step_review_content(input_data: Dict, context: Dict) -> tuple[Dict, str]:
    """
    Step 3: Review draft quality (auto-check before human review).
    Input: {"draft": "..."}
    Output: {"quality_score": 85, "issues": [...]}
    """
    draft = input_data.get("draft", "")
    
    # Simple heuristic: length check + keyword check
    score = min(100, max(50, len(draft) // 20))
    issues = []
    
    if len(draft) < 200:
        issues.append("Draft too short")
        score -= 20
    
    if "conclusion" not in draft.lower():
        issues.append("Missing conclusion section")
        score -= 10
    
    status = "needs_review" if score < 70 else "success"
    
    return {
        "quality_score": score,
        "issues": issues,
        "auto_approved": score >= 80
    }, status

def step_finalize_content(input_data: Dict, context: Dict) -> tuple[Dict, str]:
    """
    Step 4: Finalize and format content.
    Input: {"draft": "...", "feedback": "..."}
    Output: {"final_content": "...", "version": "1.0"}
    """
    draft = input_data.get("draft", "")
    feedback = input_data.get("feedback", "No feedback provided")
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.5,
        messages=[
            {"role": "system", "content": "You are an editor. Incorporate feedback and produce final polished content."},
            {"role": "user", "content": f"Finalize this draft incorporating feedback:\n\nDRAFT:\n{draft}\n\nFEEDBACK:\n{feedback}"}
        ],
        max_tokens=1500
    )
    
    final = response.choices[0].message.content
    
    return {
        "final_content": final,
        "version": "1.0",
        "final_char_count": len(final)
    }, "success"

# Registry of available steps
STEP_REGISTRY: Dict[str, Callable] = {
    "research_topic": step_research_topic,
    "draft_content": step_draft_content,
    "review_content": step_review_content,
    "finalize_content": step_finalize_content
}

# ──────────────────────────────────────────────
# 4. PREDEFINED WORKFLOWS
# ──────────────────────────────────────────────

# WORKFLOWS = {
#     "content_creation": [
#         AgentStepConfig(name="research", function_name="research_topic", next_step="draft", requires_approval=False),
#         AgentStepConfig(name="draft", function_name="draft_content", next_step="review", requires_approval=False),
#         AgentStepConfig(name="review", function_name="review_content", next_step="finalize", requires_approval=True),
#         AgentStepConfig(name="finalize", function_name="finalize_content", next_step=None, requires_approval=False)
#     ],
#     "quick_research": [
#         AgentStepConfig(name="research", function_name="research_topic", next_step=None, requires_approval=False)
#     ]
# }


WORKFLOWS = {
    "content_creation": [
        AgentStepConfig(
            name="research",
            description="Research the topic using AI",
            function_name="research_topic",
            next_step="draft",
            requires_approval=False
        ),
        AgentStepConfig(
            name="draft",
            description="Draft content based on research",
            function_name="draft_content",
            next_step="review",
            requires_approval=False
        ),
        AgentStepConfig(
            name="review",
            description="Review draft quality before human approval",
            function_name="review_content",
            next_step="finalize",
            requires_approval=True
        ),
        AgentStepConfig(
            name="finalize",
            description="Finalize content with human feedback",
            function_name="finalize_content",
            next_step=None,
            requires_approval=False
        )
    ],
    "quick_research": [
        AgentStepConfig(
            name="research",
            description="Quick research on a topic",
            function_name="research_topic",
            next_step=None,
            requires_approval=False
        )
    ]
}


# ──────────────────────────────────────────────
# 5. DATABASE INIT — Agent State Tables
# ──────────────────────────────────────────────

def init_agent_tables():
    """Create agent state tables in PostgreSQL."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workflow_name VARCHAR(100) NOT NULL,
            state VARCHAR(20) DEFAULT 'idle',
            current_step VARCHAR(50),
            completed_steps JSONB DEFAULT '[]',
            failed_steps JSONB DEFAULT '[]',
            results JSONB DEFAULT '{}',
            input_data JSONB DEFAULT '{}',
            started_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP,
            user_id VARCHAR(255),
            waiting_for_approval BOOLEAN DEFAULT FALSE,
            approval_notes TEXT
        );
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

# ──────────────────────────────────────────────
# 6. AGENT STATE MANAGEMENT
# ──────────────────────────────────────────────

def create_agent_run(workflow_name: str, input_data: Dict, user_id: str = None) -> str:
    """Initialize a new agent run in PostgreSQL."""
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO agent_runs (id, workflow_name, state, input_data, started_at, user_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (run_id, workflow_name, AgentState.IDLE, json.dumps(input_data), now, user_id))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return run_id

def get_agent_status(run_id: str) -> Optional[Dict[str, Any]]:
    """Get current status of an agent run."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, workflow_name, state, current_step, completed_steps, 
               failed_steps, results, started_at, updated_at, completed_at,
               waiting_for_approval, approval_notes
        FROM agent_runs WHERE id = %s
    """, (run_id,))
    
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row:
        return None
    
    return {
        "run_id": str(row[0]),
        "workflow_name": row[1],
        "state": row[2],
        "current_step": row[3],
        "completed_steps": row[4] if isinstance(row[4], list) else json.loads(row[4] or '[]'),
        "failed_steps": row[5] if isinstance(row[5], list) else json.loads(row[5] or '[]'),
        "results": row[6] if isinstance(row[6], dict) else json.loads(row[6] or '{}'),
        "started_at": str(row[7]),
        "updated_at": str(row[8]),
        "completed_at": str(row[9]) if row[9] else None,
        "waiting_for_approval": row[10],
        "approval_notes": row[11]
    }

def update_agent_state(run_id: str, state: str, current_step: str = None, 
                       results: Dict = None, completed_steps: List = None,
                       failed_steps: List = None, waiting: bool = False):
    """Update agent run state in PostgreSQL."""
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        UPDATE agent_runs 
        SET state = %s, current_step = %s, results = %s, 
            completed_steps = %s, failed_steps = %s, updated_at = %s,
            waiting_for_approval = %s
        WHERE id = %s
    """, (
        state, current_step, json.dumps(results or {}),
        json.dumps(completed_steps or []), json.dumps(failed_steps or []),
        now, waiting, run_id
    ))
    
    conn.commit()
    cursor.close()
    conn.close()

def complete_agent_run(run_id: str, final_results: Dict):
    """Mark agent run as completed."""
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        UPDATE agent_runs 
        SET state = %s, results = %s, completed_at = %s, updated_at = %s,
            current_step = NULL, waiting_for_approval = FALSE
        WHERE id = %s
    """, (AgentState.COMPLETED, json.dumps(final_results), now, now, run_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def fail_agent_run(run_id: str, error: str, failed_step: str):
    """Mark agent run as failed."""
    conn = get_connection()
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        UPDATE agent_runs 
        SET state = %s, updated_at = %s, current_step = NULL,
            waiting_for_approval = FALSE
        WHERE id = %s
    """, (AgentState.FAILED, now, run_id))
    
    conn.commit()
    cursor.close()
    conn.close()

# ──────────────────────────────────────────────
# 7. AGENT EXECUTION ENGINE
# ──────────────────────────────────────────────

def execute_step(step_config: AgentStepConfig, input_data: Dict, context: Dict) -> tuple[Dict, str]:
    """
    Execute a single step with retry logic.
    Returns: (output_data, status)
    """
    func = STEP_REGISTRY.get(step_config.function_name)
    if not func:
        raise ValueError(f"Unknown step function: {step_config.function_name}")
    
    last_error = None
    
    for attempt in range(step_config.max_retries + 1):
        try:
            output, status = func(input_data, context)
            
            if status == "success":
                return output, "success"
            elif status == "needs_review":
                return output, "needs_review"
            else:
                last_error = f"Step returned status: {status}"
                
        except Exception as e:
            last_error = str(e)
            if attempt < step_config.max_retries:
                time.sleep(1)  # Brief pause before retry
    
    # All retries exhausted
    return {"error": last_error, "traceback": traceback.format_exc()}, "failed"

def run_agent_workflow(run_id: str):
    """
    Main execution loop. Runs steps sequentially until completion, failure, or human pause.
    This should be called asynchronously (background task) in production.
    """
    # Get run details
    status = get_agent_status(run_id)
    if not status:
        return
    
    workflow_name = status["workflow_name"]
    workflow = WORKFLOWS.get(workflow_name, [])
    
    if not workflow:
        fail_agent_run(run_id, f"Unknown workflow: {workflow_name}", "init")
        return
    
    # Initialize
    update_agent_state(run_id, AgentState.RUNNING)
    
    # Build step lookup
    step_map = {step.name: step for step in workflow}
    
    # Start with first step
    current_step_name = workflow[0].name
    all_results = status.get("results", {})
    completed = []
    failed = []
    
    # Get initial input
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT input_data FROM agent_runs WHERE id = %s", (run_id,))
    input_row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if input_row and input_row[0]:
        step_input = input_row[0] if isinstance(input_row[0], dict) else json.loads(input_row[0])
    else:
        step_input = {}

    
    # Execution loop
    while current_step_name:
        step_config = step_map.get(current_step_name)
        if not step_config:
            fail_agent_run(run_id, f"Step not found: {current_step_name}", current_step_name)
            return
        
        # Update current step
        update_agent_state(run_id, AgentState.RUNNING, current_step_name)
        
        # Execute
        context = {
            "run_id": run_id,
            "workflow_name": workflow_name,
            "all_results": all_results
        }
        
        output, status = execute_step(step_config, step_input, context)
        
        if status == "success":
            # Store result
            all_results[current_step_name] = output
            completed.append(current_step_name)
            
            # Move to next step
            current_step_name = step_config.next_step
            
        elif status == "needs_review":
            # Pause for human approval
            all_results[current_step_name] = output
            completed.append(current_step_name)
            
            update_agent_state(
                run_id, AgentState.PAUSED, current_step_name,
                all_results, completed, failed, waiting=True
            )
            return  # Exit loop, wait for human
            
        else:  # failed
            failed.append({
                "step": current_step_name,
                "error": output.get("error", "Unknown error"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            update_agent_state(
                run_id, AgentState.FAILED, None,
                all_results, completed, failed
            )
            return
    
    # All steps completed
    complete_agent_run(run_id, all_results)

def approve_and_continue(run_id: str, approved: bool, feedback: str = None) -> Dict[str, Any]:
    """
    Human approves a paused step. Continue workflow or cancel.
    """
    status = get_agent_status(run_id)
    if not status:
        raise ValueError("Agent run not found")
    
    if status["state"] != AgentState.PAUSED:
        raise ValueError(f"Agent is not paused. Current state: {status['state']}")
    
    if not approved:
        # Cancel the run
        conn = get_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            UPDATE agent_runs 
            SET state = %s, updated_at = %s, approval_notes = %s,
                waiting_for_approval = FALSE
            WHERE id = %s
        """, (AgentState.CANCELLED, now, feedback or "Cancelled by user", run_id))
        conn.commit()
        cursor.close()
        conn.close()
        
        return {"message": "Agent run cancelled", "run_id": run_id}
    
    # Approved — continue workflow
    workflow_name = status["workflow_name"]
    workflow = WORKFLOWS.get(workflow_name, [])
    step_map = {step.name: step for step in workflow}
    
    # Find next step after the paused one
    current_step = status["current_step"]
    current_config = step_map.get(current_step)
    
    if not current_config:
        return {"error": f"Current step not found: {current_step}"}
    
    # Add feedback to results
    results = status.get("results", {})
    if current_step in results:
        results[current_step]["human_feedback"] = feedback
    
    # Determine next step
    next_step = current_config.next_step
    
    if not next_step:
        # This was the last step
        complete_agent_run(run_id, results)
        return {"message": "Workflow completed after approval", "run_id": run_id, "results": results}
    
    # Continue with next step
    update_agent_state(run_id, AgentState.RUNNING, next_step, results, 
                       status.get("completed_steps", []), 
                       status.get("failed_steps", []))
    
    # In production, trigger background task here
    # For bootcamp, we'll run synchronously in the endpoint
    return {"message": "Continuing workflow", "run_id": run_id, "next_step": next_step}