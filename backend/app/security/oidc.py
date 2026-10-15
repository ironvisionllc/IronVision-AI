"""Generic OIDC provider (Authorization Code + PKCE S256), disabled unless 'oidc' is listed in AUTH_PROVIDERS.

Env: OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET (confidential client), OIDC_REDIRECT_URI (…/api/v1/auth/oidc/callback),
OIDC_POST_LOGOUT_REDIRECT_URI, OIDC_SCOPES, OIDC_CLAIM_EMAIL (email), OIDC_CLAIM_NAME (name), OIDC_ALLOWED_ALGS (RS256,ES256).
Login succeeds only for an explicit auth_identities mapping (issuer|sub → user); roles come from IronVision RBAC only.
State/nonce/verifier live in the oidc_pending table (single-use, TTL) so restarts and replicas are safe.
"""
import base64
import hashlib
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import OidcPending

STATE_TTL = 300
DISCOVERY_TTL = 3600
_discovery: dict[str, tuple[float, dict]] = {}
_jwks: dict[str, "jwt.PyJWKClient"] = {}


def scopes(raw: str | None) -> str:
    """Space- or comma-separated, stray quotes stripped; always includes openid."""
    parts = [p for p in (raw or "").strip().strip("\"'").replace(",", " ").split() if p.strip("\"'")]
    parts = [p.strip("\"'") for p in parts] or ["openid", "profile", "email"]
    return " ".join(parts if "openid" in parts else ["openid", *parts])


def cfg() -> dict:
    return {"issuer": os.environ["OIDC_ISSUER"].rstrip("/"), "client_id": os.environ["OIDC_CLIENT_ID"],
            "client_secret": os.environ.get("OIDC_CLIENT_SECRET"), "redirect_uri": os.environ["OIDC_REDIRECT_URI"],
            "post_logout_redirect_uri": os.environ.get("OIDC_POST_LOGOUT_REDIRECT_URI") or f"{os.environ.get('FRONTEND_URL', '')}/login",
            "scopes": scopes(os.environ.get("OIDC_SCOPES")), "claim_email": os.environ.get("OIDC_CLAIM_EMAIL", "email"),
            "claim_name": os.environ.get("OIDC_CLAIM_NAME", "name"),
            "algs": [a.strip() for a in os.environ.get("OIDC_ALLOWED_ALGS", "RS256,ES256").split(",")]}


def discovery(issuer: str) -> dict:
    hit = _discovery.get(issuer)
    if hit and time.time() - hit[0] < DISCOVERY_TTL:
        return hit[1]
    m = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10).raise_for_status().json()
    if m["issuer"].rstrip("/") != issuer:
        raise RuntimeError("OIDC issuer mismatch in discovery document")
    _discovery[issuer] = (time.time(), m)
    return m


def _jwk_client(uri: str):
    # PyJWKClient caches the key set (lifespan) and refetches once when a token's kid is unknown (key rotation).
    c = _jwks.get(uri)
    if c is None or not isinstance(c, jwt.PyJWKClient):
        c = _jwks[uri] = jwt.PyJWKClient(uri, cache_jwk_set=True, lifespan=DISCOVERY_TTL)
    return c


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def authorization_url(db: Session, login_hint: str | None = None) -> str:
    c = cfg()
    m = discovery(c["issuer"])
    verifier, state, nonce = _b64(secrets.token_bytes(32)), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.execute(delete(OidcPending).where(OidcPending.expires_at < _now()))
    db.add(OidcPending(state=state, verifier=verifier, nonce=nonce, expires_at=_now() + timedelta(seconds=STATE_TTL)))
    db.commit()
    params = {"client_id": c["client_id"], "response_type": "code", "scope": c["scopes"], "redirect_uri": c["redirect_uri"],
              "state": state, "nonce": nonce, "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
              "code_challenge_method": "S256"}
    if login_hint:
        params["login_hint"] = login_hint
    return f"{m['authorization_endpoint']}?{httpx.QueryParams(params)}"


def _take_state(db: Session, state: str) -> OidcPending | None:
    """Atomic single-use: DELETE … RETURNING, so a replayed state never matches twice (even across replicas)."""
    row = db.execute(delete(OidcPending).where(OidcPending.state == state).returning(OidcPending.verifier, OidcPending.nonce,
                                                                                     OidcPending.expires_at)).first()
    db.commit()
    return row if row and row.expires_at > _now() else None


def complete(db: Session, code: str, state: str) -> dict:
    """Redeem the code with the PKCE verifier and validate the ID token (signature, iss, aud, exp, nonce). Returns claims."""
    p = _take_state(db, state)
    if p is None:
        raise ValueError("invalid_or_expired_state")
    c = cfg()
    m = discovery(c["issuer"])
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": c["redirect_uri"], "client_id": c["client_id"],
            "code_verifier": p.verifier}
    auth = (c["client_id"], c["client_secret"]) if c["client_secret"] else None
    tok = httpx.post(m["token_endpoint"], data=data, auth=auth, timeout=10).raise_for_status().json()
    key = _jwk_client(m["jwks_uri"]).get_signing_key_from_jwt(tok["id_token"]).key
    claims = jwt.decode(tok["id_token"], key, algorithms=c["algs"], issuer=c["issuer"], audience=c["client_id"],
                        options={"require": ["exp", "iat", "iss", "sub", "aud"]})
    if not secrets.compare_digest(str(claims.get("nonce", "")), p.nonce):
        raise ValueError("invalid_nonce")
    return {"subject": f"{c['issuer']}|{claims['sub']}", "sub": claims["sub"], "email": (claims.get(c["claim_email"]) or "").lower(),
            "name": claims.get(c["claim_name"]), "id_token": tok["id_token"]}


def end_session_url(id_token_hint: str | None) -> str | None:
    """RP-initiated logout URL (ends the IdP SSO session); None when the IdP does not advertise end_session_endpoint."""
    c = cfg()
    ep = discovery(c["issuer"]).get("end_session_endpoint")
    if not ep:
        return None
    q = {"client_id": c["client_id"], "post_logout_redirect_uri": c["post_logout_redirect_uri"]}
    if id_token_hint:
        q["id_token_hint"] = id_token_hint
    return f"{ep}?{httpx.QueryParams(q)}"


def mtls_principal(headers, client_host: str | None) -> dict:
    """CAC/PIV via a TLS-terminating reverse proxy that verified the client certificate and OVERWRITES these headers.
    Accepted only from MTLS_TRUSTED_PROXIES (comma list of IPs). Env: MTLS_HEADER_DN, MTLS_HEADER_EDIPI, MTLS_HEADER_VERIFY."""
    trusted = {x.strip() for x in os.environ.get("MTLS_TRUSTED_PROXIES", "").split(",") if x.strip()}
    if not trusted or client_host not in trusted:
        raise ValueError("untrusted_proxy")
    if headers.get(os.environ.get("MTLS_HEADER_VERIFY", "x-ssl-client-verify"), "") != "SUCCESS":
        raise ValueError("client_cert_not_verified")
    dn = headers.get(os.environ.get("MTLS_HEADER_DN", "x-ssl-client-s-dn"))
    edipi = headers.get(os.environ.get("MTLS_HEADER_EDIPI", "x-client-edipi"))
    if not dn or not edipi or not edipi.isdigit():
        raise ValueError("missing_identity_headers")
    return {"subject": f"edipi:{edipi}", "dn": dn}
