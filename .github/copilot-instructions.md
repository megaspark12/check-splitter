# Check Splitter — AI Agent Instructions

## Architecture Overview

A real-time bill-splitting web app using **FastAPI + SQLAlchemy (async) + vanilla JS**. The host uploads a receipt photo, Google Gemini extracts items via vision AI, and participants join via code/QR/link to claim items. WebSockets keep all clients in sync.

### Data Flow
1. **Host creates session** → `POST /api/sessions` → generates 6-char code + stores network hash for "nearby" discovery
2. **Receipt upload** → `POST /api/sessions/{code}/upload` → Gemini vision → items stored in DB
3. **Participants join** → `POST /api/sessions/{code}/participants` → WebSocket connected → all clients notified
4. **Item claiming** → `POST /api/sessions/{code}/assignments` → triggers `manager.notify_session_update()` → all clients refetch

### Key Components
| Component | Location | Purpose |
|-----------|----------|---------|
| WebSocket hub | [app/websocket_manager.py](app/websocket_manager.py) | Broadcasts `sync` events per session |
| Bill calculator | [app/services/calculator.py](app/services/calculator.py) | Splits items, distributes tax/tips proportionally |
| OCR service | [app/services/ocr_service.py](app/services/ocr_service.py) | Gemini vision API wrapper |
| Frontend state | [static/app.js](static/app.js) | Globals: `currentSession`, `currentParticipant`, `isHost` |

## Production Deployment (GCP)

### Infrastructure
- **Platform**: Google Cloud Run (containerized) with custom domain
- **Database**: Cloud SQL (PostgreSQL) with private VPC connection
- **Storage**: Cloud Storage bucket for receipt images (signed URLs)
- **Secrets**: Secret Manager for `GEMINI_API_KEY`, `SECRET_KEY`, DB credentials

### Security Requirements
- HTTPS only (Cloud Run default + custom domain SSL via managed certificates)
- `SECRET_KEY` must be a strong random string (32+ chars) in production
- Set `ENVIRONMENT=production` to disable `/docs`, `/redoc`, `/openapi.json`
- Configure `CORS_ORIGINS` to your domain only (not `*`)
- Use Cloud Armor for DDoS protection and WAF rules
- Enable Cloud Run IAM authentication for admin endpoints if needed

### Deployment Commands
```bash
# Build and push to Artifact Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/check-splitter

# Deploy to Cloud Run
gcloud run deploy check-splitter \
  --image gcr.io/PROJECT_ID/check-splitter \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets=GEMINI_API_KEY=gemini-key:latest,SECRET_KEY=secret-key:latest \
  --set-env-vars=ENVIRONMENT=production,DATABASE_URL=postgresql+asyncpg://...

# Map custom domain
gcloud run domain-mappings create --service check-splitter --domain yourdomain.com
```

## Critical Patterns

### WebSocket Sync Pattern
Every API mutation **must** broadcast to clients. Use FastAPI's `BackgroundTasks`:
```python
from app.websocket_manager import manager

@router.post("/{code}/items")
async def add_item(..., background_tasks: BackgroundTasks):
    # ... save to DB ...
    background_tasks.add_task(manager.notify_session_update, code.upper())
    return item
```

### Session Code Convention
Session codes are **always uppercase** internally. Normalize on input: `code.upper()`

### Database Sessions
Use async SQLAlchemy with dependency injection. The `get_db` dependency handles commit/rollback:
```python
from app.database import get_db

@router.get("/{code}")
async def get_session(code: str, db: AsyncSession = Depends(get_db)):
    # db.commit() called automatically on success
```

### Pydantic Schemas
All API responses use Pydantic models from `app/schemas/`. Use `from_attributes = True` for ORM conversion:
```python
class ItemInSession(BaseModel):
    class Config:
        from_attributes = True
```

### Gemini API Resilience
The OCR service must handle API failures gracefully:
- **Retry logic**: Exponential backoff (3 retries, base 1s) for transient errors (5xx, timeouts)
- **Rate limiting**: Gemini has 60 RPM free tier — implement client-side rate limiting
- **Edge cases to handle**:
  - Blurry/unreadable receipts → return user-friendly error, allow manual item entry
  - Non-receipt images → validate response structure, reject if no items extracted
  - Partial OCR results → accept partial data, flag items with low confidence
  - API quota exceeded → queue requests or show "try again later" message
```python
# Example retry pattern for ocr_service.py
import tenacity

@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(multiplier=1, min=1, max=10),
    retry=tenacity.retry_if_exception_type((APIError, TimeoutError)),
)
async def parse_receipt(self, image_data: bytes) -> List[ReceiptItem]:
    ...
```

## Development Commands

```bash
# Run server (activate venv first)
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Public URL for mobile testing
cloudflared tunnel --url http://localhost:8000
```

## Testing Conventions

### Backend Tests
- **Unit tests**: `tests/unit/` — use dataclasses prefixed with `_` to avoid pytest collection (e.g., `_Item`, `_Assignment`)
- **Integration tests**: `tests/integration/` — use async `client` fixture from [tests/conftest.py](tests/conftest.py)
- In-memory SQLite for tests: `sqlite+aiosqlite:///:memory:`

### Frontend E2E Tests (Playwright)
End-to-end tests live in `tests/e2e/` using Playwright for real browser testing:
```bash
# Install Playwright
pip install pytest-playwright
playwright install chromium

# Run E2E tests
pytest tests/e2e/ -v

# Run with headed browser (debugging)
pytest tests/e2e/ -v --headed

# Run specific test
pytest tests/e2e/test_session_flow.py -v
```

E2E test structure:
```python
# tests/e2e/test_session_flow.py
import pytest
from playwright.async_api import async_playwright, expect

@pytest.fixture
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()

async def test_host_creates_session_and_uploads_receipt(page):
    await page.goto("http://localhost:8000")
    await page.fill("#host-name", "Test Host")
    await page.click("#create-session-btn")
    await expect(page.locator(".session-code")).to_be_visible()
    # ... test receipt upload, item display, etc.

async def test_participant_joins_and_claims_items(page):
    # Test the full participant flow
    ...
```

Key E2E scenarios to cover:
1. **Host flow**: Create session → upload receipt → see extracted items → share code
2. **Participant flow**: Enter code → join → see items → claim items → see updated total
3. **Real-time sync**: Two browsers, one claims item → other sees update instantly
4. **Rejoin flow**: Refresh page → rejoin banner appears → selections preserved
5. **Error states**: Invalid code, upload failure, WebSocket disconnect recovery

## Frontend Conventions

- **No build step** — vanilla HTML/CSS/JS in `static/`
- **Single-page app** — views toggled via CSS classes in [static/index.html](static/index.html)
- **State in globals** — `currentSession`, `currentParticipant`, `isHost`, `websocket` in [static/app.js](static/app.js)
- **localStorage** — session history for rejoin, participant identity preservation

## Environment Variables

Required in `.env`:
- `GEMINI_API_KEY` — Google AI Studio key for receipt OCR
- `SECRET_KEY` — change for production (use `openssl rand -hex 32`)
- `DATABASE_URL` — defaults to SQLite; use PostgreSQL for prod

Production-specific:
- `ENVIRONMENT=production` — disables debug endpoints
- `CORS_ORIGINS=https://yourdomain.com` — restrict to your domain
- `LOG_FORMAT=json` — structured logging for Cloud Logging

See [app/config.py](app/config.py) for all options with defaults.

## File Naming Conventions

| Layer | Singular naming |
|-------|-----------------|
| Models | `app/models/item.py` → class `Item` |
| Schemas | `app/schemas/item.py` → `ItemCreate`, `ItemResponse` |
| API routes | `app/api/items.py` → router prefix `/api/sessions/{code}/items` |

## Common Pitfalls

1. **Forgetting WebSocket broadcast** — every mutation must call `manager.notify_session_update()`
2. **Case sensitivity** — always use `code.upper()` for session codes
3. **Eager loading** — use `selectinload()` for relationships to avoid N+1 queries
4. **Decimal precision** — calculator uses `Decimal` with `ROUND_HALF_UP`, not floats
