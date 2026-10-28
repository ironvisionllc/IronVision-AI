"""Live suites sign in many times; the preview limits auth POSTs to 20/60 s per IP. Retry a 429 after its Retry-After (max 65 s) so the
serial suite measures behaviour, not the rate limiter. Lockout 429s (bad passwords) are not retried."""
import time

import pytest
import requests

_orig = requests.post


def _post(url, *a, **kw):
    for _ in range(3):
        r = _orig(url, *a, **kw)
        if r.status_code != 429 or "/auth/" not in str(url) or "locked" in r.text.lower():
            return r
        time.sleep(min(65, int(r.headers.get("Retry-After") or 30)))
    return r


@pytest.fixture(autouse=True, scope="session")
def _retry_rate_limited_auth():
    requests.post = _post
    yield
    requests.post = _orig
