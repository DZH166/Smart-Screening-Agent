"""Fixed administrator credential for the host-only admin area.

Only a PBKDF2 digest is stored here, never the password itself. Comparison is
constant-time, sessions expire, and repeated failures are throttled per client
address without retaining any submitted text.

The account is a shared internal operator account, not a per-person identity:
it protects the console against casual access and does not replace the existing
host-only and token boundaries.
"""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque

ADMIN_USERNAME = "15159156156"
SALT_HEX = "36cf1394f4f22628ff5cd6685b966836"
DIGEST_HEX = "4ebde9da89e59174c77e8fa074dddb2de43264f7319576fbde3eb0125df2d47e"
ITERATIONS = 240_000

SESSION_KEY = "admin_authenticated"
EXPIRY_KEY = "admin_authenticated_until"
SESSION_SECONDS = 8 * 60 * 60

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 60


def _digest(password: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                               bytes.fromhex(SALT_HEX), ITERATIONS)


def verify_credentials(username, password) -> bool:
    """Constant-time check; no submitted value is logged or stored."""
    if not isinstance(username, str) or not isinstance(password, str):
        return False
    if not 1 <= len(username) <= 128 or not 1 <= len(password) <= 256:
        return False
    try:
        name_ok = hmac.compare_digest(username.encode("utf-8"), ADMIN_USERNAME.encode("utf-8"))
        secret_ok = hmac.compare_digest(_digest(password), bytes.fromhex(DIGEST_HEX))
    except (ValueError, UnicodeError):
        return False
    return name_ok and secret_ok


def grant_session(target, *, now=None) -> None:
    now = time.time() if now is None else now
    target[SESSION_KEY] = True
    target[EXPIRY_KEY] = now + SESSION_SECONDS
    target.permanent = True


def authenticated(target, *, now=None) -> bool:
    now = time.time() if now is None else now
    until = target.get(EXPIRY_KEY)
    return (target.get(SESSION_KEY) is True
            and isinstance(until, (int, float)) and not isinstance(until, bool)
            and until > now)


def revoke_session(target) -> None:
    target.pop(SESSION_KEY, None)
    target.pop(EXPIRY_KEY, None)


class LoginLimiter:
    """Per-address attempt throttle; holds timestamps only, never input."""

    def __init__(self, *, limit=MAX_ATTEMPTS, window=WINDOW_SECONDS, clock=time.monotonic):
        self.limit, self.window, self._clock = limit, window, clock
        self._attempts = defaultdict(deque)
        self._lock = threading.Lock()

    SWEEP_ABOVE = 1024

    def _recent(self, address):
        """Pruned timestamps for one address; the key is dropped when empty.

        Read-only probes (``blocked``) run for every login attempt, so keeping
        an empty deque per source address would let unauthenticated traffic grow
        the table without bound.
        """
        attempts = self._attempts.get(address)
        if attempts is None:
            return deque()
        now = self._clock()
        while attempts and now - attempts[0] >= self.window:
            attempts.popleft()
        if not attempts:
            self._attempts.pop(address, None)
        return attempts

    def _sweep(self, now):
        for key in [key for key, value in self._attempts.items()
                    if not value or now - value[-1] >= self.window]:
            self._attempts.pop(key, None)
        if len(self._attempts) > self.SWEEP_ABOVE:
            # Hard bound: keep the most recent sources, oldest first out. An
            # evicted address simply gets a fresh budget; memory stays bounded.
            for key, _ in sorted(self._attempts.items(), key=lambda item: item[1][-1])[
                    :len(self._attempts) - self.SWEEP_ABOVE]:
                self._attempts.pop(key, None)

    def blocked(self, address) -> bool:
        with self._lock:
            return len(self._recent(address)) >= self.limit

    def fail(self, address) -> bool:
        """Record a failure; return True when this address is now blocked."""
        with self._lock:
            now = self._clock()
            attempts = self._recent(address)
            if not attempts:
                attempts = self._attempts[address] = deque()
            attempts.append(now)
            if len(self._attempts) > self.SWEEP_ABOVE:
                self._sweep(now)
            return len(attempts) >= self.limit

    def reset(self, address) -> None:
        with self._lock:
            self._attempts.pop(address, None)
