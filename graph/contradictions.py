import os
import re
from neo4j import GraphDatabase

from graph.sentiment import POSITIVE_MARKERS, NEGATIVE_MARKERS

ANTONYM_PAIRS = [
    ("bankrupt", "profitable"),
    ("bankrupt", "raised"),
    ("bankrupt", "funded"),
    ("acquired", "independent"),
    ("acquired", "acquisition target"),
    ("merged", "split"),
    ("merged", "divested"),
    ("layoffs", "hiring"),
    ("layoffs", "expansion"),
    ("loss", "profit"),
    ("declined", "surged"),
    ("fell", "rose"),
    ("fell", "gained"),
    ("downgrade", "upgrade"),
    ("recall", "launch"),
    ("shutdown", "opening"),
    ("fine", "cleared"),
    ("sued", "settlement"),
]

def _keyword_conflict(claim_a: str, claim_b: str) -> bool:
    a = claim_a.lower()
    b = claim_b.lower()
 
    for pos_word, neg_word in ANTONYM_PAIRS:
        if (pos_word in a and neg_word in b) or (neg_word in a and pos_word in b):
            return True
 
    a_words = set(re.findall(r"\w+", a))
    b_words = set(re.findall(r"\w+", b))
 
    a_positive = bool(a_words & POSITIVE_MARKERS)
    a_negative = bool(a_words & NEGATIVE_MARKERS)
    b_positive = bool(b_words & POSITIVE_MARKERS)
    b_negative = bool(b_words & NEGATIVE_MARKERS)
 
    if (a_positive and b_negative) or (a_negative and b_positive):
        return True
 
    return False


def _embedding_conflict(claim_a: str, claim_b: str, min_similarity: float = 0.6) -> bool:
    """Keyword conflict, restricted to claims that are about the same thing.

    Embedding similarity cannot tell a contradiction from an unrelated claim
    (two claims about one company are often dissimilar without conflicting), so it
    is only used as a gate: the pair must already read as opposed by
    _keyword_conflict AND be at least `min_similarity` close in embedding space.
    That drops pairs like "record profit" vs "fined over a data breach" that the
    keyword check alone would flag. The 0.6 default was only eyeballed on a few
    hand-written claim pairs with all-MiniLM-L6-v2; it has not been tuned.
    """
    if not _keyword_conflict(claim_a, claim_b):
        return False

    try:
        from sentence_transformers import SentenceTransformer, util
    except ImportError:
        raise ImportError(
            "sentence-transformers is required for embedding-based conflict "
            "detection. Run: pip install sentence-transformers"
        )

    if not hasattr(_embedding_conflict, "_model"):
        # device="cpu": letting torch auto-select MPS crashes Celery's prefork
        # worker pool on Apple Silicon (see retrieval/embed.py for the same fix).
        _embedding_conflict._model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    model = _embedding_conflict._model
    emb_a = model.encode(claim_a, convert_to_tensor=True)
    emb_b = model.encode(claim_b, convert_to_tensor=True)
    similarity = float(util.cos_sim(emb_a, emb_b))

    return similarity >= min_similarity

def _llm_conflict(claim_a: str, claim_b: str) -> bool:
    try:
        import instructor
        from groq import Groq
        from pydantic import BaseModel
    except ImportError:
        raise ImportError(
            "instructor and groq are required for LLM-based conflict detection."
        )
 
    class ConflictVerdict(BaseModel):
        contradicts: bool
        reason: str
 
    client = instructor.from_groq(Groq(), mode=instructor.Mode.JSON)
 
    verdict: ConflictVerdict = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        response_model=ConflictVerdict,
        max_retries=2,
        messages=[
            {
                "role": "user",
                "content": (
                    "Do these two claims about the same entity logically "
                    "contradict each other? Answer strictly based on what is "
                    "stated — do not invent context.\n\n"
                    f"Claim A: {claim_a}\n"
                    f"Claim B: {claim_b}"
                ),
            }
        ],
    )
 
    return verdict.contradicts


CONFLICT_STRATEGY = os.getenv("CONFLICT_STRATEGY", "keyword")
 
def claims_conflict(claim_a: str, claim_b: str) -> bool:
    """
    Returns True when claim_a and claim_b appear to contradict each other.
 
    Strategy is controlled by the CONFLICT_STRATEGY environment variable:
      "keyword"   — fast heuristic, no extra cost       (default)
      "embedding" — keyword heuristic, but only for claims whose embeddings are
                    similar enough to be about the same thing
      "llm"       — Groq LLM judgment via Instructor
    """
    if CONFLICT_STRATEGY == "llm":
        return _llm_conflict(claim_a, claim_b)
    elif CONFLICT_STRATEGY == "embedding":
        return _embedding_conflict(claim_a, claim_b)
    else:
        return _keyword_conflict(claim_a, claim_b)
 
 
driver = GraphDatabase.driver(
    os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
    auth=(
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ.get("NEO4J_PASSWORD", "your_password_here"),
    ),
)
 
def check_and_flag_contradiction(
    session,
    entity_name: str,
    new_claim: str,
    source_url: str,
) -> bool:
    
    existing = session.run(
        "MATCH (n:Entity {name: $name})-[c:CLAIM]->(cl:Claim) "
        "RETURN cl.text AS text, cl.source AS source",
        name=entity_name,
    ).data()
 
    contradiction_found = False
 
    for row in existing:
        if claims_conflict(row["text"], new_claim):
            session.run(
                "MATCH (n:Entity {name: $name}) "
                "MERGE (c1:Claim {text: $old, source: $old_source}) "
                "MERGE (c2:Claim {text: $new, source: $new_source}) "
                "MERGE (c1)-[:CONTRADICTS {detected_at: timestamp()}]->(c2)",
                name=entity_name,
                old=row["text"],
                old_source=row["source"],
                new=new_claim,
                new_source=source_url,
            )
            contradiction_found = True
 
    return contradiction_found
 