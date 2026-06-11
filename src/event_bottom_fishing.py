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
    reasons: list[str]
    risks: list[str]
    watchpoints: list[str]
    score_breakdown: dict[str, float]
    events: list[NewsItem]
    price: PriceStats
    deep_dive_score: float = 0.0
    deep_dive_decision: str = "Review"
    deep_dive_reasons: list[str] = dataclasses.field(default_factory=list)
    deep_dive_risks: list[str] = dataclasses.field(default_factory=list)


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


def add_score(breakdown: dict[str, float], label: str, value: float) -> None:
    breakdown[label] = round(breakdown.get(label, 0.0) + value, 2)


def event_label(category: str) -> str:
    labels = {
        "earnings_miss": "earnings disappointment",
        "earnings_recoverable": "earnings or guidance event",
        "analyst_negative": "negative analyst action",
        "analyst_positive": "positive analyst action",
        "company_action_positive": "shareholder-friendly company action",
        "legal_regulatory": "legal or regulatory event",
        "terminal_risk": "terminal-risk event",
        "macro_sector": "macro or sector event",
    }
    return labels.get(category, category.replace("_", " "))


def top_category_labels(category_counts: dict[str, int], limit: int = 3) -> list[str]:
    categories = sorted(category_counts, key=category_counts.get, reverse=True)[:limit]
    return [event_label(category) for category in categories]


def count_categories(news: list[NewsItem]) -> dict[str, int]:
    category_counts: dict[str, int] = {}
    for item in news:
        for category in item.categories:
            category_counts[category] = category_counts.get(category, 0) + 1
    return category_counts


def build_reasons(
    news: list[NewsItem],
    category_counts: dict[str, int],
    price: PriceStats,
    negative_event_count: int,
    positive_event_count: int,
) -> list[str]:
    reasons = []
    if price.drawdown_60d < -8:
        reasons.append(
            f"Price is {abs(price.drawdown_60d):.1f}% below its 60-day closing high, "
            "so the setup is actually a pullback rather than a momentum chase."
        )
    if price.change_20d < -5:
        reasons.append(
            f"The stock is down {abs(price.change_20d):.1f}% over the last 20 trading days, "
            "which gives the event enough price damage to review for a rebound setup."
        )
    if price.above_5d_low > 2:
        reasons.append(
            f"It has bounced {price.above_5d_low:.1f}% from its 5-day low, "
            "a small sign that selling pressure may be slowing."
        )
    if price.volume_ratio_5d_20d > 1.2:
        reasons.append(
            f"Recent volume is {price.volume_ratio_5d_20d:.1f}x the 20-day average, "
            "so the move is tied to active repricing rather than quiet drift."
        )
    if negative_event_count:
        reasons.append(
            f"{negative_event_count} company-specific negative event headline(s) created the selloff/catalyst to investigate."
        )
    if positive_event_count:
        reasons.append(
            f"{positive_event_count} positive or offsetting headline(s) suggest the story is not one-sided."
        )
    if category_counts.get("earnings_recoverable"):
        reasons.append("The event mix includes earnings, guidance, margin, or revenue language, which can be checked in the next report.")
    if category_counts.get("analyst_positive"):
        reasons.append("At least one analyst-positive event appeared after the pullback, which can support a watchlist case.")
    if category_counts.get("company_action_positive"):
        reasons.append("Company action such as buybacks, dividends, asset sales, or activism may provide a catalyst.")

    if not reasons:
        reasons.append("It ranked mainly because recent event activity and price damage passed the basic screen.")
    return reasons


def build_watchpoints(category_counts: dict[str, int], price: PriceStats) -> list[str]:
    watchpoints = []
    if category_counts.get("earnings_miss") or category_counts.get("earnings_recoverable"):
        watchpoints.append("Read the latest earnings release or call transcript; confirm whether guidance weakness is temporary or structural.")
    if category_counts.get("analyst_negative"):
        watchpoints.append("Check whether downgrades are based on short-term valuation/catalysts or a deeper business deterioration.")
    if category_counts.get("legal_regulatory"):
        watchpoints.append("Do not treat this as a normal dip until the legal or regulatory downside is bounded.")
    if category_counts.get("terminal_risk"):
        watchpoints.append("Avoid unless primary filings prove terminal-risk language is not material.")
    if price.change_5d < -10:
        watchpoints.append("Wait for selling pressure to stabilize; the 5-day move is still sharply negative.")
    if price.above_5d_low > 2:
        watchpoints.append("Use the recent 5-day low as the first invalidation level for the rebound thesis.")
    else:
        watchpoints.append("Look for a close back above the event-day midpoint before treating it as stabilizing.")
    return watchpoints


def score_deep_dive(candidate: Candidate) -> tuple[float, list[str], list[str]]:
    category_counts = count_categories(candidate.events)
    reasons = []
    risks = []
    score = 0.0

    if category_counts.get("earnings_recoverable"):
        score += 18
        reasons.append("The main event is tied to earnings, guidance, revenue, or margin, which can be checked against the next report.")
    if category_counts.get("analyst_negative") and (
        category_counts.get("analyst_positive") or category_counts.get("earnings_recoverable")
    ):
        score += 12
        reasons.append("There is a negative catalyst, but it appears debatable rather than one-sided because offsetting events also appeared.")
    if category_counts.get("analyst_positive") or category_counts.get("company_action_positive"):
        score += 10
        reasons.append("A constructive analyst or company-action signal appeared after the selloff.")
    if -30 <= candidate.price.drawdown_60d <= -10:
        score += 16
        reasons.append("The drawdown is large enough to matter but not so extreme that the screen treats it as likely structural damage.")
    elif candidate.price.drawdown_60d < -30:
        score += 6
        risks.append("The drawdown is very deep, so the market may be pricing in more than a temporary event.")
    if candidate.price.change_20d < -5:
        score += 8
        reasons.append("The recent 20-day selloff gives the setup a clear event-driven repricing window.")
    if candidate.price.above_5d_low >= 2:
        score += 14
        reasons.append("The stock has started to lift from its 5-day low, which is a first sign that selling pressure may be cooling.")
    else:
        risks.append("There is not enough short-term stabilization yet; it may still be too early.")
    if candidate.price.change_5d < -10:
        score -= 12
        risks.append("The 5-day move is still sharply negative, so this can still be a falling-knife setup.")
    if candidate.price.volume_ratio_5d_20d > 1.2:
        score += 6
        reasons.append("Volume expanded around the move, suggesting the market is actively repricing the event.")

    legal = category_counts.get("legal_regulatory", 0)
    terminal = category_counts.get("terminal_risk", 0)
    if legal:
        score -= legal * 12
        risks.append("Legal or regulatory headlines make the downside harder to bound.")
    if terminal:
        score -= terminal * 40
        risks.append("Terminal-risk language appeared; this should not be a focus candidate without primary-source confirmation.")

    specific_events = [
        event for event in candidate.events
        if any(category != "macro_sector" for category in event.categories)
    ]
    if len(specific_events) >= 3:
        score += 8
        reasons.append("There are multiple company-specific headlines, so the setup is easier to audit than a broad macro move.")
    elif len(specific_events) == 1:
        score -= 6
        risks.append("Only one company-specific headline passed the filter, so the evidence base is thin.")

    if not reasons:
        reasons.append("It remains on the research list, but the deep-dive layer did not find a strong reason to prioritize it.")
    if not risks:
        risks.append("The largest risk is headline interpretation; verify with primary filings or the latest earnings call.")

    return round(score, 2), reasons, risks


def apply_deep_dive(candidates: list[Candidate], focus_count: int) -> list[Candidate]:
    for candidate in candidates:
        score, reasons, risks = score_deep_dive(candidate)
        candidate.deep_dive_score = score
        candidate.deep_dive_reasons = reasons
        candidate.deep_dive_risks = risks

    ranked = sorted(candidates, key=lambda item: item.deep_dive_score, reverse=True)
    focus_tickers = {candidate.ticker for candidate in ranked[:focus_count] if candidate.deep_dive_score > 0}
    for candidate in candidates:
        if candidate.ticker in focus_tickers:
            candidate.deep_dive_decision = "Focus"
        elif candidate.deep_dive_score >= 35:
            candidate.deep_dive_decision = "Watch"
        else:
            candidate.deep_dive_decision = "Pass"
    return candidates


def score_candidate(ticker: str, news: list[NewsItem], price: PriceStats) -> Candidate:
    category_counts = count_categories(news)

    specific_events = [
        item for item in news
        if any(category != "macro_sector" for category in item.categories)
    ]
    macro_event_count = len(news) - len(specific_events)
    negative_event_count = sum(1 for item in specific_events if item.sentiment < 0)
    positive_event_count = sum(1 for item in specific_events if item.sentiment > 0)
    terminal = category_counts.get("terminal_risk", 0)
    legal = category_counts.get("legal_regulatory", 0)

    breakdown: dict[str, float] = {}
    add_score(breakdown, "company-specific event count", min(len(specific_events), 6) * 4)
    add_score(breakdown, "macro/sector event count", min(macro_event_count, 3) * 1)
    add_score(breakdown, "negative event catalyst", min(negative_event_count, 4) * 6)
    add_score(breakdown, "positive offsetting catalyst", min(positive_event_count, 3) * 2)
    add_score(
        breakdown,
        "60-day drawdown",
        min(abs(price.drawdown_60d), 35) * 1.1 if price.drawdown_60d < -8 else -8,
    )
    add_score(
        breakdown,
        "20-day selloff",
        min(abs(price.change_20d), 25) * 0.8 if price.change_20d < -5 else -5,
    )
    add_score(breakdown, "bounce from 5-day low", min(price.above_5d_low, 10) * 2.0)
    add_score(breakdown, "recent volume expansion", min(max(price.volume_ratio_5d_20d - 1, 0), 3) * 4)

    if category_counts.get("earnings_recoverable"):
        add_score(breakdown, "recoverable earnings/guidance event", 8)
    if category_counts.get("analyst_positive") or category_counts.get("company_action_positive"):
        add_score(breakdown, "constructive analyst/company action", 6)
    if category_counts.get("earnings_miss"):
        add_score(breakdown, "earnings disappointment catalyst", 5)
    if legal:
        add_score(breakdown, "legal/regulatory penalty", legal * -8)
    if terminal:
        add_score(breakdown, "terminal-risk penalty", terminal * -30)
    if price.change_5d < -12 and price.above_5d_low < 2:
        add_score(breakdown, "falling-knife penalty", -12)
    if not specific_events:
        add_score(breakdown, "weak company-specific event penalty", -25)

    score = sum(breakdown.values())

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
        thesis_parts.append("recent events: " + ", ".join(top_category_labels(category_counts)))
    thesis = "; ".join(thesis_parts) or "event activity detected but signal is weak"
    reasons = build_reasons(news, category_counts, price, negative_event_count, positive_event_count)
    watchpoints = build_watchpoints(category_counts, price)

    return Candidate(
        ticker=ticker,
        score=round(score, 2),
        bucket=bucket,
        thesis=thesis,
        reasons=reasons,
        risks=risks,
        watchpoints=watchpoints,
        score_breakdown=breakdown,
        events=news,
        price=price,
    )


def candidate_to_dict(candidate: Candidate) -> dict:
    return {
        "ticker": candidate.ticker,
        "score": candidate.score,
        "bucket": candidate.bucket,
        "thesis": candidate.thesis,
        "reasons": candidate.reasons,
        "risks": candidate.risks,
        "watchpoints": candidate.watchpoints,
        "score_breakdown": candidate.score_breakdown,
        "deep_dive": {
            "score": candidate.deep_dive_score,
            "decision": candidate.deep_dive_decision,
            "reasons": candidate.deep_dive_reasons,
            "risks": candidate.deep_dive_risks,
        },
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


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


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

        focus_candidates = [candidate for candidate in candidates if candidate.deep_dive_decision == "Focus"]
        handle.write("## Deep Dive Shortlist\n\n")
        if focus_candidates:
            handle.write("These are the 2-3 candidates the second-stage review thinks are most worth serious manual research this week.\n\n")
            handle.write("| Rank | Ticker | Deep Dive Score | Original Score | Why It Is A Focus Candidate | Main Risk |\n")
            handle.write("| ---: | --- | ---: | ---: | --- | --- |\n")
            for index, candidate in enumerate(
                sorted(focus_candidates, key=lambda item: item.deep_dive_score, reverse=True),
                start=1,
            ):
                reason = candidate.deep_dive_reasons[0] if candidate.deep_dive_reasons else ""
                risk = candidate.deep_dive_risks[0] if candidate.deep_dive_risks else ""
                handle.write(
                    f"| {index} | {candidate.ticker} | {candidate.deep_dive_score:.2f} | "
                    f"{candidate.score:.2f} | {markdown_escape(reason)} | {markdown_escape(risk)} |\n"
                )
        else:
            handle.write("No candidates passed the deep-dive focus threshold this week.\n")

        handle.write("\n## Full Top-10 Event Screen\n\n")
        handle.write("| Rank | Ticker | Decision | Bucket | Score | Deep Dive | Setup | Why It Made The List | Key Risk |\n")
        handle.write("| ---: | --- | --- | --- | ---: | ---: | --- | --- | --- |\n")
        for index, candidate in enumerate(candidates, start=1):
            risk = candidate.risks[0] if candidate.risks else ""
            reason = candidate.reasons[0] if candidate.reasons else ""
            handle.write(
                f"| {index} | {candidate.ticker} | {candidate.deep_dive_decision} | "
                f"{candidate.bucket} | {candidate.score:.2f} | {candidate.deep_dive_score:.2f} | "
                f"{markdown_escape(candidate.thesis)} | "
                f"{markdown_escape(reason)} | {markdown_escape(risk)} |\n"
            )
        handle.write("\n## Candidate Rationale\n\n")
        for candidate in candidates:
            handle.write(f"### {candidate.ticker}\n\n")
            handle.write(f"**Score:** {candidate.score:.2f}  \n")
            handle.write(f"**Deep Dive Score:** {candidate.deep_dive_score:.2f}  \n")
            handle.write(f"**Deep Dive Decision:** {candidate.deep_dive_decision}  \n")
            handle.write(f"**Bucket:** {candidate.bucket}  \n")
            handle.write(f"**Setup:** {candidate.thesis}\n\n")

            handle.write("**Deep dive take**\n\n")
            for reason in candidate.deep_dive_reasons:
                handle.write(f"- {reason}\n")
            handle.write("\n")

            handle.write("**Deep dive risks**\n\n")
            for risk in candidate.deep_dive_risks:
                handle.write(f"- {risk}\n")
            handle.write("\n")

            handle.write("**Why it made the list**\n\n")
            for reason in candidate.reasons:
                handle.write(f"- {reason}\n")
            handle.write("\n")

            handle.write("**What could break the thesis**\n\n")
            for risk in candidate.risks:
                handle.write(f"- {risk}\n")
            handle.write("\n")

            handle.write("**What to verify next**\n\n")
            for watchpoint in candidate.watchpoints:
                handle.write(f"- {watchpoint}\n")
            handle.write("\n")

            handle.write("**Score breakdown**\n\n")
            for label, value in candidate.score_breakdown.items():
                handle.write(f"- {label}: {value:+.2f}\n")
            handle.write("\n")

            handle.write("**Event evidence**\n\n")
            for event in candidate.events[:5]:
                date = event.published.date().isoformat() if event.published else "unknown date"
                categories = ", ".join(event_label(category) for category in event.categories)
                handle.write(f"- {date}: [{event.title}]({event.link}) ({categories})\n")
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
        return apply_deep_dive(candidates[: args.top], args.deep_dive_focus)

    investable = [candidate for candidate in candidates if candidate.bucket != "D"]
    if len(investable) >= args.top:
        return apply_deep_dive(investable[: args.top], args.deep_dive_focus)
    avoid = [candidate for candidate in candidates if candidate.bucket == "D"]
    return apply_deep_dive((investable + avoid)[: args.top], args.deep_dive_focus)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE)
    parser.add_argument("--aliases", default=DEFAULT_ALIASES)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--lookback-days", type=int, default=14)
    parser.add_argument("--max-news", type=int, default=8)
    parser.add_argument("--deep-dive-focus", type=int, default=3)
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
