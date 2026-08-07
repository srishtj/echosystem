import yfinance as yf

PREFERRED_EXCHANGES = {"NMS", "NYQ", "NGM", "NCM", "ASE"}


def resolve_ticker(query: str) -> dict | None:
    quotes = yf.Search(query, max_results=10).quotes
    equities = [q for q in quotes if q.get("quoteType") == "EQUITY"]
    if not equities:
        return None

    preferred = [q for q in equities if q.get("exchange") in PREFERRED_EXCHANGES]
    best = (preferred or equities)[0]
    return {
        "symbol": best["symbol"],
        "name": best.get("longname") or best.get("shortname") or best["symbol"],
        "exchange": best.get("exchDisp"),
    }


def get_stock_data(query: str) -> dict | None:
    match = resolve_ticker(query)
    if not match:
        return None

    ticker = yf.Ticker(match["symbol"])
    hist = ticker.history(period="6mo")
    if hist.empty:
        return None

    info = ticker.info
    prices = [
        {"date": ts.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 2)}
        for ts, row in hist.iterrows()
    ]

    return {
        "symbol": match["symbol"],
        "name": match["name"],
        "exchange": match["exchange"],
        "current_price": info.get("currentPrice"),
        "change_percent": info.get("regularMarketChangePercent"),
        "market_cap": info.get("marketCap"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "sector": info.get("sector"),
        "prices": prices,
    }
