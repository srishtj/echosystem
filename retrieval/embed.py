from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid

_model = SentenceTransformer("all-MiniLM-L6-v2")

qdrant = QdrantClient(url="http://localhost:6333")

existing = [c.name for c in qdrant.get_collections().collections]
if "articles" not in existing:
    qdrant.create_collection(
        collection_name="articles",
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

def embed_text(text: str) -> list[float]:
    return _model.encode(text, convert_to_tensor=False).tolist()

def embed_and_store(text: str, metadata: dict):
    vector = embed_text(text)
    qdrant.upsert(
        collection_name="articles",
        points=[
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload=metadata,
            )
        ],
    )