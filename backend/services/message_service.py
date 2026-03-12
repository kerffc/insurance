"""Claude-powered notification message generation."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import HAIKU_MODEL, MESSAGE_BATCH_SIZE
from services.anthropic_client import anthropic_create

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional insurance advisor's assistant in Singapore. You help \
insurance agents compose clear, professional, and empathetic notification \
messages to their clients about policy changes.

Guidelines:
- Tone: Formal but warm and reassuring. The agent is the sender, not you.
- Language: English (Singapore standard). Use "Mr/Ms [Surname]" for salutation \
  unless the agent specifies otherwise.
- Structure: Brief greeting -> What changed -> How it affects them -> \
  What action (if any) the client should take -> Offer to discuss further.
- Keep messages concise: 100-180 words for WhatsApp/SMS, up to 250 for email.
- Do NOT include legal disclaimers or compliance boilerplate — the agent \
  will add those separately if needed.
- Reference the specific insurer and policy type naturally.
- Be sensitive: insurance changes can cause anxiety. Reassure where appropriate.
- For WhatsApp: use line breaks for readability, no HTML.
- For email: include a subject line as the first line prefixed with "Subject: ".
- For SMS: keep under 160 characters per segment, max 2 segments (320 chars total)."""


def _build_user_prompt(client: dict, change: dict, channel: str, agent_name: str) -> str:
    parts = [
        f"Generate a {channel} notification message for the following client about a policy change.",
        "",
        "Client:",
        f"- Name: {client['name']}",
        f"- Policy: {client['insurer']} {client['policy_type']} (Policy #{client['policy_number']})",
    ]
    if client.get("plan_name"):
        parts.append(f"- Plan: {client['plan_name']}")
    if client.get("remarks"):
        parts.append(f"- Agent notes: {client['remarks']}")
    parts.extend([
        "",
        "Policy Change:",
        f"- Insurer: {change['insurer']}",
        f"- What changed: {change['change_title']}",
        f"- Details: {change['change_description']}",
        f"- Effective date: {change['effective_date']}",
        f"- Impact: {change['impact_summary']}",
        "",
        f"The message should come from the agent (first person). Sign off with the agent's name: {agent_name}.",
    ])
    return "\n".join(parts)


def generate_message(client: dict, change: dict, channel: str, agent_name: str) -> str:
    """Generate a single notification message via Claude Haiku."""
    user_prompt = _build_user_prompt(client, change, channel, agent_name)
    response = anthropic_create(
        model=HAIKU_MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


def generate_messages_batch(
    clients: list[dict],
    change: dict,
    channel_map: dict[str, str],
    agent_name: str,
) -> list[dict]:
    """Generate messages for multiple clients in parallel.

    channel_map: {client_id: channel} e.g. {"uuid1": "whatsapp", "uuid2": "email"}
    Returns list of {"client_id": ..., "channel": ..., "message": ..., "error": ...}
    """
    results = []

    def _gen(client: dict) -> dict:
        channel = channel_map.get(client["id"], "whatsapp")
        try:
            msg = generate_message(client, change, channel, agent_name)
            return {"client_id": client["id"], "channel": channel, "message": msg, "error": None}
        except Exception as e:
            logger.error("Failed to generate message for %s: %s", client["name"], e)
            return {"client_id": client["id"], "channel": channel, "message": "", "error": str(e)}

    with ThreadPoolExecutor(max_workers=MESSAGE_BATCH_SIZE) as pool:
        futures = {pool.submit(_gen, c): c for c in clients}
        for future in as_completed(futures):
            results.append(future.result())

    return results
