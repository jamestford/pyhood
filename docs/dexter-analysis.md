# Dexter Analysis — What Can pyhood Learn?

**Repo:** https://github.com/virattt/dexter  
**Analyzed:** 2026-03-19  
**Purpose:** Identify tools, patterns, and features worth adopting for pyhood's backtesting engine and autoresearch system.

---

## Section 1: What Dexter Does

### Architecture Overview

Dexter is an **autonomous financial research agent** — think "Claude Code for finance." It takes natural language questions about stocks, crypto, and companies, then:

1. **Plans** — decomposes complex queries into research steps
2. **Executes** — calls financial data APIs, web search, SEC filings, stock screeners
3. **Self-validates** — checks its own work with loop detection and iteration limits
4. **Remembers** — persistent memory with vector + keyword hybrid search (SQLite + embeddings)

It is NOT a trading system. It does not backtest, execute trades, or manage portfolios. It's a **research assistant** that answers financial questions.

### Key Features

- **Meta-tool routing**: Single `get_financials` tool that accepts natural language and uses a secondary LLM call to route to the right sub-tool (income statements, balance sheets, key ratios, etc.). Same pattern for `get_market_data`.
- **Stock screener**: Natural language → structured API filters via LLM structured output. "P/E below 15 and revenue growth above 20%" becomes exact API query.
- **SEC filing reader**: Reads 10-K, 10-Q, 8-K filing content from an API.
- **Persistent memory**: SQLite-backed memory with embedding search (OpenAI/Gemini/Ollama), chunking, hybrid vector+keyword retrieval. Memory survives sessions.
- **Scratchpad/debugging**: Every tool call logged to JSONL files with timestamps, args, results, and LLM reasoning. Full audit trail.
- **Evaluation suite**: LLM-as-judge evaluation against a CSV dataset of financial questions. LangSmith integration for tracking accuracy over time.
- **Skill system**: YAML frontmatter-based skill files (like DCF valuation) that encode multi-step financial workflows.
- **DCF valuation skill**: Complete discounted cash flow analysis with sector-specific WACC tables, sensitivity matrices, and sanity checks.
- **Context management**: Anthropic-style context window management — keeps full tool results, clears oldest when approaching token limits, flushes important info to memory before clearing.
- **Multi-provider LLM**: Supports OpenAI, Anthropic, Google, Ollama, OpenRouter, X.ai.
- **WhatsApp gateway**: Chat with the agent via WhatsApp messages.
- **Tool call limits**: Soft limits on repeated tool calls with similarity detection to prevent retry loops.

### Tech Stack

- **Runtime:** Bun (TypeScript)
- **LLM Framework:** LangChain
- **Database:** better-sqlite3 (for memory/embeddings)
- **Financial Data:** financialdatasets.ai API
- **Search:** Exa, Tavily, Perplexity (fallback chain)
- **Browser:** Playwright
- **Evaluation:** LangSmith
- **UI:** pi-tui (terminal UI)

---

## Section 2: What Dexter Has That We Don't

### 2.1 Fundamental Data Pipeline
**What:** Access to income statements, balance sheets, cash flow statements, key financial ratios, analyst estimates, earnings data, revenue segments, insider trades, SEC filings — all via structured APIs.

**Why it matters:** pyhood currently only uses price/volume data (candles) for strategy decisions. Fundamental data could enable strategies like: "only buy when P/E < 15 AND insider buying is up" or "sell when earnings estimates drop."

### 2.2 Stock Screener with Natural Language
**What:** LLM translates natural language screening criteria into structured API filters. Returns matching tickers.

**Why it matters:** Could automate the "which stocks should I even look at?" question. Instead of manually picking SPY/QQQ/AAPL, you could screen for "stocks with revenue growth >20% and P/E <20" and run autoresearch on the results.

### 2.3 Persistent Memory with Semantic Search
**What:** SQLite database storing conversation context, research findings, user preferences. Hybrid vector (embedding) + keyword search. Survives across sessions.

**Why it matters:** pyhood's autoresearch currently loses context between runs. If the engine discovered that "RSI strategies fail on crypto" in a previous run, it has no way to remember that. Memory could make the research process cumulative.

### 2.4 Evaluation/Benchmarking Framework
**What:** CSV dataset of financial questions with expected answers. LLM-as-judge scoring. LangSmith tracking. Can run on samples or full dataset.

**Why it matters:** pyhood has no equivalent for evaluating the quality of its autoresearch outputs. We could build an eval suite that tests: "Does the autoresearcher actually find strategies that work out-of-sample?"

### 2.5 Scratchpad / Audit Trail
**What:** Every tool call logged to JSONL with timestamps, arguments, raw results, and LLM reasoning. Creates a full audit trail per query.

**Why it matters:** pyhood's `OvernightRunner` logs to `run_log.txt` and `errors.log`, but doesn't capture the full reasoning chain. A JSONL scratchpad would help debug why the autoresearcher made certain decisions.

### 2.6 Skill System (Workflow Templates)
**What:** Markdown files with YAML frontmatter that encode multi-step financial workflows. The DCF skill, for example, has 8 steps with specific data gathering, calculation, and validation steps.

**Why it matters:** pyhood's `program.md` is essentially a manual skill. But it's not machine-parseable or composable. A formal skill system could encode workflows like "Overnight Research Program", "Single Strategy Deep Dive", "Market Regime Analysis" as pluggable templates.

### 2.7 Tool Call Deduplication / Loop Prevention
**What:** Tracks tool calls per query, detects similar queries using Jaccard similarity, warns the LLM when approaching limits, and suggests alternative approaches.

**Why it matters:** If pyhood ever adds an LLM-driven research layer (which it should), this prevents the agent from hammering the same API call in a loop.

### 2.8 News & Sentiment Integration
**What:** Company news, insider trades, earnings surprises — all accessible as tools. Can combine price moves with news to explain "why did X go up?"

**Why it matters:** Could enable event-driven strategies. "Buy when insider buying spikes" or "avoid stocks with negative news sentiment before earnings."

---

## Section 3: Recommendations for pyhood

### Priority 1: Fundamental Data Integration (HIGH IMPACT / MEDIUM EFFORT)

**What:** Add a fundamental data layer that supplements price/volume data. Start with key ratios (P/E, P/B, debt/equity, revenue growth) and insider trading activity.

**Why:** Every strategy in pyhood is purely technical. Adding fundamental filters could dramatically improve signal quality. Example: "Only take EMA crossover signals when P/E < 20 and insider buying is positive."

**How:**
1. Add `financialdatasets.ai` or `yfinance` fundamentals as a data source
2. Create a `FundamentalFilter` wrapper that takes a technical strategy and a fundamental condition
3. Add fundamental screening to autoresearch: sweep not just technical parameters, but fundamental filters too

**Effort:** Medium (2-3 days for basic integration, 1 week for autoresearch integration)  
**Impact:** High — opens entire new class of strategies

### Priority 2: Stock Universe Screening (HIGH IMPACT / LOW EFFORT)

**What:** Before running autoresearch, automatically screen for candidate stocks based on fundamental criteria instead of hardcoding SPY/QQQ/AAPL.

**Why:** The current approach tests strategies on a fixed set of tickers. A screener could find better candidates: "What stocks have high volatility AND strong fundamentals?" — those are ideal for active trading.

**How:**
1. Use `yfinance` or a screening API to filter stocks by criteria
2. Feed the filtered tickers into AutoResearcher as the test universe
3. Run overnight sweeps across both parameter space AND ticker space

**Effort:** Low (1-2 days)  
**Impact:** High — could find dramatically better trading candidates

### Priority 3: Research Memory / Knowledge Base (MEDIUM IMPACT / MEDIUM EFFORT)

**What:** Persistent storage of autoresearch findings, strategy performance across runs, and learned patterns. Use SQLite (like Dexter) with structured data.

**Why:** Currently each autoresearch run starts from scratch. Memory would enable:
- "Last run found RSI(2) Connors works on SPY with these params — start there"
- "EMA strategies fail on crypto — skip those"
- "Regime X is starting — recall which strategies perform best"
- Cumulative research that gets smarter over time

**How:**
1. SQLite database storing: strategy results, regime observations, failed experiments
2. Query interface: "What worked last time on QQQ?" → returns top strategies
3. Auto-load previous best as starting point for new runs

**Effort:** Medium (3-5 days)  
**Impact:** Medium — mostly time savings and smarter starting points

### Priority 4: Evaluation Framework (MEDIUM IMPACT / LOW EFFORT)

**What:** Automated evaluation of autoresearch quality. Does the system actually find strategies that work? Track this over time.

**How:**
1. After each overnight run, forward-test the top strategies on the most recent 3 months (out-of-sample)
2. Track a "hit rate" — what % of strategies that pass train/test/validate actually profit in the next quarter
3. Store results in the memory system above

**Effort:** Low (1-2 days)  
**Impact:** Medium — crucial for knowing if the whole system actually works

### Priority 5: LLM-Driven Strategy Generation (HIGH IMPACT / HIGH EFFORT)

**What:** Use an LLM (like Dexter's agent loop) to generate NEW strategy hypotheses, not just sweep parameters of existing ones.

**Why:** pyhood's autoresearch sweeps parameters of 11 known strategies. But the real alpha is in discovering NEW strategies. An LLM could:
- Read financial research papers and extract strategy ideas
- Combine existing indicators in novel ways
- Propose strategies based on market regime analysis
- Write Python strategy functions and test them

**How:**
1. Build an agent loop (similar to Dexter's) that can write Python strategy code
2. Use autoresearch to validate LLM-generated strategies
3. Persist successful strategies and the reasoning behind them

**Effort:** High (1-2 weeks)  
**Impact:** High — this is the endgame for automated alpha discovery

### Priority 6: Event-Driven Strategy Support (MEDIUM IMPACT / HIGH EFFORT)

**What:** Extend the backtesting engine to handle non-price signals: earnings, insider trades, news sentiment, SEC filings.

**Why:** Many profitable strategies are event-driven, not purely technical. "Buy 3 days before earnings if RSI < 30" or "Sell when CEO sells >$1M in shares."

**How:**
1. Add event data sources (earnings calendar, insider trades, news)
2. Extend the `Candle` model or create a parallel event stream
3. Let strategies access both price and event data
4. Update autoresearch to sweep event-based parameters

**Effort:** High (1-2 weeks)  
**Impact:** Medium — high potential but complex to implement correctly

### Not Recommended

- **WhatsApp/messaging gateway** — Dexter has this but it's irrelevant for pyhood's mission
- **Browser automation** — Overkill for data gathering when APIs exist
- **LangChain** — pyhood is Python; if we add an LLM layer, use the AI SDK or raw API calls, not LangChain's abstractions
- **Terminal UI (TUI)** — Nice for Dexter's interactive mode but pyhood runs headless overnight

---

## Section 4: What We Have That Dexter Doesn't

### 4.1 Actual Trading Engine
Dexter is research-only. pyhood has a complete backtesting engine with:
- Long and short position support
- Slippage modeling
- Equity curve tracking
- Sharpe ratio, max drawdown, win rate, profit factor, CAGR
- Buy & hold benchmark comparison
- yfinance integration for 30+ years of data

Dexter can't backtest anything. It can only answer questions.

### 4.2 Automated Strategy Discovery (AutoResearch)
pyhood's autoresearch system is far ahead:
- Train/test/validate data splitting with overfitting detection
- Multi-parameter grid search with top-N forwarding
- Cross-validation across related tickers
- Regime-aware analysis (bull/bear/recovery/correction)
- Overnight runner with crash resilience, resume, and timeouts
- 11 built-in strategies with parameter grids
- Comprehensive anti-overfitting checklist

Dexter has nothing like this.

### 4.3 Market Regime Classification
pyhood classifies regimes (bull/bear/recovery/correction) using 200-SMA and its slope, then tracks strategy performance by regime. This is critical for understanding WHEN a strategy works.

Dexter has no concept of market regimes.

### 4.4 Strategy Robustness Testing
pyhood checks parameter stability (nearby parameters should produce similar results), cross-validates on related tickers, detects regime dependency, and flags overfitting. This is serious quantitative rigor.

Dexter evaluates answer quality, not strategy quality.

### 4.5 Chart Pattern Recognition
Bull flag detection with configurable parameters — actual pattern recognition in Python.

### 4.6 Volume Analysis
Net Distribution indicator (volume direction analysis), volume-confirmed breakouts. Dexter can fetch volume data but can't analyze it.

---

## Section 5: Architecture Patterns Worth Adopting

### 5.1 Meta-Tool Pattern (Natural Language → Sub-Tool Routing)

Dexter's `get_financials` and `get_market_data` are brilliant: a single tool that accepts natural language and uses an inner LLM call to route to the right sub-tool. This means the outer agent only needs to decide "I need financial data" — not which specific API endpoint to call.

**Adopt for pyhood:** If we add an LLM-driven research layer, use this pattern. One tool: "analyze_strategy" that accepts natural language and routes to: backtest, parameter sweep, cross-validate, regime analysis, etc.

### 5.2 Scratchpad Pattern (JSONL Audit Trail)

Every action logged to append-only JSONL files. Cheap, crash-safe, debuggable. Each research session gets its own file with a timestamp hash.

**Adopt for pyhood:** Add JSONL logging to autoresearch. Each experiment logs: hypothesis, parameters, results, reasoning. This becomes the training data for the LLM-driven strategy generator.

### 5.3 Tool Call Budget Pattern

Dexter tracks tool usage per query and warns when approaching limits. Uses Jaccard similarity to detect "you're asking the same thing again."

**Adopt for pyhood:** Apply to autoresearch — if the system has tried 50 variations of EMA crossover and none beat the benchmark, it should automatically move on to the next strategy family.

### 5.4 Memory Flush Pattern

When context gets large, Dexter asks the LLM to summarize what's worth remembering, stores it in persistent memory, then clears the context. This keeps the agent running indefinitely without losing critical insights.

**Adopt for pyhood:** After each autoresearch run, summarize findings into a persistent knowledge base. "Regime-dependent strategies found for SPY: [list]. Failed approaches: [list]. Next research directions: [list]."

### 5.5 Skill System (Workflow Templates)

YAML frontmatter + markdown instructions. Machine-parseable, composable, discoverable at startup.

**Adopt for pyhood:** Convert `program.md` into a formal skill format. Add more skills: "Quick Backtest", "Deep Parameter Sweep", "Regime Analysis", "Cross-Ticker Robustness Check". Each with clear inputs/outputs and step-by-step workflow.

### 5.6 Evaluation-Driven Development

Dexter has an eval suite that measures whether the agent actually answers financial questions correctly. Every code change can be validated against the eval set.

**Adopt for pyhood:** Build a "strategy discovery eval" — a set of known-good strategies (verified manually) that the autoresearcher should find. Track discovery rate over time. This tells you if your system improvements actually help.

---

## Bottom Line

**Dexter and pyhood are complementary, not competitive.** Dexter is a financial research chatbot. pyhood is a quantitative trading system. The biggest opportunity is combining them:

1. **Use Dexter-style fundamental data** to filter pyhood's trading signals
2. **Use Dexter-style LLM agents** to generate new strategy hypotheses for pyhood to backtest
3. **Use Dexter-style memory** to make pyhood's autoresearch cumulative across runs
4. **Use Dexter-style screening** to find better tickers to trade

The highest-ROI change: **add fundamental data filtering to the backtesting engine**. It's the single biggest gap in pyhood's strategy space, and Dexter shows exactly which data sources and APIs make it practical.
