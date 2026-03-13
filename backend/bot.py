"""Telegram bot for Insurance Update Automation.

Daily auto-updates:
- Fetches Singapore insurance news from Google News RSS
- Claude summarises relevant articles into structured updates
- Broadcasts to all subscribers daily at configured time (default 9am SGT)

Agent (admin) manual commands:
- /summarise <url> — manually summarise + broadcast an article
- /paste <text> — summarise pasted text + broadcast
- /daily — trigger daily digest now (testing)
- /subscribers — list subscribers
- /history — broadcast history

Client commands:
- /start — subscribe to updates
- /stop — unsubscribe
"""

import asyncio
import io
import logging
import os
import re
import threading
from datetime import time as dt_time, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv

load_dotenv()

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from services.storage_service import ensure_dirs, save_user_policy, get_user_policy, get_all_user_policies
from services.article_service import summarise_from_url, summarise_article, fetch_article_text, advise_for_policy, fetch_diagram_image, answer_question
from services.news_service import fetch_new_articles
from services.subscriber_service import (
    add_subscriber,
    remove_subscriber,
    get_active_subscribers,
    get_subscribers,
    save_broadcast,
    get_broadcasts,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_IDS = [
    int(x.strip()) for x in os.environ.get("ADMIN_CHAT_IDS", "").split(",") if x.strip()
]
# Daily digest schedule in SGT (UTC+8) — comma-separated HH:MM times
# Falls back to legacy DAILY_HOUR / DAILY_MINUTE if DIGEST_TIMES not set
_DIGEST_TIMES_RAW = os.environ.get("DIGEST_TIMES", "")
DIGEST_TIMES: list[tuple[int, int]] = []
for _t in _DIGEST_TIMES_RAW.split(","):
    _t = _t.strip()
    if _t:
        _h, _m = _t.split(":")
        DIGEST_TIMES.append((int(_h), int(_m)))
if not DIGEST_TIMES:
    # Legacy single-time fallback
    DIGEST_TIMES = [(int(os.environ.get("DAILY_HOUR", "9")), int(os.environ.get("DAILY_MINUTE", "0")))]

# Agent sign-off (appended to every broadcast)
AGENT_SIGNOFF = os.environ.get("AGENT_SIGNOFF", "")

# SGT timezone
SGT = timezone(timedelta(hours=8))

# Conversation states — review flow
REVIEW_MESSAGE, EDIT_MESSAGE = range(2)

# Conversation states — policy advisor flow
POLICY_INSURER, POLICY_TYPE, POLICY_PLAN = range(3)

# Store pending messages per admin
_pending_messages: dict[int, dict] = {}

# Temp policy data during /mypolicy conversation
_policy_store: dict[int, dict] = {}


def is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_CHAT_IDS


def _client_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📰 Latest Updates", callback_data="nav_latest"),
        InlineKeyboardButton("🚫 Unsubscribe", callback_data="nav_stop"),
    ]])


def _unsubscribed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ Subscribe", callback_data="nav_start"),
    ]])


def _review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📢 Broadcast", callback_data="review_broadcast"),
        InlineKeyboardButton("✏️ Edit", callback_data="review_edit"),
        InlineKeyboardButton("❌ Cancel", callback_data="review_cancel"),
    ]])


def _insurer_keyboard() -> InlineKeyboardMarkup:
    insurers = ["AIA", "Prudential", "Great Eastern", "NTUC Income", "Manulife", "Other"]
    rows = []
    for i in range(0, len(insurers), 2):
        rows.append([
            InlineKeyboardButton(ins, callback_data=f"policy_insurer_{ins}")
            for ins in insurers[i:i+2]
        ])
    return InlineKeyboardMarkup(rows)


def _policy_type_keyboard() -> InlineKeyboardMarkup:
    types = ["Health/Medical", "Life", "Critical Illness", "Other"]
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t, callback_data=f"policy_type_{t}")
        for t in types[:2]
    ], [
        InlineKeyboardButton(t, callback_data=f"policy_type_{t}")
        for t in types[2:]
    ]])


def _plan_skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Skip", callback_data="policy_skip"),
    ]])


def _split_message(text: str, max_len: int = 4096) -> list[str]:
    """Split a long message at newlines to fit Telegram's 4096-char limit."""
    if len(text) <= max_len:
        return [text]
    parts = []
    while len(text) > max_len:
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        parts.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    if text:
        parts.append(text)
    return parts


async def _broadcast_to_subscribers(bot, message: str, subscribers: list[dict], image_bytes: bytes | None = None) -> tuple[int, int]:
    """Send message (and optional image) to all subscribers. Returns (sent_count, failed_count)."""
    sent_count = 0
    failed_count = 0
    for sub in subscribers:
        try:
            if image_bytes:
                try:
                    buf = io.BytesIO(image_bytes)
                    buf.name = "diagram.jpg"
                    await bot.send_photo(chat_id=sub["chat_id"], photo=buf)
                    logger.info("Photo sent OK to %s (%d bytes)", sub["chat_id"], len(image_bytes))
                except Exception as img_err:
                    logger.error("Photo send FAILED for %s: %s", sub["chat_id"], img_err)
            for chunk in _split_message(message):
                await bot.send_message(chat_id=sub["chat_id"], text=chunk)
            sent_count += 1
        except Exception as e:
            logger.warning("Failed to send to %s: %s", sub["chat_id"], e)
            failed_count += 1
    return sent_count, failed_count


# ── Daily digest job ─────────────────────────────────────────────────────────

async def daily_digest(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job: fetch news, summarise, broadcast to subscribers."""
    logger.info("Running daily digest...")

    subscribers = get_active_subscribers()
    if not subscribers:
        logger.info("No subscribers — skipping daily digest.")
        for admin_id in ADMIN_CHAT_IDS:
            try:
                await context.bot.send_message(admin_id, "Daily digest: No subscribers yet.")
            except Exception:
                pass
        return

    # Fetch new relevant articles
    articles = await asyncio.to_thread(fetch_new_articles)
    if not articles:
        logger.info("Daily digest: no new relevant articles this run.")
        return  # No admin notification — this runs 3× per day, silence is fine

    logger.info("Found %d new relevant articles", len(articles))

    # Summarise each article and broadcast (cap at 3 per day)
    for article in articles[:3]:
        try:
            article_text = await asyncio.to_thread(fetch_article_text, article["url"])
            summary = await asyncio.to_thread(summarise_article, article_text)

            if AGENT_SIGNOFF:
                summary += f"\n\n{AGENT_SIGNOFF}"

            image_bytes = await asyncio.to_thread(fetch_diagram_image, summary)

            sent_count, failed_count = await _broadcast_to_subscribers(
                context.bot, summary, subscribers, image_bytes
            )

            save_broadcast(summary, sent_to=sent_count, source_url=article["url"])
            logger.info("Broadcast '%s' to %d subscribers", article["title"][:50], sent_count)

            await _send_personalised_followups(context.bot, summary, subscribers)

            for admin_id in ADMIN_CHAT_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"Daily digest sent:\n{article['title']}\n{article['url']}\n→ {sent_count} subscribers"
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error("Failed to process article '%s': %s", article.get("title", "?"), e)
            for admin_id in ADMIN_CHAT_IDS:
                try:
                    await context.bot.send_message(admin_id, f"Failed to process: {article.get('title', '?')}\n{e}")
                except Exception:
                    pass


# ── Client commands ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribe to insurance updates."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    is_new = add_subscriber(chat_id, first_name=user.first_name or "", username=user.username or "")

    if is_new:
        await update.message.reply_text(
            f"Hi {user.first_name}! You're now subscribed to daily insurance updates.",
            reply_markup=_client_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"Hi {user.first_name}! You're already subscribed.",
            reply_markup=_client_keyboard(),
        )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from updates."""
    chat_id = update.effective_chat.id
    removed = remove_subscriber(chat_id)
    if removed:
        await update.message.reply_text("You've been unsubscribed.", reply_markup=_unsubscribed_keyboard())
    else:
        await update.message.reply_text("You weren't subscribed.", reply_markup=_unsubscribed_keyboard())


# ── Admin commands ───────────────────────────────────────────────────────────

async def cmd_summarise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarise an article URL into a broadcast message."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("This command is for admins only.")
        return ConversationHandler.END

    text = update.message.text
    url_match = re.search(r'https?://\S+', text)
    if not url_match:
        await update.message.reply_text("Usage: /summarise https://example.com/article [optional notes]")
        return ConversationHandler.END

    url = url_match.group(0)
    after_url = text[url_match.end():].strip()

    await update.message.reply_text("Fetching and summarising... please wait.")

    try:
        result = await asyncio.to_thread(summarise_from_url, url, after_url)
        summary = result["summary"]
        if AGENT_SIGNOFF:
            summary += f"\n\n{AGENT_SIGNOFF}"

        _pending_messages[update.effective_chat.id] = {"message": summary, "source_url": url}
        await update.message.reply_text(summary)
        await update.message.reply_text("Review the message above, then choose:", reply_markup=_review_keyboard())
        return REVIEW_MESSAGE

    except Exception as e:
        logger.error("Failed to summarise: %s", e)
        await update.message.reply_text(f"Failed: {e}")
        return ConversationHandler.END


async def cmd_paste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paste article text directly."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Admin only.")
        return ConversationHandler.END

    text = update.message.text.replace("/paste", "", 1).strip()
    if not text or len(text) < 50:
        await update.message.reply_text("Usage: /paste [article text...]")
        return ConversationHandler.END

    await update.message.reply_text("Summarising... please wait.")

    try:
        summary = await asyncio.to_thread(summarise_article, text)
        if AGENT_SIGNOFF:
            summary += f"\n\n{AGENT_SIGNOFF}"

        _pending_messages[update.effective_chat.id] = {"message": summary, "source_url": ""}
        await update.message.reply_text(summary)
        await update.message.reply_text("Review the message above, then choose:", reply_markup=_review_keyboard())
        return REVIEW_MESSAGE

    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")
        return ConversationHandler.END


async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle review state commands."""
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    pending = _pending_messages.get(chat_id)

    if not pending:
        await update.message.reply_text("No pending message. Use /summarise to create one.")
        return ConversationHandler.END

    if text.startswith("/broadcast"):
        return await do_broadcast(update, context)
    elif text.startswith("/edit"):
        await update.message.reply_text("Send me the new message text:")
        return EDIT_MESSAGE
    elif text.startswith("/append"):
        extra = text.replace("/append", "", 1).strip()
        if extra:
            pending["message"] += "\n\n" + extra
            _pending_messages[chat_id] = pending
            await update.message.reply_text("Updated:")
            await update.message.reply_text(pending["message"])
            await update.message.reply_text("Review the message above, then choose:", reply_markup=_review_keyboard())
            return REVIEW_MESSAGE
        await update.message.reply_text("Usage: /append [text]")
        return REVIEW_MESSAGE
    elif text.startswith("/cancel"):
        _pending_messages.pop(chat_id, None)
        await update.message.reply_text("Discarded.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("Choose an action:", reply_markup=_review_keyboard())
        return REVIEW_MESSAGE


async def handle_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive edited message text."""
    chat_id = update.effective_chat.id
    pending = _pending_messages.get(chat_id)
    if not pending:
        return ConversationHandler.END

    pending["message"] = update.message.text.strip()
    _pending_messages[chat_id] = pending
    await update.message.reply_text("Updated:")
    await update.message.reply_text(pending["message"])
    await update.message.reply_text("Review the message above, then choose:", reply_markup=_review_keyboard())
    return REVIEW_MESSAGE


async def _send_personalised_followups(bot, broadcast_message: str, subscribers: list[dict]) -> None:
    """Send personalised 🔍 follow-ups to subscribers who have a saved policy."""
    policies = get_all_user_policies()
    if not policies:
        return
    sub_ids = {str(s["chat_id"]) for s in subscribers}
    for chat_id_str, policy in policies.items():
        if chat_id_str not in sub_ids:
            continue
        try:
            advice = await asyncio.to_thread(
                advise_for_policy,
                policy["insurer"],
                policy["policy_type"],
                policy.get("plan_name") or None,
                [broadcast_message],
            )
            await bot.send_message(chat_id=int(chat_id_str), text=f"🔍\n\n{advice}")
        except Exception as e:
            logger.warning("Personalised follow-up failed for %s: %s", chat_id_str, e)


async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast pending message to all subscribers."""
    chat_id = update.effective_chat.id
    pending = _pending_messages.get(chat_id)

    if not pending:
        await update.message.reply_text("No pending message.")
        return ConversationHandler.END

    subscribers = get_active_subscribers()
    if not subscribers:
        await update.message.reply_text("No subscribers. Ask clients to /start the bot.")
        return REVIEW_MESSAGE

    message = pending["message"]

    await update.message.reply_text(f"Broadcasting to {len(subscribers)} subscribers...")

    image_bytes = await asyncio.to_thread(fetch_diagram_image, message)
    logger.info("Diagram image: %s bytes", len(image_bytes) if image_bytes else "None")
    sent_count, failed_count = await _broadcast_to_subscribers(context.bot, message, subscribers, image_bytes)

    save_broadcast(message, sent_to=sent_count, source_url=pending.get("source_url", ""))
    _pending_messages.pop(chat_id, None)

    result = f"Sent to {sent_count} subscriber(s)!"
    if failed_count:
        result += f" ({failed_count} failed)"
    await update.message.reply_text(result)

    await _send_personalised_followups(context.bot, message, subscribers)
    return ConversationHandler.END


async def handle_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button taps during message review (Broadcast / Edit / Cancel)."""
    query = update.callback_query
    await query.answer()

    chat_id = query.from_user.id
    pending = _pending_messages.get(chat_id)

    if not pending:
        await query.message.reply_text("No pending message.")
        return ConversationHandler.END

    if query.data == "review_broadcast":
        subscribers = get_active_subscribers()
        if not subscribers:
            await query.message.reply_text("No subscribers. Ask clients to /start the bot.")
            return REVIEW_MESSAGE

        message = pending["message"]
        await query.message.reply_text(f"Broadcasting to {len(subscribers)} subscribers...")

        image_bytes = await asyncio.to_thread(fetch_diagram_image, message)
        logger.info("Diagram image (review callback): %s bytes", len(image_bytes) if image_bytes else "None")
        sent_count, failed_count = await _broadcast_to_subscribers(context.bot, message, subscribers, image_bytes)

        save_broadcast(message, sent_to=sent_count, source_url=pending.get("source_url", ""))
        _pending_messages.pop(chat_id, None)

        result = f"Sent to {sent_count} subscriber(s)!"
        if failed_count:
            result += f" ({failed_count} failed)"
        await query.message.reply_text(result)

        await _send_personalised_followups(context.bot, message, subscribers)
        return ConversationHandler.END

    elif query.data == "review_edit":
        await query.message.reply_text("Send me the new message text:")
        return EDIT_MESSAGE

    elif query.data == "review_cancel":
        _pending_messages.pop(chat_id, None)
        await query.message.reply_text("Discarded.")
        return ConversationHandler.END

    return REVIEW_MESSAGE


async def handle_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle navigation button taps (Latest / Subscribe / Unsubscribe)."""
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    user = query.from_user

    if query.data == "nav_latest":
        broadcasts = get_broadcasts()
        if not broadcasts:
            await query.message.reply_text("No updates yet. Check back later!")
            return
        recent = broadcasts[-3:]
        recent.reverse()
        for b in recent:
            text = b["full_message"]
            if b.get("source_url"):
                text += f"\n\n{b['source_url']}"
            for chunk in _split_message(text):
                await query.message.reply_text(chunk)

    elif query.data == "nav_stop":
        removed = remove_subscriber(chat_id)
        if removed:
            await query.message.reply_text("You've been unsubscribed.", reply_markup=_unsubscribed_keyboard())
        else:
            await query.message.reply_text("You weren't subscribed.", reply_markup=_unsubscribed_keyboard())

    elif query.data == "nav_start":
        is_new = add_subscriber(chat_id, first_name=user.first_name or "", username=user.username or "")
        if is_new:
            await query.message.reply_text("You're now subscribed to daily insurance updates!", reply_markup=_client_keyboard())
        else:
            await query.message.reply_text("You're already subscribed!", reply_markup=_client_keyboard())



async def cmd_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger daily digest (admin, for testing)."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Admin only.")
        return
    await update.message.reply_text("Triggering daily digest now...")
    await daily_digest(context)


async def cmd_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all subscribers (admin only)."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Admin only.")
        return

    subs = get_subscribers()
    if not subs:
        await update.message.reply_text("No subscribers yet.")
        return

    lines = [f"Subscribers ({len(subs)}):"]
    for i, s in enumerate(subs, 1):
        name = s.get("first_name", "Unknown")
        uname = f" @{s['username']}" if s.get("username") else ""
        lines.append(f"{i}. {name}{uname}")

    await update.message.reply_text("\n".join(lines))


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show broadcast history (admin only)."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Admin only.")
        return

    broadcasts = get_broadcasts()
    if not broadcasts:
        await update.message.reply_text("No broadcasts yet.")
        return

    lines = [f"Broadcast History (last 10 of {len(broadcasts)}):"]
    for b in broadcasts[-10:]:
        date = b["sent_at"][:10]
        preview = b["message_preview"][:80]
        lines.append(f"\n#{b['id']} ({date}) → {b['sent_to']} subs")
        lines.append(f"  {preview}...")

    await update.message.reply_text("\n".join(lines))


async def cmd_testimage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: test the Pollinations.ai image pipeline without broadcasting."""
    if not is_admin(update.effective_chat.id):
        await update.message.reply_text("Admin only.")
        return

    await update.message.reply_text("Generating test diagram...")
    test_summary = (
        "From April 2026, new IP riders will no longer cover the minimum deductible. "
        "Co-payment cap rises from $3,000 to $6,000/year. Premiums drop ~30%."
    )
    try:
        image_bytes = await asyncio.to_thread(fetch_diagram_image, test_summary)
        if image_bytes:
            buf = io.BytesIO(image_bytes)
            buf.name = "diagram.jpg"
            await update.message.reply_photo(photo=buf, caption=f"Test diagram ({len(image_bytes)} bytes)")
        else:
            await update.message.reply_text("fetch_diagram_image returned None — check Railway logs for details.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent updates with clickable buttons. Fetches live news if no broadcasts exist."""
    broadcasts = get_broadcasts()
    if not broadcasts:
        # No broadcasts yet — fetch live news and generate a summary on the spot
        await update.message.reply_text("Fetching the latest insurance news for you...")
        try:
            articles = await asyncio.to_thread(fetch_new_articles)
            if not articles:
                await update.message.reply_text(
                    "No recent Singapore insurance news found right now. Check back later!"
                )
                return
            # Summarise the first article and send it directly
            article = articles[0]
            article_text = await asyncio.to_thread(fetch_article_text, article["url"])
            summary = await asyncio.to_thread(summarise_article, article_text)
            if AGENT_SIGNOFF:
                summary += f"\n\n{AGENT_SIGNOFF}"
            for chunk in _split_message(summary):
                await update.message.reply_text(chunk)
            # Save as a broadcast so future /latest calls show it
            save_broadcast(summary, sent_to=0, source_url=article["url"])
        except Exception as e:
            logger.error("Failed to fetch live news for /latest: %s", e)
            await update.message.reply_text(
                "Couldn't fetch news right now. Try again later!"
            )
        return

    recent = broadcasts[-3:]  # last 3
    recent.reverse()  # newest first

    for b in recent:
        text = b["full_message"]
        if b.get("source_url"):
            text += f"\n\n{b['source_url']}"
        for chunk in _split_message(text):
            await update.message.reply_text(chunk)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help."""
    is_adm = is_admin(update.effective_chat.id)
    if is_adm:
        text = (
            "Admin Commands:\n"
            "/summarise <url> [notes] — Summarise article + broadcast\n"
            "/paste <text> — Summarise pasted text + broadcast\n"
            "/daily — Trigger daily digest now\n"
            "/subscribers — List subscribers\n"
            "/history — Broadcast history\n"
        )
        await update.message.reply_text(text, reply_markup=_client_keyboard())
    else:
        await update.message.reply_text("What would you like to do?", reply_markup=_client_keyboard())


SEED_BROADCAST = """Hi valued clients,
From 1 April 2026, new IP riders will cost less but cover less — your deductible and co-payment exposure increases.

Here's what's changing:
• New riders will no longer cover the minimum IP deductible
• Co-payment cap doubles from $3,000 to $6,000/year
• Premiums drop ~30%, saving private hospital holders ~$600/year and public hospital holders ~$200/year

What this means for you:
• Bought your rider before 26 Nov 2025 → you're fully protected, nothing changes
• Bought or buying before 31 March 2026 → current benefits stay until renewal after April 2028
• Buying after 1 April 2026 → new rules apply

Bottom line: No need to panic, but worth reviewing your coverage before renewal. Drop me a message if you'd like to go through your plan together."""

SEED_BROADCAST_2 = """Hi valued clients,
MediShield Life premiums are being revised upward from 1 April 2026 to keep pace with rising medical costs.

What's Changing
• Premiums rise by 35–40% across most age bands — e.g. age 41–45 goes from $465 to ~$640/year
• The Annual Claims Limit increases from $150,000 to $200,000 per year
• MAS requires all insurers to notify policyholders at least 30 days before renewal

Your Current Policy
• On standard MediShield Life (no IP) → premium rises apply; check your CPF statement for exact amount
• With an Integrated Shield Plan → IP insurer will notify you separately; Medisave can still offset most of the increase

What To Do
No action needed unless you want to upgrade your IP coverage — Medisave auto-pays MediShield Life premiums. Message me if you'd like to review whether your current plan still fits your needs!"""


async def post_init(application: Application):
    """Set bot commands and schedule daily digest."""
    try:
        await application.bot.set_my_commands([
            BotCommand("start", "Subscribe to daily insurance updates"),
            BotCommand("stop", "Unsubscribe from updates"),
            BotCommand("latest", "Read recent updates"),
            BotCommand("mypolicy", "Get advice based on your policy"),
            BotCommand("help", "Show available commands"),
        ])
    except Exception as e:
        logger.error("Failed to set bot commands: %s", e)

    # Seed default broadcasts by source URL so they're added even on existing installs
    existing = get_broadcasts()
    existing_urls = {b.get("source_url", "") for b in existing}
    seeds = [
        (SEED_BROADCAST, "https://www.moh.gov.sg/newsroom/new-requirements-for-integrated-shield-plan-riders-to-strengthen-sustainability-of-private-health-insurance-and-address-rising-healthcare-costs/"),
        (SEED_BROADCAST_2, "https://www.cpf.gov.sg/member/healthcare-financing/medishield-life"),
    ]
    added = 0
    for seed_msg, seed_url in seeds:
        if seed_url not in existing_urls:
            msg = seed_msg
            if AGENT_SIGNOFF:
                msg += f"\n\n{AGENT_SIGNOFF}"
            save_broadcast(msg, sent_to=0, source_url=seed_url)
            added += 1
    if added:
        logger.info("Seeded %d new broadcast(s)", added)

    for hour, minute in DIGEST_TIMES:
        t = dt_time(hour=hour, minute=minute, tzinfo=SGT)
        application.job_queue.run_daily(daily_digest, time=t, name=f"daily_digest_{hour:02d}{minute:02d}")
    times_str = ", ".join(f"{h:02d}:{m:02d}" for h, m in DIGEST_TIMES)
    logger.info("Daily digests scheduled at: %s SGT", times_str)

    # Notify admins that bot started and digests are scheduled
    subs = get_active_subscribers()
    for admin_id in ADMIN_CHAT_IDS:
        try:
            await application.bot.send_message(
                admin_id,
                f"Bot started. Digests scheduled at {times_str} SGT.\n"
                f"Active subscribers: {len(subs)}",
            )
        except Exception as e:
            logger.error("Failed to notify admin %s: %s", admin_id, e)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass  # suppress health check logs


def start_health_server():
    """Start a minimal HTTP server for Railway health checks."""
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health check server on port %d", port)


async def cmd_mypolicy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for /mypolicy — shows saved policy (if any) then asks for insurer."""
    chat_id = update.effective_chat.id
    saved = get_user_policy(chat_id)
    if saved:
        plan_str = f" ({saved['plan_name']})" if saved.get("plan_name") else ""
        await update.message.reply_text(
            f"Your saved policy: {saved['insurer']} {saved['policy_type']}{plan_str}\n\n"
            "Update it below, or tap your insurer to re-run advice with current details.",
            reply_markup=_insurer_keyboard(),
        )
    else:
        await update.message.reply_text("Which insurer is your policy with?", reply_markup=_insurer_keyboard())
    return POLICY_INSURER


async def handle_policy_insurer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store insurer choice and ask for policy type."""
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    insurer = query.data.replace("policy_insurer_", "", 1)
    _policy_store[chat_id] = {"insurer": insurer}
    await query.message.reply_text(f"Got it — {insurer}. What type of policy?", reply_markup=_policy_type_keyboard())
    return POLICY_TYPE


async def handle_policy_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store policy type and ask for plan name."""
    query = update.callback_query
    await query.answer()
    chat_id = query.from_user.id
    policy_type = query.data.replace("policy_type_", "", 1)
    _policy_store[chat_id]["policy_type"] = policy_type
    await query.message.reply_text(
        f"What's your plan name? (e.g. Paramount Plan, HealthShield Gold Max A)\n"
        f"Or tap Skip if you're not sure.",
        reply_markup=_plan_skip_keyboard(),
    )
    return POLICY_PLAN


async def handle_policy_plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'Skip' button on plan name step."""
    query = update.callback_query
    await query.answer()
    await _generate_advice(query.from_user.id, plan_name=None, reply_func=query.message.reply_text)
    return ConversationHandler.END


async def handle_policy_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive typed plan name and generate advice."""
    chat_id = update.effective_chat.id
    plan_name = update.message.text.strip()
    await _generate_advice(chat_id, plan_name=plan_name, reply_func=update.message.reply_text)
    return ConversationHandler.END


async def _generate_advice(chat_id: int, plan_name: str | None, reply_func) -> None:
    """Save policy, cross-reference broadcasts, return personalised advice."""
    from datetime import datetime
    store = _policy_store.pop(chat_id, {})
    insurer = store.get("insurer", "Unknown")
    policy_type = store.get("policy_type", "Unknown")

    policy = {
        "insurer": insurer,
        "policy_type": policy_type,
        "plan_name": plan_name or "",
        "updated_at": datetime.utcnow().isoformat(),
    }
    save_user_policy(chat_id, policy)

    await reply_func("Generating personalised advice...")

    broadcasts = get_broadcasts()
    recent_messages = [b["full_message"] for b in broadcasts[-3:]] if broadcasts else []

    try:
        advice = await asyncio.to_thread(advise_for_policy, insurer, policy_type, plan_name, recent_messages)
        await reply_func(advice, reply_markup=_client_keyboard())
    except Exception as e:
        logger.error("advise_for_policy failed: %s", e)
        await reply_func("Sorry, couldn't generate advice right now. Try again later.")


async def cancel_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel and end the conversation properly."""
    chat_id = update.effective_chat.id
    _pending_messages.pop(chat_id, None)
    await update.message.reply_text("Discarded.")
    return ConversationHandler.END


async def handle_client_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answer a subscriber's free-text question using recent broadcast content."""
    chat_id = update.effective_chat.id
    if is_admin(chat_id):
        return  # don't intercept admin free text
    question = update.message.text.strip()
    if not question:
        return
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    broadcasts = get_broadcasts()
    if not broadcasts:
        await update.message.reply_text(
            "I don't have any updates yet — check back after the next broadcast!\n\nType /latest to see if there's anything new.",
            reply_markup=_client_keyboard(),
        )
        return
    recent = [b["full_message"] for b in broadcasts[-5:]]
    answer = await asyncio.to_thread(answer_question, question, recent)
    await update.message.reply_text(answer, reply_markup=_client_keyboard())


def main():
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN env var is required")
    if not ADMIN_CHAT_IDS:
        logger.warning("No ADMIN_CHAT_IDS set — no one can use admin commands")

    ensure_dirs()
    start_health_server()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("summarise", cmd_summarise),
            CommandHandler("paste", cmd_paste),
        ],
        states={
            REVIEW_MESSAGE: [
                CommandHandler("broadcast", do_broadcast),
                CommandHandler("edit", handle_review),
                CommandHandler("append", handle_review),
                CommandHandler("cancel", handle_review),
                CallbackQueryHandler(handle_review_callback, pattern=r"^review_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review),
            ],
            EDIT_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_text),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_fallback),
        ],
        conversation_timeout=600,  # 10 min — cleans up abandoned review sessions
    )

    policy_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("mypolicy", cmd_mypolicy)],
        states={
            POLICY_INSURER: [
                CallbackQueryHandler(handle_policy_insurer, pattern=r"^policy_insurer_"),
            ],
            POLICY_TYPE: [
                CallbackQueryHandler(handle_policy_type, pattern=r"^policy_type_"),
            ],
            POLICY_PLAN: [
                CallbackQueryHandler(handle_policy_plan_callback, pattern=r"^policy_skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_policy_plan),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_fallback)],
        conversation_timeout=600,
    )

    app.add_handler(conv_handler)
    app.add_handler(policy_conv_handler)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("testimage", cmd_testimage))
    app.add_handler(CommandHandler("subscribers", cmd_subscribers))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_nav_callback, pattern=r"^nav_"))
    # Catch-all: client free-text questions — must be registered last
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_question))

    logger.info("Bot starting... Digests at %s SGT", ", ".join(f"{h:02d}:{m:02d}" for h, m in DIGEST_TIMES))
    app.run_polling()


if __name__ == "__main__":
    main()
