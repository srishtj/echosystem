import sys
import types

import pytest

from graph.contradictions import _keyword_conflict, _embedding_conflict, _llm_conflict

ANTONYM_CASES = [
    (
        "The company went bankrupt last quarter.",
        "The company remained profitable throughout the year.",
        True,
    ),
    ("Layoffs hit the division hard.", "The division announced major hiring plans.", True),
    ("Sales fell sharply in Q3.", "Sales rose sharply in Q3.", True),
    ("The stock was upgraded by analysts.", "The stock was downgraded by analysts.", True),
]

MARKER_OVERLAP_CASES = [
    (
        "The company reported record profit growth.",
        "The company reported a steep loss and decline.",
        True,
    ),
    (
        "The company reported record profit growth.",
        "The company expanded operations further.",
        False,
    ),
]

NO_CONFLICT_CASES = [
    ("The company is headquartered in Austin.", "The company was founded in 2010.", False),
    ("The CEO spoke at the conference.", "The CEO spoke at the conference.", False),
]


@pytest.mark.parametrize(
    "claim_a,claim_b,expected", ANTONYM_CASES + MARKER_OVERLAP_CASES + NO_CONFLICT_CASES
)
def test_keyword_conflict(claim_a, claim_b, expected):
    assert _keyword_conflict(claim_a, claim_b) is expected


def test_embedding_conflict_low_similarity_is_flagged(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")

    class FakeModel:
        def encode(self, text, convert_to_tensor=True):
            return text

    class FakeUtil:
        @staticmethod
        def cos_sim(a, b):
            return 0.1  # below the default 0.3 threshold -> conflict

    fake_module.SentenceTransformer = lambda name, device=None: FakeModel()
    fake_module.util = FakeUtil()
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    import graph.contradictions as contradictions

    if hasattr(contradictions._embedding_conflict, "_model"):
        delattr(contradictions._embedding_conflict, "_model")

    assert contradictions._embedding_conflict("claim A", "claim B") is True


def test_embedding_conflict_high_similarity_is_not_flagged(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")

    class FakeModel:
        def encode(self, text, convert_to_tensor=True):
            return text

    class FakeUtil:
        @staticmethod
        def cos_sim(a, b):
            return 0.95  # above the default 0.3 threshold -> no conflict

    fake_module.SentenceTransformer = lambda name, device=None: FakeModel()
    fake_module.util = FakeUtil()
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    import graph.contradictions as contradictions

    if hasattr(contradictions._embedding_conflict, "_model"):
        delattr(contradictions._embedding_conflict, "_model")

    assert contradictions._embedding_conflict("claim A", "claim B") is False


def test_llm_conflict_returns_verdict_from_client(monkeypatch):
    fake_instructor = types.ModuleType("instructor")
    fake_instructor.Mode = types.SimpleNamespace(JSON="json")

    class FakeCompletions:
        def create(self, **kwargs):
            return types.SimpleNamespace(contradicts=True, reason="opposite outcomes stated")

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake_instructor.from_groq = lambda client, mode=None: FakeClient()

    fake_groq = types.ModuleType("groq")
    fake_groq.Groq = lambda *args, **kwargs: object()

    monkeypatch.setitem(sys.modules, "instructor", fake_instructor)
    monkeypatch.setitem(sys.modules, "groq", fake_groq)

    import graph.contradictions as contradictions

    assert contradictions._llm_conflict("claim A", "claim B") is True
