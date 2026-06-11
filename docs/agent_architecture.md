# Multi-Agent Research Pipeline Design

## Goal

Upgrade the current event-driven bottom-fishing screener into a research pipeline that behaves more like a small investment research desk.

The system should not try to predict stock prices directly. Its value should come from:

- Collecting evidence from multiple sources
- Separating source credibility from market excitement
- Reading primary documents before trusting secondary commentary
- Debating bull and bear cases
- Penalizing structural risk before producing a focus list
- Producing an auditable research note, not an opaque signal

The output remains a research watchlist, not investment advice or an auto-trading instruction.

## Terminology and Reality Check

The first implementation should be described as an `agent-inspired modular pipeline`, not a full AI agent system.

In the near-term design, each "agent" is a bounded research module:

- It has a fixed responsibility.
- It consumes known data sources.
- It returns structured scores, evidence, concerns, and confidence.
- It does not autonomously plan, choose tools, browse for missing evidence, or run multi-step investigations.

This is still valuable because it makes the system auditable and easier to extend. However, it is not yet an AI agent in the stricter sense.

A true LLM-assisted agent version would add:

- Task-level goals per agent, such as "determine whether this selloff is temporary or structural"
- Tool choice, such as deciding whether to read an 8-K, a 10-Q risk factor section, an earnings transcript, or multiple news sources
- Multi-step reasoning and follow-up questions
- Structured conclusions with evidence, counterarguments, missing data, and confidence
- Debate between bull and bear interpretations
- Memory of prior research notes and outcome feedback

So the roadmap should be:

```text
Current screener
  -> Agent-inspired modular research pipeline
  -> LLM-assisted multi-agent research system
```

## Target Architecture

The long-term architecture is:

```text
News Agent
SEC Filing Agent
Financial Agent
Reddit Agent
Technical Agent
      |
      v
Debate Agent
      |
      v
Risk Agent
      |
      v
Trade Agent
```

For Phase 1, these are deterministic modules with agent-style outputs. In later phases, selected modules can become LLM-assisted agents where extra reasoning and tool choice add real value.

## Agent Responsibilities

### News Agent

Purpose: detect fresh market-moving events.

Near-term behavior: classify and score events from known news feeds.

Future AI-agent behavior: decide which additional sources to verify, identify whether coverage is independent or syndicated, and summarize disagreement between credible sources.

Inputs:

- Yahoo Finance RSS in the current version
- Future: Reuters, Benzinga, MarketWatch, company press releases

Outputs:

- Event category
- Event freshness
- Headline sentiment
- Company-specific vs macro/sector relevance
- News consistency score
- Duplicate/news-noise warning

Example output:

```json
{
  "agent": "news",
  "stance": "mixed_positive",
  "score": 18,
  "confidence": 0.55,
  "evidence": [
    "Analyst downgrade created selloff catalyst",
    "Positive analyst follow-up suggests debate is not one-sided"
  ],
  "concerns": [
    "Some headlines are commentary rather than primary evidence"
  ]
}
```

### SEC Filing Agent

Purpose: verify whether the event has primary-source support.

Near-term behavior: inspect available SEC metadata, recent filings, and company facts.

Future AI-agent behavior: read specific filing sections, compare risk-factor changes, extract 8-K items, and judge whether management language supports or contradicts the market narrative.

Inputs:

- SEC company submissions
- SEC company facts
- Future: 8-K item extraction, 10-Q/10-K risk factor diffing

Outputs:

- Recent relevant filing list
- Primary-source confirmation
- Red flags from filings
- Whether the issue is temporary, cyclical, or structural

Priority:

SEC evidence should outrank all secondary news. If Yahoo says a company has a major issue but SEC filings do not support it, confidence should be capped.

### Financial Agent

Purpose: judge whether the company is worth bottom-fishing.

Near-term behavior: calculate business quality, valuation, and structural risk from available metrics.

Future AI-agent behavior: compare the company against peers, read management commentary, identify accounting distortions, and explain whether valuation improved enough to matter.

Inputs:

- SEC company facts
- Existing price data
- Future: quarterly statements, analyst estimates, peer comparisons

Outputs:

- Business Quality Score
- Valuation Score
- Structural Risk Penalty
- Key metrics:
  - revenue growth
  - net margin
  - free-cash-flow margin
  - liabilities/assets
  - P/S
  - P/E
  - FCF yield

This agent prevents low-quality companies from entering the focus list just because they dropped.

### Reddit Agent

Purpose: measure retail sentiment and narrative intensity.

Near-term behavior: unavailable or low-weight placeholder until a reliable ingestion path exists.

Future AI-agent behavior: cluster narratives, separate serious due diligence from hype, detect crowded trades, and flag one-sided sentiment as a risk.

Inputs:

- Future: Reddit API or Pushshift-style source if available
- Subreddits such as stocks, investing, wallstreetbets, security-specific communities

Outputs:

- Mention velocity
- Positive/negative sentiment
- Narrative crowding
- Meme-risk flag
- Contrarian signal if sentiment is extremely one-sided

Important rule:

Reddit should have low source credibility by default. It can improve awareness of crowd behavior, but it should not override SEC or financial evidence.

### Technical Agent

Purpose: judge whether the setup is stabilizing or still falling.

Near-term behavior: calculate drawdown, short-term stabilization, volume, and falling-knife warnings.

Future AI-agent behavior: compare against sector ETFs, identify regime changes, and produce timing-oriented questions rather than treating charts as proof of business value.

Inputs:

- Daily prices
- Volume
- Future: intraday VWAP, relative strength, sector ETF comparison

Outputs:

- Drawdown
- 5-day stabilization
- 20-day selloff
- Volume expansion
- Falling-knife warning
- Relative strength vs SPY/QQQ/sector ETF

Technical evidence should influence timing, not business quality.

## Debate Agent

Purpose: combine agent outputs into bull and bear cases.

Near-term behavior: deterministic aggregation of module outputs into bull case, bear case, open questions, and a debate score.

Future AI-agent behavior: run an explicit bull-vs-bear review where one side challenges the other, then summarize what evidence would change the conclusion.

Inputs:

- All agent signals
- Source credibility weights
- Evidence quality score

Outputs:

- Bull case
- Bear case
- Disagreement summary
- Debate score
- Questions to verify next

Example:

```text
Bull case:
- Event appears tied to guidance rather than permanent demand destruction.
- Business quality remains high.
- Valuation has improved after the selloff.

Bear case:
- Price has not stabilized.
- Analyst downgrade may reflect slower structural growth.
- Data confidence is only Medium.
```

## Risk Agent

Purpose: block weak or dangerous setups from becoming focus candidates.

Near-term behavior: apply hard rules and penalties.

Future AI-agent behavior: inspect risk evidence, recognize unusual legal/accounting/financing concerns, and veto candidates where the apparent dip is likely structural.

Inputs:

- Debate Agent output
- Structural Risk Penalty
- Legal/terminal-risk events
- Data Confidence
- Technical falling-knife status

Outputs:

- Risk rating: Low / Medium / High / Blocked
- Position-sizing suggestion for research notes only
- Reasons a candidate cannot be Focus

Hard blocks:

- bankruptcy
- fraud/accounting irregularity
- delisting
- severe liquidity issue
- high structural risk with weak business quality
- data confidence too low for the claimed thesis

## Trade Agent

Purpose: produce a final research action.

This should not place trades. It should classify the candidate:

- `Focus`: worth serious manual research now
- `Watch`: monitor, but not top priority
- `Pass`: not worth time this cycle
- `Blocked`: risk/data quality makes the thesis unreliable

Near-term behavior: convert scores and risk gates into a research action.

Future AI-agent behavior: generate the next research plan, including what to verify before buying, what would invalidate the thesis, and what upcoming event matters most.

Outputs:

- Final action
- Trade score
- Research rationale
- Invalidation level or condition
- Next verification event

Example:

```text
Action: Watch
Reason:
- Event is real and valuation improved.
- Business quality is acceptable.
- But technical stabilization is weak and data confidence is Low.
```

## Dynamic Quality Multiplier

The quality multiplier should not be a fixed constant.

It should be calculated from:

```text
Source credibility
News quantity
News consistency
Primary-source confirmation
Data freshness
Historical source hit rate
```

### Source Credibility

Initial weights:

```text
SEC filings:          1.00
Company reports:      0.90
Earnings transcripts: 0.85
Reuters/Bloomberg:    0.80
Major financial news: 0.65
Yahoo RSS headlines:  0.45
Reddit/social:        0.20
```

### News Quantity

More articles are not always better. The score should increase with independent corroboration, but penalize duplicate or syndicated headlines.

Suggested formula:

```text
quantity_score = min(unique_company_specific_events, 5) / 5
```

### News Consistency

Measure whether sources agree on direction:

```text
positive_count
negative_count
mixed_count
```

High consistency:

- Most credible sources point in the same direction

Low consistency:

- Headlines are contradictory
- Commentary conflicts with filings

### Historical Hit Rate

Later phase.

Track whether signals from each source historically produced useful focus candidates.

Example:

```text
source_hit_rate = successful_focus_outcomes / total_focus_outcomes
```

This can eventually tune credibility weights automatically.

### Proposed Evidence Quality Score

```text
evidence_quality =
  0.40 * source_credibility
+ 0.20 * primary_source_confirmation
+ 0.15 * news_consistency
+ 0.10 * unique_event_quantity
+ 0.10 * data_freshness
+ 0.05 * historical_hit_rate
```

Until historical data exists, set `historical_hit_rate = 0.5`.

## Final Scoring Model

The current model should evolve from:

```text
event score + deep dive score
```

to:

```text
trade_score =
  event_opportunity_score
+ technical_stabilization_score
+ business_quality_score
+ valuation_score
+ debate_score
- structural_risk_penalty
- legal_terminal_risk_penalty
- falling_knife_penalty

trade_score = trade_score * evidence_quality_multiplier
```

Where:

```text
evidence_quality_multiplier = 0.70 + 0.60 * evidence_quality
```

This creates a multiplier range of `0.70` to `1.30`.

Low-quality evidence dampens a candidate. High-quality corroborated evidence can lift it.

## Output Design

The report should start with:

```text
Daily Deep Dive Shortlist

Rank | Ticker | Action | Trade Score | Evidence Quality | Risk | Main Bull Case | Main Bear Case
```

Each candidate should include:

```text
Agent Committee Summary
- News Agent
- SEC Filing Agent
- Financial Agent
- Reddit Agent
- Technical Agent

Debate
- Bull case
- Bear case
- Open questions

Risk Review
- Main risks
- Hard blocks
- Invalidation conditions

Trade Agent
- Action
- Trade score
- Why Focus/Watch/Pass
```

## Implementation Plan

### Phase 1: Agent-Inspired Modular Pipeline

No new external APIs.

- Add `AgentSignal`
- Add `AgentCommittee`
- Convert current logic into agent-style outputs:
  - News Agent from current RSS categories
  - SEC Agent from recent filings and company facts
  - Financial Agent from current fundamental scoring
  - Technical Agent from current price stats
  - Reddit Agent as unavailable/neutral placeholder
- Add Debate/Risk/Trade aggregation
- Report agent table in Markdown and JSON

This phase should avoid pretending the modules are autonomous AI agents. The main goal is clean structure, explainability, and a stable contract for later LLM-assisted work.

### Phase 2: Better Primary Documents

- Download and parse recent 8-K text
- Add 10-Q/10-K risk factor diffing
- Add earnings release detection
- Add transcript ingestion if a reliable source is available

### Phase 3: Selective LLM-Assisted Analysis

Use LLM calls only where they provide clear value over rules:

- Summarize SEC filing sections
- Compare current and prior risk factors
- Extract management tone from transcripts
- Produce bull/bear arguments with citations
- Identify missing evidence before a candidate is promoted to Focus

Guardrails:

- LLM output must cite source snippets or structured evidence IDs.
- LLM confidence should not override source credibility.
- The system must keep deterministic fallbacks when LLM calls fail.

### Phase 4: Reddit Agent

- Add Reddit ingestion
- Score mention velocity and sentiment
- Add meme/crowding risk
- Keep Reddit low credibility unless backtested

### Phase 5: Backtesting and Historical Hit Rate

- Store daily outputs
- Track forward returns and drawdowns
- Learn source hit rates
- Tune evidence quality weights

### Phase 6: Trade Workflow

Still no auto-trading by default.

- Add paper-trade mode
- Add watchlist state
- Add invalidation alerts
- Add position sizing suggestions for manual review

## Design Principles

- Primary evidence beats commentary.
- Quality and structural risk gate Focus decisions.
- Reddit can inform sentiment but must not dominate.
- Every final score must be explainable.
- Every Focus candidate must include a bear case.
- The system should prefer saying `Watch` over forcing a trade idea.
