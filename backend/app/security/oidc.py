"""Generic OIDC provider (Authorization Code + PKCE S256), disabled unless 'oidc' is listed in AUTH_PROVIDERS.

Env: OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET (confidential client), OIDC_REDIRECT_URI (…/api/v1/auth/oidc/callback),
OIDC_SCOPES, OIDC_CLAIM_EMAIL (email), OIDC_CLAIM_NAME (name), OIDC_ALLOWED_ALGS (RS256,ES256), FRONTEND_URL.
Users must already exist (matched by email claim, linked by issuer+sub on first login); roles come from AegisRMF RBAC only.
"""
import base64
import hashlib
import os
import secrets
import time
from functools import lru_cache

import httpx
import jwt

STATE_TTL = 300
_pending: dict[str, dict] = {}  # state → {verifier, nonce, ts}; single-process. Multi-replica: use a shared store (DEPLOYMENT.md).


def cfg() -> dict:
    return {"issuer": os.environ["OIDC_ISSUER"].rstrip("/"), "client_id": os.environ["OIDC_CLIENT_ID"],
            "client_secret": os.environ.get("OIDC_CLIENT_SECRET"), "redirect_uri": os.environ["OIDC_REDIRECT_URI"],
            "scopes": os.environ.get("OIDC_SCOPES", "openid profile email"), "claim_email": os.environ.get("OIDC_CLAIM_EMAIL", "email"),
            "claim_name": os.environ.get("OIDC_CLAIM_NAME", "name"),
            "algs": [a.strip() for a in os.environ.get("OIDC_ALLOWED_ALGS", "RS256,ES256").split(",")]}


@lru_cache(maxsize=1)
def discovery(issuer: str) -> dict:
    m = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10).raise_for_status().json()
    if m["issuer"].rstrip("/") != issuer:
        raise RuntimeError("OIDC issuer mismatch in discovery document")
    return m


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def authorization_url() -> str:
    c = cfg()
    m = discovery(c["issuer"])
    verifier, state, nonce = _b64(secrets.token_bytes(32)), secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["ts"] > STATE_TTL]:
        _pending.pop(k, None)
    _pending[state] = {"verifier": verifier, "nonce": nonce, "ts": now}
    q = httpx.QueryParams({"client_id": c["client_id"], "response_type": "code", "scope": c["scopes"], "redirect_uri": c["redirect_uri"],
                           "state": state, "nonce": nonce, "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
                           "code_challenge_method": "S256"})
    return f"{m['authorization_endpoint']}?{q}"


def complete(code: str, state: str) -> dict:
    """Redeem the code with the PKCE verifier and validate the ID token (signature, iss, aud, exp, nonce). Returns claims."""
    p = _pending.pop(state, None)
    if p is None or time.time() - p["ts"] > STATE_TTL:
        raise ValueError("invalid_or_expired_state")
    c = cfg()
    m = discovery(c["issuer"])
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": c["redirect_uri"], "client_id": c["client_id"],
            "code_verifier": p["verifier"]}
    auth = (c["client_id"], c["client_secret"]) if c["client_secret"] else None
    tok = httpx.post(m["token_endpoint"], data=data, auth=auth, timeout=10).raise_for_status().json()
    key = jwt.PyJWKClient(m["jwks_uri"]).get_signing_key_from_jwt(tok["id_token"]).key
    claims = jwt.decode(tok["id_token"], key, algorithms=c["algs"], issuer=c["issuer"], audience=c["client_id"],
                        options={"require": ["exp", "iat", "iss", "sub", "aud"]})
    if claims.get("nonce") != p["nonce"]:
        raise ValueError("invalid_nonce")
    return {"subject": f"{c['issuer']}|{claims['sub']}", "email": (claims.get(c["claim_email"]) or "").lower(),
            "name": claims.get(c["claim_name"])}


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
