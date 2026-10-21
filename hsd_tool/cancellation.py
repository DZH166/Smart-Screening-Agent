"""Cooperative task cancellation; never interrupts an atomic commit or invents usage."""
from contextlib import contextmanager
from contextvars import ContextVar


class TaskCancelled(Exception):
    pass


_check = ContextVar('hsd_cancel_check', default=None)


def check():
    callback = _check.get()
    if callback is not None:
        callback()


def current_check():
    return _check.get()


@contextmanager
def scope(callback):
    token = _check.set(callback)
    try:
        yield
    finally:
        _check.reset(token)
