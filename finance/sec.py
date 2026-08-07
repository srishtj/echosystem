import os

import httpx
from dotenv import load_dotenv
load_dotenv()
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

USER_AGENT = f"EchoSystem-AI {os.environ.get('SEC_CONTACT_EMAIL', 'research-project@example.com')}"
HEADERS = {"User-Agent": USER_AGENT}


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

_ticker_cik_cache: dict[str, dict] | None = None

KEY_CONCEPTS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "Assets",
    "Liabilities",
]


def _load_ticker_map() -> dict[str, dict]:
    global _ticker_cik_cache
    if _ticker_cik_cache is None:
        resp = _get(
            "https://www.sec.gov/files/company_tickers.json", headers=HEADERS, timeout=15
        )
        _ticker_cik_cache = {
            entry["ticker"].upper(): {"cik": entry["cik_str"], "title": entry["title"]}
            for entry in resp.json().values()
        }
    return _ticker_cik_cache


def resolve_cik(query: str) -> dict | None:
    ticker_map = _load_ticker_map()

    upper = query.strip().upper()
    if upper in ticker_map:
        match = ticker_map[upper]
        return {"cik": match["cik"], "title": match["title"], "ticker": upper}

    lowered = query.strip().lower()
    for ticker, entry in ticker_map.items():
        if lowered in entry["title"].lower():
            return {"cik": entry["cik"], "title": entry["title"], "ticker": ticker}

    return None


def get_company_facts(cik: int) -> dict:
    resp = _get(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
        headers=HEADERS,
        timeout=15,
    )
    gaap = resp.json().get("facts", {}).get("us-gaap", {})

    facts = {}
    for concept in KEY_CONCEPTS:
        entries = gaap.get(concept, {}).get("units", {}).get("USD", [])
        annual = [e for e in entries if e.get("form") == "10-K"]
        pool = annual or entries
        if pool:
            latest = max(pool, key=lambda e: e.get("end", ""))
            facts[concept] = {
                "value": latest["val"],
                "end": latest["end"],
                "form": latest.get("form"),
            }

    return facts


def search_filings(query: str, forms: str = "10-K,10-Q,8-K", limit: int = 10) -> list[dict]:
    resp = _get(
        "https://efts.sec.gov/LATEST/search-index",
        params={"q": query, "forms": forms},
        headers=HEADERS,
        timeout=15,
    )
    hits = resp.json().get("hits", {}).get("hits", [])[:limit]

    results = []
    for hit in hits:
        src = hit["_source"]
        ciks = src.get("ciks") or []
        accession_nodash = src.get("adsh", "").replace("-", "")
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(ciks[0])}/{accession_nodash}/"
            if ciks and accession_nodash
            else None
        )
        results.append(
            {
                "company": ", ".join(src.get("display_names", [])),
                "form": (src.get("root_forms") or [src.get("form")])[0],
                "filed": src.get("file_date"),
                "url": url,
            }
        )
    return results


def get_sec_snapshot(query: str) -> dict | None:
    match = resolve_cik(query)
    if not match:
        return None

    facts = get_company_facts(match["cik"])
    filings = search_filings(match["title"])

    return {
        "cik": match["cik"],
        "title": match["title"],
        "ticker": match["ticker"],
        "facts": facts,
        "filings": filings,
    }
