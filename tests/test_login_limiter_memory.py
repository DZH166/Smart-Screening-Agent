"""Login throttles must not grow with the number of source addresses.

Synthetic addresses and a fake clock only; no network or credentials.
"""
from __future__ import annotations

import pytest

from hsd_tool.admin_auth import LoginLimiter
from hsd_tool.lan import LanAccess


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_probing_the_admin_throttle_does_not_create_entries():
    limiter = LoginLimiter(clock=Clock())
    for index in range(500):
        assert limiter.blocked(f"10.0.{index // 250}.{index % 250}") is False
    assert limiter._attempts == {}


def test_expired_attempts_are_dropped_instead_of_accumulating():
    clock = Clock()
    limiter = LoginLimiter(clock=clock)
    limiter.fail("10.0.0.1")
    limiter.fail("10.0.0.2")
    clock.now += 61
    # A blocked() probe prunes this address and removes the now-empty key.
    assert limiter.blocked("10.0.0.1") is False
    assert "10.0.0.1" not in limiter._attempts
    # A sweep keeps the table bounded even when old addresses never return.
    for index in range(2000):
        limiter.fail(f"192.168.1.{index}")
    assert len(limiter._attempts) <= LoginLimiter.SWEEP_ABOVE + 1


def test_a_blocked_address_stays_blocked_until_the_window_passes():
    clock = Clock()
    limiter = LoginLimiter(clock=clock)
    for _ in range(10):
        limiter.fail("10.0.0.9")
    assert limiter.blocked("10.0.0.9") is True
    clock.now += 61
    assert limiter.blocked("10.0.0.9") is False
    assert "10.0.0.9" not in limiter._attempts


def test_lan_success_and_failures_leave_no_dead_keys(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    lan = LanAccess("192.168.0.160/24", inputs, tmp_path / "outputs", code="synthetic-code")
    assert lan.login("192.168.0.25", "synthetic-code") is True
    assert lan._attempts == {}
    assert lan.login("192.168.0.26", "wrong") is False
    assert list(lan._attempts) == ["192.168.0.26"]
    for index in range(1500):
        lan.login(f"10.1.{index // 250}.{index % 250}", "wrong")
    assert len(lan._attempts) <= 1025
    assert "192.168.0.26" not in lan._attempts
