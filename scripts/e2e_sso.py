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
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

R: list[tuple[str, bool, str]] = []
T: list[str] = []          # full HTTP transcript (redacted) – --transcript FILE
CTX = {"rehearsal": False, "public_hosts": set(), "app_host": "", "contacted": set()}
_RED = [(re.compile(r"(?i)\b(code|state|session_state|nonce|oidc_code|token|access_token|refresh_token|id_token|password|client_secret|"
                    r"credentialId|execution|tab_id|session_code|client_data)=([^&\s\"']+)"), r"\1=***"),
        (re.compile(r"(?i)\"(access_token|refresh_token|id_token|password|client_secret|end_session_url|code)\"\s*:\s*\"[^\"]*\""), r'"\1": "***"'),
        (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1***"),
        (re.compile(r"(?i)(name=\"(?:password|password-confirm)\"[^>]*value=\")[^\"]*"), r"\1***")]
TITLE = re.compile(r"<title>(.*?)</title>", re.S)
PAGE = re.compile(r'id="kc-page-title"[^>]*>(.*?)<', re.S)
FEEDBACK = re.compile(r"(?:kc-feedback-text|input-error[\w-]*|alert-[\w-]+)[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,200})")
FIELDS = re.compile(r'name="([^"]+)"')


def redact(s: str) -> str:
    for p, r in _RED:
        s = p.sub(r, s)
    return s


def check(name: str, ok: bool, detail: str = "") -> bool:
    R.append((name, bool(ok), redact(detail)[:300]))
    T.append(f"STEP {'PASS' if ok else 'FAIL'}: {name} {redact(detail)[:300]}")
    return bool(ok)


def _log(r: httpx.Response) -> None:
    r.read()
    CTX["contacted"].add(r.request.url.netloc.decode())
    body = r.text[:1500] if "json" in r.headers.get("content-type", "") or r.status_code >= 400 else f"<{len(r.content)} bytes {r.headers.get('content-type', '')}>"
    if "html" in r.headers.get("content-type", ""):  # Keycloak page: title, feedback/errors and form fields (no values)
        t = r.text
        body = (f"<html {len(r.content)} bytes> title={TITLE.findall(t)[:1]} page={[x.strip() for x in PAGE.findall(t)[:1]]} "
                f"feedback={[x.strip() for x in FEEDBACK.findall(t)[:3]]} fields={sorted(set(FIELDS.findall(t)))[:15]}")
    T.append(redact(f"{r.request.method} {r.request.url} → {r.status_code}"
                    + (f" location={r.headers['location']}" if "location" in r.headers else "")
                    + (f" set-cookie={[c.split('=', 1)[0] for c in r.headers.get_list('set-cookie')]}" if "set-cookie" in r.headers else "")
                    + f"\n    {body}"))


def client(**kw) -> httpx.Client:
    c = httpx.Client(timeout=20, **kw)
    c.event_hooks["response"] = [_log]
    return c


def form(page: str):
    m = re.search(r"<form[^>]*\baction=\"([^\"]+)\"", page)
    if not m:
        return None
    hidden = dict(re.findall(r"<input[^>]*type=\"hidden\"[^>]*name=\"([^\"]+)\"[^>]*value=\"([^\"]*)\"", page))
    return html.unescape(m.group(1)), {k: html.unescape(v) for k, v in hidden.items()}


def browser(insecure: bool) -> httpx.Client:
    b = client()
    if insecure:  # plain-http test Keycloak marks cookies Secure
        b.event_hooks["response"].append(lambda _r: [setattr(c, "secure", False) for c in b.cookies.jar])
    return b


CALLBACK = "/api/v1/auth/oidc/callback"


def drive(app: httpx.Client, b: httpx.Client, start: str, fields: dict) -> httpx.Response:
    """Follow app → Keycloak → app; fill username/password/registration forms with `fields`. Returns the last response.
    --rehearsal: Keycloak redirects to the PUBLIC callback (the registered redirect URI); it is delivered to the rehearsal
    backend (like a hosts-file override) and never to the production backend."""
    first = app.get(start, follow_redirects=False)
    if "location" not in first.headers:
        check(f"{start} redirects to Keycloak", False, f"{first.status_code} {first.text[:200]}")
        return first
    r = b.get(first.headers["location"])
    base = str(app.base_url).rstrip("/")
    for _ in range(8):
        if r.status_code in (302, 303):
            loc = r.headers["location"]
            if loc.startswith(base):
                return app.get(loc[len(base):], follow_redirects=False)
            u = urlparse(loc)
            if CTX["rehearsal"] and u.path == CALLBACK:
                CTX["public_hosts"].add(u.netloc)
                T.append(f"REHEARSAL: callback for {u.netloc} delivered to the rehearsal backend {base} (production backend NOT contacted)")
                return app.get(f"{u.path}?{u.query}", follow_redirects=False)
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
    ap.add_argument("--rehearsal", action="store_true", help="target is the rehearsal backend: public callbacks go to it, never to production")
    ap.add_argument("--no-wrong-password", action="store_true", help="skip the wrong-password step (live Keycloak: no brute-force counter)")
    ap.add_argument("--transcript", default="")
    ap.add_argument("--forbid-host", action="append", default=[], help="host[:port] that must never be contacted (production)")
    a = ap.parse_args()
    CTX["rehearsal"] = a.rehearsal
    try:
        run(a)
    except Exception as exc:  # noqa: BLE001 – any abort (DNS, TLS, unexpected body) is a FAILED step with the exact error
        check(f"aborted: {type(exc).__name__}", False, str(exc))
    if a.forbid_host:
        def norm(h: str) -> str:
            return h.lower().replace("localhost", "127.0.0.1")
        hit = sorted(c for c in CTX["contacted"] if any(norm(c) == norm(f) or norm(c).split(":")[0] == norm(f) for f in a.forbid_host))
        check("production Keycloak + backend never contacted", not hit, f"forbidden {a.forbid_host}; contacted {sorted(CTX['contacted'])}")
    if a.rehearsal and CTX["public_hosts"]:
        check("rehearsal: production backend never contacted", not (CTX["contacted"] & CTX["public_hosts"]),
              f"public callback host(s) {sorted(CTX['public_hosts'])}; contacted {sorted(CTX['contacted'])}")
    if a.transcript:
        Path(a.transcript).write_text("\n".join(T) + "\n")
        os.chmod(a.transcript, 0o600)
    if a.json:
        print(json.dumps([{"step": n, "pass": ok, "detail": d} for n, ok, d in R], indent=1))
    else:
        for n, ok, d in R:
            print(f"{'PASS' if ok else 'FAIL'}  {n}  {d}")
    return 0 if R and all(ok for _, ok, _ in R) else 1


def run(a) -> None:
    pw = os.environ.get("E2E_PASSWORD", "")
    app = client(base_url=a.base.rstrip("/"))
    p = app.get("/api/v1/auth/provider")
    if not check("provider endpoint", p.status_code == 200, f"{p.status_code}"):
        return
    prov = p.json()
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
    if not pw:
        check("login: probe credentials available", False, "no e2e credentials (rehearsal: scratch_sso setup creates the scratch user)")
    if pw:
        if not a.no_wrong_password:
            bad = drive(app, browser(a.insecure_cookies), "/api/v1/auth/oidc/login", {"username": a.user, "password": pw + "-wrong"})
            rejected = "oidc_code=" not in bad.headers.get("location", "") and bad.request.url.path != CALLBACK
            check("negative: wrong password rejected by Keycloak (expected rejection, NOT a login)", rejected, str(bad.status_code))
        b = browser(a.insecure_cookies)
        cb = drive(app, b, "/api/v1/auth/oidc/login", {"username": a.user, "password": pw})
        check("login: Keycloak accepted credentials → callback (auth code + PKCE)", cb.request.url.path == CALLBACK, f"{cb.request.url.path} {cb.status_code}")
        tok = exchange(app, cb)
        if check("callback → one-time code exchange", tok, cb.headers.get("location", str(cb.status_code))[-120:]):
            h = {"Authorization": f"Bearer {tok['access_token']}"}
            me = app.get("/api/v1/auth/me", headers=h)
            check("authenticated access: /auth/me", me.status_code == 200, me.json().get("email", "") if me.status_code == 200 else str(me.status_code))
            check(f"authenticated access: {a.protected} → 200", app.get(a.protected, headers=h).status_code == 200)
            check(f"authorization denial: {a.restricted} → 403", app.get(a.restricted, headers=h).status_code == 403)
            m2 = app.get("/api/v1/auth/me", headers=h)
            check("session handling: same session valid on a later request", m2.status_code == 200 and m2.json().get("email") == me.json().get("email"), str(m2.status_code))
            out = app.post("/api/v1/auth/logout", headers=h).json()
            check("logout: old app session rejected afterwards", app.get("/api/v1/auth/me", headers=h).status_code == 401)
            es = out.get("end_session_url")
            if check("logout returns Keycloak end-session URL", es, ""):
                r = b.get(es, follow_redirects=False)
                check("Keycloak end-session accepted", r.status_code in (200, 302, 303), str(r.status_code))
                again = b.get(app.get("/api/v1/auth/oidc/login", follow_redirects=False).headers.get("location", ""), follow_redirects=False)
                check("logout: Keycloak session ended (same browser must log in again, no silent SSO)",
                      again.status_code == 200 and form(again.text) is not None and "oidc_code=" not in again.headers.get("location", ""),
                      f"{again.status_code} {again.headers.get('location', '')[:80]}")
    if a.demo:
        if not check("demo login enabled (Explore Demo)", prov.get("demo_login_enabled"), json.dumps(prov.get("demo_login_enabled"))):
            return
        d = app.post("/api/v1/auth/demo-login")
        ok = check("demo login (Explore Demo, Option B launcher)", d.status_code == 200, f"{d.status_code} {d.text[:200] if d.status_code != 200 else ''}")
        if ok:
            h = {"Authorization": f"Bearer {d.json()['access_token']}"}
            s = app.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=h)
            check("role switch → ISSM", s.status_code == 200 and s.json()["user"]["persona_role"] == "issm", str(s.status_code))
            check(f"demo: protected {a.protected} → 200", app.get(a.protected, headers=h).status_code == 200)
            check(f"demo: restricted {a.restricted} → 403", app.get(a.restricted, headers=h).status_code == 403)
            app.post("/api/v1/auth/logout", headers=h)
            check("demo: logout → app token rejected", app.get("/api/v1/auth/me", headers=h).status_code == 401)


if __name__ == "__main__":
    sys.exit(main())
