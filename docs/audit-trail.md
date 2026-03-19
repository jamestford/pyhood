# Audit Trail

Append-only JSONL logging for every autoresearch decision. Crash-safe, debuggable, and ready for future ML training pipelines.

## Why

Every overnight research run makes thousands of decisions: which experiments to run, which to skip, what passed, what failed, why a strategy was kept or discarded. Without a trail, debugging "why did it pick this strategy?" is archaeology.

The audit trail captures **every significant action** as a single JSON line, appended to a file. If the process crashes mid-run, you lose at most the current line — everything before it is intact on disk.

## JSONL Format

Each audit file is [JSONL](https://jsonlines.org/) — one JSON object per line. This is intentional:

- **Append-only**: No need to parse the whole file to add an entry
- **Crash-safe**: Each line is a complete, valid JSON object
- **Streamable**: `tail -f` works. `grep` works. `jq` works.
- **Compact**: No formatting overhead

Each line has this structure:

```json
{"timestamp": "2026-03-19T20:30:00+00:00", "event": "experiment_started", "data": {"strategy_name": "EMA Crossover", "params": {"fast": 5, "slow": 20}, "ticker": "SPY"}}
```

Fields:
- `timestamp` — ISO 8601 UTC
- `event` — Event type string
- `data` — Event-specific payload (always a dict)

## File Naming

```
{audit_dir}/audit_{run_id}_{YYYYMMDD_HHMMSS}.jsonl
```

- `run_id` — Integer or string identifying the research run
- Timestamp is UTC at run start
- Each run gets its own file — no mixing

Example: `autoresearch_results/audit/audit_7_20260319_203000.jsonl`

## Event Types

### `run_started`
Logged when `start_run()` is called. First event in every file.

```json
{"timestamp": "2026-03-19T20:30:00+00:00", "event": "run_started", "data": {"run_id": 7, "ticker": "SPY", "config": {"total_period": "10y", "experiment_timeout": 60}}}
```

### `experiment_started`
Before each experiment begins.

```json
{"timestamp": "2026-03-19T20:30:01+00:00", "event": "experiment_started", "data": {"strategy_name": "EMA Crossover", "params": {"fast": 5, "slow": 20}, "ticker": "SPY"}}
```

### `experiment_completed`
After an experiment finishes successfully.

```json
{"timestamp": "2026-03-19T20:30:05+00:00", "event": "experiment_completed", "data": {"strategy_name": "EMA Crossover", "params": {"fast": 5, "slow": 20}, "train_sharpe": 1.52, "test_sharpe": 1.31, "kept": true, "reason": "Beat baseline on both splits"}}
```

### `experiment_skipped`
When an experiment is skipped (deduplication, memory hint, etc.).

```json
{"timestamp": "2026-03-19T20:30:06+00:00", "event": "experiment_skipped", "data": {"strategy_name": "EMA Crossover", "params": {"fast": 5, "slow": 20}, "reason": "already completed (resume)"}}
```

### `experiment_failed`
When an experiment throws an exception.

```json
{"timestamp": "2026-03-19T20:30:07+00:00", "event": "experiment_failed", "data": {"strategy_name": "MACD", "params": {"fast": 12, "slow": 26}, "error": "ValueError: not enough data", "traceback": "Traceback (most recent call last):\n  ..."}}
```

### `experiment_timeout`
When an experiment exceeds the time limit.

```json
{"timestamp": "2026-03-19T20:31:07+00:00", "event": "experiment_timeout", "data": {"strategy_name": "EMA Crossover", "params": {"fast": 5, "slow": 200}, "timeout_seconds": 60}}
```

### `insight_generated`
When the system auto-generates a research insight.

```json
{"timestamp": "2026-03-19T21:00:00+00:00", "event": "insight_generated", "data": {"insight_text": "EMA crossovers with fast<10 consistently outperform", "category": "strategy_selection", "confidence": "high", "evidence_count": 15}}
```

### `priority_created`
When a new research priority is queued.

```json
{"timestamp": "2026-03-19T21:00:01+00:00", "event": "priority_created", "data": {"description": "Test mean reversion on crypto pairs", "priority_level": "high", "source_insight": "Trend-following underperforms on BTC"}}
```

### `sweep_started`
At the beginning of a parameter sweep.

```json
{"timestamp": "2026-03-19T20:30:00+00:00", "event": "sweep_started", "data": {"strategy_name": "EMA Crossover", "param_grid": {"fast": [5, 7, 9], "slow": [20, 30, 50]}, "total_combos": 9}}
```

### `sweep_completed`
At the end of a parameter sweep.

```json
{"timestamp": "2026-03-19T20:35:00+00:00", "event": "sweep_completed", "data": {"strategy_name": "EMA Crossover", "total_combos": 9, "kept_count": 2, "best_sharpe": 1.52}}
```

### `validation_result`
Final validation results for a strategy.

```json
{"timestamp": "2026-03-19T22:00:00+00:00", "event": "validation_result", "data": {"strategy_name": "EMA Crossover", "params": {"fast": 5, "slow": 20}, "validate_sharpe": 1.15, "cross_validation": {"passed": true, "results": {"QQQ": {"sharpe": 0.95}}}}}
```

### `decision`
Explicit research decisions with reasoning.

```json
{"timestamp": "2026-03-19T20:45:00+00:00", "event": "decision", "data": {"description": "Moving to RSI family", "reasoning": "EMA sweep exhausted, diminishing returns"}}
```

### `memory_query`
When the system queries research memory.

```json
{"timestamp": "2026-03-19T20:30:00+00:00", "event": "memory_query", "data": {"query_type": "similar_experiments", "result_summary": "Found 5 prior runs with EMA on SPY"}}
```

### `run_completed`
Last event in every file. Logged by `end_run()`.

```json
{"timestamp": "2026-03-19T23:00:00+00:00", "event": "run_completed", "data": {"total_experiments": 632, "errors": 3, "timeouts": 1, "best_train_sharpe": 2.1, "best_test_sharpe": 1.8, "kept_strategies": 12}}
```

## Reading and Analyzing

### Python API

```python
from pyhood.autoresearch import AuditTrail

audit = AuditTrail(audit_dir='autoresearch_results/audit')

# List all audit files (newest first)
files = audit.get_audit_files()

# Read events from a specific file
events = audit.read_events(files[0])
for ev in events:
    print(f"{ev['timestamp']} | {ev['event']}")

# Get summary statistics
s = audit.summary(files[0])
print(f"Run {s['run_id']}: {s['total_events']} events, "
      f"{s['experiments_completed']} completed, "
      f"{s['experiments_kept']} kept")
```

### CLI Tools

Pretty-print a JSONL file:
```bash
cat audit_7_20260319_203000.jsonl | python -m json.tool --json-lines
```

Filter with `jq`:
```bash
# All kept experiments
cat audit.jsonl | jq 'select(.event == "experiment_completed" and .data.kept == true)'

# Failures only
cat audit.jsonl | jq 'select(.event == "experiment_failed")'

# Strategy names that were kept
cat audit.jsonl | jq 'select(.data.kept == true) | .data.strategy_name'

# Count events by type
cat audit.jsonl | jq -s 'group_by(.event) | map({event: .[0].event, count: length})'

# Timeline of a specific strategy
cat audit.jsonl | jq 'select(.data.strategy_name == "EMA Crossover")'

# Sharpe ratios over time
cat audit.jsonl | jq 'select(.event == "experiment_completed") | {ts: .timestamp, sharpe: .data.train_sharpe}'
```

Watch a live run:
```bash
tail -f audit.jsonl | jq '.'
```

## Debugging Research Decisions

The audit trail answers questions like:

- **"Why was this strategy kept?"** — Find the `experiment_completed` event with `kept: true` and check the `reason` field.
- **"What failed?"** — Filter for `experiment_failed` events to see errors and stack traces.
- **"How long did each sweep take?"** — Compare timestamps between `sweep_started` and `sweep_completed`.
- **"Was this combination tested?"** — Search for `experiment_started` with matching params.
- **"What was skipped and why?"** — Filter for `experiment_skipped` events.

## Integration with OvernightRunner

The `OvernightRunner` automatically creates and manages the audit trail:

```python
from pyhood.autoresearch.overnight import OvernightRunner

runner = OvernightRunner(
    ticker='SPY',
    audit=True,  # default — set False to disable
)
result = runner.run()

# Audit files are in: autoresearch_results/audit/
```

Set `audit=False` to disable (backward compatible, zero overhead when off).

## Future: Training Data for LLM-Driven Strategy Generation

Every audit file is a complete record of research decisions and outcomes. This is structured training data for LLM-driven strategy generation:

- **Input**: Strategy parameters, market conditions, prior results
- **Output**: Whether the strategy was kept, sharpe ratios, failure modes
- **Signal**: Which parameter regions are productive vs. exhausted

A corpus of audit trails across tickers and time periods becomes a dataset for learning:
- Which strategy families work for which market regimes
- Optimal parameter search patterns
- When to stop exploring a family (diminishing returns)
- How to prioritize experiments based on prior evidence

The JSONL format makes this trivial to ingest into any ML pipeline.
