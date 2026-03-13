"""Article fetching and summarisation into structured insurance updates."""

import logging
import re

import httpx

from config import HAIKU_MODEL
from services.anthropic_client import anthropic_create

logger = logging.getLogger(__name__)

SUMMARISE_SYSTEM = """You are a Singapore insurance advisor's assistant. Read a news article and produce a SHORT, clear update for clients.

Format (follow exactly, plain text only — no markdown, no ** or #):

Hi valued clients,
[One sentence summary of the key change and its impact.]

Here's what's changing:
• [specific change]
• [specific change, include SGD amounts / % where relevant]

What this means for you:
• [who is affected and how]
• [any deadlines or action needed]

Bottom line: [1–2 sentence plain-English summary. Warm, not alarmist. End with: "Drop me a message if you'd like to go through your plan together."]

Rules:
- Plain text only — no bold, no headers with #
- Use • for bullets
- Singapore English, professional and warm
- Target ~150 words. Be concise."""


def fetch_article_text(url: str) -> str:
    """Fetch article content from URL and return as text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
    resp.raise_for_status()
    html = resp.text

    # Basic HTML to text: strip tags, decode entities
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate to ~8000 chars to fit in context
    return text[:8000]


def summarise_article(article_text: str, agent_notes: str = "") -> str:
    """Generate a structured WhatsApp update from article text using Claude."""
    user_parts = [
        "Read the following article about insurance/healthcare changes in Singapore "
        "and produce a structured WhatsApp update message that an insurance agent can broadcast to clients.",
    ]
    if agent_notes:
        user_parts.append(f"\nAgent's additional notes/context: {agent_notes}")
    user_parts.append(f"\n---\nARTICLE:\n{article_text}\n---")

    response = anthropic_create(
        model=HAIKU_MODEL,
        max_tokens=800,
        system=SUMMARISE_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
    )
    return response.content[0].text.strip()


ADVISE_SYSTEM = """You are a Singapore insurance advisor's assistant. A client has shared their current policy details.
Based on the recent updates below, give them clear, personal advice on what (if anything) has changed for them.

Format rules (strictly follow):
- Plain text only — no markdown, no **bold**, no # headers
- Use plain section headers on their own line, e.g. "Good News" or "What To Do"
- Use bullet points (•) within sections
- Be specific to their insurer and policy type
- If nothing applies, say so clearly
- Under 150 words
- End with: "Message me if you have questions!" """


def advise_for_policy(insurer: str, policy_type: str, plan_name: str | None, recent_updates: list[str]) -> str:
    """Generate personalised advice for a client based on their policy and recent broadcasts."""
    updates_text = "\n---\n".join(recent_updates) if recent_updates else "No recent updates available."
    user_msg = (
        f"Client's Policy:\n"
        f"- Insurer: {insurer}\n"
        f"- Policy Type: {policy_type}\n"
        f"- Plan Name: {plan_name or 'not specified'}\n\n"
        f"Recent Updates:\n{updates_text}"
    )
    response = anthropic_create(
        model=HAIKU_MODEL,
        max_tokens=600,
        system=ADVISE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text.strip()


def summarise_from_url(url: str, agent_notes: str = "") -> dict:
    """Fetch article from URL and summarise it."""
    article_text = fetch_article_text(url)
    summary = summarise_article(article_text, agent_notes)
    return {"url": url, "article_preview": article_text[:500] + "...", "summary": summary}
