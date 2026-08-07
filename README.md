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

## What Makes This Different

- **Self-correcting Critic Loop** — a Researcher agent drafts a report from hybrid graph+vector
  context; an independent Auditor agent (separate prompt, structured verdict) cross-checks every
  claim against the retrieved source chunks and sends it back for a rewrite (max 3 attempts) if
  anything is unsupported or contradictory.
- **Contradiction-aware graph** — when two sources disagree about the same entity, the system
  doesn't silently pick a side; it records a `CONTRADICTS` edge between both claims. Three
  pluggable detection strategies (keyword heuristic, embedding similarity, LLM judgment) are
  swappable via `CONFLICT_STRATEGY`.
- **Dynamic, token-aware chunking** — long articles/filings are split by actual token density
  (via `tiktoken`) rather than a fixed character count, so extraction never silently truncates or
  blows the context window.
- **Hybrid Graph-RAG retrieval** — every retrieval fuses Qdrant semantic search with a Neo4j graph
  traversal of the matched entity's neighborhood, so the Researcher sees both *what was said* and
  *how it connects* to everything else.

## Tech Stack

LangGraph · Neo4j · Qdrant · FastAPI · Celery/Redis · Instructor · Groq (Llama 3.3) · Next.js 16

## Project Structure

```
ingestion/    FastAPI app + Celery workers (RSS polling, HTML cleaning)
extraction/   Pydantic schemas + Instructor calls + token-aware chunking
graph/        Neo4j MERGE-based ingestion + contradiction detection
retrieval/    Qdrant embeddings + hybrid graph+vector retriever
agents/       LangGraph state, Researcher/Auditor nodes, the Critic Loop
dashboard/    Next.js force-graph view + live report feed
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

## Deploying (EC2 + Neo4j Aura + Qdrant Cloud)

Neo4j and Qdrant run on their managed free tiers; only Redis, the API/worker/beat processes, and
the dashboard run on the (free-tier) EC2 box — comfortably inside 1GB of RAM.

```bash
# .env: point NEO4J_URI at your Aura instance, QDRANT_URL at your Qdrant Cloud cluster,
# and NEXT_PUBLIC_API_URL at your EC2 public IP/domain
docker compose -f docker-compose.prod.yml up -d --build
```

## Performance & Cost Notes

Measured during development against the Groq free tier + local Docker Neo4j/Qdrant:

- Single article extraction (Instructor call): ~2–6s depending on article length/relation count
- Neo4j MERGE write + contradiction check: well under 100ms
- Hybrid retrieval (Qdrant search + graph neighborhood expansion): sub-second, no LLM call
- **Groq's free tier caps at 100k tokens/day** — heavy ingestion (many articles in a short window)
  plus running the Critic Loop can exhaust this during active development; the daily cap resets on
  a rolling window, not midnight-to-midnight.
