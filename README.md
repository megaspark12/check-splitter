# 🧾 Check Splitter

Split restaurant bills fairly with friends — in seconds. Upload a receipt photo, let AI extract the items, and everyone picks what they ordered from their own phone.

## ✨ Features

### Core
- 📷 **Receipt Scanning** — Take a photo or choose from gallery; AI extracts items & prices automatically
- 👥 **Real-Time Sessions** — Create a session, share via code / QR / link, and friends join instantly
- ✅ **Item Selection** — Each person taps what they ordered; shared items split proportionally
- 💰 **Smart Splitting** — Handles tax distribution, per-person tips, and discounts
- 🔄 **Live Sync** — WebSocket-powered real-time updates across all participants

### Sharing & Session Management
- 📋 **Copy Code / QR Code / Share Link** — Available to both host and participants
- 🚪 **Leave / End Session** — Participants can leave; host can end the session for everyone
- 🕐 **Session History** — Quickly rejoin recent sessions from the home screen
- ⚡ **Auto-Rejoin** — Accidentally refreshed? A banner lets you jump right back in
- 🔒 **Identity Preservation** — Rejoining restores your name and all previous selections

### Extras
- 🏷️ **Discounts** — Host can add percentage or fixed-amount discounts (per person or everyone)
- 📡 **Nearby Sessions** — Discover active sessions on your local network
- 📱 **PWA Support** — Installable on mobile, works offline-capable with service worker
- 🌍 **Auto Currency** — Detects your timezone and shows the correct currency symbol

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, async SQLAlchemy, SQLite (dev) / PostgreSQL (prod) |
| **Frontend** | Vanilla HTML, CSS, JavaScript — no framework, no build step |
| **Real-Time** | Native WebSockets via FastAPI |
| **AI** | Google Gemini 2.0 Flash for receipt OCR |
| **Infra** | Docker, Docker Compose, Alembic migrations |

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- A free [Google Gemini API key](https://aistudio.google.com/apikey)

### Setup

```bash
# Clone the repo
git clone <repo-url> && cd receipt-scanner

# Create & activate virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** — you're ready to split bills!

### Docker

```bash
# Copy & configure env
cp .env.example .env
# Edit .env — set GEMINI_API_KEY and SECRET_KEY

# Run (data persisted in Docker volumes)
docker compose up -d
```

## 📂 Project Structure

```
├── app/
│   ├── api/              # FastAPI route handlers
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── services/         # Business logic (sessions, receipts, etc.)
│   ├── config.py         # Settings via pydantic-settings
│   ├── database.py       # Async DB engine & session
│   ├── main.py           # App entry point & lifespan
│   ├── middleware.py      # Request logging & CORS
│   └── websocket_manager.py  # Real-time sync hub
├── static/
│   ├── index.html        # Single-page app UI
│   ├── app.js            # All client-side logic
│   ├── styles.css        # Full stylesheet
│   ├── sw.js             # Service worker (PWA)
│   └── manifest.json     # PWA manifest
├── alembic/              # Database migrations
├── tests/                # Test suite
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## ⚙️ Configuration

All settings are in `.env` (see `.env.example` for defaults):

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key | *required* |
| `GEMINI_MODEL` | Gemini model for receipt OCR | `gemini-2.0-flash` |
| `GEMINI_DAILY_LIMIT` | Max API calls per day (0 = unlimited) | `100` |
| `DATABASE_URL` | SQLite or PostgreSQL connection string | `sqlite+aiosqlite:///./check_splitter.db` |
| `SESSION_EXPIRY_MINUTES` | Auto-cleanup inactive sessions | `15` |
| `MAX_UPLOAD_SIZE_MB` | Max receipt image size | `10` |
| `WORKERS` | Gunicorn/uvicorn workers | `2` |
| `RATE_LIMIT_PER_MINUTE` | API rate limit | `180` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `LOG_FORMAT` | Log output format | `json` |

## 📄 License

MIT

