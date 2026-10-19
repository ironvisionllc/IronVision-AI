#!/usr/bin/env python3
"""Post-deploy demo smoke test (stdlib only). Creates NO users: the Keycloak registration form is only fetched, never submitted.
Usage: python3 scripts/demo_smoke.py https://demo.ironvisionai.com   → exit 0 all PASS · 1 any FAIL
Checks: /health + /ready, provider flags (registration + Explore Demo on), /oidc/register redirects to the Keycloak
registration form, Explore Demo login, ISSM role switch (then back to the starting persona)."""
import json
import sys
import urllib.error
import urllib.request

RESULTS: list[tuple[str, bool, str]] = []


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def call(url: str, method: str = "GET", body: dict | None = None, token: str | None = None, follow: bool = True):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode(errors="replace")


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'} {name}{' – ' + detail if detail else ''}")
    return ok


def main(argv: list[str]) -> int:
    base = argv[0].rstrip("/")
    api = f"{base}/api/v1"
    for p in ("health", "ready"):
        s, _, _ = call(f"{api}/{p}")
        check(f"/api/v1/{p}", s == 200, f"HTTP {s}")
    s, _, b = call(f"{api}/auth/provider")
    prov = json.loads(b) if s == 200 else {}
    check("provider: registration_enabled", prov.get("registration_enabled") is True, f"{prov.get('registration_enabled')!r}")
    check("provider: demo_login_enabled", prov.get("demo_login_enabled") is True, f"{prov.get('demo_login_enabled')!r}")
    check("provider: signup_enabled is false (sign-up is Keycloak registration)", prov.get("signup_enabled") is False,
          f"{prov.get('signup_enabled')!r}")

    s, h, _ = call(f"{api}/auth/oidc/register", follow=False)
    loc = h.get("Location") or h.get("location") or ""
    if check("/auth/oidc/register → Keycloak registrations endpoint", s in (302, 303, 307) and "/protocol/openid-connect/registrations" in loc,
             f"HTTP {s}"):
        s2, _, page = call(loc)
        check("Keycloak registration form reachable (not submitted – no user created)", s2 == 200 and "register" in page.lower(), f"HTTP {s2}")

    s, _, b = call(f"{api}/auth/demo-login", "POST")
    tok = json.loads(b).get("access_token") if s == 200 else None
    if check("Explore Demo (POST /auth/demo-login)", bool(tok), f"HTTP {s}"):
        start = (json.loads(b).get("user") or {}).get("acting_role") or "isso"
        s, _, b2 = call(f"{api}/sandbox/act-as", "POST", {"role": "issm"}, tok)
        ok = check("role switch → ISSM (POST /sandbox/act-as)", s == 200 and "issm" in b2.lower(), f"HTTP {s}")
        if ok and start != "issm":
            t2 = json.loads(b2).get("access_token")
            s, _, _ = call(f"{api}/sandbox/act-as", "POST", {"role": start}, t2)
            check(f"role switch back → {start.upper()}", s == 200, f"HTTP {s}")
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"demo_smoke: {'PASS' if not failed else 'FAIL'} {len(RESULTS) - len(failed)}/{len(RESULTS)}"
          " – registration verified up to the Keycloak form; no temporary user was created")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
