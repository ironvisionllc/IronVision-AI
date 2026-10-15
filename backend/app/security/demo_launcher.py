"""Explore-the-demo launcher (Option B): server-side password grant on the dedicated Keycloak client `ironvision-demo-launcher`.

Keycloak itself restricts that client to users with attribute demo_launcher=true (client-specific direct-grant flow), and the realm
browser flow denies those users before any password is checked, so visitors can neither use nor lock the demo account.
The returned ID token is validated like a normal OIDC login; the Keycloak session is ended immediately (backchannel logout with
the refresh token) – Keycloak tokens never leave the backend.
Env: KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID, KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET, KEYCLOAK_DEMO_USERNAME, KEYCLOAK_DEMO_PASSWORD, OIDC_ISSUER.
"""
import os

import httpx
import jwt

from app.security import oidc


class DemoLauncherError(RuntimeError):
    pass


def client_id() -> str:
    return os.environ.get("KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID") or "ironvision-demo-launcher"


def username() -> str:
    """Unpublished Keycloak handle of the launcher user (NOT the public demo e-mail): Keycloak counts brute-force failures even for
    users denied on the browser flow, so visitors must not be able to name this account at all."""
    return os.environ["KEYCLOAK_DEMO_USERNAME"].lower()


def configured() -> bool:
    return all(os.environ.get(k) for k in ("OIDC_ISSUER", "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET", "KEYCLOAK_DEMO_PASSWORD",
                                           "KEYCLOAK_DEMO_USERNAME"))


def login() -> dict:
    issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    m = oidc.discovery(issuer)
    auth = (client_id(), os.environ["KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"])
    r = httpx.post(m["token_endpoint"], auth=auth, timeout=10, data={
        "grant_type": "password", "username": username(), "password": os.environ["KEYCLOAK_DEMO_PASSWORD"], "scope": "openid"})
    if r.status_code != 200:
        err = r.json().get("error", "") if r.headers.get("content-type", "").startswith("application/json") else ""
        raise DemoLauncherError(f"keycloak_token_{r.status_code}:{err[:40]}")
    tok = r.json()
    key = oidc._jwk_client(m["jwks_uri"]).get_signing_key_from_jwt(tok["id_token"]).key
    claims = jwt.decode(tok["id_token"], key, algorithms=oidc.cfg()["algs"], issuer=issuer, audience=client_id(),
                        options={"require": ["exp", "iat", "iss", "sub", "aud"]})
    ended = False
    if tok.get("refresh_token") and m.get("end_session_endpoint"):  # no lingering Keycloak session for the shared demo user
        ended = httpx.post(m["end_session_endpoint"], auth=auth, timeout=10, data={"refresh_token": tok["refresh_token"]}).status_code in (200, 204)
    return {"subject": f"{issuer}|{claims['sub']}", "sub": claims["sub"], "email": (claims.get("email") or "").lower(),
            "keycloak_session_ended": ended}
