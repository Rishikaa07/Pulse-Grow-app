# Pulse — A Market Attention Engine

> *"Don't make users watch the market. Make the market tell them what changed."*

Pulse is a full-stack web application that answers one question: **"I was away for three hours — what changed in my watchlist, how unusual was it, and what deserves my attention first?"**

It is not a stock dashboard. It is an attention engine that happens to track stocks.

---

## What makes it different

### The Attention Score

Every watched symbol receives a score built from **seven independent signals**, each weighted and explained:

| Signal | What it measures |
|---|---|
| **Price movement** | The move size, normalised by *that stock's own* recent volatility scaled to the window being judged — 2% in Costco outranks 2% in Rivian |
| **Volume anomaly** | Volume vs what you'd expect to have traded *by this point in the session*, not vs a full-day average |
| **Sector outperformance** | How far the stock moved vs its sector, measured over the identical window |
| **Market outperformance** | How far vs the broad market, adjusted for the stock's beta |
| **Historical unusualness** | Percentile in 90 days of closes — what fraction of days was bigger than this |
| **Event** | Guidance raises, analyst actions, macro prints — detected from the scenario tape |
| **Missed while away** | What fraction of today's move happened after you last looked |

The score is the literal arithmetic sum of the signals. The explanation is generated from those signals, so the two can never disagree. There is no model, no hidden weighting, no black box.

### Visit-based baselines

The insight most watchlists get wrong: "since you last checked" must mean *since you last actually looked*, not since the opening bell.

Pulse records a **Visit** every time you open the dashboard. Polling inside a visit (the page auto-refreshes every 30 seconds) does not move the baseline. Only a genuine absence — longer than a configurable idle timeout — opens a new visit and resets the comparison point. Tests assert this property explicitly.

### Honest data handling

- Every quote carries a **freshness state**: `fresh`, `delayed`, `stale`, or `unavailable`
- Two providers run in parallel. When they **disagree beyond tolerance**, the higher-priority source wins — but the discrepancy is recorded, surfaced in the UI, and lowers the confidence on the affected scores. Nothing is silently overwritten.
- When all feeds fail, the **last known good snapshot** is served, honestly labelled
- If data is stale, **confidence decreases** but the score itself is not adjusted — the number is still what the signals produced; you just know to trust it less

### Deterministic demo tape

Six scripted scenarios produce realistic, internally consistent market data:

- `NORMAL_MARKET` — ordinary session, most names within range
- `NVDA_BREAKOUT` — scripted surge with heavy volume, pulls semis
- `TSLA_DROP` — targeted drawdown, sector contagion
- `HIGH_VOLUME_EVENT` — macro print lifts volatility across financials/energy
- `STALE_PROVIDER` — primary feed stops updating; confidence degrades
- `CONFLICTING_PROVIDER` — feeds disagree on selected symbols; reconciler fires

Prices are a **pure function of (scenario, symbol, wall-clock time)** — refreshing the page does not reroll the dice. Sector and market indices are capitalisation-weighted aggregates of the same instruments, so "outperformed semiconductors by 3.1%" is arithmetic, not decoration.

---

## Architecture

```
Frontend (Next.js 15)
  ↓  /api/* proxied same-origin (httpOnly cookie, no JS token handling)
FastAPI
  ↓
Domain Services (market.py, overview.py)
  ↓
Repositories (SQL lives here, nowhere else)
  ↓
SQLAlchemy / SQLite (dev) or PostgreSQL (prod)

Market ingestion
  ↓
ProviderRegistry (fan-out, reconcile, degrade gracefully)
  ↓
In-memory cache (swaps to Redis via REDIS_URL)
  ↓
AttentionEngine (pure, no I/O, fully unit-tested)
  ↓
ChangeEvents (inbox, idempotent fingerprint)
```

**Why this shape, not microservices:** The background refresh loop is a single asyncio task in the same process. It has one job — keep the shared cache warm — and it fails safely (exponential backoff, never takes the API down). Adding a real Redis and running two API replicas is the only infrastructure change needed to scale; the code does not change because the cache abstraction is already there.

---

## Running locally

### Backend

```bash
cd backend
pip install -r requirements.txt        # fastapi, uvicorn, sqlalchemy, pydantic
# Optional: pip install -r requirements-optional.txt  (psycopg, redis)

# Minimum config (SQLite, in-memory cache — no infrastructure needed)
export PULSE_SECRET_KEY=change-me-in-production

uvicorn app.main:app --reload --port 8000
# API docs: http://localhost:8000/api/docs
```

Key environment variables:

| Variable | Default | Notes |
|---|---|---|
| `PULSE_SECRET_KEY` | `dev-only-insecure-key` | **Set this in production** |
| `DATABASE_URL` | `sqlite:///./pulse.db` | Use `postgresql+psycopg://…` for Postgres |
| `REDIS_URL` | *(unset)* | Falls back to in-memory cache |
| `REFRESH_INTERVAL_S` | `30` | Background tape refresh cadence |
| `VISIT_IDLE_TIMEOUT_S` | `900` | Minutes of inactivity that opens a new visit |

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
```

The `next.config.mjs` proxies `/api/*` to `http://127.0.0.1:8000` so both servers run independently and the session cookie stays httpOnly.

To point at a different API host:
```bash
PULSE_API_ORIGIN=https://your-api.example.com npm run dev
```

### Tests

```bash
cd backend
pytest                    # 51 tests: engine, providers, API, journey
pytest tests/test_attention_engine.py   # engine unit tests only
pytest tests/test_journey.py            # end-to-end demo flow
```

---

## The demo flow

1. Open `http://localhost:3000` and click **Enter Market Pulse** (demo login — no email needed)
2. You land on the Pulse dashboard. The scenario is **NVDA Breakout**. NVDA and AMD should show as high or medium severity with volume and sector signals.
3. Click any stock node in the **Market Pulse** field or the **Why?** link in the feed to open the intelligence panel. The "Last visit" journey shows what you saw vs what is true now.
4. Scroll down to **Demo market** and switch to **Normal market** — the feed goes quiet; 0 meaningful changes.
5. Switch back to **NVDA Breakout**. Switch to **Stale provider** — the data-quality banner appears and confidence drops on every score.
6. Switch to **Conflicting providers** — feeds disagree; the discrepancy is surfaced in the banner and logged under Settings → Data quality log.
7. Check the **Activity** page to see the inbox, review events, and dismiss items.
8. Open **Settings** to tune the attention weights and watch scores change on the next overview load.

---

## What "meaningful change" means

A change is meaningful if:

- The attention score reaches the **high** threshold (≥ 65 by default), placing it in "Needs your attention"
- At least one signal used ≥ 45% of its weight budget — a stock cannot be headlined "unusually large move" if the price signal barely fired
- The materiality gate clears — below ~0.5σ of actual movement, context signals (sector, market) are damped to zero, so a flat stock cannot accumulate points because its sector drifted

A change event is written to the inbox **idempotently**: 30-second polling can never create duplicate rows because the `(watchlist_id, fingerprint)` pair is uniquely constrained at the database level. The fingerprint buckets the score by tens, so a score drifting from 71 to 73 is the same change; a genuine escalation to a higher bucket is not.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend runtime | Python / FastAPI | Pydantic models, async lifespan, clean DI |
| ORM | SQLAlchemy 2.0 | Typed mapped columns, WAL SQLite for dev |
| Frontend | Next.js 15 / React 19 | App Router, same-origin proxy, no token in JS |
| Styles | Tailwind CSS | Design tokens in one file, no runtime CSS-in-JS |
| Visualisations | Vanilla SVG | Two custom charts, zero chart library dependencies |
| Auth | stdlib PBKDF2 + httpOnly cookie | No JWT, revocation works, nothing in localStorage |
| Cache | In-memory → Redis | Swaps via env var; zero code changes to scale |

Runtime frontend dependencies: **3** (`next`, `react`, `react-dom`).
Runtime backend dependencies: **4** (`fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`).

---

## Not built

Per the brief: no trading execution, no buy/sell recommendations, no brokerage integration, no social features, no AI chatbot, no cryptocurrency, no portfolio accounting. The product is focused on one thing and does it well.
