#!/usr/bin/env python3
"""Event-only weekly US stock bottom-fishing screener.

This script intentionally avoids valuation and broad multi-factor models.
It uses public, no-key data sources and produces a research watchlist.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import email.utils
import html
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterable


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_UNIVERSE = os.path.join(ROOT, "config", "universe_sp100.txt")
DEFAULT_ALIASES = os.path.join(ROOT, "config", "company_aliases.json")
OUTPUT_DIR = os.path.join(ROOT, "outputs")

EVENT_KEYWORDS = {
    "earnings_miss": {
        "miss", "misses", "missed", "disappoint", "disappoints", "weak guidance",
        "cuts forecast", "cut forecast", "lowers guidance", "guidance cut",
    },
    "earnings_recoverable": {
        "earnings", "revenue", "sales", "guidance", "margin", "forecast",
        "outlook", "profit", "free cash flow",
    },
    "analyst_negative": {
        "downgrade", "downgrades", "price target cut", "target cut", "sell rating",
        "underperform", "bearish",
    },
    "analyst_positive": {
        "upgrade", "upgrades", "price target raised", "target raised", "buy rating",
        "outperform", "bullish",
    },
    "company_action_positive": {
        "buyback", "repurchase", "dividend increase", "raises dividend", "spin off",
        "spinoff", "strategic review", "asset sale", "activist",
    },
    "legal_regulatory": {
        "lawsuit", "sues", "sued", "investigation", "probe", "doj", "ftc", "sec",
        "antitrust", "fda", "warning letter", "recall",
    },
    "terminal_risk": {
        "bankruptcy", "chapter 11", "going concern", "delisting", "fraud",
        "accounting irregularities", "restatement", "halted", "insolvency",
    },
    "macro_sector": {
        "tariff", "rates", "inflation", "oil", "chip", "semiconductor", "ai",
        "consumer spending", "housing", "drug pricing",
    },
}

NEGATIVE_WORDS = {
    "miss", "misses", "missed", "falls", "drops", "tumbles", "plunges", "slumps",
    "cuts", "cut", "lowers", "downgrade", "downgrades", "probe", "investigation",
    "lawsuit", "recall", "weak", "disappointing", "concern", "pressure",
}

POSITIVE_WORDS = {
    "beats", "beat", "raises", "raised", "upgrade", "upgrades", "surges", "jumps",
    "buyback", "repurchase", "dividend", "approval", "record", "strong",
}


@dataclasses.dataclass
class NewsItem:
    title: str
    link: str
    published: dt.datetime | None
    categories: list[str]
    sentiment: int


@dataclasses.dataclass
class PriceStats:
    last_close: float
    change_5d: float
    change_20d: float
    drawdown_60d: float
    above_5d_low: float
    volume_ratio_5d_20d: float


@dataclasses.dataclass
class Candidate:
    ticker: str
    score: float
    bucket: str
    thesis: str
    risks: list[str]
    events: list[NewsItem]
    price: PriceStats


def fetch_url(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 event-bottom-fishing-agent/0.1",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def load_universe(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as handle:
        tickers = []
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                tickers.append(stripped.upper())
        return tickers


def load_aliases(path: str) -> dict[str, list[str]]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return {str(key).upper(): [str(item) for item in value] for key, value in payload.items()}


def parse_rss_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def categorize(title: str) -> list[str]:
    lower = title.lower()
    categories = []
    for category, words in EVENT_KEYWORDS.items():
        if any(word in lower for word in words):
            categories.append(category)
    return categories


def headline_sentiment(title: str) -> int:
    words = set(re.findall(r"[a-z0-9]+", title.lower()))
    neg = len(words & NEGATIVE_WORDS)
    pos = len(words & POSITIVE_WORDS)
    return max(-3, min(3, pos - neg))


def is_relevant_title(ticker: str, aliases: list[str], title: str) -> bool:
    lower = title.lower()
    normalized_ticker = ticker.replace("-", ".").lower()
    ticker_pattern = re.compile(rf"(?<![a-z0-9]){re.escape(normalized_ticker)}(?![a-z0-9])")
    if ticker_pattern.search(lower):
        return True
    return any(alias.lower() in lower for alias in aliases)


def fetch_news(
    ticker: str,
    aliases: list[str],
    max_items: int,
    lookback_days: int,
    allow_broad_news: bool,
) -> list[NewsItem]:
    symbol = ticker.replace("-", ".")
    params = urllib.parse.urlencode({"s": symbol, "region": "US", "lang": "en-US"})
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?{params}"
    raw = fetch_url(url)
    root = ET.fromstring(raw)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)
    items = []
    for item in root.findall("./channel/item"):
        title = html.unescape((item.findtext("title") or "").strip())
        if not allow_broad_news and not is_relevant_title(ticker, aliases, title):
            continue
        link = (item.findtext("link") or "").strip()
        published = parse_rss_date(item.findtext("pubDate"))
        if published and published < cutoff:
            continue
        categories = categorize(title)
        if not categories:
            continue
        items.append(
            NewsItem(
                title=title,
                link=link,
                published=published,
                categories=categories,
                sentiment=headline_sentiment(title),
            )
        )
        if len(items) >= max_items:
            break
    return items


def fetch_price_stats(ticker: str) -> PriceStats | None:
    symbol = urllib.parse.quote(ticker.replace("-", "-"))
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range=6mo&interval=1d&includePrePost=false"
    )
    raw = fetch_url(url)
    payload = json.loads(raw.decode("utf-8"))
    result = payload.get("chart", {}).get("result") or []
    if not result:
        return None
    quote = result[0]["indicators"]["quote"][0]
    closes = [x for x in quote.get("close", []) if isinstance(x, (int, float))]
    volumes = [x for x in quote.get("volume", []) if isinstance(x, (int, float))]
    if len(closes) < 61 or len(volumes) < 25:
        return None
    last = closes[-1]
    high_60 = max(closes[-60:])
    low_5 = min(closes[-5:])
    avg_vol_5 = sum(volumes[-5:]) / 5
    avg_vol_20 = sum(volumes[-20:]) / 20
    return PriceStats(
        last_close=last,
        change_5d=(last / closes[-6] - 1) * 100,
        change_20d=(last / closes[-21] - 1) * 100,
        drawdown_60d=(last / high_60 - 1) * 100,
        above_5d_low=(last / low_5 - 1) * 100,
        volume_ratio_5d_20d=avg_vol_5 / avg_vol_20 if avg_vol_20 else 0,
    )


def score_candidate(ticker: str, news: list[NewsItem], price: PriceStats) -> Candidate:
    category_counts: dict[str, int] = {}
    for item in news:
        for category in item.categories:
            category_counts[category] = category_counts.get(category, 0) + 1

    specific_events = [
        item for item in news
        if any(category != "macro_sector" for category in item.categories)
    ]
    macro_event_count = len(news) - len(specific_events)
    negative_event_count = sum(1 for item in specific_events if item.sentiment < 0)
    positive_event_count = sum(1 for item in specific_events if item.sentiment > 0)
    terminal = category_counts.get("terminal_risk", 0)
    legal = category_counts.get("legal_regulatory", 0)

    score = 0.0
    score += min(len(specific_events), 6) * 4
    score += min(macro_event_count, 3) * 1
    score += min(negative_event_count, 4) * 6
    score += min(positive_event_count, 3) * 2
    score += min(abs(price.drawdown_60d), 35) * 1.1 if price.drawdown_60d < -8 else -8
    score += min(abs(price.change_20d), 25) * 0.8 if price.change_20d < -5 else -5
    score += min(price.above_5d_low, 10) * 2.0
    score += min(max(price.volume_ratio_5d_20d - 1, 0), 3) * 4

    if category_counts.get("earnings_recoverable"):
        score += 8
    if category_counts.get("analyst_positive") or category_counts.get("company_action_positive"):
        score += 6
    if category_counts.get("earnings_miss"):
        score += 5
    if legal:
        score -= legal * 8
    if terminal:
        score -= terminal * 30
    if price.change_5d < -12 and price.above_5d_low < 2:
        score -= 12
    if not specific_events:
        score -= 25

    risks = []
    if terminal:
        risks.append("terminal-risk language appeared in recent event headlines")
    if legal:
        risks.append("legal/regulatory event may be hard to handicap")
    if price.change_5d < -10:
        risks.append("short-term price action is still falling sharply")
    if price.drawdown_60d < -25:
        risks.append("deep drawdown may reflect real fundamental damage")
    if not risks:
        risks.append("event interpretation may be noisy; read the primary source")

    if terminal:
        bucket = "D"
    elif score >= 70:
        bucket = "A"
    elif score >= 50:
        bucket = "B"
    elif score >= 30:
        bucket = "C"
    else:
        bucket = "D"

    thesis_parts = []
    if price.drawdown_60d < -8:
        thesis_parts.append(f"{price.drawdown_60d:.1f}% below its 60-day closing high")
    if price.above_5d_low > 2:
        thesis_parts.append(f"{price.above_5d_low:.1f}% above its 5-day low")
    if category_counts:
        top_categories = sorted(category_counts, key=category_counts.get, reverse=True)[:3]
        thesis_parts.append("recent events: " + ", ".join(top_categories))
    thesis = "; ".join(thesis_parts) or "event activity detected but signal is weak"

    return Candidate(
        ticker=ticker,
        score=round(score, 2),
        bucket=bucket,
        thesis=thesis,
        risks=risks,
        events=news,
        price=price,
    )


def candidate_to_dict(candidate: Candidate) -> dict:
    return {
        "ticker": candidate.ticker,
        "score": candidate.score,
        "bucket": candidate.bucket,
        "thesis": candidate.thesis,
        "risks": candidate.risks,
        "price": dataclasses.asdict(candidate.price),
        "events": [
            {
                "title": event.title,
                "link": event.link,
                "published": event.published.isoformat() if event.published else None,
                "categories": event.categories,
                "sentiment": event.sentiment,
            }
            for event in candidate.events
        ],
    }


def write_outputs(candidates: list[Candidate], path_prefix: str) -> tuple[str, str]:
    json_path = f"{path_prefix}.json"
    md_path = f"{path_prefix}.md"
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "method": "event-only bottom-fishing watchlist; not investment advice",
        "candidates": [candidate_to_dict(candidate) for candidate in candidates],
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("# Weekly Event-Only Bottom-Fishing Watchlist\n\n")
        handle.write(f"Generated: {payload['generated_at']}\n\n")
        handle.write("This is a research watchlist, not investment advice or an auto-trading signal.\n\n")
        handle.write("| Rank | Ticker | Bucket | Score | Event Thesis | Key Risk |\n")
        handle.write("| ---: | --- | --- | ---: | --- | --- |\n")
        for index, candidate in enumerate(candidates, start=1):
            risk = candidate.risks[0] if candidate.risks else ""
            handle.write(
                f"| {index} | {candidate.ticker} | {candidate.bucket} | "
                f"{candidate.score:.2f} | {candidate.thesis} | {risk} |\n"
            )
        handle.write("\n## Event Details\n\n")
        for candidate in candidates:
            handle.write(f"### {candidate.ticker}\n\n")
            for event in candidate.events[:5]:
                date = event.published.date().isoformat() if event.published else "unknown date"
                handle.write(f"- {date}: [{event.title}]({event.link})\n")
            handle.write("\n")
    return json_path, md_path


def scan(args: argparse.Namespace) -> list[Candidate]:
    tickers = load_universe(args.universe)
    aliases_by_ticker = load_aliases(args.aliases)
    candidates = []
    for index, ticker in enumerate(tickers, start=1):
        try:
            news = fetch_news(
                ticker,
                aliases_by_ticker.get(ticker, []),
                args.max_news,
                args.lookback_days,
                args.allow_broad_news,
            )
            if not news:
                continue
            price = fetch_price_stats(ticker)
            if not price:
                continue
            candidate = score_candidate(ticker, news, price)
            candidates.append(candidate)
            if args.verbose:
                print(f"[{index}/{len(tickers)}] {ticker}: {candidate.score:.2f}", flush=True)
            time.sleep(args.sleep)
        except Exception as exc:  # noqa: BLE001 - scanner should continue per ticker.
            if args.verbose:
                print(f"[{index}/{len(tickers)}] {ticker}: skipped ({exc})", file=sys.stderr, flush=True)
            continue
    candidates.sort(key=lambda item: item.score, reverse=True)
    if args.include_avoid:
        return candidates[: args.top]

    investable = [candidate for candidate in candidates if candidate.bucket != "D"]
    if len(investable) >= args.top:
        return investable[: args.top]
    avoid = [candidate for candidate in candidates if candidate.bucket == "D"]
    return (investable + avoid)[: args.top]


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument("--aliases", default=DEFAULT_ALIASES)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--max-news", type=int, default=8)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--allow-broad-news", action="store_true")
    parser.add_argument("--include-avoid", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    candidates = scan(args)
    if not candidates:
        print("No candidates found. Check network access or widen the universe/lookback window.")
        return 1

    today = dt.datetime.now().strftime("%Y-%m-%d")
    path_prefix = os.path.join(OUTPUT_DIR, f"weekly_event_bottom_fishing_{today}")
    json_path, md_path = write_outputs(candidates, path_prefix)
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    print()
    for index, candidate in enumerate(candidates, start=1):
        print(f"{index:>2}. {candidate.ticker:<6} {candidate.bucket} {candidate.score:>6.2f}  {candidate.thesis}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
