# AI Agent Research System Design

## Purpose

This project is a research system for event-driven US stock bottom-fishing.
It is not an auto-trader and it does not predict prices directly.

The goal is narrower and more useful:

1. find names that sold off after a real event
2. explain why the setup may be temporary or structural
3. surface the 10 stocks most worth human attention
4. narrow those 10 down to 2-3 serious deep-dive candidates
5. show the evidence, missing evidence, and risk gate behind every conclusion

The system should behave like a small research desk, not like a single scoring function with a fancy label.

## Design Principles

The design is intentionally opinionated.

- Event context comes first
- Primary evidence beats commentary
- SEC filings outrank headlines
- Business quality matters more than cheapness alone
- Structural risk can block a candidate even when the price looks attractive
- Reasoning matters as much as the final rank
- Every output should be auditable
- Token usage should be explicit and bounded

The most important product idea is not "LLM predicts stock price".
It is "LLM helps convert noisy event data into a readable research packet".

## Current System Shape

The current codebase already implements a real version of this design.

```text
Event Screener
    |
    v
Deep Dive Filter
    |
    v
Agent Runtime
    |
    +--> News / SEC / Financial / Technical / Sentiment
    |
    +--> Debate
    |
    +--> Risk
    |
    v
Report Writer
```

The screener still does the first-pass narrowing.
The agent runtime then adds structured research, committee-style reasoning, and a final risk-aware recommendation.

## Repository Layout

The current implementation is split by responsibility:

- `src/event_bottom_fishing.py`: candidate generation, event scoring, CLI
- `src/agent_runtime.py`: agent plan, tool orchestration, optional LLM overlay
- `src/models.py`: shared dataclasses and structured outputs
- `src/llm_prompts.py`: prompt templates and token helpers
- `src/reporting.py`: Markdown and JSON rendering
- `src/data_sources.py`: price, news, and SEC retrieval helpers
- `src/scoring.py`: deterministic scoring helpers

This split matters because it keeps reasoning, retrieval, scoring, and rendering from collapsing into one giant file.

## Pipeline

### 1. Candidate Generation

The screener starts with a universe of US stocks.
It fetches recent event headlines and price context, then assigns a first-pass score.

The first-pass score is designed to answer one question:

> Is this stock interesting enough to justify a deeper human look?

Signals in this stage include:

- negative or mixed event catalysts
- drawdown from the recent high
- early stabilization near the low
- company-specific headlines vs broad macro noise
- obvious terminal-risk language

This stage is intentionally lightweight.
It should be fast, deterministic, and easy to inspect.

### 2. Deep Dive Filter

The deep dive stage narrows the first-pass top 10 to 2-3 names.

This stage adds the structure that the user asked for:

- Business Quality Score
- Valuation Score
- Structural Risk Penalty
- Deep Dive Score

The point of this stage is to avoid ranking a stock too high just because it fell a lot.
A cheap bad business is still a bad business.

### 3. Agent Runtime

The agent runtime is the research layer.
It takes the shortlisted candidates and runs a structured multi-step review.

The current plan contains these specialist agents:

- News Agent
- SEC Filing Agent
- Financial Agent
- Technical Agent
- Sentiment Agent
- Debate Agent
- Risk Agent

Each agent has a mission, a tool bundle, a short prompt, and a structured output.

### 4. Final Review

The final review decides whether a candidate becomes:

- `Focus`
- `Watch`
- `Pass`
- `Blocked`

This is not just a numeric threshold.
It is a research decision that combines:

- the deep dive score
- evidence quality
- debate results
- risk gate output
- missing evidence

### 5. Report Writing

The output layer writes both Markdown and JSON.

The report exposes:

- ranking
- rationale
- deep dive reasoning
- agent committee results
- tool trace
- risk notes
- missing evidence

This makes the daily run readable by a human and machine-parseable by downstream automation.

## Agent Modes

The system supports three modes.

### `deterministic`

No LLM calls.
All agent conclusions are produced by deterministic logic.

Use this mode when:

- testing the pipeline
- avoiding token spend
- running in environments without an API key
- wanting stable, cheap daily runs

### `lean`

One compact LLM synthesis per reviewed candidate.

Use this mode when:

- you want a lightweight AI layer
- you want the summary and classification to sound more like a research note
- you want to keep token usage low

This is the default behavior when `OPENAI_API_KEY` is present.

### `full`

LLM support for each agent step plus the final synthesis.

Use this mode when:

- you want the richest reasoning output
- you are doing design work or backtesting the workflow
- token cost matters less than depth

This mode is the closest thing to a "multi-agent research desk" inside the current codebase.

## Agent Responsibilities

### News Agent

The News Agent answers:

> What event caused the selloff, and is the narrative coherent?

It looks at the event headlines and classifies whether the story is:

- recoverable
- noisy
- negative
- structurally alarming

It should not claim business quality.
It only explains the event narrative.

### SEC Filing Agent

The SEC Filing Agent answers:

> Do primary filings support the market story?

This agent is high authority.

If SEC evidence conflicts with the narrative, it should dominate the result.
The agent is especially important for:

- liquidity risk
- accounting risk
- guidance changes
- risk factor changes
- structural deterioration

### Financial Agent

The Financial Agent answers:

> Is this a good business that got cheaper, or a weak business that just got less expensive?

This is where the Business Quality Score and Valuation Score matter.

The purpose is to prevent low-quality names from ranking too high just because the chart looks oversold.

### Technical Agent

The Technical Agent answers:

> Is the stock stabilizing, or is it still a falling knife?

This agent only judges timing and setup quality.
It should not rescue a structurally poor business.

### Sentiment Agent

The Sentiment Agent answers:

> Is crowd behavior creating opportunity, noise, or danger?

This signal is intentionally low trust.
It can help with crowding risk and narrative detection, but it should not outrank filings or fundamentals.

### Debate Agent

The Debate Agent forces the system to confront both sides.

It answers:

> What is the strongest bull case, what is the strongest bear case, and what evidence would change the conclusion?

This is the most useful part of the AI layer.
It turns multiple partial views into a single research argument.

### Risk Agent

The Risk Agent protects the shortlist.

It answers:

> Should this candidate be blocked, downgraded, or allowed through?

It has veto power.

That means a candidate can still be blocked even if the event setup looks attractive.
That is a feature, not a bug.

## Tool Layer

Tools are deterministic helpers.
They fetch or compute information, but they do not decide what the stock means.

Typical tool categories:

- news summaries
- SEC filings and company facts
- price history
- technical context
- risk rules
- committee summaries

The rule is simple:

- tools retrieve and calculate
- agents reason
- reports explain

This separation keeps the system understandable.

## Evidence Quality

Evidence quality is a separate concept from score.

It answers:

> How much should we trust this research packet?

Evidence quality depends on:

- source credibility
- primary-source confirmation
- source consistency
- source independence
- data freshness
- evidence completeness

Credibility should be weighted roughly like this:

- SEC filings: highest trust
- company disclosures and transcripts: high trust
- major financial news: medium trust
- Yahoo headlines: lower trust
- social sentiment: lowest trust

The critical design choice is that low evidence quality should change the decision, not just shave a few points off a score.

## Scoring Model

The current system uses deterministic scores as guardrails, not as the final answer.

Main score components:

- event opportunity
- business quality
- valuation
- structural risk penalty
- data confidence
- technical stabilization

This keeps the system honest in two ways:

1. the LLM does not invent the entire ranking
2. the ranking is still explainable if the LLM is unavailable

The correct mental model is:

```text
deterministic scores = structure and guardrails
agent reasoning = interpretation and judgment
report = explanation and audit trail
```

## Decision Rules

The final classification should follow a few hard rules:

- no `Focus` without a bear case
- no `Focus` with high structural risk
- no `Focus` with low evidence quality
- no `Focus` if primary filings contradict the thesis
- no automatic trading
- every candidate must show why it made the list
- every candidate must show what could break the thesis

These guardrails are more important than a small score difference.

## Output Contract

Every reviewed candidate should include:

- final action
- review score
- evidence quality
- risk rating
- reasoning
- main bull case
- main bear case
- missing evidence
- invalidation conditions
- agent plan
- tool trace

This is what makes the system usable in practice.

The report should answer the reader's real question:

> Why is this name on the list, and what would make us change our mind?

## Token Strategy

Token control is a first-class design constraint.

The system should spend LLM budget where it creates value:

- the final synthesis
- debate and risk framing
- the hardest candidates

The system should avoid spending tokens on:

- long raw article dumps
- redundant prompt context
- unnecessary repeated calls on low-priority names

This is why the code supports `deterministic`, `lean`, and `full`.

## Daily Workflow

```text
1. Candidate generator selects the daily event-driven universe.
2. Deep dive ranks the top candidates.
3. Agent runtime reviews the most important names.
4. Debate and risk gate consolidate the reasoning.
5. Report writer produces Markdown and JSON.
6. GitHub Actions can publish the result on a schedule.
```

The current workflow is designed to run before the US market open on weekdays.

## Extensibility Roadmap

The design leaves space for future upgrades without forcing them into the first version.

Good next additions:

- earnings transcript ingestion
- 8-K and 10-Q section extraction
- risk factor diffing
- better source credibility calibration
- source hit-rate tracking
- social sentiment ingestion
- memory of past thesis outcomes

These should be added as tools or data sources, not as ad hoc prompt text.

## What This System Is Not

This project is not:

- a price prediction engine
- a black-box ranking model
- an automatic execution bot
- a high-frequency trading system
- a social sentiment scraper with agent labels

It is a research workflow for finding and explaining event-driven bottom-fishing ideas.

## Design Summary

The best way to think about this system is:

```text
event screen
+ deterministic guardrails
+ agent reasoning
+ evidence trace
+ risk gate
= daily research shortlist
```

That is the core architecture.
Everything else should support it.
