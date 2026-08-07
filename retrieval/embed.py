import os
from dotenv import load_dotenv
load_dotenv()

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid

_model = None
_qdrant = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        # Force CPU: letting torch auto-select the Metal (MPS) backend touches
        # Objective-C classes that aren't fork-safe, which crashes Celery's
        # prefork worker pool ("+[MPSGraphObject initialize] ... fork() was
        # called"). CPU is plenty fast for this small a model.
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _model


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        client = QdrantClient(
            url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
            api_key=os.environ.get("QDRANT_API_KEY") or None,
        )
        existing = [c.name for c in client.get_collections().collections]
        if "articles" not in existing:
            client.create_collection(
                collection_name="articles",
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
        _qdrant = client
    return _qdrant


def embed_text(text: str) -> list[float]:
    return _get_model().encode(text, convert_to_tensor=False).tolist()


def embed_and_store(text: str, metadata: dict):
    vector = embed_text(text)
    _get_qdrant().upsert(
        collection_name="articles",
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=metadata,
            )
        ],
    )