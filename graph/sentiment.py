import re

# Shared with graph/contradictions.py's keyword conflict strategy — a claim that
# reads as bullish/bearish for contradiction detection should read the same way
# for sentiment scoring, so both live off the same marker sets.
POSITIVE_MARKERS = {
    "profit", "gain", "growth", "surge", "raised", "hired", "won",
    "approved", "cleared", "launched", "expanded", "record", "high",
}
NEGATIVE_MARKERS = {
    "loss", "decline", "fell", "bankrupt", "laid off", "fired", "recall",
    "fraud", "fine", "sued", "shutdown", "low", "crash", "default",
}


def score_sentiment(text: str) -> str:
    """Cheap keyword-based sentiment label for a claim: positive | neutral | negative.

    No LLM call — this runs on every claim at ingestion time, and the extraction
    model's rate limit is already the pipeline's tightest bottleneck.
    """
    words = set(re.findall(r"\w+", text.lower()))
    positive = bool(words & POSITIVE_MARKERS)
    negative = bool(words & NEGATIVE_MARKERS)
    if positive and not negative:
        return "positive"
    if negative and not positive:
        return "negative"
    return "neutral"
