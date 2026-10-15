# EchoSystem AI

EchoSystem AI turns news about a company or topic into a knowledge graph and a short written report, then checks that report against the articles it came from.

You give it a topic, say "Nvidia". It pulls recent articles from NewsAPI, extracts entities and relationships ("Acme acquired Globex"), writes them to Neo4j, and indexes the text in Qdrant. A researcher step drafts a report from the retrieved passages. An auditor step compares the draft with those same passages and can send it back for a rewrite, up to three attempts. If the third attempt still fails, the report is saved with an `[UNVERIFIED]` note rather than passed off as checked.

When two articles disagree about the same entity (one says profit, another says loss), the graph keeps both claims and links them with a `CONTRADICTS` edge instead of picking one.

It's a prototype. The auditor is an LLM comparing text to text, so a "pass" means the model found nothing wrong, not that the report is true. Nobody has measured how often it's right (see [Testing](#testing)).

## What a run looks like

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H 'Content-Type: application/json' -d '{"query": "Nvidia"}'
# {"status":"queued","query":"Nvidia"}

curl http://localhost:8000/api/reports      # after the worker finishes
```

The API returns immediately and a Celery worker does the rest (`poll_topic` in `ingestion/tasks.py`):

1. Ask NewsAPI for up to 8 recent English articles.
2. Fetch each page and strip the HTML. If that leaves under 200 characters, use the text NewsAPI returned instead.
3. Split the text into chunks of about 3000 tokens and extract entities and relations from each one with `llama-3.1-8b-instant` through Instructor. The output is validated against a Pydantic schema.
4. Embed each chunk into Qdrant. Write entities, relations and claims to Neo4j, checking each new claim against the entity's existing ones for contradictions.
5. Run the researcher/auditor loop on the topic and save the report plus run metrics (duration, tokens, retries, flagged claims) to a local SQLite file.

There is also `POST /api/ask`, which answers a free-form question. That agent can call four tools (graph search, stock data, SEC filings, Reddit) and its answer goes through the same auditor.

## How the pieces fit

```
POST /api/ingest ─▶ Celery worker (Redis broker)
                        │ NewsAPI → fetch + clean HTML
                        ▼
              chunk → Groq via Instructor → Pydantic schema
                        │
            ┌───────────┴───────────┐
            ▼                       ▼
      Qdrant (chunk vectors)   Neo4j (entities, relations, claims, CONTRADICTS)
            └───────────┬───────────┘
                        ▼   hybrid_search: top vector hits, then graph neighbours
              LangGraph: researcher ──draft──▶ auditor
                        ▲                        │ fail, fewer than 3 audits
                        └────────────────────────┤
                                                 │ pass           → finalize
                                                 │ 3rd fail       → finalize_with_warning
                                                 ▼
                      SQLite reports.db ─▶ FastAPI ─▶ Next.js dashboard

POST /api/ask ─▶ LangGraph: analyst (up to 4 tool rounds) ─▶ same auditor and finalize nodes
Celery beat   ─▶ run_research_cycle every 30 min (due watchlist entries), send_daily_digest at 08:00
```

- **LangGraph** runs the draft, audit, retry loop. The auditor routes through a conditional edge, and the state carries the draft, the verdict, the retry count and token counts. The Ask agent is a second graph that reuses the auditor and finalize nodes.
- **Neo4j** holds the structure: entities, typed relations with the supporting sentence stored as `evidence`, and `Claim` nodes with source URL, date and a keyword sentiment label. It's also where contradictions live.
- **Qdrant** holds one vector per chunk (`all-MiniLM-L6-v2`, 384 dimensions, cosine) with the text, title, source URL and the first entity extracted from that chunk.
- **Retrieval** (`retrieval/hybrid.py`) takes the top 5 chunks from Qdrant, then asks Neo4j for up to 10 neighbours of each chunk's first entity. So the researcher sees both what an article said and what that entity is connected to. It's a vector search followed by a graph lookup, not a combined ranking.
- **Celery + Redis** keep slow work (scraping, extraction, research) out of the API process and run the scheduled jobs. Add a company or topic on the Settings page and the 30-minute cycle re-researches it daily or weekly. If `SLACK_WEBHOOK_URL` is set, a daily digest goes to Slack; otherwise it's logged.
- **SQLite** (`reports.db`, created on first use) stores reports, run metrics, the watchlist and the last-digest time. It means no extra service to run, at the cost of being one file on one machine.
- **Dashboard** (Next.js): force graph, report feed, per-entity detail, a compare page for up to four entities (stock, SEC facts, mention volume, sentiment trend), an impact page and the watchlist. Stock data comes from yfinance, filings from SEC EDGAR, discussion from Reddit via PRAW.

## The auditor

The researcher embeds the topic, retrieves context, and drafts a report that is told to stick to the context. The auditor gets the draft and the retrieved context in a separate prompt and returns a structured verdict: `pass` or `fail`, a reason, and a list of flagged claims. Its prompt asks it to flag claims that aren't supported or that contradict other parts of the context, and to fail when support is ambiguous.

`retry_count` goes up by one each time the auditor runs, and `MAX_RETRIES` is 3. So a topic gets at most three drafts and three audits. On a fail with attempts left, the researcher is called again with the reason and flagged claims added to its prompt. On the third fail, the draft is saved with `[UNVERIFIED: failed audit after 3 attempts. Review manually.]` appended and `audit_status = "fail"`.

Things worth knowing:

- The auditor only sees the retrieved chunks. It can't tell you whether the articles themselves are right, and it doesn't check numbers independently.
- A retry runs the same retrieval query again, so the evidence usually doesn't change. If the evidence is thin, retries rarely help, and the loop ends in the UNVERIFIED outcome instead of spinning.
- Empty retrieval isn't special-cased. The researcher still drafts and the auditor still runs.
- If the auditor call itself errors out, the exception propagates. During topic ingestion it's logged and no report is saved. `/api/ask` returns 502.

## Running it

You need Python 3.13 (the pinned `numpy` and `scipy` need 3.12 or newer), Docker for Redis/Neo4j/Qdrant, Node 20+, a [Groq](https://console.groq.com) key, and a [NewsAPI](https://newsapi.org/register) key for topic ingestion. Reddit and Slack are optional.

```bash
cp .env.example .env     # every variable is explained in the file
docker compose up -d redis neo4j qdrant

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt    # pulls in PyTorch; it's a big download

uvicorn ingestion.main:app --reload --port 8000        # terminal 1
celery -A ingestion.celery_app worker --loglevel=info  # terminal 2 (--pool=solo on macOS)
celery -A ingestion.celery_app beat --loglevel=info    # terminal 3

cd dashboard && npm install && npm run dev             # terminal 4, http://localhost:3000
```

The API and workers won't start without `GROQ_API_KEY`, `NEO4J_URI`, `NEO4J_USER` and `NEO4J_PASSWORD`. `NEWSAPI_KEY` is needed for `/api/ingest`. `docker-compose.yml` uses `NEO4J_PASSWORD` as the local Neo4j password, but Neo4j only applies it the first time its data volume is created.

There's no separate indexing step. Chunks are embedded and written to the graph during ingestion, and the Qdrant collection is created on first use. The first run downloads the embedding model.

The dashboard never talks to the API directly. Its own server forwards `/api/*` requests to the backend (`dashboard/app/api/[...path]/route.ts`) and adds the `X-API-Key` header there, so the key isn't in the browser bundle. It reads `API_URL` (default `http://localhost:8000`) and `API_KEY` from the environment; for `npm run dev`, put them in `dashboard/.env.local`.

### Trying it without services

The keyword contradiction check, sentiment scoring and chunker are plain Python:

```bash
GROQ_API_KEY=x NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j NEO4J_PASSWORD=x python - <<'EOF'
from graph.contradictions import _keyword_conflict
from graph.sentiment import score_sentiment
from extraction.chunking import dynamic_chunks

a = "Acme Corp completed its acquisition of Globex and reported a record profit."
b = "Acme Corp reported a loss in the quarter as Globex gained share."
print(_keyword_conflict(a, b))                    # True  (profit vs loss)
print(score_sentiment(a), score_sentiment(b))     # positive negative
print(len(dynamic_chunks("word " * 5000, 3000)))  # 4
EOF
```

The dummy variables are there because importing `graph.contradictions` builds a Neo4j driver object. It doesn't connect.

### Seeding synthetic data

With the Docker services up and a real `GROQ_API_KEY`, this loads two invented articles, so no NewsAPI key is needed, and runs the research loop on them. This snippet hasn't been run end to end, because Docker wasn't available when the docs were written.

```python
from graph.ingest import write_to_graph
from retrieval.embed import embed_and_store
from agents.graph import run_research

def seed(evidence, relation, url):
    extraction = {
        "entities": [{"name": "Acme Corp", "type": "Company"}, {"name": "Globex", "type": "Company"}],
        "relations": [{"source": "Acme Corp", "target": "Globex",
                       "relation_type": relation, "evidence": evidence}],
        "summary": evidence,
    }
    write_to_graph(extraction, url, "2025-01-01T00:00:00+00:00")
    embed_and_store(evidence, {"text": evidence, "title": "synthetic",
                               "source_url": url, "primary_entity": "Acme Corp"})

seed("Acme Corp completed its acquisition of Globex and reported a record profit.",
     "ACQUIRED", "https://example.com/a")
seed("Acme Corp reported a loss in the quarter as Globex gained share.",
     "COMPETES_WITH", "https://example.com/b")

result = run_research("Acme Corp")
print(result["final_report"], result["audit"].status, result["retry_count"])
```

With the default `keyword` strategy the second `seed` call should create a `CONTRADICTS` edge. Check it in the Neo4j browser at http://localhost:7474 with `MATCH ()-[r:CONTRADICTS]->() RETURN r`.

### Deploying

`docker-compose.prod.yml` builds the API, worker, beat and dashboard images. It expects Neo4j and Qdrant to be hosted elsewhere (for example Neo4j Aura and Qdrant Cloud) via `NEO4J_URI` and `QDRANT_URL`. The API port is bound to `127.0.0.1`; the dashboard on port 3000 is the public entry point and reaches the API over the compose network. These images haven't been built or run, so treat this path as untested. See the notes on access below.

## Testing

```bash
pytest
```

There are 85 tests. Every call to Groq, Neo4j, Qdrant, Redis and the market-data libraries is mocked, so nothing needs to be running. `tests/conftest.py` sets placeholder `GROQ_API_KEY` and `NEO4J_*` values because several modules build clients at import time. CI runs the same suite on every push.

What they cover:

- research-loop routing, including the three-attempt cutoff and token and flagged-claim accounting
- the Ask agent's tool loop and its forced final answer after four rounds
- extraction schemas and chunking
- the three contradiction strategies, with the embedding model mocked
- sentiment scoring
- API-key checks and CORS settings
- report, metrics and watchlist storage
- digest and compare helpers

What they don't cover: the Cypher queries, Qdrant retrieval, article fetching, `extraction/tasks.py`, the finance and Reddit clients, most API endpoints, and the dashboard components. The dashboard type-checks (`npx tsc --noEmit`) and builds, and its proxy route was checked by hand against a stub backend, which isn't an automated test.

There is no evaluation of output quality. No labelled data exists, so the auditor's precision or recall, the contradiction check's accuracy, and how faithful the reports are have not been measured. The Impact page shows operational numbers only. "Audit catch rate" is the share of runs where at least one claim was flagged on some attempt. "Recovery rate" is the share of runs that needed a retry and ended in a pass. Cost is estimated from reference per-token prices in `agents/graph.py`, which you can override with environment variables, so it isn't a bill.

## Design choices

More detail, including how each was checked, is in [docs/ENGINEERING_NOTES.md](docs/ENGINEERING_NOTES.md).

- **Separate auditor call with a structured verdict.** Routing is deterministic because the verdict is a validated object. The cost is another model call per attempt, and the check is still an LLM's opinion.
- **Three attempts, then label and save.** It bounds token spend. Some reports end up marked UNVERIFIED. The alternatives were dropping them or retrying indefinitely.
- **Keep contradictions instead of resolving them.** Both claims stay in the graph. Detection is heuristic, though (see below).
- **Keyword sentiment.** It's a word-list lookup because an LLM call per claim would hit the extraction model's rate limit. It's crude.
- **Two model sizes.** `llama-3.1-8b-instant` does extraction and the optional LLM contradiction check. `llama-3.3-70b-versatile` drafts, audits and runs the Ask agent.
- **A single shared API key.** It's a minimal guard, not user authentication.

## Limitations

**Contradiction detection is rough.** The default `keyword` strategy flags a pair if it contains a listed antonym pair or a positive word in one claim and a negative word in the other. It matches whole words only, so "surged" doesn't match "surge", and it doesn't check that two claims are about the same fact or period. The `embedding` strategy runs the same keyword check but only for pairs whose embeddings are at least 0.6 similar. That threshold was eyeballed on five hand-written pairs, not tuned. The `llm` strategy asks a model about each pair and costs one call per existing claim.

**The graph is naive about identity.** Entities are matched by exact name, so "Nvidia" and "NVIDIA Corp" become two nodes. A relation is dropped if its two endpoints weren't both extracted in the same call. Re-ingesting an article adds new Qdrant points rather than updating old ones. A chunk that fails extraction is logged and skipped.

**Access control is thin.** `API_KEY` protects the API port. The dashboard proxy attaches it for every visitor, so anyone who can open the dashboard can ingest topics, ask questions and edit the watchlist, which spends Groq and NewsAPI quota. If the dashboard is reachable from the internet, put access control in front of it. The rate limit (5 requests a minute on `/api/ingest` and `/api/ask`) is keyed by client IP, so behind the proxy it effectively applies to the whole dashboard. For browser clients other than the bundled dashboard, set `CORS_ORIGINS`.

**Other.** Free-tier Groq and NewsAPI quotas can cut a long run short. Retrieval uses only the topic string as its query.

## What's next

Nothing below exists yet:

1. A small labelled set to measure the auditor and the contradiction strategies.
2. Entity aliasing and article de-duplication.
3. Integration tests against throwaway Neo4j and Qdrant containers in CI.
4. A stance-aware contradiction check (an NLI model, for example) in place of the keyword rules.
5. A Docker deployment that has been built and run end to end.

## Layout

```
ingestion/   FastAPI app, Celery app and tasks, SQLite store, compare helpers
extraction/  Pydantic schemas, Instructor extraction task, chunking
graph/       Neo4j writes, contradiction detection, sentiment
retrieval/   Qdrant embedding and the hybrid retriever
agents/      LangGraph research loop, auditor, Ask agent
finance/     yfinance and SEC EDGAR lookups
social/      Reddit lookup
dashboard/   Next.js dashboard and its API proxy
tests/       pytest suite, external calls mocked
```

## How it was built

Claude was used during development to brainstorm architecture options and to help debug. The author integrated the retrieval and agent workflows, reviewed the changes, and tested the system's behavior, and is responsible for understanding the implementation and its limitations. See [docs/ENGINEERING_NOTES.md](docs/ENGINEERING_NOTES.md) for design details.

There's no license file yet.
