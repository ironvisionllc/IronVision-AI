"""Web hardening middleware: security headers, in-process rate limiting for auth/upload endpoints, Prometheus metrics."""
import os
import time
from collections import defaultdict, deque

from prometheus_client import Counter, Gauge, Histogram
from starlette.requests import Request
from starlette.responses import JSONResponse

REQ_LATENCY = Histogram("aegis_http_request_duration_seconds", "HTTP request latency", ["method", "route", "status"])
JOB_DURATION = Histogram("aegis_job_duration_seconds", "Worker job duration", ["job_type", "status"])
JOB_FAILURES = Counter("aegis_job_failures_total", "Worker job failures", ["job_type"])
INGEST_RUNS = Counter("aegis_ingest_runs_total", "Ingest runs processed", ["format", "status"])
EMASS_QUEUE = Gauge("aegis_emass_queue_depth", "Open outbound eMASS changes", ["status"])
RATE_LIMITED = Counter("aegis_rate_limited_total", "Requests rejected by rate limiting", ["bucket"])

CSP = os.environ.get("CONTENT_SECURITY_POLICY", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; frame-ancestors 'none'")


def security_headers(request: Request, response) -> None:
    h = response.headers
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    h.setdefault("Cache-Control", "no-store")
    h.setdefault("Content-Security-Policy", DOCS_CSP if request.url.path.startswith(("/api/docs", "/api/redoc")) else CSP)
    tls = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    if tls and os.environ.get("HSTS_ENABLED", "true").lower() == "true":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")


# path-prefix → (requests, window seconds). Per client IP; per-process (use a shared store such as Redis behind
# multiple replicas – documented in DEPLOYMENT.md). Configure with RATE_LIMIT_AUTH / RATE_LIMIT_UPLOAD = "N/seconds".
def _rule(env: str, default: str) -> tuple[int, int]:
    n, w = os.environ.get(env, default).split("/")
    return int(n), int(w)


RULES = {"auth": _rule("RATE_LIMIT_AUTH", "20/60"), "upload": _rule("RATE_LIMIT_UPLOAD", "30/60")}
PRIVATE = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,127.0.0.0/8,169.254.0.0/16,::1/128,fc00::/7"


def _trusted() -> list:
    import ipaddress

    raw = os.environ.get("TRUSTED_PROXIES", "").strip()
    if not raw and os.environ.get("TRUST_PROXY_HEADERS") == "true":
        raw = PRIVATE  # legacy flag: trust private-network proxies (edge nginx / ingress) only
    nets = []
    for x in raw.split(","):
        x = x.strip()
        if x:
            try:
                nets.append(ipaddress.ip_network(x, strict=False))
            except ValueError:
                nets.append(x)  # exact host name (e.g. a proxy hostname)
    return nets


def _is_trusted(ip: str, nets: list) -> bool:
    import ipaddress

    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return ip in [n for n in nets if isinstance(n, str)]
    return any(not isinstance(n, str) and a.version == n.version and a in n for n in nets)


def client_ip(request: Request) -> str:
    """Real client IP: X-Forwarded-For is honoured only when the immediate peer is a TRUSTED_PROXIES address; the chain is walked
    right-to-left skipping trusted hops. Otherwise the peer address is used. Shared by login, sign-up, upload and API limiters."""
    peer = request.client.host if request.client else "?"
    nets = _trusted()
    if not nets or not _is_trusted(peer, nets):
        return peer
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    for h in reversed(hops):
        if not _is_trusted(h, nets):
            return h
    return hops[0] if hops else peer
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def _bucket(request: Request) -> str | None:
    p, m = request.url.path, request.method
    if p.startswith("/api/v1/auth/") and m == "POST":
        return "auth"
    if m == "POST" and (p.endswith("/uploads") or p.endswith("/evidence") or p == "/api/v1/policies"):
        return "upload"
    return None


def rate_limited(request: Request) -> JSONResponse | None:
    b = _bucket(request)
    if b is None or os.environ.get("RATE_LIMIT_ENABLED", "true").lower() != "true":
        return None
    limit, window = RULES[b]
    key = (b, client_ip(request))
    q, t = _hits[key], time.monotonic()
    while q and q[0] <= t - window:
        q.popleft()
    if len(q) >= limit:
        RATE_LIMITED.labels(b).inc()
        return JSONResponse({"detail": f"Rate limit exceeded ({limit} requests per {window}s). Retry later."}, status_code=429,
                            headers={"Retry-After": str(window)})
    q.append(t)
    return None


def reset_rate_limits() -> None:
    _hits.clear()
