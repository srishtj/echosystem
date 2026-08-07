import os
from dotenv import load_dotenv
load_dotenv()

from neo4j import GraphDatabase
from retrieval.embed import embed_text, _get_qdrant

driver = GraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
)


def hybrid_search(query: str, top_k: int = 5):
    query_vector = embed_text(query)
    hits = _get_qdrant().query_points(
        collection_name="articles", query=query_vector, limit=top_k
    ).points

    enriched = []
    with driver.session() as session:
        for hit in hits:
            entity_name = hit.payload.get("primary_entity")
            graph_ctx = []
            if entity_name:
                graph_ctx = session.run(
                    "MATCH (n:Entity {name: $name})-[r]-(m) "
                    "RETURN type(r) AS rel, m.name AS neighbor LIMIT 10",
                    name=entity_name
                ).data()
            enriched.append({
                "text": hit.payload.get("text", ""),
                "score": hit.score,
                "graph_context": graph_ctx,
            })
    return enriched
