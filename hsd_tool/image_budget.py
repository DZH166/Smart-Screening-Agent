"""Process-wide admission for decoded pixels, independent of upload byte size.

The estimate covers live RGBA copies, conversion and PNG/thumbnail work. It is
an admission estimate, not a measurement or a hard native-memory limit. Existing
large ribbon operations reserve the whole budget; small material images can run
together. Callers must reserve before state/database locks and release only once
their large image objects are closed, never around model/network waits.
"""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import threading


PIXEL_BUDGET_BYTES = 768 * 1024 * 1024
PIXEL_WORKSPACE_BYTES = 20
IMAGE_OVERHEAD_BYTES = 32 * 1024 * 1024


def image_workspace_bytes(pixels):
    return int(pixels) * PIXEL_WORKSPACE_BYTES + IMAGE_OVERHEAD_BYTES


class PixelBudget:
    def __init__(self, capacity=PIXEL_BUDGET_BYTES):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Image memory budget must be positive")
        self.capacity = capacity
        self._condition = threading.Condition()
        self._waiting = deque()
        self._used = 0
        self._local = threading.local()

    @contextmanager
    def reserve(self, estimated=None, *, check_cancel=None):
        # An existing supported image above the estimate runs alone; this does
        # not invent a new file-size/pixel limit or promise it fits native RAM.
        amount = self.capacity if estimated is None else min(self.capacity, max(1, int(estimated)))
        held = getattr(self._local, "held", 0)
        if held:
            if amount > held:
                # Waiting for an upgrade while holding pixels can deadlock two
                # readers. A caller must reserve its complete workspace first.
                raise RuntimeError("Nested image work must reserve its complete workspace first")
            if check_cancel is not None:
                check_cancel()
            yield
            return
        ticket = object()
        admitted = False
        with self._condition:
            self._waiting.append(ticket)
        try:
            while True:
                # Cancellation may acquire a task lock: never call it under
                # the budget condition or any other application's state lock.
                if check_cancel is not None:
                    check_cancel()
                with self._condition:
                    if self._waiting[0] is ticket and self._used + amount <= self.capacity:
                        self._waiting.popleft()
                        self._used += amount
                        self._local.held = amount
                        admitted = True
                        self._condition.notify_all()
                        break
                    self._condition.wait(.05)
            if check_cancel is not None:
                check_cancel()
            yield
        finally:
            with self._condition:
                if admitted:
                    self._local.held = 0
                    self._used -= amount
                else:
                    self._waiting.remove(ticket)
                self._condition.notify_all()


IMAGE_BUDGET = PixelBudget()
