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

import logging
import os
import re
import threading
from datetime import time as dt_time, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv

load_dotenv()

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from services.storage_service import ensure_dirs
from services.article_service import summarise_from_url, summarise_article, fetch_article_text
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
# Daily digest time in SGT (UTC+8), default 9:00 AM
DAILY_HOUR = int(os.environ.get("DAILY_HOUR", "9"))
DAILY_MINUTE = int(os.environ.get("DAILY_MINUTE", "0"))

# Agent sign-off (appended to every broadcast)
AGENT_SIGNOFF = os.environ.get("AGENT_SIGNOFF", "")

# SGT timezone
SGT = timezone(timedelta(hours=8))

# Conversation states
REVIEW_MESSAGE, EDIT_MESSAGE = range(2)

# Store pending messages per admin
_pending_messages: dict[int, dict] = {}


def is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_CHAT_IDS


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
    articles = fetch_new_articles()
    if not articles:
        logger.info("No new relevant articles found today.")
        for admin_id in ADMIN_CHAT_IDS:
            try:
                await context.bot.send_message(admin_id, "Daily digest: No new insurance news today.")
            except Exception:
                pass
        return

    logger.info("Found %d new relevant articles", len(articles))

    # Summarise each article and broadcast (cap at 3 per day)
    for article in articles[:3]:
        try:
            article_text = fetch_article_text(article["url"])
            summary = summarise_article(article_text)

            if AGENT_SIGNOFF:
                summary += f"\n\n{AGENT_SIGNOFF}"

            sent_count = 0
            for sub in subscribers:
                try:
                    await context.bot.send_message(chat_id=sub["chat_id"], text=summary)
                    sent_count += 1
                except Exception as e:
                    logger.warning("Failed to send to %s: %s", sub["chat_id"], e)

            save_broadcast(summary, sent_to=sent_count, source_url=article["url"])
            logger.info("Broadcast '%s' to %d subscribers", article["title"][:50], sent_count)

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
            f"Hi {user.first_name}! You're now subscribed to daily insurance updates.\n\n"
            "You'll receive:\n"
            "• Daily summaries of Singapore insurance news\n"
            "• Policy change alerts\n"
            "• Regulatory updates (MAS, MOH)\n"
            "• Actionable advice from your insurance advisor\n\n"
            "Use /stop to unsubscribe anytime."
        )
    else:
        await update.message.reply_text(
            f"Hi {user.first_name}! You're already subscribed.\n"
            "You'll continue receiving daily updates.\n\n"
            "Use /stop to unsubscribe."
        )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribe from updates."""
    chat_id = update.effective_chat.id
    removed = remove_subscriber(chat_id)
    if removed:
        await update.message.reply_text("You've been unsubscribed. Use /start to resubscribe anytime.")
    else:
        await update.message.reply_text("You weren't subscribed. Use /start to subscribe.")


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
        result = summarise_from_url(url, agent_notes=after_url)
        summary = result["summary"]
        if AGENT_SIGNOFF:
            summary += f"\n\n{AGENT_SIGNOFF}"

        _pending_messages[update.effective_chat.id] = {"message": summary, "source_url": url}
        await update.message.reply_text(summary)
        await update.message.reply_text(
            "---\n/broadcast — Send to all subscribers\n/edit — Replace with your own text\n"
            "/append [text] — Add text at the end\n/cancel — Discard"
        )
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
        summary = summarise_article(text)
        if AGENT_SIGNOFF:
            summary += f"\n\n{AGENT_SIGNOFF}"

        _pending_messages[update.effective_chat.id] = {"message": summary, "source_url": ""}
        await update.message.reply_text(summary)
        await update.message.reply_text(
            "---\n/broadcast — Send to all subscribers\n/edit — Replace\n"
            "/append [text] — Add at end\n/cancel — Discard"
        )
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
            await update.message.reply_text("/broadcast, /edit, /append, or /cancel")
            return REVIEW_MESSAGE
        await update.message.reply_text("Usage: /append [text]")
        return REVIEW_MESSAGE
    elif text.startswith("/cancel"):
        _pending_messages.pop(chat_id, None)
        await update.message.reply_text("Discarded.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("/broadcast, /edit, /append [text], or /cancel")
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
    await update.message.reply_text("/broadcast, /edit, /append, or /cancel")
    return REVIEW_MESSAGE


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
    sent_count = 0
    failed_count = 0

    await update.message.reply_text(f"Broadcasting to {len(subscribers)} subscribers...")

    for sub in subscribers:
        try:
            await context.bot.send_message(chat_id=sub["chat_id"], text=message)
            sent_count += 1
        except Exception as e:
            logger.warning("Failed to send to %s: %s", sub["chat_id"], e)
            failed_count += 1

    save_broadcast(message, sent_to=sent_count, source_url=pending.get("source_url", ""))
    _pending_messages.pop(chat_id, None)

    result = f"Sent to {sent_count} subscriber(s)!"
    if failed_count:
        result += f" ({failed_count} failed)"
    await update.message.reply_text(result)
    return ConversationHandler.END


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


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help."""
    is_adm = is_admin(update.effective_chat.id)
    text = (
        "Insurance Update Bot\n\n"
        "/start — Subscribe to daily insurance updates\n"
        "/stop — Unsubscribe\n"
        "/help — Show this help\n"
    )
    if is_adm:
        text += (
            "\nAdmin Commands:\n"
            "/summarise <url> [notes] — Summarise article + broadcast\n"
            "/paste <text> — Summarise pasted text + broadcast\n"
            "/daily — Trigger daily digest now\n"
            "/subscribers — List subscribers\n"
            "/history — Broadcast history\n"
        )
    await update.message.reply_text(text)


async def post_init(application: Application):
    """Set bot commands and schedule daily digest."""
    await application.bot.set_my_commands([
        BotCommand("start", "Subscribe to daily insurance updates"),
        BotCommand("stop", "Unsubscribe from updates"),
        BotCommand("help", "Show available commands"),
    ])

    digest_time = dt_time(hour=DAILY_HOUR, minute=DAILY_MINUTE, tzinfo=SGT)
    application.job_queue.run_daily(daily_digest, time=digest_time, name="daily_digest")
    logger.info("Daily digest scheduled for %02d:%02d SGT", DAILY_HOUR, DAILY_MINUTE)


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
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_review),
            ],
            EDIT_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_text),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: u.message.reply_text("Discarded.")),
        ],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("daily", cmd_daily))
    app.add_handler(CommandHandler("subscribers", cmd_subscribers))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("help", cmd_help))

    logger.info("Bot starting... Daily digest at %02d:%02d SGT", DAILY_HOUR, DAILY_MINUTE)
    app.run_polling()


if __name__ == "__main__":
    main()
