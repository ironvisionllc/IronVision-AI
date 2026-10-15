#!/usr/bin/env python3
"""Browser-less end-to-end SSO probe (no browser, no secrets printed). Runs in the pod against the live test Keycloak and on the
Droplet against the rehearsal backend or the live site.

  E2E_PASSWORD=… python3 scripts/e2e_sso.py --base https://demo.ironvisionai.com --user e2e-probe [--json]
      [--restricted /api/v1/admin/identity-mappings] [--demo] [--register] [--insecure-cookies]

Steps: /oidc/login → Keycloak form → credentials → callback → one-time code exchange → /auth/me → protected 200 →
restricted 403 → logout → token rejected + Keycloak session ended; wrong password rejected; optional demo launcher + role
switch; optional self-registration (clean workspace), duplicate e-mail (ao@aegisrmf.demo) and reserved names refused.
Exit 1 when any step fails.
"""
import argparse
import html
import json
import os
import re
import secrets
import sys
from urllib.parse import parse_qs, urlparse

import httpx

R: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    R.append((name, bool(ok), detail[:160]))
    return bool(ok)


def form(page: str):
    m = re.search(r"<form[^>]*\baction=\"([^\"]+)\"", page)
    if not m:
        return None
    hidden = dict(re.findall(r"<input[^>]*type=\"hidden\"[^>]*name=\"([^\"]+)\"[^>]*value=\"([^\"]*)\"", page))
    return html.unescape(m.group(1)), {k: html.unescape(v) for k, v in hidden.items()}


def browser(insecure: bool) -> httpx.Client:
    b = httpx.Client(timeout=20)
    if insecure:  # plain-http test Keycloak marks cookies Secure
        b.event_hooks["response"] = [lambda _r: [setattr(c, "secure", False) for c in b.cookies.jar]]
    return b


def drive(app: httpx.Client, b: httpx.Client, start: str, fields: dict) -> httpx.Response:
    """Follow app → Keycloak → app; fill username/password/registration forms with `fields`. Returns the last response."""
    r = b.get(app.get(start, follow_redirects=False).headers["location"])
    base = str(app.base_url).rstrip("/")
    for _ in range(8):
        if r.status_code in (302, 303):
            loc = r.headers["location"]
            if loc.startswith(base):
                return app.get(loc[len(base):], follow_redirects=False)
            r = b.get(loc)
            continue
        f = form(r.text)
        if f is None:
            return r
        action, data = f
        want = {k: v for k, v in fields.items() if f'name="{k}"' in r.text}
        if not want:
            return r
        r = b.post(action, data={**data, **want, "credentialId": ""})
        if r.status_code == 200 and all(f'name="{k}"' in r.text for k in want):
            return r  # Keycloak re-rendered the same form: rejected
    return r


def exchange(app: httpx.Client, cb: httpx.Response) -> dict | None:
    loc = cb.headers.get("location", "")
    if "oidc_code=" not in loc:
        return None
    r = app.post("/api/v1/auth/oidc/exchange", json={"code": parse_qs(urlparse(loc).query)["oidc_code"][0]})
    return r.json() if r.status_code == 200 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--user", default=os.environ.get("E2E_USER", "e2e-probe"))
    ap.add_argument("--protected", default="/api/v1/systems")
    ap.add_argument("--restricted", default="/api/v1/admin/identity-mappings")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--insecure-cookies", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    pw = os.environ.get("E2E_PASSWORD", "")
    app = httpx.Client(base_url=a.base.rstrip("/"), timeout=20)
    prov = app.get("/api/v1/auth/provider").json()
    check("provider: oidc enabled", prov.get("oidc_enabled"), json.dumps({k: prov.get(k) for k in ("oidc_enabled", "demo_login_enabled", "registration_enabled")}))
    if a.register and prov.get("registration_enabled"):
        n = secrets.token_hex(4)
        reg = {"password": f"E2e-Reg-{n}-Pass!", "password-confirm": f"E2e-Reg-{n}-Pass!", "firstName": "E2E", "lastName": "Probe"}
        t = exchange(app, drive(app, browser(a.insecure_cookies), "/api/v1/auth/oidc/register", {**reg, "username": f"e2e-reg-{n}", "email": f"e2e-reg-{n}@example.org"}))
        if not pw:  # no supplied probe user: the fresh registrant becomes the probe for the password login steps
            a.user, pw = f"e2e-reg-{n}", reg["password"]
        if check("self-registration → clean workspace", t and t["user"]["is_sandbox"], ""):
            h = {"Authorization": f"Bearer {t['access_token']}"}
            check("clean workspace has zero systems", app.get("/api/v1/systems", headers=h).json() == [])
        for label, email in (("duplicate e-mail ao@aegisrmf.demo refused", "ao@aegisrmf.demo"), ("reserved demo@ironvision.ai refused", "demo@ironvision.ai")):
            r = drive(app, browser(a.insecure_cookies), "/api/v1/auth/oidc/register", {**reg, "username": f"e2e-dup-{secrets.token_hex(3)}", "email": email})
            check(label, "oidc_code=" not in r.headers.get("location", ""), r.headers.get("location", str(r.status_code))[-60:])
    if pw:
        bad = drive(app, browser(a.insecure_cookies), "/api/v1/auth/oidc/login", {"username": a.user, "password": pw + "-wrong"})
        check("wrong password rejected by Keycloak", "oidc_code=" not in bad.headers.get("location", ""), str(bad.status_code))
        tok = exchange(app, drive(app, browser(a.insecure_cookies), "/api/v1/auth/oidc/login", {"username": a.user, "password": pw}))
        if check("login → callback → one-time code exchange", tok, ""):
            h = {"Authorization": f"Bearer {tok['access_token']}"}
            me = app.get("/api/v1/auth/me", headers=h)
            check("/auth/me", me.status_code == 200, me.json().get("email", "") if me.status_code == 200 else str(me.status_code))
            check(f"protected {a.protected} → 200", app.get(a.protected, headers=h).status_code == 200)
            check(f"restricted {a.restricted} → 403", app.get(a.restricted, headers=h).status_code == 403)
            out = app.post("/api/v1/auth/logout", headers=h).json()
            check("logout: app token rejected", app.get("/api/v1/auth/me", headers=h).status_code == 401)
            es = out.get("end_session_url")
            if check("logout returns Keycloak end-session URL", es, ""):
                r = httpx.get(es, follow_redirects=False, timeout=20)
                check("Keycloak end-session accepted", r.status_code in (200, 302, 303), str(r.status_code))
    if a.demo and prov.get("demo_login_enabled"):
        d = app.post("/api/v1/auth/demo-login")
        ok = check("demo launcher login", d.status_code == 200, str(d.status_code))
        if ok:
            h = {"Authorization": f"Bearer {d.json()['access_token']}"}
            s = app.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=h)
            check("role switch → ISSM", s.status_code == 200 and s.json()["user"]["persona_role"] == "issm", str(s.status_code))
    if a.json:
        print(json.dumps([{"step": n, "pass": ok, "detail": d} for n, ok, d in R], indent=1))
    else:
        for n, ok, d in R:
            print(f"{'PASS' if ok else 'FAIL'}  {n}  {d}")
    return 0 if all(ok for _, ok, _ in R) else 1


if __name__ == "__main__":
    sys.exit(main())
