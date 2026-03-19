"""Append-only JSONL audit trail for autoresearch decisions.

Every significant action gets logged as a single JSON line.
Cheap, crash-safe, debuggable. Each run gets its own file.

File naming: {audit_dir}/audit_{run_id}_{timestamp}.jsonl
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone


class AuditTrail:
    """Append-only JSONL audit trail for autoresearch decisions.

    Every significant action gets logged as a single JSON line.
    Cheap, crash-safe, debuggable. Each run gets its own file.

    File naming: {audit_dir}/audit_{run_id}_{timestamp}.jsonl
    """

    def __init__(self, audit_dir: str = 'autoresearch_results/audit'):
        """Initialize audit trail directory."""
        self._audit_dir = audit_dir
        self._file_path: str | None = None
        self._run_id: int | str | None = None
        os.makedirs(audit_dir, exist_ok=True)

    @property
    def file_path(self) -> str | None:
        """Current audit file path."""
        return self._file_path

    @property
    def audit_dir(self) -> str:
        """Audit directory path."""
        return self._audit_dir

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_run(self, run_id: int | str, ticker: str, config: dict | None = None):
        """Start a new audit file for this run.

        Creates: audit_{run_id}_{YYYYMMDD_HHMMSS}.jsonl
        Logs a 'run_started' event.
        """
        self._run_id = run_id
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f'audit_{run_id}_{ts}.jsonl'
        self._file_path = os.path.join(self._audit_dir, filename)
        self.log('run_started', {
            'run_id': run_id,
            'ticker': ticker,
            'config': config or {},
        })

    def log(self, event_type: str, data: dict | None = None):
        """Append a single event to the JSONL file.

        Each line is:
        {"timestamp": "2026-03-19T20:30:00+00:00", "event": "experiment_started", "data": {...}}
        """
        if self._file_path is None:
            return
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': event_type,
            'data': data or {},
        }
        with open(self._file_path, 'a') as f:
            f.write(json.dumps(entry, default=str) + '\n')

    def end_run(self, summary: dict | None = None):
        """Log run completion and close."""
        self.log('run_completed', summary or {})

    # ------------------------------------------------------------------
    # Convenience methods for common events
    # ------------------------------------------------------------------

    def experiment_started(self, strategy_name: str, params: dict, ticker: str):
        """Log that an experiment is about to run."""
        self.log('experiment_started', {
            'strategy_name': strategy_name,
            'params': params,
            'ticker': ticker,
        })

    def experiment_completed(
        self,
        strategy_name: str,
        params: dict,
        train_sharpe: float,
        test_sharpe: float | None = None,
        kept: bool = False,
        reason: str = '',
    ):
        """Log experiment completion with results."""
        self.log('experiment_completed', {
            'strategy_name': strategy_name,
            'params': params,
            'train_sharpe': train_sharpe,
            'test_sharpe': test_sharpe,
            'kept': kept,
            'reason': reason,
        })

    def experiment_skipped(self, strategy_name: str, params: dict, reason: str):
        """Log that an experiment was skipped (dedup, insight, etc.)."""
        self.log('experiment_skipped', {
            'strategy_name': strategy_name,
            'params': params,
            'reason': reason,
        })

    def experiment_failed(
        self, strategy_name: str, params: dict, error: str, traceback: str = '',
    ):
        """Log experiment failure."""
        self.log('experiment_failed', {
            'strategy_name': strategy_name,
            'params': params,
            'error': error,
            'traceback': traceback,
        })

    def experiment_timeout(
        self, strategy_name: str, params: dict, timeout_seconds: int,
    ):
        """Log experiment timeout."""
        self.log('experiment_timeout', {
            'strategy_name': strategy_name,
            'params': params,
            'timeout_seconds': timeout_seconds,
        })

    def insight_generated(
        self,
        insight_text: str,
        category: str,
        confidence: str,
        evidence_count: int,
    ):
        """Log auto-generated insight."""
        self.log('insight_generated', {
            'insight_text': insight_text,
            'category': category,
            'confidence': confidence,
            'evidence_count': evidence_count,
        })

    def priority_created(
        self, description: str, priority_level: str, source_insight: str = '',
    ):
        """Log new research priority."""
        self.log('priority_created', {
            'description': description,
            'priority_level': priority_level,
            'source_insight': source_insight,
        })

    def priority_resolved(
        self, description: str, status: str, result: str = '',
    ):
        """Log priority completion."""
        self.log('priority_resolved', {
            'description': description,
            'status': status,
            'result': result,
        })

    def sweep_started(
        self, strategy_name: str, param_grid: dict, total_combos: int,
    ):
        """Log start of a parameter sweep."""
        self.log('sweep_started', {
            'strategy_name': strategy_name,
            'param_grid': param_grid,
            'total_combos': total_combos,
        })

    def sweep_completed(
        self,
        strategy_name: str,
        total_combos: int,
        kept_count: int,
        best_sharpe: float | None = None,
    ):
        """Log sweep completion with summary."""
        self.log('sweep_completed', {
            'strategy_name': strategy_name,
            'total_combos': total_combos,
            'kept_count': kept_count,
            'best_sharpe': best_sharpe,
        })

    def validation_result(
        self,
        strategy_name: str,
        params: dict,
        validate_sharpe: float,
        cross_validation: dict | None = None,
    ):
        """Log final validation results."""
        self.log('validation_result', {
            'strategy_name': strategy_name,
            'params': params,
            'validate_sharpe': validate_sharpe,
            'cross_validation': cross_validation,
        })

    def decision(self, description: str, reasoning: str = ''):
        """Log a research decision (e.g., 'Moving to next strategy family because...')."""
        self.log('decision', {
            'description': description,
            'reasoning': reasoning,
        })

    def memory_query(self, query_type: str, result_summary: str):
        """Log when the system queries research memory."""
        self.log('memory_query', {
            'query_type': query_type,
            'result_summary': result_summary,
        })

    # ------------------------------------------------------------------
    # Reading / Analysis
    # ------------------------------------------------------------------

    def read_events(self, file_path: str | None = None) -> list[dict]:
        """Read all events from a JSONL file. Defaults to current file."""
        target = file_path or self._file_path
        if target is None or not os.path.exists(target):
            return []
        events = []
        with open(target) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events

    def get_audit_files(self) -> list[str]:
        """List all audit JSONL files, newest first."""
        if not os.path.isdir(self._audit_dir):
            return []
        files = [
            os.path.join(self._audit_dir, f)
            for f in os.listdir(self._audit_dir)
            if f.startswith('audit_') and f.endswith('.jsonl')
        ]
        files.sort(reverse=True)
        return files

    def summary(self, file_path: str | None = None) -> dict:
        """Generate summary stats from an audit file.

        Returns:
            {
                'run_id': '...',
                'total_events': 150,
                'experiments_started': 50,
                'experiments_completed': 48,
                'experiments_skipped': 12,
                'experiments_failed': 2,
                'experiments_kept': 5,
                'insights_generated': 8,
                'priorities_created': 3,
                'duration_seconds': None,
                'event_types': {'experiment_started': 50, ...}
            }
        """
        events = self.read_events(file_path)
        if not events:
            return {
                'run_id': None,
                'total_events': 0,
                'experiments_started': 0,
                'experiments_completed': 0,
                'experiments_skipped': 0,
                'experiments_failed': 0,
                'experiments_kept': 0,
                'insights_generated': 0,
                'priorities_created': 0,
                'duration_seconds': None,
                'event_types': {},
            }

        event_types: dict[str, int] = {}
        run_id = None
        kept_count = 0

        for ev in events:
            etype = ev.get('event', 'unknown')
            event_types[etype] = event_types.get(etype, 0) + 1
            if etype == 'run_started':
                run_id = ev.get('data', {}).get('run_id')
            if etype == 'experiment_completed':
                if ev.get('data', {}).get('kept'):
                    kept_count += 1

        # Duration from first to last event
        duration = None
        try:
            first_ts = datetime.fromisoformat(events[0]['timestamp'])
            last_ts = datetime.fromisoformat(events[-1]['timestamp'])
            duration = (last_ts - first_ts).total_seconds()
        except (KeyError, ValueError, TypeError):
            pass

        return {
            'run_id': run_id,
            'total_events': len(events),
            'experiments_started': event_types.get('experiment_started', 0),
            'experiments_completed': event_types.get('experiment_completed', 0),
            'experiments_skipped': event_types.get('experiment_skipped', 0),
            'experiments_failed': event_types.get('experiment_failed', 0),
            'experiments_kept': kept_count,
            'insights_generated': event_types.get('insight_generated', 0),
            'priorities_created': event_types.get('priority_created', 0),
            'duration_seconds': duration,
            'event_types': event_types,
        }
