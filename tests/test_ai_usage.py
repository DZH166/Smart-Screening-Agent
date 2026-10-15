import json
import multiprocessing
import os
from pathlib import Path

import pytest

from hsd_tool.ai_usage import UsageLedger, empty_usage


def _usage(requests=1):
    value = empty_usage()
    value.update(requests=requests, successes=requests, prompt_tokens=13 * requests,
                 completion_tokens=7 * requests, cache_miss_tokens=13 * requests,
                 estimated_usd=.000123 * requests)
    return value


def _concurrent_writer(directory, start, repetitions):
    ledger = UsageLedger(directory)
    start.wait(15)
    for _ in range(repetitions):
        ledger.add(_usage())
    assert not ledger.snapshot()["warning"]


def test_real_independent_process_writers_preserve_every_increment(tmp_path):
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    workers = [context.Process(target=_concurrent_writer, args=(str(tmp_path), start, 25)) for _ in range(4)]
    for worker in workers:
        worker.start()
    start.set()
    try:
        for worker in workers:
            worker.join(25)
        assert all(not worker.is_alive() and worker.exitcode == 0 for worker in workers)
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
    result = UsageLedger(tmp_path).snapshot()
    assert result["requests"] == result["successes"] == 100
    assert result["prompt_tokens"] == result["cache_miss_tokens"] == 1300
    assert result["completion_tokens"] == 700
    assert result["estimated_usd"] == pytest.approx(.0123)
    assert not result["warning"] and not result["cost_incomplete"]
    assert not list(tmp_path.glob(".ai-usage-*.tmp"))


def test_existing_desktop_instance_observes_later_cli_writes(tmp_path):
    desktop = UsageLedger(tmp_path)
    desktop.add(_usage(2))
    cli = UsageLedger(tmp_path)
    cli.add(_usage(3))
    result = desktop.snapshot()
    assert result["requests"] == 5
    desktop.add(_usage(4))
    assert cli.snapshot()["requests"] == 9


def test_failed_save_preserves_pending_usage_when_other_process_adds(tmp_path, monkeypatch):
    desktop = UsageLedger(tmp_path)
    desktop.add(_usage(2))
    real_replace = os.replace
    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk unavailable")))
        desktop.add(_usage(3))
        assert desktop.snapshot()["requests"] == 5
        assert desktop.snapshot()["warning"]
    cli = UsageLedger(tmp_path)
    cli.add(_usage(4))
    assert desktop.snapshot()["requests"] == 9  # 6 persisted + 3 unsaved.
    desktop.add(_usage(1))
    result = UsageLedger(tmp_path).snapshot()
    assert result["requests"] == 10
    assert not desktop.snapshot()["warning"]
    assert os.replace is real_replace


@pytest.mark.parametrize("content", ["not JSON", "{}", "[]", '{"estimated_usd":NaN}',
    json.dumps({**_usage(2), "requests": True}),
    json.dumps({**_usage(2), "estimated_usd": 10 ** 400})],
    ids=["malformed", "missing-counters", "not-object", "nonfinite", "boolean-counter", "overflow-number"])
def test_bad_history_is_explicitly_incomplete_and_keeps_new_known_usage(tmp_path, content):
    path = tmp_path / "ai_usage.json"
    path.write_text(content)
    ledger = UsageLedger(tmp_path)
    initial = ledger.snapshot()
    assert initial["history_incomplete"] and initial["cost_incomplete"]
    assert initial["estimated_usd_upper_bound"] is None
    assert "仅统计本次运行" in initial["warning"]
    ledger.add(_usage(3))
    result = UsageLedger(tmp_path).snapshot()
    assert result["requests"] == 3
    assert result["history_incomplete"] and result["cost_incomplete"]
    assert result["estimated_usd_upper_bound"] is None and result["warning"]


def test_corruption_after_success_does_not_erase_known_historical_count(tmp_path):
    ledger = UsageLedger(tmp_path)
    ledger.add(_usage(7))
    ledger.path.write_text("corrupted JSON")
    assert ledger.snapshot()["requests"] == 7
    ledger.add(_usage(2))
    result = UsageLedger(tmp_path).snapshot()
    assert result["requests"] == 9 and result["history_incomplete"]


def test_removed_or_rolled_back_history_keeps_known_lower_bound(tmp_path):
    ledger = UsageLedger(tmp_path)
    ledger.add(_usage(7))
    ledger.path.unlink()
    assert ledger.snapshot()["requests"] == 7
    assert ledger.snapshot()["history_incomplete"]
    ledger.path.write_text(json.dumps(_usage(2)))
    assert ledger.snapshot()["requests"] == 7
    ledger.add(_usage(3))
    assert UsageLedger(tmp_path).snapshot()["requests"] == 10


def test_unknown_billing_and_known_cost_are_preserved_across_writers(tmp_path):
    first, second = UsageLedger(tmp_path), UsageLedger(tmp_path)
    first.add({"requests": 2, "failures": 2, "unknown_usage_requests": 2, "cost_incomplete": True})
    second.add(_usage(3))
    result = first.snapshot()
    assert result["requests"] == 5 and result["unknown_usage_requests"] == 2
    assert result["estimated_usd"] == pytest.approx(.000369)
    assert result["cost_incomplete"] and result["estimated_usd_upper_bound"] is None
    assert not result["history_incomplete"]


def test_invalid_incoming_counters_do_not_create_fictitious_requests(tmp_path):
    ledger = UsageLedger(tmp_path)
    ledger.add({"requests": True, "successes": -3, "prompt_tokens": "500", "estimated_usd": float("nan")})
    result = ledger.snapshot()
    assert result["requests"] == result["successes"] == result["prompt_tokens"] == result["estimated_usd"] == 0


def test_cost_overflow_keeps_known_amount_and_marks_incomplete(tmp_path):
    ledger = UsageLedger(tmp_path)
    ledger.add({"estimated_usd": 1e308})
    ledger.add({"estimated_usd": 1e308})
    result = UsageLedger(tmp_path).snapshot()
    assert result["estimated_usd"] == 1e308
    assert result["cost_incomplete"] and result["estimated_usd_upper_bound"] is None
    assert result["requests"] == 0
