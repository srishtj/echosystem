from neo4j import GraphDatabase
from ingestion.celery_app import celery_app
from graph.contradictions import check_and_flag_contradiction
from graph.sentiment import score_sentiment

from dotenv import load_dotenv
import os

load_dotenv()

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
)

@celery_app.task
def write_to_graph(extraction: dict, source_url: str = "", published_at: str | None = None):
    with driver.session() as session:
        for e in extraction["entities"]:
            session.run(
                "MERGE (n:Entity {name: $name})"
                "SET n.type = $type",
                name = e["name"], type=e["type"]
            )
        for r in extraction["relations"]:
            session.run(
                "MATCH (a:Entity {name: $src}), (b:Entity {name: $tgt}) "
                "MERGE (a)-[rel:" + r["relation_type"] + "]->(b) "
                "SET rel.evidence = $evidence, rel.last_seen = timestamp(), "
                "rel.published_at = $published_at",
                src=r["source"], tgt=r["target"], evidence=r["evidence"],
                published_at=published_at,
            )

            sentiment = score_sentiment(r["evidence"])
            for entity_name in (r["source"], r["target"]):
                check_and_flag_contradiction(session, entity_name, r["evidence"], source_url)
                session.run(
                    "MATCH (n:Entity {name: $name}) "
                    "MERGE (cl:Claim {text: $claim, source: $source}) "
                    "SET cl.published_at = $published_at, cl.sentiment = $sentiment "
                    "MERGE (n)-[:CLAIM]->(cl)",
                    name=entity_name, claim=r["evidence"], source=source_url,
                    published_at=published_at, sentiment=sentiment,
                )


def find_mentioned_entities(text: str) -> list[str]:
    with driver.session() as session:
        names = [r["name"] for r in session.run("MATCH (n:Entity) RETURN n.name AS name").data()]

    lowered = text.lower()
    return [name for name in names if name and name.lower() in lowered]