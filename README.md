# Event-Only US Stock Bottom-Fishing Agent

This is a first-pass research agent for weekly US stock bottom-fishing candidates.

It does **not** give investment advice or auto-trade. It ranks stocks that recently sold off around identifiable events and produces a watchlist for further research.

## What It Looks At

The first version intentionally avoids multi-factor valuation models. It focuses on:

- Recent news events from Yahoo Finance RSS as the discovery source
- Recent price drawdown
- Whether the stock is stabilizing after the event
- Whether the event appears potentially recoverable
- Whether the event looks like a hard avoid, such as fraud, bankruptcy, delisting, or severe regulatory action
- A ticker/company-name relevance filter to reduce broad market-news noise
- Recent SEC filings as a primary-source event cross-check
- Stooq daily prices, when available, as a second price source to check Yahoo price calculations

## Run

```bash
python3 src/event_bottom_fishing.py
```

Outputs are written to `outputs/` as both Markdown and JSON.

The Markdown report is designed for a human reader. Each candidate includes:

- A deep-dive shortlist that narrows the top 10 down to 2-3 focus candidates
- A `Data Confidence` rating based on SEC filing evidence and second-source price consistency
- The setup summary
- Why it made the list
- What could break the thesis
- What to verify next
- A transparent score breakdown
- Source event headlines

## Weekly Use

Run it once a week, ideally after the Friday close or before the Monday open:

```bash
python3 src/event_bottom_fishing.py --top 10
```

To generate the report and email it from your own machine or any SMTP-enabled environment:

```bash
python3 src/email_weekly_report.py --to lvyongyu@gmail.com
```

Email settings are loaded from environment variables or a local `.env` file. Start from the example:

```bash
cp config/email.env.example .env
```

For Gmail, set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, and use a Gmail app password as `SMTP_PASSWORD`. The `.env` file is ignored by Git.

## GitHub Actions Schedule

The repository includes `.github/workflows/weekly-stock-report.yml`.

It runs every Monday at 13:00 UTC, before the US market open in both US daylight-saving and standard-time periods. You can also run it manually from the GitHub Actions tab with `workflow_dispatch`.

By default, the GitHub workflow does not need an SMTP server. It generates the report and creates a GitHub Issue with the full watchlist. If your GitHub notifications are enabled, GitHub will email you when the issue is created.

To receive it by email, make sure you are watching the repository:

```text
Repository -> Watch -> All Activity
```

Also confirm GitHub email notifications are enabled:

```text
GitHub -> Settings -> Notifications -> Email
```

For a larger or smaller universe, edit `config/universe_sp100.txt`.
For company-name matching, edit `config/company_aliases.json`.

## Ranking Idea

The first-stage score favors stocks that:

- Have meaningful negative or mixed events recently
- Dropped enough to be interesting
- Show early stabilization rather than continued free-fall
- Do not have obvious terminal-risk event language

After the first-stage top 10 is selected, a second-stage deep dive narrows the list to 2-3 focus candidates. It favors stocks where:

- The event is tied to something verifiable, such as earnings, guidance, revenue, margin, or analyst revisions
- The drawdown is meaningful but not so extreme that it likely signals structural damage
- The stock shows at least early stabilization from its 5-day low
- The risk is bounded enough to investigate, instead of being dominated by legal, delisting, fraud, or bankruptcy language
- There are multiple company-specific headlines rather than only broad macro noise

The report also assigns `Data Confidence`:

- `High`: SEC filing evidence is present and Yahoo/Stooq price calculations broadly agree
- `Medium`: at least one major cross-check supports the signal
- `Low`: the candidate relies mostly on Yahoo headlines/prices and needs manual verification before serious research

The output classes are:

- `A`: High-priority research candidate
- `B`: Watchlist
- `C`: Weak or noisy event
- `D`: Avoid/review only because the event risk is too severe

Always read the actual event context before doing anything with real money.
