import pytest

from graph.sentiment import score_sentiment


@pytest.mark.parametrize(
    "text,expected",
    [
        ("The company reported record profit growth.", "positive"),
        ("Sales fell sharply amid a steep loss.", "negative"),
        ("The company is headquartered in Austin.", "neutral"),
        ("The company reported record profit but also a steep loss.", "neutral"),
    ],
)
def test_score_sentiment(text, expected):
    assert score_sentiment(text) == expected


def test_score_sentiment_is_case_insensitive():
    assert score_sentiment("RECORD PROFIT GROWTH") == "positive"
