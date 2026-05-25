"""
alerting.py
Slack/Discord webhook integration for critical alerts.
Optional: only works if SLACK_WEBHOOK_URL or DISCORD_WEBHOOK_URL env vars are set.
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Webhook URLs from environment variables
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def send_slack_alert(message: str, details: Dict[str, Any] = None) -> bool:
    """Send alert to Slack webhook."""
    if not SLACK_WEBHOOK_URL:
        return False

    try:
        import requests
        payload = {
            "text": f"🚨 AI Bootcamp Alert: {message}",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Alert:* {message}\n"
                        f"*Time:* {datetime.now(timezone.utc).isoformat()}\n"
                        f"*Details:* {json.dumps(details, default=str) if details else 'None'}"
                    )
                }
            }]
        }
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to send Slack alert: {e}")
        return False

def send_discord_alert(message: str, details: Dict[str, Any] = None) -> bool:
    """Send alert to Discord webhook."""
    if not DISCORD_WEBHOOK_URL:
        return False

    try:
        import requests
        
        payload = {
            "content": (
                f"🚨 **AI Bootcamp Alert**\n"
                f"**Message:** {message}\n"
                f"**Time:** {datetime.now(timezone.utc).isoformat()}"
            ),
            "embeds": [{
                "title": "Details",
                "description": (
                    json.dumps(details, default=str, indent=2)
                    if details else "No details"
                ),
                "color": 15158332
            }]
        }

        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        return response.status_code == 204
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")
        return False

def send_alert(message: str, details: Dict[str, Any] = None, channels: List[str] = None) -> Dict[str, bool]:
    """Send alert to all configured channels."""
    channels = channels or ["slack", "discord"]
    results = {}

    if "slack" in channels:
        results["slack"] = send_slack_alert(message, details)
    if "discord" in channels:
        results["discord"] = send_discord_alert(message, details)

    return results


