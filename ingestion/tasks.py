import logging
import os
import time
from datetime import datetime, timezone

import feedparser, httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv()

from ingestion.celery_app import celery_app

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; EchoSystem/1.0)"


def _is_transient_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_transient_error),
    reraise=True,
)
def _get(*args, **kwargs):
    resp = httpx.get(*args, **kwargs)
    resp.raise_for_status()
    return resp

FEEDS = [
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://feeds.ycombinator.com/rss/frontpage",
]


@celery_app.task
def poll_all_feeds():
    for url in FEEDS:
        try:
            parsed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
        except Exception as e:
            logger.warning("Feed parse failed for %s: %s", url, e)
            continue

        logger.info("Feed: %s — found %d entries", url, len(parsed.entries))
        for entry in parsed.entries[:10]:
            published_at = None
            if getattr(entry, "published_parsed", None):
                published_at = datetime.fromtimestamp(
                    time.mktime(entry.published_parsed), tz=timezone.utc
                ).isoformat()
            try:
                fetch_and_clean(entry.link, entry.title, published_at=published_at)
            except Exception as e:
                logger.warning("fetch_and_clean failed for %s: %s", entry.link, e)


@celery_app.task
def poll_topic(query: str, page_size: int = 8):
    resp = _get(
        "https://newsapi.org/v2/everything",
        params={
            "q": query,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": page_size,
            "apiKey": os.environ["NEWSAPI_KEY"],
        },
        timeout=15,
    )
    articles = resp.json().get("articles", [])
    logger.info("NewsAPI query %r — found %d articles", query, len(articles))

    for article in articles:
        fallback_text = " ".join(
            filter(None, [article.get("description"), article.get("content")])
        )
        try:
            fetch_and_clean(
                article["url"],
                article["title"],
                fallback_text,
                published_at=article.get("publishedAt"),
            )
        except Exception as e:
            logger.warning("fetch_and_clean failed for %s: %s", article["url"], e)

    _generate_topic_report(query)


def _generate_topic_report(topic: str):
    try:
        from agents.graph import run_research_and_persist

        run_research_and_persist(topic)
    except Exception as e:
        logger.warning("Report generation failed for topic %r: %s", topic, e)


@celery_app.task
def fetch_and_clean(
    url: str, title: str, fallback_text: str = "", published_at: str | None = None
):
    text = ""
    try:
        resp = _get(
            url, timeout=10, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = " ".join(soup.stripped_strings)
    except httpx.HTTPError as e:
        logger.warning("Scrape failed for %s: %s", url, e)

    if len(text) < 200 and fallback_text:
        text = fallback_text

    logger.debug("Cleaned article: %s...", title[:60])
    logger.debug("Text length: %d chars", len(text))

    if not text:
        return

    from extraction.tasks import extract_entities
    extract_entities(title, text, url, published_at)
