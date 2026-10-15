# Engineering notes

How the main pieces work, what each choice costs, and what hasn't been checked. Everything here is
taken from the code, tests and commit history. See the [README](../README.md) for setup.

## The audit loop

The problem: an LLM drafting a report from retrieved passages will sometimes state things the
passages don't say.

`agents/auditor.py` makes a second, separate call. It receives the draft and the retrieved context
and returns a Pydantic-validated verdict: `pass`/`fail`, a reason, and the flagged claims.
`route_after_audit` in `agents/graph.py` then picks one of three paths: finalize, go back to the
researcher with the reason and flagged claims in its prompt, or finalize with an `[UNVERIFIED ...]`
suffix.

The auditor node increments `retry_count`, and `MAX_RETRIES` is 3, so the worst case is three drafts
and three audits. The prompt tells the auditor to fail when support is ambiguous. That should bias it
toward false alarms over missed claims, but nothing here measures the bias.

What it costs: another model call per attempt, and the verdict is still a model's opinion about
retrieved text. A retry runs the same retrieval query, so it can rephrase a draft but can't add
evidence that wasn't indexed. When evidence is thin, the loop ends in the UNVERIFIED path.

Checked by `tests/agents/test_graph.py`: pass on the first attempt, fail then pass, and repeated
failure, including token and flagged-claim accumulation. The model calls are mocked. Not checked:
how accurate the auditor is on real drafts, or what it does when retrieval returns nothing (that case
isn't handled specially).

## One verification path for reports and answers

The Ask agent needed the same check. `agents/analyst.py` builds a second LangGraph graph that reuses
`auditor_node`, `route_after_audit`, `finalize` and `finalize_with_warning`. To make that work,
`AskState` uses the same field names as `ResearchState`, and the router's `"researcher"` outcome is
mapped onto the analyst node.

That avoids two copies of the retry logic. The price is that the two state types are coupled, and the
node-name mapping only makes sense with the comment next to it. Covered by `tests/agents/test_analyst.py`
(the tool loop, the forced answer after four rounds, and the three audit outcomes).

## Contradictions

News sources disagree, and keeping only one claim hides that. Each relation's evidence sentence
becomes a `Claim` node linked to both entities. When a claim is written, it's compared with that
entity's existing claims, and a match creates a `CONTRADICTS` edge. `CONFLICT_STRATEGY` selects the
comparison:

- `keyword` (default): a listed antonym pair, or a positive marker word in one claim and a negative
  one in the other. Free and fast. It matches whole words only ("surged" doesn't match "surge") and
  doesn't check that the two claims are about the same fact or time period.
- `embedding`: the same keyword check, but only for pairs whose `all-MiniLM-L6-v2` cosine similarity
  is at least 0.6.
- `llm`: `llama-3.1-8b-instant` is asked whether the pair contradicts. It's the only strategy that can
  read meaning, and it costs one call per existing claim.

The embedding strategy originally flagged a pair when similarity was *below* 0.3. That treated
"different" as "contradictory", so two unrelated claims about one company (a profit report and a
regulatory fine) would be linked as a conflict. Embeddings measure topical closeness, not agreement,
so they now serve only as a same-topic filter on the keyword check. In a quick check, sentence pairs
that really opposed each other scored 0.75 to 0.81, while two unrelated pairs about the same company
scored 0.50 and 0.45, which is where 0.6 came from. That's five hand-written pairs, so
the threshold is a placeholder, not a tuned value.

Tests in `tests/graph/test_contradictions.py` use a mocked embedding model and check three things: opposed
claims about the same thing are flagged, opposed wording in unrelated claims isn't, and two merely
dissimilar claims aren't (and the embedding model isn't even loaded for them). No accuracy
measurement against real data exists for any strategy. A real fix for the underlying problem would
be a stance- or NLI-based check, which isn't built.

## Extraction schema

The schema is a starting point for organizing business news, not a model of every market event.
Entities are limited to four types, Company, Person, Product and Material, and relations to six
types. The relations connect those entities so the graph can add structure (who is tied to whom, and
by what sentence) next to the article passages that come back from the vector index. Both lists are
`Literal` types in `extraction/schemas.py`. Instructor validates model output against them and retries
up to twice.

A closed set keeps the graph consistent. It also matters for safety: the relation type is
interpolated into the Cypher `MERGE` in `graph/ingest.py`, so the `Literal` constraint is what keeps
free text out of the query.

### The six relation types

Each relation is a directed edge from `source` to `target`, with the supporting sentence stored in
`evidence`. The examples below are made-up sentences showing how each type is meant to be read. They
are not output from real data.

| Type | Read as | Example sentence and edge |
|---|---|---|
| `COMPETES_WITH` | the two entities sell against each other | "Acme and Globex are fighting for the same cloud customers." gives `Acme -COMPETES_WITH-> Globex` |
| `INVESTS_IN` | source puts money into target | "Initech took a 10% stake in Globex." gives `Initech -INVESTS_IN-> Globex` |
| `THREATENED_BY` | target is a threat to source | "Acme's margins are under pressure from cheaper rival Globex." gives `Acme -THREATENED_BY-> Globex` |
| `PARTNERS_WITH` | the two entities cooperate | "Acme and Globex announced a joint chip-design effort." gives `Acme -PARTNERS_WITH-> Globex` |
| `ACQUIRED` | source bought target | "Acme completed its acquisition of Globex." gives `Acme -ACQUIRED-> Globex` |
| `SUPPLIES` | source provides goods to, or is a supplier of, target | "Globex supplies lithium to Acme." gives `Globex -SUPPLIES-> Acme` or `Globex -SUPPLIES-> lithium` |

What the code does and doesn't pin down:

- The extraction prompt (`_extract_chunk` in `extraction/tasks.py`) is just "Extract entities and
  relations from this article." It doesn't define the types or their direction, so the model works
  from the names alone. The directions in the table are a reading of the names, not something the
  code enforces.
- That leaves some cases ambiguous. For `SUPPLIES`, the target could be the customer or the thing
  supplied, which is why the table shows both. `COMPETES_WITH` and `PARTNERS_WITH` are symmetric in
  meaning but stored as one directed edge, so which side is the source depends on the sentence.
- Nothing restricts which entity types a relation connects. A `Person` can invest in a `Company`,
  but the schema would also accept a `Material` that `ACQUIRED` a `Product`.
- Edges are `MERGE`d on (source, target, type), so one pair has at most one edge of each type. A later
  article about the same pair overwrites `evidence` and `last_seen` (and the `published_at` of the
  latest write) instead of adding a second edge. A relation is silently skipped if either endpoint
  wasn't extracted in the same call.
- The dashboard shows the type name as the edge label and tags each relation in/out relative to the
  selected entity.

Schema behavior is tested in `tests/extraction/test_schemas.py`, which accepts `ACQUIRED` and
`SUPPLIES` and rejects an unlisted type (`MERGED_WITH`). `extraction/tasks.py` and the Neo4j writes
have no tests. Entities are matched by exact name, so alias variants become separate nodes.

## Chunking and rate limits

`extraction/chunking.py` splits on whitespace into chunks of at most 3000 `cl100k_base` tokens. That
tokenizer only approximates the Llama models' own, and chunks don't overlap. A chunk that fails
extraction is logged and skipped so one bad chunk doesn't lose the article. Sentiment is a word-list
lookup because a model call per claim would compete with extraction for the same rate limit, as the
comment in `graph/sentiment.py` says.

## Retrieval

Vector search alone returns passages without saying how their entities relate.
`retrieval/hybrid.py` takes the top 5 Qdrant hits, then fetches up to 10 neighbours in Neo4j for
each hit's `primary_entity`, which is simply the first entity extracted from that chunk. It's a
heuristic, and only neighbour names come back, not their evidence text. There's no re-ranking, and
no tests cover it.

## Access to the API

The API has one shared secret, `API_KEY`, checked as an `X-API-Key` header on every `/api/*` route
except `/health`. The dashboard used to send it from the browser as `NEXT_PUBLIC_API_KEY`. Next.js
inlines `NEXT_PUBLIC_*` values into the client JavaScript, so anyone who loaded the dashboard could
read the key. With it they could call every route: queue ingestion (NewsAPI plus Groq calls for the
report), ask questions (Groq), add watchlist entries (which the 30-minute cycle then researches
repeatedly), read all stored data, and hit the stock, SEC and Reddit lookups. Only `/api/ingest` and
`/api/ask` were rate-limited, at 5 per minute per IP. In practice the key only stopped someone who
could reach the API port but hadn't loaded the dashboard, and the compose file published that port.

Now the dashboard has a small catch-all route, `dashboard/app/api/[...path]/route.ts`, that forwards
requests to the backend and adds the key from server-side `API_KEY`. A production build of the
dashboard contains neither the key nor the backend URL. The browser only talks to the dashboard's own
origin, which also removes the need for CORS in the bundled setup. In `docker-compose.prod.yml` the API
port is bound to `127.0.0.1`.

This doesn't authenticate dashboard visitors. The proxy attaches the key for anyone who can open the
page, so a dashboard reachable from the internet still lets strangers spend quota. Protecting it
(a reverse proxy with basic auth, a VPN, or similar) is up to the deployer and isn't in the repo.
A side effect: the backend sees one client IP, the dashboard server, so the rate limit is shared by
all dashboard users.

For browser clients other than the dashboard, `CORS_ORIGINS` (comma-separated) replaces the default
of any `http://localhost:<port>`. `tests/ingestion/test_cors.py` checks both behaviors with a
preflight request. The proxy was checked by hand against a stub backend (path, query string, body and
status codes pass through; the key is added server-side) and by building the dashboard and searching
the client bundle for the key. Those checks aren't automated.

## Operational details in the code

- Embedding models are forced onto CPU in `retrieval/embed.py` and `graph/contradictions.py`. A
  comment says the Metal backend crashes Celery's prefork workers on Apple Silicon.
- `ingestion/celery_app.py` re-adds the repo root to `sys.path` on Celery lifecycle signals, because
  modules imported lazily inside tasks otherwise can't be found.
- Article and SEC fetches retry up to three times with exponential backoff, only for transport errors
  and 5xx responses.
- Cost is estimated: token counts accumulate across the research loop and are priced at reference
  per-token rates, since the free tier costs nothing. Auditor token counts come from Instructor's raw
  response when it's available and are zero otherwise.
- `docker-compose.yml` takes the Neo4j password from `NEO4J_PASSWORD` instead of hardcoding it. The
  Dockerfile was changed from Python 3.11 to 3.13 because the pinned `numpy` and `scipy` need 3.12+.
- `pytest` originally failed on a fresh clone because several modules build Groq and Neo4j clients at
  import time. CI worked around it with environment variables; `tests/conftest.py` now supplies
  placeholders.

## Checked and not checked

Checked: 85 unit tests with external services mocked (they also run in GitHub Actions), a clean-copy
run of the suite without a `.env`, a dashboard type-check and production build, the dashboard proxy
against a stub backend, and the embedding strategy against the real `all-MiniLM-L6-v2` model on a few
pairs.

Not checked: ingestion against live Groq, NewsAPI, Neo4j and Qdrant; the Cypher queries; Docker image
builds; the production compose setup; and any measure of output quality (auditor accuracy,
contradiction accuracy, report faithfulness). Those are the largest open risks.

## How this was built

Claude was used during development to brainstorm architecture options and to help debug. The author's
part was integrating the retrieval and agent workflows, reviewing implementation changes, and testing
system behavior. The work was iterative and AI-assisted, and the author is responsible for
understanding the implementation and its limitations.
