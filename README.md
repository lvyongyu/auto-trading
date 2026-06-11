# Event-Only US Stock Bottom-Fishing Agent

This is a first-pass research agent for weekly US stock bottom-fishing candidates.

It does **not** give investment advice or auto-trade. It ranks stocks that recently sold off around identifiable events and produces a watchlist for further research.

## What It Looks At

The first version intentionally avoids multi-factor valuation models. It focuses on:

- Recent news events from Yahoo Finance RSS
- Recent price drawdown
- Whether the stock is stabilizing after the event
- Whether the event appears potentially recoverable
- Whether the event looks like a hard avoid, such as fraud, bankruptcy, delisting, or severe regulatory action
- A ticker/company-name relevance filter to reduce broad market-news noise

## Run

```bash
python3 src/event_bottom_fishing.py
```

Outputs are written to `outputs/` as both Markdown and JSON.

## Weekly Use

Run it once a week, ideally after the Friday close or before the Monday open:

```bash
python3 src/event_bottom_fishing.py --top 10
```

For a larger or smaller universe, edit `config/universe_sp100.txt`.
For company-name matching, edit `config/company_aliases.json`.

## Ranking Idea

The score favors stocks that:

- Have meaningful negative or mixed events recently
- Dropped enough to be interesting
- Show early stabilization rather than continued free-fall
- Do not have obvious terminal-risk event language

The output classes are:

- `A`: High-priority research candidate
- `B`: Watchlist
- `C`: Weak or noisy event
- `D`: Avoid/review only because the event risk is too severe

Always read the actual event context before doing anything with real money.
