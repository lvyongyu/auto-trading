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

The Markdown report is designed for a human reader. Each candidate includes:

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

To generate the report and email it:

```bash
python3 src/email_weekly_report.py --to lvyongyu@gmail.com
```

Email settings are loaded from environment variables or a local `.env` file. Start from the example:

```bash
cp config/email.env.example .env
```

For Gmail, set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, and use a Gmail app password as `SMTP_PASSWORD`. The `.env` file is ignored by Git.

## GitHub Actions Schedule

The repository includes `.github/workflows/weekly-stock-email.yml`.

It runs every Monday at 13:00 UTC, before the US market open in both US daylight-saving and standard-time periods. You can also run it manually from the GitHub Actions tab with `workflow_dispatch`.

Configure these repository secrets in GitHub:

- `SMTP_USERNAME`: Gmail address or SMTP username
- `SMTP_PASSWORD`: Gmail app password or SMTP password
- `SMTP_FROM`: optional sender address; usually the same as `SMTP_USERNAME`

GitHub path:

```text
Repository -> Settings -> Secrets and variables -> Actions -> New repository secret
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
