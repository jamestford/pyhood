"""Tests for the JSONL audit trail module."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone

from pyhood.autoresearch.audit import AuditTrail

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_audit(tmpdir: str | None = None) -> tuple[AuditTrail, str]:
    """Create an AuditTrail in a temp directory."""
    if tmpdir is None:
        tmpdir = tempfile.mkdtemp()
    audit_dir = os.path.join(tmpdir, 'audit')
    audit = AuditTrail(audit_dir=audit_dir)
    return audit, audit_dir


def _read_jsonl(path: str) -> list[dict]:
    """Read all JSON lines from a file."""
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


# ---------------------------------------------------------------------------
# Tests — Initialization
# ---------------------------------------------------------------------------

class TestAuditTrailInit:

    def test_creates_directory_on_init(self):
        tmpdir = tempfile.mkdtemp()
        audit_dir = os.path.join(tmpdir, 'nested', 'audit')
        AuditTrail(audit_dir=audit_dir)
        assert os.path.isdir(audit_dir)

    def test_file_path_none_before_start(self):
        audit, _ = _make_audit()
        assert audit.file_path is None

    def test_audit_dir_property(self):
        tmpdir = tempfile.mkdtemp()
        audit_dir = os.path.join(tmpdir, 'audit')
        audit = AuditTrail(audit_dir=audit_dir)
        assert audit.audit_dir == audit_dir

    def test_existing_directory_ok(self):
        tmpdir = tempfile.mkdtemp()
        audit_dir = os.path.join(tmpdir, 'audit')
        os.makedirs(audit_dir)
        # Should not raise
        AuditTrail(audit_dir=audit_dir)
        assert os.path.isdir(audit_dir)


# ---------------------------------------------------------------------------
# Tests — start_run
# ---------------------------------------------------------------------------

class TestStartRun:

    def test_creates_jsonl_file(self):
        audit, audit_dir = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        assert audit.file_path is not None
        assert os.path.exists(audit.file_path)

    def test_file_name_pattern(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=42, ticker='SPY')
        filename = os.path.basename(audit.file_path)
        assert filename.startswith('audit_42_')
        assert filename.endswith('.jsonl')

    def test_file_name_with_string_run_id(self):
        audit, _ = _make_audit()
        audit.start_run(run_id='abc', ticker='QQQ')
        filename = os.path.basename(audit.file_path)
        assert filename.startswith('audit_abc_')

    def test_start_run_logs_event(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY', config={'timeout': 60})
        events = _read_jsonl(audit.file_path)
        assert len(events) == 1
        assert events[0]['event'] == 'run_started'
        assert events[0]['data']['run_id'] == 1
        assert events[0]['data']['ticker'] == 'SPY'
        assert events[0]['data']['config'] == {'timeout': 60}


# ---------------------------------------------------------------------------
# Tests — log
# ---------------------------------------------------------------------------

class TestLog:

    def test_log_appends_valid_json_lines(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.log('custom_event', {'key': 'value'})
        audit.log('another_event', {'count': 42})

        events = _read_jsonl(audit.file_path)
        assert len(events) == 3  # start_run + 2 logs

    def test_each_line_is_parseable(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        for i in range(10):
            audit.log(f'event_{i}', {'index': i})

        with open(audit.file_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    parsed = json.loads(line)
                    assert 'timestamp' in parsed
                    assert 'event' in parsed
                    assert 'data' in parsed

    def test_log_without_data(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.log('empty_event')
        events = _read_jsonl(audit.file_path)
        assert events[-1]['data'] == {}

    def test_log_before_start_run_is_noop(self):
        audit, audit_dir = _make_audit()
        # No start_run called, file_path is None
        audit.log('orphan_event', {'data': 1})
        # No file should be created
        files = [f for f in os.listdir(audit_dir) if f.endswith('.jsonl')]
        assert len(files) == 0

    def test_timestamps_are_iso_format(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.log('test_event')

        events = _read_jsonl(audit.file_path)
        for ev in events:
            ts = ev['timestamp']
            # Should parse without error
            parsed = datetime.fromisoformat(ts)
            assert parsed.tzinfo is not None  # UTC-aware


# ---------------------------------------------------------------------------
# Tests — Convenience methods
# ---------------------------------------------------------------------------

class TestConvenienceMethods:

    def _setup(self) -> AuditTrail:
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        return audit

    def test_experiment_started(self):
        audit = self._setup()
        audit.experiment_started('EMA', {'fast': 5}, 'SPY')
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'experiment_started'
        assert ev['data']['strategy_name'] == 'EMA'
        assert ev['data']['params'] == {'fast': 5}
        assert ev['data']['ticker'] == 'SPY'

    def test_experiment_completed(self):
        audit = self._setup()
        audit.experiment_completed(
            'EMA', {'fast': 5}, train_sharpe=1.5,
            test_sharpe=1.2, kept=True, reason='beat baseline',
        )
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'experiment_completed'
        assert ev['data']['train_sharpe'] == 1.5
        assert ev['data']['test_sharpe'] == 1.2
        assert ev['data']['kept'] is True
        assert ev['data']['reason'] == 'beat baseline'

    def test_experiment_skipped(self):
        audit = self._setup()
        audit.experiment_skipped('RSI', {'period': 14}, 'already tested')
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'experiment_skipped'
        assert ev['data']['reason'] == 'already tested'

    def test_experiment_failed(self):
        audit = self._setup()
        audit.experiment_failed('MACD', {'fast': 12}, 'ValueError', 'traceback...')
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'experiment_failed'
        assert ev['data']['error'] == 'ValueError'
        assert ev['data']['traceback'] == 'traceback...'

    def test_experiment_timeout(self):
        audit = self._setup()
        audit.experiment_timeout('EMA', {'fast': 5}, 60)
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'experiment_timeout'
        assert ev['data']['timeout_seconds'] == 60

    def test_insight_generated(self):
        audit = self._setup()
        audit.insight_generated(
            'EMA works best with fast<10',
            category='strategy_selection',
            confidence='high',
            evidence_count=15,
        )
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'insight_generated'
        assert ev['data']['insight_text'] == 'EMA works best with fast<10'
        assert ev['data']['confidence'] == 'high'
        assert ev['data']['evidence_count'] == 15

    def test_priority_created(self):
        audit = self._setup()
        audit.priority_created(
            'Test mean reversion on crypto',
            priority_level='high',
            source_insight='EMA underperforms on crypto',
        )
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'priority_created'
        assert ev['data']['priority_level'] == 'high'

    def test_sweep_started(self):
        audit = self._setup()
        audit.sweep_started('EMA', {'fast': [5, 9], 'slow': [20, 30]}, 4)
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'sweep_started'
        assert ev['data']['total_combos'] == 4

    def test_sweep_completed(self):
        audit = self._setup()
        audit.sweep_completed('EMA', total_combos=4, kept_count=1, best_sharpe=1.8)
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'sweep_completed'
        assert ev['data']['kept_count'] == 1
        assert ev['data']['best_sharpe'] == 1.8

    def test_validation_result(self):
        audit = self._setup()
        audit.validation_result(
            'EMA', {'fast': 5}, validate_sharpe=1.1,
            cross_validation={'passed': True},
        )
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'validation_result'
        assert ev['data']['validate_sharpe'] == 1.1
        assert ev['data']['cross_validation'] == {'passed': True}

    def test_decision(self):
        audit = self._setup()
        audit.decision('Moving to RSI family', reasoning='EMA exhausted')
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'decision'
        assert ev['data']['description'] == 'Moving to RSI family'
        assert ev['data']['reasoning'] == 'EMA exhausted'

    def test_memory_query(self):
        audit = self._setup()
        audit.memory_query('similar_experiments', 'Found 5 prior runs')
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'memory_query'
        assert ev['data']['query_type'] == 'similar_experiments'


# ---------------------------------------------------------------------------
# Tests — end_run
# ---------------------------------------------------------------------------

class TestEndRun:

    def test_end_run_logs_completion(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.end_run({'total': 50, 'errors': 2})
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'run_completed'
        assert ev['data']['total'] == 50

    def test_end_run_no_summary(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.end_run()
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['event'] == 'run_completed'
        assert ev['data'] == {}


# ---------------------------------------------------------------------------
# Tests — read_events
# ---------------------------------------------------------------------------

class TestReadEvents:

    def test_returns_all_events_in_order(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.log('event_a')
        audit.log('event_b')
        audit.log('event_c')

        events = audit.read_events()
        assert len(events) == 4  # start_run + 3
        assert events[0]['event'] == 'run_started'
        assert events[1]['event'] == 'event_a'
        assert events[2]['event'] == 'event_b'
        assert events[3]['event'] == 'event_c'

    def test_read_events_from_specific_file(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.log('test')
        path = audit.file_path

        events = audit.read_events(file_path=path)
        assert len(events) == 2

    def test_read_events_missing_file(self):
        audit, _ = _make_audit()
        events = audit.read_events('/nonexistent/path.jsonl')
        assert events == []

    def test_read_events_no_current_file(self):
        audit, _ = _make_audit()
        # No start_run called
        events = audit.read_events()
        assert events == []

    def test_read_events_empty_file(self):
        audit, audit_dir = _make_audit()
        # Create an empty file
        empty_path = os.path.join(audit_dir, 'empty.jsonl')
        with open(empty_path, 'w'):
            pass
        events = audit.read_events(file_path=empty_path)
        assert events == []

    def test_read_events_handles_corrupt_lines(self):
        audit, audit_dir = _make_audit()
        corrupt_path = os.path.join(audit_dir, 'corrupt.jsonl')
        with open(corrupt_path, 'w') as f:
            f.write('{"event": "good", "timestamp": "2026-01-01T00:00:00+00:00", "data": {}}\n')
            f.write('this is not json\n')
            f.write(
                '{"event": "also_good", "timestamp": "2026-01-01T00:00:01+00:00", "data": {}}\n'
            )
        events = audit.read_events(file_path=corrupt_path)
        assert len(events) == 2
        assert events[0]['event'] == 'good'
        assert events[1]['event'] == 'also_good'


# ---------------------------------------------------------------------------
# Tests — get_audit_files
# ---------------------------------------------------------------------------

class TestGetAuditFiles:

    def test_lists_files_newest_first(self):
        audit, audit_dir = _make_audit()

        # Create files with different timestamps in names
        for name in ['audit_1_20260101_000000.jsonl',
                      'audit_1_20260301_000000.jsonl',
                      'audit_1_20260201_000000.jsonl']:
            with open(os.path.join(audit_dir, name), 'w') as f:
                f.write('')

        files = audit.get_audit_files()
        basenames = [os.path.basename(f) for f in files]
        assert basenames[0] == 'audit_1_20260301_000000.jsonl'
        assert basenames[1] == 'audit_1_20260201_000000.jsonl'
        assert basenames[2] == 'audit_1_20260101_000000.jsonl'

    def test_empty_directory(self):
        audit, _ = _make_audit()
        files = audit.get_audit_files()
        assert files == []

    def test_ignores_non_audit_files(self):
        audit, audit_dir = _make_audit()
        # Create non-audit files
        with open(os.path.join(audit_dir, 'notes.txt'), 'w') as f:
            f.write('hello')
        with open(os.path.join(audit_dir, 'audit_1_20260101_000000.jsonl'), 'w') as f:
            f.write('')
        files = audit.get_audit_files()
        assert len(files) == 1
        assert 'notes.txt' not in files[0]

    def test_missing_directory(self):
        tmpdir = tempfile.mkdtemp()
        audit = AuditTrail(audit_dir=os.path.join(tmpdir, 'audit'))
        # Remove the dir
        os.rmdir(os.path.join(tmpdir, 'audit'))
        files = audit.get_audit_files()
        assert files == []


# ---------------------------------------------------------------------------
# Tests — summary
# ---------------------------------------------------------------------------

class TestSummary:

    def test_summary_counts(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=7, ticker='SPY')
        audit.experiment_started('EMA', {'fast': 5}, 'SPY')
        audit.experiment_completed('EMA', {'fast': 5}, 1.5, 1.2, kept=True)
        audit.experiment_started('RSI', {'period': 14}, 'SPY')
        audit.experiment_completed('RSI', {'period': 14}, 0.5, 0.3, kept=False)
        audit.experiment_started('MACD', {'fast': 12}, 'SPY')
        audit.experiment_failed('MACD', {'fast': 12}, 'error')
        audit.experiment_skipped('BB', {'period': 20}, 'dedup')
        audit.insight_generated('test insight', 'cat', 'high', 3)
        audit.priority_created('test priority', 'high')
        audit.end_run()

        s = audit.summary()
        assert s['run_id'] == 7
        # start + 3 started + 2 completed + 1 failed + 1 skipped
        # + 1 insight + 1 priority + end
        assert s['total_events'] == 11
        assert s['experiments_started'] == 3
        assert s['experiments_completed'] == 2
        assert s['experiments_failed'] == 1
        assert s['experiments_skipped'] == 1
        assert s['experiments_kept'] == 1
        assert s['insights_generated'] == 1
        assert s['priorities_created'] == 1
        assert s['duration_seconds'] is not None
        assert s['duration_seconds'] >= 0

    def test_summary_event_types(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.experiment_started('EMA', {}, 'SPY')
        audit.experiment_completed('EMA', {}, 1.0)
        audit.end_run()

        s = audit.summary()
        assert 'run_started' in s['event_types']
        assert 'experiment_started' in s['event_types']
        assert 'experiment_completed' in s['event_types']
        assert 'run_completed' in s['event_types']

    def test_summary_empty_file(self):
        audit, _ = _make_audit()
        s = audit.summary()
        assert s['run_id'] is None
        assert s['total_events'] == 0
        assert s['experiments_started'] == 0
        assert s['event_types'] == {}

    def test_summary_from_specific_file(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.log('custom')
        path = audit.file_path

        s = audit.summary(file_path=path)
        assert s['total_events'] == 2


# ---------------------------------------------------------------------------
# Tests — Multiple runs
# ---------------------------------------------------------------------------

class TestMultipleRuns:

    def test_multiple_runs_create_separate_files(self):
        audit, audit_dir = _make_audit()

        audit.start_run(run_id=1, ticker='SPY')
        audit.log('event_run1')
        audit.end_run()
        path1 = audit.file_path

        # Small delay to ensure different timestamp
        time.sleep(0.01)

        audit.start_run(run_id=2, ticker='QQQ')
        audit.log('event_run2')
        audit.end_run()
        path2 = audit.file_path

        assert path1 != path2
        assert os.path.exists(path1)
        assert os.path.exists(path2)

        events1 = _read_jsonl(path1)
        events2 = _read_jsonl(path2)
        assert events1[0]['data']['ticker'] == 'SPY'
        assert events2[0]['data']['ticker'] == 'QQQ'

    def test_get_audit_files_after_multiple_runs(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.end_run()
        time.sleep(0.01)
        audit.start_run(run_id=2, ticker='QQQ')
        audit.end_run()

        files = audit.get_audit_files()
        assert len(files) == 2


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_log_with_non_serializable_data(self):
        """datetime objects should be serialized via default=str."""
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.log('test', {'dt': datetime.now(timezone.utc)})
        events = _read_jsonl(audit.file_path)
        assert len(events) == 2  # Should not crash

    def test_large_data_payload(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        big_data = {'params': {f'param_{i}': i for i in range(100)}}
        audit.log('big_event', big_data)
        events = _read_jsonl(audit.file_path)
        assert len(events[-1]['data']['params']) == 100

    def test_experiment_completed_defaults(self):
        audit, _ = _make_audit()
        audit.start_run(run_id=1, ticker='SPY')
        audit.experiment_completed('EMA', {'fast': 5}, train_sharpe=1.0)
        events = _read_jsonl(audit.file_path)
        ev = events[-1]
        assert ev['data']['test_sharpe'] is None
        assert ev['data']['kept'] is False
        assert ev['data']['reason'] == ''
