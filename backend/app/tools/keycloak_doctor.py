"""Explore-the-demo / self-registration diagnosis for the built-in Keycloak. Read-only except one launcher token probe (its
Keycloak session is ended immediately). Never prints secrets – only whether they are set.

python -m app.tools.keycloak_doctor      (scripts/keycloak.sh [ENV_FILE] doctor; deploy.sh prints it in the summary)
Exit 1 when any check FAILs; every failing line names the exact fix command.
"""
import json
import os
import sys

import httpx

R: list[tuple[str, str, str, str]] = []


def _true(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def add(status: str, item: str, detail: str = "", fix: str = "") -> None:
    R.append((status, item, detail, fix if status != "OK" else ""))


def env_checks(envf: str) -> dict:
    e = os.environ.get
    prov = [p.strip() for p in (e("AUTH_PROVIDERS") or "").split(",") if p.strip()]
    add("OK" if "oidc" in prov else "FAIL", "AUTH_PROVIDERS", ",".join(prov) or "(empty)", f"set AUTH_PROVIDERS=oidc in {envf}, then ./deploy.sh")
    kind = (e("DEPLOYMENT_KIND") or "").lower()
    add("OK" if kind == "demo" else "WARN", "DEPLOYMENT_KIND", kind or "(empty)", f"set DEPLOYMENT_KIND=demo in {envf} (demo deployments only)")
    demo = _true(e("ALLOW_DEMO_LOGIN"))
    add("OK" if demo else "WARN", "ALLOW_DEMO_LOGIN", str(demo).lower(), f"set ALLOW_DEMO_LOGIN=true in {envf} (DEPLOYMENT_KIND=demo), then ./deploy.sh")
    keys = ("KEYCLOAK_DEMO_USERNAME", "KEYCLOAK_DEMO_PASSWORD", "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET")
    missing = [k for k in keys if not e(k)]
    add("OK" if not missing else ("FAIL" if demo else "WARN"), "KEYCLOAK_DEMO_* env", "all set" if not missing else "empty: " + ", ".join(missing),
        "./deploy.sh  (gen_env_secrets fills empty values in place, with a backup)")
    reg = _true(e("KEYCLOAK_ALLOW_REGISTRATION"))
    add("OK", "KEYCLOAK_ALLOW_REGISTRATION", str(reg).lower())
    if reg:
        add("OK" if e("KEYCLOAK_BACKEND_CLIENT_SECRET") else "FAIL", "KEYCLOAK_BACKEND_CLIENT_SECRET", "set" if e("KEYCLOAK_BACKEND_CLIENT_SECRET") else "empty",
            "./deploy.sh  (gen_env_secrets)")
    return {"demo": demo, "reg": reg, "launcher_env": not missing}


def keycloak_checks(f: dict) -> dict:
    from app.services.keycloak_admin import KeycloakAdmin
    from app.tools import keycloak_config as kcfg

    out: dict = {}
    realm = kcfg.realm_name()
    try:
        kc = KeycloakAdmin().login()
    except Exception as exc:  # noqa: BLE001
        add("FAIL", "Keycloak admin API", str(exc)[:140], "docker compose … ps keycloak; then scripts/keycloak.sh plan")
        return out
    r = kc.realm(realm)
    add("OK" if r else "FAIL", f"realm {realm}", "present" if r else "ABSENT", "./deploy.sh --apply-realm")
    if not r:
        return out
    cid = os.environ.get("KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID") or "ironvision-demo-launcher"
    c = kc.client(realm, cid)
    ok = bool(c and c.get("directAccessGrantsEnabled") and (c.get("authenticationFlowBindingOverrides") or {}).get("direct_grant"))
    add("OK" if ok else ("FAIL" if f["demo"] else "WARN"), f"launcher client {cid}", "present, direct grant, restricted flow" if ok else ("missing" if not c else "misconfigured"),
        "./deploy.sh --apply-realm  (needs KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET)")
    handle = (os.environ.get("KEYCLOAK_DEMO_USERNAME") or "").lower()
    rows = kc.users_by(realm, username=handle) if handle else []
    u = rows[0] if rows else None
    ok = bool(u and u.get("enabled") and (u.get("attributes") or {}).get(kcfg.DEMO_ATTR) == ["true"])
    add("OK" if ok else ("FAIL" if f["demo"] else "WARN"), "demo launcher Keycloak user",
        "present, enabled, demo_launcher=true" if ok else ("missing" if not u else "disabled or attribute missing"), "./deploy.sh --apply-realm")
    out["kc_demo_id"] = u["id"] if u else None
    add("OK" if bool(r.get("registrationAllowed")) == f["reg"] else "FAIL", "realm registrationAllowed",
        str(bool(r.get("registrationAllowed"))).lower() + f" (env {str(f['reg']).lower()})", "./deploy.sh --apply-realm")
    if f["reg"]:
        bc = kc.client(realm, os.environ.get("KEYCLOAK_BACKEND_CLIENT_ID") or "ironvision-backend")
        add("OK" if bc else "FAIL", "backend service-account client", "present" if bc else "missing", "./deploy.sh --apply-realm")
        ev = r
        ok = bool(ev.get("eventsEnabled") and "REGISTER" in (ev.get("enabledEventTypes") or []))
        add("OK" if ok else "FAIL", "REGISTER events recorded", str(ok).lower(), "./deploy.sh --apply-realm")
    return out


def app_checks(f: dict, kco: dict, envf: str) -> None:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Organization, User
    from app.services import identity_map
    from app.services.sandbox import DEMO_EMAIL

    try:
        with SessionLocal() as db:
            u = db.scalar(select(User).where(User.email == DEMO_EMAIL))
            org = db.get(Organization, u.org_id) if u else None
            ok = bool(u and u.is_active and org and org.sandbox_status == "ready")
            add("OK" if ok else ("FAIL" if f["demo"] else "WARN"), f"demo app user {DEMO_EMAIL}",
                "active, sandbox ready" if ok else ("missing" if not u else f"active={u.is_active} sandbox={getattr(org, 'sandbox_status', None)}"),
                "./deploy.sh  (the migrate step seeds the demo sandbox when DEPLOYMENT_KIND=demo + ALLOW_DEMO_LOGIN=true + oidc)")
            issuer = (os.environ.get("OIDC_ISSUER") or "").rstrip("/")
            ident = identity_map.identity_for(db, u.id, issuer) if u and issuer else None
            mapped = ident.subject.rsplit("|", 1)[-1] if ident else None
            ok = bool(mapped and mapped == kco.get("kc_demo_id"))
            add("OK" if ok else ("FAIL" if f["demo"] else "WARN"), "demo identity mapping",
                "mapped to the launcher user" if ok else ("missing" if not mapped else "mapped to a DIFFERENT Keycloak user"),
                f"scripts/keycloak.sh {envf} migrate   (dry run → note plan hash), then: scripts/keycloak.sh {envf} migrate --apply --link --plan-hash <HASH>")
    except Exception as exc:  # noqa: BLE001
        add("FAIL", "app database", str(exc)[:140], "check DATABASE_URL / postgres health")


def launcher_probe(f: dict) -> None:
    if not (f["demo"] and f["launcher_env"]):
        return
    from app.security import demo_launcher
    try:
        c = demo_launcher.login()
        add("OK", "launcher token grant", "ok, Keycloak session ended" if c.get("keycloak_session_ended") else "ok")
    except Exception as exc:  # noqa: BLE001
        add("FAIL", "launcher token grant", str(exc)[:140], "./deploy.sh --apply-realm  (re-syncs launcher secret + demo user password from env)")


def providers_check(f: dict) -> None:
    url = (os.environ.get("BACKEND_INTERNAL_URL") or "http://backend:8001").rstrip("/") + "/api/v1/auth/provider"
    try:
        p = httpx.get(url, timeout=10).json()
    except Exception as exc:  # noqa: BLE001
        add("WARN", "/auth/provider", f"backend not reachable ({str(exc)[:80]})", "docker compose … logs backend")
        return
    keys = {k: p.get(k) for k in ("provider", "enabled_providers", "oidc_enabled", "demo_login_enabled", "registration_enabled", "dev_password_enabled")}
    bad = (f["demo"] and not p.get("demo_login_enabled")) or (f["reg"] and not p.get("registration_enabled"))
    add("FAIL" if bad else "OK", "/auth/provider", json.dumps(keys), "restart the backend with the fixed env: ./deploy.sh")


def main(argv: list[str] | None = None) -> int:
    R.clear()
    envf = os.environ.get("DOCTOR_ENV_FILE") or "deploy/digitalocean/.env.production"
    f = env_checks(envf)
    kco = keycloak_checks(f)
    app_checks(f, kco, envf)
    launcher_probe(f)
    providers_check(f)
    print("[keycloak-doctor] Explore-the-demo / registration diagnosis (no secrets printed)")
    for status, item, detail, fix in R:
        print(f"  {status:<4} {item}: {detail}")
        if fix:
            print(f"       FIX: {fix}")
    fails = sum(1 for s in R if s[0] == "FAIL")
    print(f"[keycloak-doctor] {fails} failing check(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
