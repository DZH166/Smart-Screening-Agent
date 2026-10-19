"""Acceptance must not mistake a resource handoff queue for completion."""
from tools.acceptance_client import Client


def test_acceptance_waits_through_queue_handoffs(monkeypatch):
    client = Client.__new__(Client)
    states = iter({'status': state, 'progress': {'message': 'synthetic'}}
                  for state in ('matching', 'queued', 'ai_review', 'ready'))
    client.request = lambda *args: next(states)
    monkeypatch.setattr('tools.acceptance_client.time.sleep', lambda duration: None)
    assert client.wait('synthetic', timeout=5)['status'] == 'ready'
