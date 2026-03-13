# CLAUDE.md — Insurance Update Automation

## Architecture
Two components:
- **`backend/`** — Telegram bot (Python) + FastAPI API server + Claude AI
- **`frontend/`** — React + TypeScript SPA (web dashboard, optional)

### Primary Interface: Telegram Bot
The main user-facing interface is a Telegram bot that:
1. **Daily auto-digest**: Fetches SG insurance news from Google News RSS at 9am, 12pm, and 4pm SGT (configurable via `DIGEST_TIMES`), uses Claude to filter relevant articles, summarises them into structured WhatsApp-style updates, broadcasts to all subscribers. Deduplication ensures the same article is never sent twice.
2. **Manual broadcasts**: Agent uses /summarise <url> to generate + broadcast updates from specific articles
3. **Subscriber management**: Clients /start to subscribe, /stop to unsubscribe

### Bot Commands
| Command | Who | Purpose |
|---------|-----|---------|
| /start | Anyone | Subscribe to daily updates |
| /stop | Anyone | Unsubscribe |
| /help | Anyone | Show commands |
| /summarise <url> | Admin | Summarise article → review → broadcast |
| /paste <text> | Admin | Summarise pasted text → broadcast |
| /daily | Admin | Trigger daily digest now (testing) |
| /broadcast | Admin | Send pending message to subscribers |
| /edit | Admin | Replace pending message |
| /append <text> | Admin | Add text to pending message |
| /cancel | Admin | Discard pending message |
| /subscribers | Admin | List all subscribers |
| /history | Admin | Show broadcast history |

### Backend API (secondary)
FastAPI server with endpoints for CSV upload, policy change CRUD, client matching, and message generation. Can be used alongside the bot for more complex workflows.

### Model
```python
HAIKU_MODEL = "claude-haiku-4-5-20251001"  # summarisation + message generation
```

### Storage
JSON files in `backend/data/` (gitignored):
- `users.json` — registered users (web API)
- `subscribers.json` — Telegram subscribers
- `broadcasts.json` — broadcast history
- `seen_urls.json` — already-processed article URLs
- `policy_changes.json` — saved policy changes
- `sessions/{id}.json` — per-session clients + notifications

## Running locally

**Telegram Bot:**
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in API keys + bot token
python bot.py
```

**Web API (optional):**
```bash
uvicorn main:app --reload --port 8000
```

**Frontend (optional):**
```bash
cd frontend
npm install
npm start  # dev server on :3000
```

## Env vars
```
ANTHROPIC_API_KEY=
JWT_SECRET=              # required for web API
TELEGRAM_BOT_TOKEN=      # from @BotFather
ADMIN_CHAT_IDS=          # comma-separated TG chat IDs of admins
AGENT_SIGNOFF=           # appended to every broadcast, e.g. "Claire Ong"
DIGEST_TIMES=09:00,12:00,16:00  # comma-separated HH:MM times in SGT for daily digests
ALLOWED_ORIGINS=http://localhost:3000
```

## Getting your Telegram Chat ID
1. Message the bot with /start
2. Check bot logs for the chat_id, or use @userinfobot
3. Add your chat_id to ADMIN_CHAT_IDS

## News Sources
Google News RSS feeds for:
- Singapore insurance policy changes
- MAS insurance regulation
- Health insurance / MediShield / riders
- CPF insurance updates

## Deployment
| Service | Platform | Notes |
|---------|----------|-------|
| Bot + API | Railway | Root dir: `backend/`, Dockerfile runs `python bot.py` |
| Frontend | Vercel | Optional, root dir: `frontend/` |

## Singapore Insurance Context
Insurers: AIA, Prudential, Great Eastern, NTUC Income, Manulife, AXA, Tokio Marine, FWD, Aviva, Etiqa, HSBC Life, Singlife
Policy types: Life, Health/Medical, Motor, Travel, Home, Critical Illness, ILP, Personal Accident, Disability Income, Group
