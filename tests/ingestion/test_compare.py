import pytest

from ingestion.compare import parse_entity_list, sentiment_trend, week_bucket


def test_week_bucket_none_for_missing_date():
    assert week_bucket(None) is None
    assert week_bucket("") is None


def test_week_bucket_none_for_unparseable_date():
    assert week_bucket("not-a-date") is None


def test_week_bucket_anchors_to_monday():
    # 2024-01-01 was a Monday.
    assert week_bucket("2024-01-01T10:00:00") == "2024-01-01"
    # 2024-01-03 (Wednesday) falls in the same week.
    assert week_bucket("2024-01-03T10:00:00") == "2024-01-01"


def test_week_bucket_handles_zulu_suffix():
    assert week_bucket("2024-01-01T10:00:00Z") == "2024-01-01"


def test_sentiment_trend_averages_within_a_week():
    claims = [
        {"published_at": "2024-01-01T10:00:00", "sentiment": "positive"},
        {"published_at": "2024-01-03T10:00:00", "sentiment": "negative"},
    ]
    trend = sentiment_trend(claims)
    assert trend == [{"week": "2024-01-01", "avg_sentiment": 0.0}]


def test_sentiment_trend_separates_weeks_and_sorts_chronologically():
    claims = [
        {"published_at": "2024-01-15T10:00:00", "sentiment": "positive"},
        {"published_at": "2024-01-01T10:00:00", "sentiment": "negative"},
    ]
    trend = sentiment_trend(claims)
    assert [t["week"] for t in trend] == ["2024-01-01", "2024-01-15"]
    assert trend[0]["avg_sentiment"] == -1.0
    assert trend[1]["avg_sentiment"] == 1.0


def test_sentiment_trend_excludes_undated_claims():
    claims = [
        {"published_at": None, "sentiment": "positive"},
        {"published_at": "2024-01-01T10:00:00", "sentiment": "neutral"},
    ]
    trend = sentiment_trend(claims)
    assert trend == [{"week": "2024-01-01", "avg_sentiment": 0.0}]


def test_sentiment_trend_treats_missing_sentiment_as_neutral():
    claims = [{"published_at": "2024-01-01T10:00:00", "sentiment": None}]
    assert sentiment_trend(claims) == [{"week": "2024-01-01", "avg_sentiment": 0.0}]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Acme, Globex", ["Acme", "Globex"]),
        (" Acme ,, Globex ", ["Acme", "Globex"]),
        ("", []),
        ("Acme,Globex,Initech,Umbrella,Hooli", ["Acme", "Globex", "Initech", "Umbrella"]),
    ],
)
def test_parse_entity_list(raw, expected):
    assert parse_entity_list(raw) == expected
