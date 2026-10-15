import os

# Several modules build their Groq/Neo4j clients at import time. Every test mocks
# its external calls, so placeholder values are enough to import them on a clean
# checkout (the same values .github/workflows/test.yml sets).
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test-password")
