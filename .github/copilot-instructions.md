# Check Splitter — AI Agent Instructions

## Architecture

Real-time bill-splitting app: **FastAPI (async) + SQLAlchemy + vanilla JS**. Host uploads receipt → Gemini vision extracts items → participants join via code/QR/link → claim items → WebSockets sync all clients.

**Data flow**: `POST /api/sessions` → `POST /api/sessions/{code}/upload` (Gemini OCR) → `POST .../participants` (join) → `POST .../assignments` (claim) → each mutation triggers `manager.notify_session_update(code.upper())` via `BackgroundTasks`.

**Key files**: `app/websocket_manager.py` (WS hub), `app/services/calculator.py` (bill math), `app/services/ocr_service.py` (Gemini wrapper), `static/app.js` (all frontend state in globals: `currentSession`, `currentParticipant`, `isHost`).

## Critical Patterns

### Every mutation must broadcast
```python
background_tasks.add_task(manager.notify_session_update, code.upper())
```
Forgetting this causes client desync. Check every `POST`/`PUT`/`DELETE` handler.

### Session codes are ALWAYS uppercase
Normalize at every boundary: `code.upper()`. Lookups break without this.

### Two auth levels via dependencies
- **Read endpoints**: `session: Session = Depends(get_session_or_404)` — anyone can read
- **Write endpoints**: `session: Session = Depends(require_host_token)` — validates `X-Host-Token` header (SHA-256 hash comparison via `session.verify_host_token()`)

### Database session lifecycle
`get_db()` auto-commits on success, auto-rollbacks on exception. Don't manually commit unless you need `flush()` to get IDs mid-transaction (see `session_service.py:create_session`).

### Decimal everywhere, never floats
All monetary values use `Decimal("15.00")` (string-constructed). Calculator uses `ROUND_HALF_UP` and `_distribute_with_remainder()` to ensure penny-level conservation.

### Eager loading required
Use `selectinload()` for relationships to avoid N+1 queries:
```python
stmt = select(Session).options(selectinload(Session.items), selectinload(Session.participants), selectinload(Session.discounts))
```

## File & Naming Conventions

| Layer | Pattern | Example |
|-------|---------|---------|
| Models | `app/models/{entity}.py` → class `Entity` | `app/models/item.py` → `Item` |
| Schemas | `app/schemas/{entity}.py` → `EntityCreate`, `EntityUpdate`, `EntityResponse` | `ItemCreate`, `ItemUpdate` |
| API routes | `app/api/{entities}.py` → nested under `/api/sessions/{code}/...` | `app/api/items.py` |
| Services | `app/services/{name}_service.py` | `session_service.py`, `ocr_service.py` |

Schemas use `from_attributes = True` for ORM conversion. `ItemUpdate` fields are all `Optional` — handlers check `if field is not None` individually.

## Development

```bash
make dev              # Run server with auto-reload (or: python run.py)
make test             # All tests (pytest tests/ -v)
make test-unit        # Unit tests only
make test-integration # Integration tests only
pytest tests/e2e/ -v  # E2E tests (requires: playwright install chromium)
make migrate          # alembic upgrade head
make migrate-create MSG="description"  # New migration
```

Config via `.env` — see `app/config.py` for all options. Key vars: `GEMINI_API_KEY`, `DATABASE_URL` (defaults to SQLite), `ENVIRONMENT` (set `production` to disable `/docs`).

## Testing Conventions

- **Unit tests** (`tests/unit/`): Use `_`-prefixed dataclasses (`_Item`, `_Assignment`) to avoid pytest collection. All data constructed inline, no fixtures. Import the class under test inside each method.
- **Integration tests** (`tests/integration/`): Use `client: AsyncClient` fixture (in-memory SQLite). Create all data through API calls, not ORM inserts. Pass `X-Host-Token` header for write operations.
- **E2E tests** (`tests/e2e/`): Playwright against a real subprocess uvicorn server on a random port with file-based SQLite (`test_e2e.db`). Rate limiting disabled via `RATE_LIMIT_PER_MINUTE=9999`.
- `asyncio_mode = auto` in `pytest.ini` — no need for `@pytest.mark.asyncio`.
- `nest_asyncio` patching in `tests/conftest.py` handles Python 3.13 event loop nesting with Playwright.

## Storage Abstraction

`app/services/storage_service.py` uses an ABC (`StorageBackend`) with a factory: `get_storage_backend()` returns `LocalStorage` (dev, uses `aiofiles`) or `GCSStorage` (prod, wraps blocking GCS calls in `asyncio.to_thread()`). Configured via `STORAGE_BACKEND=local|gcs` and `GCS_BUCKET_NAME`.

## OCR Service Internals

`app/services/ocr_service.py` has two layers: `GeminiReceiptParser` (AI interaction + validation) and `OCRService` (app-level wrapper).

- **Daily rate limiter**: Thread-safe `DailyCallLimiter` singleton, configured via `GEMINI_DAILY_LIMIT` (0 = unlimited). Resets at midnight.
- **Retry**: `tenacity` with 3 attempts, exponential backoff (1s→10s) on `ConnectionError`/`TimeoutError`/`OSError`.
- **Markdown stripping**: Gemini often wraps JSON in `` ```json ... ``` `` — the parser detects and strips this.
- **Defensive validation**: `_validate_result()` clamps quantities to 1–100, rejects empty names / negative prices, converts floats via `Decimal(str(float_val)).quantize(Decimal('0.01'))`.

## Known Inconsistencies

- **Discounts API** (`app/api/discounts.py`) duplicates session-lookup logic from `app/api/dependencies.py` with its own inline `selectinload(Session.discounts).selectinload(Discount.participant)` instead of using the shared `get_session_or_404`/`require_host_token` dependencies. It also manually constructs `DiscountResponse` (rather than using `from_attributes`) because the response includes a computed `participant_name` not on the ORM model.
- **Tip mutual exclusion** is enforced in the `PUT /participants` handler (setting `tip_percentage` clears `tip_amount` and vice versa), not in the Pydantic schema.

## Frontend

No build step — vanilla HTML/CSS/JS in `static/`. Single-page app with views toggled via CSS classes. State in globals + `localStorage` for session history and rejoin. PWA-enabled (service worker + manifest).

## Deployment (GCP)

Cloud Run (Docker) + Cloud SQL (PostgreSQL) + Cloud Storage (receipt images). Deploy with `make deploy` (Cloud Build) or `gcloud builds submit`. Terraform in `terraform/` manages infrastructure. Set `ENVIRONMENT=production` to disable debug endpoints and enable HSTS.
