import logging
from dotenv import load_dotenv
import os
load_dotenv()

import instructor
from groq import Groq
from extraction.schemas import ExtractionResult
from extraction.chunking import dynamic_chunks
from ingestion.celery_app import celery_app

logger = logging.getLogger(__name__)

client = instructor.from_groq(
    Groq(api_key=os.environ["GROQ_API_KEY"]),
    mode=instructor.Mode.JSON
)


def _extract_chunk(title: str, text: str) -> ExtractionResult:
    return client.chat.completions.create(
        model="llama-3.1-8b-instant",
        response_model=ExtractionResult,
        max_retries=2,
        messages=[{
            "role": "user",
            "content": (
                "Extract entities and relations from this article."
                f"\n\nTitle: {title}\n\nText: {text}"
            ),
        }],
    )


@celery_app.task
def extract_entities(
    title: str, text: str, source_url: str = "", published_at: str | None = None
):
    from retrieval.embed import embed_and_store
    from graph.ingest import write_to_graph

    chunks = dynamic_chunks(text, max_tokens=3000)

    entities_by_name = {}
    relations = []
    summaries = []

    for chunk in chunks:
        try:
            result = _extract_chunk(title, chunk)
        except Exception as exc:
            logger.warning("Chunk extraction failed for %r: %s", title[:60], exc)
            continue

        for e in result.entities:
            entities_by_name[e.name] = e
        relations.extend(result.relations)
        summaries.append(result.summary)

        embed_and_store(chunk, {
            "text": chunk,
            "title": title,
            "source_url": source_url,
            "primary_entity": result.entities[0].name if result.entities else None,
        })

    merged = {
        "entities": [e.model_dump() for e in entities_by_name.values()],
        "relations": [r.model_dump() for r in relations],
        "summary": " ".join(summaries),
    }

    logger.debug("Extraction result: %s", merged)
    write_to_graph(merged, source_url, published_at)
    return merged