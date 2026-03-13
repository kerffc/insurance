"""Article fetching and summarisation into structured insurance updates."""

import logging
import re
import urllib.parse

import httpx

from config import HAIKU_MODEL
from services.anthropic_client import anthropic_create

logger = logging.getLogger(__name__)

SUMMARISE_SYSTEM = """You are a Singapore insurance advisor's assistant. Read a news article and produce a SHORT, clear update for clients.

Format (follow exactly, plain text only — no markdown, no ** or #):

Hi valued clients, here's a quick update on [topic]!

What's Changing
• [specific change]
• [specific change, include SGD amounts / % where relevant]

The Good News
• [positive aspect or saving]
• [another positive or benefit if applicable]

Your Current [Policy/Rider/Plan]
• [scenario 1, e.g. "Bought before X date"] → [outcome]
• [scenario 2] → [outcome]

What To Do
[1–2 sentences. Calm, actionable. No bullets here. End with: "Message me if you have questions!"]

Rules:
- Plain text only — no bold, no headers with #, no markdown
- Use • for bullets in the first three sections
- "What To Do" is a short paragraph, not bullets
- Section headers are plain text on their own line (no colon)
- Use → (arrow) for if/then scenarios in "Your Current" section
- Include SGD amounts and % where available
- Singapore English, professional and warm
- Target ~150 words. Be concise.
- If there is no clear "Good News", skip that section and use a relevant section instead"""


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


ANSWER_SYSTEM = """You are a Singapore insurance advisor's assistant. A client has asked a question.
Answer using ONLY the recent insurance updates provided below.

Rules:
- Plain text only — no markdown, no **bold**, no # headers
- Use • for bullet points if listing items
- If the answer is in the updates, give a clear specific answer with relevant numbers/dates
- If not covered, say so honestly and suggest they contact the advisor directly
- Under 150 words
- End with: "Message me if you have questions!" """


def answer_question(question: str, recent_updates: list[str]) -> str:
    """Answer a client's question using recent broadcast content as context."""
    updates_text = "\n---\n".join(recent_updates) if recent_updates else "No recent updates."
    response = anthropic_create(
        model=HAIKU_MODEL,
        max_tokens=600,
        system=ANSWER_SYSTEM,
        messages=[{"role": "user", "content": f"Recent updates:\n{updates_text}\n\nClient question: {question}"}],
    )
    return response.content[0].text.strip()


IMAGE_PROMPT_SYSTEM = """You are a visual designer. Given an insurance news summary, write a short prompt for a whiteboard-style diagram that illustrates the key concept.

Rules:
- Describe a simple diagram: Venn diagram, comparison table, flowchart, or arrow diagram
- Style must include: "clean hand-drawn whiteboard sketch, black ink on white background, minimalist"
- Include 2-3 key concepts or labels from the article as part of the diagram description
- No people, no faces, no logos
- Max 40 words total"""


def generate_diagram_prompt(summary: str) -> str:
    """Use Claude Haiku to generate an image generation prompt for the article."""
    response = anthropic_create(
        model=HAIKU_MODEL,
        max_tokens=80,
        system=IMAGE_PROMPT_SYSTEM,
        messages=[{"role": "user", "content": f"Summary:\n{summary}"}],
    )
    return response.content[0].text.strip()


def fetch_diagram_image(summary: str) -> bytes | None:
    """Generate a whiteboard-style diagram image via Pollinations.ai. Returns image bytes or None."""
    try:
        prompt = generate_diagram_prompt(summary)
        logger.info("Diagram prompt: %s", prompt)
        encoded = urllib.parse.quote(prompt, safe="")
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=500&model=flux&seed=42&nologo=true"
        logger.info("Fetching diagram from Pollinations.ai...")
        resp = httpx.get(url, timeout=90, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        logger.info("Pollinations response: status=%s content-type=%s size=%d bytes",
                    resp.status_code, content_type, len(resp.content))
        if not content_type.startswith("image/"):
            logger.warning("Pollinations returned non-image content-type: %s (first 200 chars: %s)",
                           content_type, resp.text[:200])
            return None
        return resp.content
    except httpx.TimeoutException:
        logger.warning("Pollinations.ai timed out after 90s — skipping image")
        return None
    except Exception as e:
        logger.warning("Failed to generate diagram image: %s", e)
        return None


def summarise_from_url(url: str, agent_notes: str = "") -> dict:
    """Fetch article from URL and summarise it."""
    article_text = fetch_article_text(url)
    summary = summarise_article(article_text, agent_notes)
    return {"url": url, "article_preview": article_text[:500] + "...", "summary": summary}
