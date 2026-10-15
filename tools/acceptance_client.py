"""HTTP client for an isolated, already running desktop acceptance instance."""
import json
import re
import time
import urllib.request


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        html = urllib.request.urlopen(self.base, timeout=10).read().decode()
        self.token = json.loads(re.search(r'window.HSD_TOKEN\s*=\s*("[^"]+")', html).group(1))

    def request(self, path, payload=None):
        headers, body = {}, None
        if payload is not None:
            headers = {"Content-Type": "application/json", "X-HSD-Token": self.token}
            body = json.dumps(payload).encode()
        request = urllib.request.Request(self.base + path, data=body, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def wait(self, identifier, timeout=600):
        deadline = time.monotonic() + timeout
        previous = None
        while time.monotonic() < deadline:
            job = self.request("/api/jobs/" + identifier)
            if job["status"] != previous:
                print(job["status"], job["progress"]["message"], flush=True)
                previous = job["status"]
            if job["status"] not in {"importing", "matching", "ai_review", "exporting"}:
                assert job["status"] != "error", job.get("error")
                return job
            time.sleep(.5)
        raise TimeoutError("Desktop acceptance task did not finish")
