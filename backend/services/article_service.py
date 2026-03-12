"""Article fetching and summarisation into structured insurance updates."""

import logging
import re

import httpx

from config import HAIKU_MODEL
from services.anthropic_client import anthropic_create

logger = logging.getLogger(__name__)

SUMMARISE_SYSTEM = """You are a Singapore insurance advisor's assistant. Your job is to read news articles \
about insurance policy changes, regulatory updates, or healthcare cost changes, and produce a clear, \
structured WhatsApp-friendly update message that an insurance agent can send to their clients.

Format guidelines:
- Start with a warm greeting: "Hi valued clients, here's a quick update on [topic]"
- Use numbered sections with emoji headers (1️⃣, 2️⃣, 3️⃣, etc.)
- Use bullet points (•) within sections for clarity
- Include concrete examples with dollar amounts where relevant (SGD)
- Include a section on "What should you do now?" with actionable advice
- End with a reassuring sign-off and invitation to reach out
- Tone: professional but warm, educational, not alarmist
- Language: Singapore English
- Use line breaks liberally for WhatsApp readability
- If the article mentions specific insurers (AIA, Prudential, Great Eastern, etc.), \
  include insurer-specific sections where relevant
- Keep it comprehensive but scannable — clients should be able to skim the key points
- Do NOT add a sign-off name — the agent will add their own

Key sections to include where applicable:
- Main Changes (what's changing)
- Why the changes are happening
- Impact on policyholders (with examples)
- Insurer-specific notes (if applicable)
- What should you do now (actionable steps)
- Closing reassurance + CTA to reach out"""


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
        max_tokens=2000,
        system=SUMMARISE_SYSTEM,
        messages=[{"role": "user", "content": "\n".join(user_parts)}],
    )
    return response.content[0].text.strip()


def summarise_from_url(url: str, agent_notes: str = "") -> dict:
    """Fetch article from URL and summarise it."""
    article_text = fetch_article_text(url)
    summary = summarise_article(article_text, agent_notes)
    return {"url": url, "article_preview": article_text[:500] + "...", "summary": summary}
