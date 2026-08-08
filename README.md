# EchoSystem-AI

An autonomous multi-agent market intelligence system. It ingests live news, extracts structured
entities/relations via LLM function-calling, persists them in a Neo4j knowledge graph alongside a
Qdrant vector index, and runs a cyclic LangGraph workflow where a Researcher agent drafts reports
and an Auditor agent fact-checks them against the source data before anything reaches the dashboard.

## Architecture

```
RSS/News feeds ─▶ FastAPI + Celery/Redis ingestion ─▶ Instructor + Pydantic extraction
                                                              │
                                              ┌───────────────┴───────────────┐
                                              ▼                               ▼
                                        Neo4j (graph)                  Qdrant (vectors)
                                              └───────────────┬───────────────┘
                                                              ▼
                                              LangGraph Orchestrator (hybrid retrieval)
                                                     │                    ▲
                                                     ▼                    │
                                            Researcher Agent ──draft──▶ Auditor Agent
                                                     ▲                    │
                                                     └──fail, retry≤3─────┘
                                                              │ pass
                                                              ▼
                                                     Next.js Dashboard
```

The same Auditor node also fact-checks the natural-language Ask agent's answers — one
verification path for every claim that reaches the user, not two.

## What Makes This Different

- **Self-correcting Critic Loop** — a Researcher agent drafts a report from hybrid graph+vector
  context; an independent Auditor agent (separate prompt, structured verdict) cross-checks every
  claim against the retrieved source chunks and sends it back for a rewrite (max 3 attempts) if
  anything is unsupported or contradictory.
- **Contradiction-aware graph** — when two sources disagree about the same entity, the system
  doesn't silently pick a side; it records a `CONTRADICTS` edge between both claims. Three
  pluggable detection strategies (keyword heuristic, embedding similarity, LLM judgment) are
  swappable via `CONFLICT_STRATEGY`.
- **Hybrid Graph-RAG retrieval** — every retrieval fuses Qdrant semantic search with a Neo4j graph
  traversal of the matched entity's neighborhood, so agents see both *what was said* and
  *how it connects* to everything else.
- **Natural-language Ask agent** — a ReAct-style tool-calling agent that pulls from the knowledge
  graph, live stock data, SEC filings, and Reddit discussion to answer plain-language questions,
  routed through the same Auditor for verification before the answer is shown.
- **Zero-code watchlist automation** — add a company or topic in Settings and it's automatically
  researched on a daily/weekly cadence and rolled into a digest (Slack), no redeploy required.
- **Measurable audit impact** — every run's duration, token cost, retry count, and flagged-claim
  count is tracked, surfaced on an Impact dashboard (audit catch rate, recovery rate, cost).

## Features

- **Knowledge graph** — interactive force-directed graph with search, hover summaries, and
  click-through to full sourced detail per entity.
- **Topic research** — type any company/industry/person; the system ingests real articles, extracts
  entities and relationships, and generates a fact-checked summary report.
- **Ask EchoSystem** — a chat interface for plain-language questions, answered by the tool-calling
  agent and verified before display.
- **Compare** — side-by-side stock price, SEC fundamentals, mention volume, and sentiment trend
  across up to 4 entities.
- **Settings / Watchlist** — add companies or topics with a cadence (daily/weekly); a background
  scheduler keeps them researched automatically and feeds the daily digest.
- **Impact dashboard** — reports generated, audit catch/recovery rate, contradictions surfaced,
  estimated LLM cost, and a reports-per-day trend.
- **Market data** — live stock price/history (yfinance), SEC EDGAR filings and financial facts,
  and Reddit discussion, surfaced per entity.

## Tech Stack

LangGraph · Neo4j · Qdrant · FastAPI · Celery/Redis · Instructor · Groq (Llama 3.3) · Next.js 16 ·
yfinance · SEC EDGAR · PRAW (Reddit) · slowapi

## Project Structure

```
ingestion/    FastAPI app + Celery workers (RSS/topic polling, watchlist digest, HTML cleaning)
extraction/   Pydantic schemas + Instructor calls + token-aware chunking
graph/        Neo4j MERGE-based ingestion + contradiction detection + sentiment scoring
retrieval/    Qdrant embeddings + hybrid graph+vector retriever
agents/       LangGraph state, Researcher/Auditor Critic Loop, and the Ask agent
finance/      Stock price (yfinance) and SEC EDGAR lookups
social/       Reddit discussion lookup
dashboard/    Next.js dashboard — graph, reports, compare, settings, impact, ask agent
tests/        pytest suite (mocked LLM/API calls, no live services required)
```

## Quick Start (local dev)

```bash
cp .env.example .env   # fill in GROQ_API_KEY and NEO4J_PASSWORD

docker compose up -d redis neo4j qdrant

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

uvicorn ingestion.main:app --reload --port 8000        # terminal 1
celery -A ingestion.celery_app worker --loglevel=info  # terminal 2 (add --pool=solo on macOS)
celery -A ingestion.celery_app beat --loglevel=info    # terminal 3

cd dashboard && npm install && npm run dev              # terminal 4 → http://localhost:3000
```

Run the test suite with `pytest` — it mocks every external call (Groq, Neo4j, Qdrant, market data),
so it runs without any live services.

## Deploying (EC2 + Neo4j Aura + Qdrant Cloud)

Neo4j and Qdrant run on their managed free tiers; only Redis, the API/worker/beat processes, and
the dashboard run on the (free-tier) EC2 box — comfortably inside 1GB of RAM.

```bash
# .env: point NEO4J_URI at your Aura instance, QDRANT_URL at your Qdrant Cloud cluster,
# NEXT_PUBLIC_API_URL at your EC2 public IP/domain, and set API_KEY / NEXT_PUBLIC_API_KEY
# to require auth on every /api/* route
docker compose -f docker-compose.prod.yml up -d --build
```

Every `/api/*` route (except `/health`) requires an `X-API-Key` header when `API_KEY` is set, and
`/api/ingest` / `/api/ask` are rate-limited to protect the Groq free-tier quota.

## Performance & Cost Notes

Measured during development against the Groq free tier + local Docker Neo4j/Qdrant:

- Single article extraction (Instructor call): ~2–6s depending on article length/relation count
- Neo4j MERGE write + contradiction check: well under 100ms
- Hybrid retrieval (Qdrant search + graph neighborhood expansion): sub-second, no LLM call
- **Groq's free tier caps at 100k tokens/day** for the larger model (Researcher/Auditor/Ask agent)
  and 6k tokens/minute for the extraction model — heavy ingestion plus active Critic Loop use can
  exhaust either during a busy session; the daily cap resets on a rolling window, not
  midnight-to-midnight.
