# EchoSystem-AI — Build Plan (v2)

**Goal:** finish the system and extend it from "impressive multi-agent architecture" into a demonstrable
**market research agent with quantifiable business impact** — suitable for the internship application's
required writeup + Loom video (problem → solution → agent → measurable effect).

Hand this whole file to the coding agent as the spec. Phases are ordered by dependency — don't skip
Phase 1 to jump to the flashy stuff; the impact numbers in Phase 2 need Phase 1's plumbing to be trustworthy.

## Current state (verified in repo, Aug 2026)

Already working: FastAPI ingestion (RSS + NewsAPI) → Celery tasks → Instructor/Pydantic extraction with
token-aware chunking → Neo4j graph write + 3-strategy contradiction detection → Qdrant embeddings →
LangGraph Researcher/Auditor critic loop (max 3 retries) → SQLite report store → Next.js dashboard
(GraphView, EntityPanel, ReportFeed, TopicSearch, MarketData) → `finance/stock.py` (yfinance),
`finance/sec.py` (SEC EDGAR XBRL facts + filings search), `social/reddit.py` (praw). Celery beat runs a
research cycle every 30 min on 3 hardcoded topics.

Gaps that matter for the internship framing: no tests, no auth, no cost/latency tracking, no way to
prove the audit loop actually catches anything, no user-manageable watchlist (everything is
code-defined), no digest/notification output, no NL query interface, `print()`-based logging only.

---

## Phase 1 — Foundation: tests, logging, resilience

Do this first. Nothing you build later is credible in a demo if it silently breaks.

1. **Test harness.** Add `pytest`, `pytest-mock`, `pytest-asyncio` to `requirements.txt`. Create `tests/`
   mirroring the package layout:
   - `tests/extraction/test_chunking.py` — token boundaries, empty input, single-token-over-limit input.
   - `tests/extraction/test_schemas.py` — `ExtractionResult`/`Relation` validation, reject bad `relation_type`.
   - `tests/graph/test_contradictions.py` — table-driven cases for `_keyword_conflict` (antonym pairs,
     positive/negative marker overlap, no-conflict case). Mock `sentence_transformers` and the Groq client
     for the embedding/llm strategies so tests run with zero API calls.
   - `tests/agents/test_graph.py` — run `compiled_graph` with a fake Groq client (monkeypatch
     `researcher.client` / `auditor.audit_client`) to assert the retry-then-finalize-with-warning path
     triggers after 3 fails, and the pass path short-circuits on attempt 1.
   - `tests/ingestion/test_report_store.py` — round-trip save/load against a temp sqlite file.
2. **CI.** Add `.github/workflows/test.yml` running `pytest` on push/PR (no external services needed given
   the mocking above).
3. **Structured logging.** Replace every `print(...)` in `ingestion/tasks.py`, `extraction/tasks.py`,
   `graph/ingest.py` with Python `logging` (module-level `logger = logging.getLogger(__name__)`), configured
   once in `ingestion/celery_app.py` via `logging.basicConfig` (JSON formatter optional, but at least
   include timestamp + level + module). This is a prerequisite for Phase 2's metrics.
4. **Resilience.** Wrap outbound HTTP (`httpx` calls in `ingestion/tasks.py`, `finance/sec.py`) with
   `tenacity` retry (already a dependency) — 2 retries, exponential backoff — for transient failures.
   Add a Celery task-level try/except around `poll_all_feeds`/`poll_topic` so one bad feed doesn't kill
   the whole beat cycle (mostly already true, verify).
5. **Startup validation.** In `ingestion/main.py` and `ingestion/celery_app.py`, fail fast with a clear
   message if `GROQ_API_KEY`/`NEO4J_PASSWORD` are unset, instead of a deep `KeyError` traceback later.

**Acceptance:** `pytest` green locally and in CI; grep for `print(` in `ingestion/`, `extraction/`,
`graph/` returns nothing.

---

## Phase 2 — Impact metrics (this is the number for your Loom video)

The whole pitch to a business owner is "this replaces manual research." You need a real number, not a
vibe. This phase makes the audit loop's value and the time savings measurable and visible.

1. **New table** `metrics` in the existing sqlite db (extend `ingestion/report_store.py`): one row per
   `run_research` call — `report_id`, `topic`, `started_at`, `finished_at`, `duration_seconds`,
   `retry_count`, `audit_status`, `input_tokens`, `output_tokens` (Groq responses include usage — capture
   it in `researcher.py`/`auditor.py` and thread it through the state dict), `estimated_cost_usd` (Groq
   free tier = $0, but compute what it *would* cost on a paid model so the number generalizes).
2. **Audit efficacy tracking.** Every time `auditor_node` returns `status == "fail"`, log the
   `flagged_claims` count to the metrics row. This gives you: *"the auditor caught and forced a rewrite
   of N unsupported claims across M reports — a X% catch rate."* That's your headline "here's the effect"
   stat for the Loom video, and it's real, not marketing.
3. **`/api/stats` endpoint** (`ingestion/main.py`) aggregating: total reports generated, avg
   `duration_seconds`, audit fail→pass recovery rate, total contradictions detected (`COUNT` on
   `CONTRADICTS` edges in Neo4j), reports per day over last 30 days.
4. **Baseline you must measure yourself, honestly:** time yourself doing one manual competitor/market
   research brief of the same depth as one EchoSystem report (find sources, read, cross-check, write).
   Record that number. Don't estimate it — actually do it once and time it. That's your "before" in the
   problem→solution→effect narrative; without it the impact claim is unverifiable and you shouldn't use it.
5. **Dashboard page** `dashboard/app/impact/page.tsx` (+ `components/ImpactStats.tsx`): cards for
   reports generated, avg generation time vs. your measured manual baseline (time saved %), audit catch
   rate, contradictions surfaced. This is the screen you screen-record for the Loom "effects" segment.

**Acceptance:** `/api/stats` returns real numbers after running a few `run_research` cycles; the impact
page renders them; you have one honestly-measured manual-baseline number written down.

---

## Phase 3 — Watchlist + digest (the "hands off, business-owner-manageable" feature)

Right now everything is code-defined (`TOPICS` list, hardcoded `FEEDS`). A business owner can't manage
that. This phase turns EchoSystem from "a script I run" into "a tool a non-technical person configures."

1. **Watchlist table** (sqlite, alongside `reports`/`metrics`): `id`, `type` (`company` | `topic`),
   `value`, `cadence` (`daily` | `weekly`), `created_at`, `active`.
2. **CRUD endpoints:** `POST/GET/DELETE /api/watchlist`.
3. **Settings UI** `dashboard/app/settings/page.tsx`: add/remove watchlist entries, pick cadence — no code
   editing required. This directly satisfies the JD's "train the business owner to build/implement/manage
   AI agents themselves" line; screenshot this for the application.
4. **Scheduler rework.** Replace the hardcoded `agents/tasks.py` `TOPICS` list: `run_research_cycle`
   should read active watchlist rows due for their cadence (track `last_run_at` per row) instead of a
   fixed list. Keep `celery_app.conf.beat_schedule` polling every 30 min but have the task itself decide
   what's due.
5. **Digest generator** `ingestion/digest.py`: once a day, compile everything new since the last digest
   (new reports, new contradictions, notable stock moves >5%, new SEC filings) for watchlist entities into
   one summary (reuse the Researcher/Auditor pattern or a simpler single Groq call — this doesn't need the
   full critic loop). Send via email (Resend or SMTP — add `RESEND_API_KEY` to `.env.example`) or a Slack
   incoming webhook (simpler to demo, add `SLACK_WEBHOOK_URL`). Pick whichever you can wire up fastest;
   Slack webhook is less setup.
6. **Celery beat entry:** `send-daily-digest` at a fixed hour.

**Acceptance:** adding a company via the Settings UI causes it to show up in the next digest without
touching any code or redeploying.

---

## Phase 4 — Comparison + sentiment trend

Gives you a second, more visual demo screen and rounds out "market research agent" (not just single-entity
lookups).

1. **Sentiment on claims.** Extend `extraction/schemas.py` `Relation` (or add a new field to `Claim` nodes
   in `graph/ingest.py`) with a lightweight sentiment label — cheapest path: reuse the existing
   `POSITIVE_MARKERS`/`NEGATIVE_MARKERS` keyword sets from `graph/contradictions.py` (factor them into a
   shared `graph/sentiment.py` module so you're not duplicating), or ask the extraction LLM call to also
   return `sentiment: Literal["positive","neutral","negative"]` per relation — cleaner, costs one field.
2. **`/api/compare?entities=A,B,C`** endpoint merging: `finance/stock.py` price history,
   `finance/sec.py` key facts, sentiment trend (weekly bucketed average from claim sentiment) and
   mention volume from the graph, for up to 4 entities.
3. **`dashboard/app/compare/page.tsx`**: side-by-side cards + one Recharts/Chart.js line chart overlaying
   normalized stock price and sentiment trend per entity.

**Acceptance:** comparing 2 real tickers shows correct price history and a sentiment line that visibly
moves when you seed a strongly positive/negative article for one of them.

---

## Phase 5 — Natural-language "Ask" agent (the live demo moment)

This is the highest-leverage addition for the Loom video: a business owner typing a plain question and
getting a sourced answer beats reading a graph.

1. **New LangGraph agent** `agents/analyst.py`: a ReAct-style node with tool access to `hybrid_search`
   (existing), `finance.stock.get_stock_data`, `finance.sec.get_sec_snapshot`, `social.reddit.search_reddit`.
   Use LangGraph's tool-calling support (you already depend on `langgraph-prebuilt`) so the model picks
   which tool(s) to call based on the question, then synthesizes a cited answer. Reuse the Auditor node
   against this answer too — same critic-loop guarantee, don't build a second unverified path.
2. **`/api/ask`** endpoint (`POST {question: str}`), streaming if straightforward, otherwise synchronous.
3. **Chat component** `dashboard/app/components/AskAgent.tsx` on the main dashboard page — a simple
   input + threaded answer with source chips linking back to the entity/report it pulled from.

**Acceptance:** asking "has [watchlisted company] had any negative news this month?" returns an answer
that cites specific report/claim sources, and refuses (or says "no supported claims found") rather than
hallucinating when nothing relevant exists in the graph.

---

## Phase 6 — Security & deploy hardening

Needed before you'd ever hand this to an actual business owner, and worth having done before the
interview in case they ask "could I actually use this."

1. **API key auth** on `ingestion/main.py`: single shared-secret header check (`X-API-Key`) via a FastAPI
   dependency, applied to all `/api/*` routes except `/health`. Not enterprise auth — just enough that the
   API isn't wide open on a public EC2 box.
2. **Rate limit** `/api/ingest` and `/api/ask` (e.g. `slowapi`) — protects the Groq free-tier cap called
   out in the README.
3. **`docker-compose.prod.yml`**: add `healthcheck` blocks and `restart: unless-stopped` for each service.
4. Confirm `.env.example` documents every new var added above (`RESEND_API_KEY` or `SLACK_WEBHOOK_URL`,
   `API_KEY`).

---

## Phase 7 — Demo/application polish

1. **Seed script** `scripts/seed_demo_data.py`: populates a handful of realistic reports/entities/claims
   (including at least one deliberate contradiction) so you can record the Loom demo without depending on
   live API rate limits or waiting on real ingestion.
2. **`/api/stats` → one-pager generator**: a small script that pulls current stats and formats them as
   markdown, so the "quantifiable impact" paragraph in your written application always matches what's
   actually in the dashboard (no risk of the app and the writeup disagreeing).
3. Update root `README.md`'s "Performance & Cost Notes" section with the real Phase 2 numbers once you
   have them.

---

## Loom video mapping (for your reference, not the coding agent's)

- **Problem:** manually monitoring competitors/market signals across news, SEC filings, stock moves, and
  social chatter is slow and error-prone; and you have no visibility into which claims in a
  research brief have actually been verified.
- **Solution:** an agent pipeline that ingests continuously, cross-checks every claim against sources
  before it reaches a report, and surfaces contradictions instead of hiding them.
- **The agent:** show the Settings/watchlist page (owner adds a company, zero code), then the Ask agent
  answering a live question, then the Impact dashboard.
- **Effect:** your Phase 2 numbers — audit catch rate, time-to-report vs. your measured manual baseline,
  contradictions surfaced that a manual skim would've missed.
