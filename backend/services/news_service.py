"""Auto-fetch Singapore insurance news from RSS feeds and news sources."""

import logging
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from config import HAIKU_MODEL, DATA_DIR
from services.anthropic_client import anthropic_create
from services.storage_service import read_json, write_json

logger = logging.getLogger(__name__)

SEEN_URLS_FILE = os.path.join(DATA_DIR, "seen_urls.json")

# RSS / search sources for Singapore insurance news
NEWS_SOURCES = [
    # Google News RSS for Singapore insurance
    "https://news.google.com/rss/search?q=singapore+insurance+policy+change&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=singapore+MAS+insurance+regulation&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=singapore+health+insurance+rider+medishield&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=singapore+CPF+insurance+update&hl=en-SG&gl=SG&ceid=SG:en",
    # MOH and government policy announcements
    "https://news.google.com/rss/search?q=MOH+singapore+integrated+shield+plan+IP+rider&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=MSF+MOH+singapore+insurance+subsidy+policy&hl=en-SG&gl=SG&ceid=SG:en",
    # Straits Times Singapore insurance and financial policy
    "https://news.google.com/rss/search?q=straits+times+singapore+insurance+premium+rider&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=singapore+lasting+power+attorney+LPA+CPF+insurance&hl=en-SG&gl=SG&ceid=SG:en",
    # CNA and Business Times broader coverage
    "https://news.google.com/rss/search?q=CNA+singapore+insurance+healthcare+medisave&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=business+times+singapore+insurance+premium+regulation&hl=en-SG&gl=SG&ceid=SG:en",
    # CPF and retirement planning
    "https://news.google.com/rss/search?q=singapore+CPF+retirement+savings+payout+changes&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=singapore+medisave+hospitalisation+claims+limits&hl=en-SG&gl=SG&ceid=SG:en",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

RELEVANCE_SYSTEM = """You are a Singapore insurance news filter. Given an article title and snippet, \
rate its relevance to Singapore insurance policyholders:

YES — Directly relevant: insurance policy/premium/coverage changes, MAS/MOH/MSF regulatory updates, \
IP riders, MediShield Life, CPF insurance changes, insurer announcements (AIA, Prudential, Great Eastern, \
NTUC Income, Manulife, AXA, FWD, Singlife etc.), healthcare costs affecting insurance.

MAYBE — Broadly useful: Singapore healthcare news, CPF/retirement planning, government financial schemes, \
hospital bills, Medisave usage, personal finance topics a policyholder would care about.

NO — Not relevant: overseas news, unrelated business/politics, general Singapore news with no insurance angle.

Reply with ONLY "YES", "MAYBE", or "NO"."""


def get_seen_urls() -> set[str]:
    data = read_json(SEEN_URLS_FILE)
    return set(data) if isinstance(data, list) else set()


def mark_urls_seen(urls: list[str]) -> None:
    seen = get_seen_urls()
    seen.update(urls)
    # Keep last 1000 URLs to prevent unbounded growth
    recent = sorted(seen)[-1000:]
    write_json(SEEN_URLS_FILE, recent)


def fetch_rss_articles(source_url: str) -> list[dict]:
    """Fetch articles from an RSS feed URL."""
    articles = []
    try:
        resp = httpx.get(source_url, headers=HEADERS, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)

        # Handle both RSS 2.0 and Atom formats
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")

            if title_el is not None and link_el is not None:
                articles.append({
                    "title": title_el.text or "",
                    "url": link_el.text or "",
                    "description": (desc_el.text or "")[:500],
                    "published": pub_el.text if pub_el is not None else "",
                })
    except Exception as e:
        logger.warning("Failed to fetch RSS from %s: %s", source_url, e)

    return articles


def check_relevance(title: str, description: str) -> str:
    """Use Claude to score article relevance. Returns 'YES', 'MAYBE', or 'NO'."""
    try:
        response = anthropic_create(
            model=HAIKU_MODEL,
            max_tokens=10,
            system=RELEVANCE_SYSTEM,
            messages=[{"role": "user", "content": f"Title: {title}\nSnippet: {description}"}],
        )
        score = response.content[0].text.strip().upper()
        return score if score in ("YES", "MAYBE") else "NO"
    except Exception as e:
        logger.warning("Relevance check failed: %s", e)
        return "NO"


def fetch_new_articles() -> list[dict]:
    """Fetch new, unseen, relevant articles from all sources."""
    seen = get_seen_urls()
    all_articles = []

    for source in NEWS_SOURCES:
        articles = fetch_rss_articles(source)
        logger.info("RSS %s → %d articles", source.split("q=")[1].split("&")[0], len(articles))
        for a in articles:
            if a["url"] not in seen:
                all_articles.append(a)

    # Deduplicate by URL
    unique = {}
    for a in all_articles:
        if a["url"] not in unique:
            unique[a["url"]] = a

    # Check relevance (limit to 12 to control API costs)
    candidates = list(unique.values())[:12]
    relevant = []
    new_urls = []

    maybes = []
    for a in candidates:
        new_urls.append(a["url"])
        score = check_relevance(a["title"], a["description"])
        if score == "YES":
            relevant.append(a)
        elif score == "MAYBE":
            maybes.append(a)

    # Fall back to MAYBE articles if nothing scored YES
    if not relevant and maybes:
        relevant = maybes[:1]
        logger.info("No YES articles found — using best MAYBE fallback: %s", maybes[0]["title"][:60])

    # Mark all checked URLs as seen (even irrelevant ones)
    if new_urls:
        mark_urls_seen(new_urls)

    logger.info("Daily digest: %d total unseen, %d candidates checked, %d relevant (%d maybe)",
                len(unique), len(candidates), len(relevant), len(maybes))
    return relevant, len(unique), len(candidates)
