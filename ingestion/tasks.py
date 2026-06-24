import feedparser, httpx

from bs4 import BeautifulSoup

from ingestion.celery_app import celery_app

FEEDS = [
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "https://feeds.ycombinator.com/rss/frontpage",
]

@celery_app.task
def poll_all_feeds():
    for url in FEEDS:
        parsed = feedparser.parse(
            url,
            request_headers={"User-Agent": "Mozilla/5.0 (compatible; EchoSystem/1.0)"}
        )
        print(f"Feed: {url} — found {len(parsed.entries)} entries")
        for entry in parsed.entries[:10]:
            fetch_and_clean.delay(entry.link, entry.title)

@celery_app.task
def fetch_and_clean(url: str, title: str):
    resp = httpx.get(url, timeout=10, follow_redirects=True)
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    print(f"Cleaned article: {title[:60]}...")
    print(f"Text length: {len(text)} chars")
    
    # from extraction.tasks import extract_entities
    # extract_entities.delay(title, text[:8000])

