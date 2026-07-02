from neo4j import GraphDatabase
from ingestion.celery_app import celery_app

from dotenv import load_dotenv
import os

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
)

@celery_app.task
def write_to_graph(extraction: dict):
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
                "SET rel.evidence = $evidence, rel.last_seen = timestamp()",
                src=r["source"], tgt=r["target"], evidence=r["evidence"]
            )