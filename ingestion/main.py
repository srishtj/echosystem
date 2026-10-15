from dotenv import load_dotenv
load_dotenv()

from ingestion.celery_app import validate_required_env_vars
validate_required_env_vars()

import os
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from graph.ingest import driver
from ingestion.compare import build_entity_comparison, parse_entity_list
from ingestion.report_store import (
    add_watchlist_entry,
    delete_watchlist_entry,
    get_stats,
    list_watchlist,
    load_recent_reports,
)
from ingestion.tasks import poll_topic


class IngestRequest(BaseModel):
    query: str


class WatchlistRequest(BaseModel):
    type: Literal["company", "topic"]
    value: str
    cadence: Literal["daily", "weekly"] = "daily"


class AskRequest(BaseModel):
    question: str


# Single shared-secret header, not enterprise auth — just enough that the API
# isn't wide open on a public EC2 box. Unset API_KEY disables the check
# entirely (local dev default); set it in .env to require it.
API_KEY = os.environ.get("API_KEY")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(api_key_header)):
    if not API_KEY:
        return
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="EchoSystem-AI Ingestion")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

def cors_settings() -> dict:
    """Origins allowed to call the API from a browser.

    CORS_ORIGINS (comma-separated) overrides the default of any localhost port.
    The bundled dashboard does not need this: it calls the API through its own
    server-side proxy. It matters only for other browser clients.
    """
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:
        return {"allow_origins": origins}
    return {"allow_origin_regex": r"http://localhost:\d+"}


app.add_middleware(
    CORSMiddleware,
    **cors_settings(),
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Every /api/* route requires the API key (when configured); /health does not,
# so load balancers/uptime checks don't need a credential.
api = APIRouter(dependencies=[Depends(require_api_key)])


@app.get("/health")
def health():
    return {"status": "ok"}


@api.post("/api/ingest")
@limiter.limit("5/minute")
def ingest_topic(request: Request, req: IngestRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=422, detail="query must not be empty")
    poll_topic.delay(query)
    return {"status": "queued", "query": query}


@api.get("/api/graph")
def get_graph_snapshot():
    with driver.session() as session:
        nodes = session.run(
            "MATCH (n:Entity) RETURN n.name AS name, n.type AS type LIMIT 200"
        ).data()
        names = [n["name"] for n in nodes]
        # Edges must be restricted to the same node set returned above — an edge
        # pointing at an entity outside that set crashes react-force-graph's
        # internal link resolution ("node not found: X").
        edges = session.run(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WHERE a.name IN $names AND b.name IN $names "
            "RETURN a.name AS source, b.name AS target, type(r) AS relation LIMIT 300",
            names=names,
        ).data()
    return {"nodes": nodes, "edges": edges}


@api.get("/api/reports")
def get_recent_reports():
    return load_recent_reports()


@api.get("/api/watchlist")
def get_watchlist():
    return list_watchlist()


@api.post("/api/watchlist")
def create_watchlist_entry(req: WatchlistRequest):
    value = req.value.strip()
    if not value:
        raise HTTPException(status_code=422, detail="value must not be empty")
    entry_id = add_watchlist_entry(req.type, value, req.cadence)
    return {"id": entry_id, "type": req.type, "value": value, "cadence": req.cadence}


@api.delete("/api/watchlist/{entry_id}")
def remove_watchlist_entry(entry_id: str):
    delete_watchlist_entry(entry_id)
    return {"status": "deleted", "id": entry_id}


@api.get("/api/stats")
def get_impact_stats():
    stats = get_stats()

    with driver.session() as session:
        contradictions = session.run(
            "MATCH ()-[r:CONTRADICTS]->() RETURN count(r) AS c"
        ).single()["c"]

    stats["total_contradictions"] = contradictions
    return stats


@api.get("/api/timeline/{name}")
def get_entity_timeline(name: str):
    with driver.session() as session:
        claims = session.run(
            "MATCH (n:Entity {name: $name})-[:CLAIM]->(c:Claim) "
            "RETURN c.text AS claim, c.source AS source, c.published_at AS published_at "
            "ORDER BY c.published_at IS NULL, c.published_at DESC "
            "LIMIT 50",
            name=name,
        ).data()
    return claims


@api.get("/api/entity/{name}")
def get_entity_detail(name: str):
    with driver.session() as session:
        node = session.run(
            "MATCH (n:Entity {name: $name}) RETURN n.name AS name, n.type AS type",
            name=name,
        ).single()
        if not node:
            raise HTTPException(status_code=404, detail="Entity not found")

        relations = session.run(
            "MATCH (n:Entity {name: $name})-[r]-(m:Entity) "
            "RETURN type(r) AS relation, m.name AS neighbor, "
            "CASE WHEN startNode(r).name = $name THEN 'out' ELSE 'in' END AS direction, "
            "r.evidence AS evidence "
            "LIMIT 50",
            name=name,
        ).data()

        claims = session.run(
            "MATCH (n:Entity {name: $name})-[:CLAIM]->(c:Claim) "
            "OPTIONAL MATCH (c)-[:CONTRADICTS]-(other:Claim) "
            "RETURN c.text AS claim, c.source AS source, c.published_at AS published_at, "
            "count(other) AS contradiction_count "
            "ORDER BY c.published_at IS NULL, c.published_at DESC "
            "LIMIT 50",
            name=name,
        ).data()

    return {
        "name": node["name"],
        "type": node["type"],
        "relations": relations,
        "claims": claims,
    }


@api.post("/api/ask")
@limiter.limit("5/minute")
def ask_question(request: Request, req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")

    from agents.analyst import run_ask

    try:
        result = run_ask(question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ask agent failed: {e}")
    audit = result.get("audit")
    return {
        "answer": result["final_report"],
        "audit_status": audit.status if audit else "unknown",
        "retry_count": result["retry_count"],
        "sources": result.get("retrieved_context", []),
    }


@api.get("/api/compare")
def compare_entities(entities: str):
    names = parse_entity_list(entities)
    if not names:
        raise HTTPException(status_code=422, detail="entities must not be empty")
    return {"entities": [build_entity_comparison(name) for name in names]}


@api.get("/api/stock/{query}")
def get_stock(query: str):
    from finance.stock import get_stock_data

    try:
        data = get_stock_data(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stock lookup failed: {e}")
    if not data:
        raise HTTPException(status_code=404, detail="No matching ticker found")
    return data


@api.get("/api/sec/{query}")
def get_sec(query: str):
    from finance.sec import get_sec_snapshot

    try:
        data = get_sec_snapshot(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SEC lookup failed: {e}")
    if not data:
        raise HTTPException(status_code=404, detail="No matching SEC filer found")
    return data


@api.get("/api/social/{query}")
def get_social(query: str):
    from social.reddit import search_reddit

    try:
        return search_reddit(query)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Reddit lookup failed: {e}")


app.include_router(api)
