import os
from datetime import datetime, timezone

import praw
from dotenv import load_dotenv
load_dotenv()

SUBREDDITS = "stocks+wallstreetbets+technology+business+investing+news+worldnews"

_client: praw.Reddit | None = None


def _get_client() -> praw.Reddit:
    global _client
    if _client is None:
        _client = praw.Reddit(
            client_id=os.environ["REDDIT_CLIENT_ID"],
            client_secret=os.environ["REDDIT_CLIENT_SECRET"],
            user_agent="EchoSystem-AI/1.0 (market intelligence research tool)",
        )
    return _client


def search_reddit(query: str, limit: int = 10) -> list[dict]:
    reddit = _get_client()
    posts = []
    for submission in reddit.subreddit(SUBREDDITS).search(query, sort="new", limit=limit):
        posts.append(
            {
                "title": submission.title,
                "subreddit": str(submission.subreddit),
                "score": submission.score,
                "num_comments": submission.num_comments,
                "created_at": datetime.fromtimestamp(
                    submission.created_utc, tz=timezone.utc
                ).isoformat(),
                "url": f"https://www.reddit.com{submission.permalink}",
            }
        )
    return posts
