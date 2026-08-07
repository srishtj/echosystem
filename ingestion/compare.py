from datetime import datetime, timedelta

SENTIMENT_SCORES = {"positive": 1, "neutral": 0, "negative": -1}
MAX_ENTITIES = 4


def week_bucket(iso_date: str | None) -> str | None:
    """Monday-anchored ISO week (YYYY-MM-DD) for a claim's published_at, or None
    if the claim is undated/unparseable — those claims are excluded from trends
    since they can't be placed on a timeline."""
    if not iso_date:
        return None
    try:
        d = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except ValueError:
        return None
    monday = d - timedelta(days=d.weekday())
    return monday.strftime("%Y-%m-%d")


def sentiment_trend(claims: list[dict]) -> list[dict]:
    """claims: [{"published_at": str|None, "sentiment": str|None}] -> weekly
    average sentiment (-1..1), sorted chronologically."""
    buckets: dict[str, list[int]] = {}
    for claim in claims:
        week = week_bucket(claim.get("published_at"))
        if week is None:
            continue
        score = SENTIMENT_SCORES.get(claim.get("sentiment"), 0)
        buckets.setdefault(week, []).append(score)
    return [
        {"week": week, "avg_sentiment": sum(scores) / len(scores)}
        for week, scores in sorted(buckets.items())
    ]


def parse_entity_list(entities_param: str) -> list[str]:
    names = [n.strip() for n in entities_param.split(",") if n.strip()]
    return names[:MAX_ENTITIES]


def build_entity_comparison(name: str) -> dict:
    from graph.ingest import driver
    from finance.stock import get_stock_data
    from finance.sec import get_sec_snapshot

    with driver.session() as session:
        claims = session.run(
            "MATCH (n:Entity {name: $name})-[:CLAIM]->(c:Claim) "
            "RETURN c.published_at AS published_at, c.sentiment AS sentiment",
            name=name,
        ).data()
        mention_volume = session.run(
            "MATCH (n:Entity {name: $name})-[:CLAIM]->(c:Claim) RETURN count(c) AS c",
            name=name,
        ).single()["c"]

    try:
        stock = get_stock_data(name)
    except Exception:
        stock = None
    try:
        sec = get_sec_snapshot(name)
    except Exception:
        sec = None

    return {
        "name": name,
        "mention_volume": mention_volume,
        "sentiment_trend": sentiment_trend(claims),
        "stock": stock,
        "sec_facts": sec["facts"] if sec else None,
    }
