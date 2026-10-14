"""Environment validation for IronVision AI deployments (used by scripts/check_env.py and the backend start-up guard).
Profiles: development | staging | production. Never prints secret values."""
import base64
import os
from typing import Mapping

DOCUMENTED_DEMO_PASSWORD = "AegisDemo!2026"
PLACEHOLDERS = ("change-me", "changeme", "change_me", "replace-me", "password", "secret", "example", "xxx", "todo")

REQUIRED = [
    "APP_ENV", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
    "JWT_SECRET", "SECRET_STORE_KEY", "CORS_ORIGINS", "FRONTEND_URL", "AUTH_PROVIDERS",
]
REQUIRED_DEPLOYED = ["APP_DOMAIN"]


def _true(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _weak(v: str, min_len: int) -> bool:
    low = v.lower()
    return len(v) < min_len or any(p in low for p in PLACEHOLDERS) or v == DOCUMENTED_DEMO_PASSWORD


def _fernet_ok(k: str) -> bool:
    try:
        return len(base64.urlsafe_b64decode(k.encode())) == 32
    except Exception:
        return False


def providers(env: Mapping[str, str]) -> list[str]:
    return [p.strip() for p in (env.get("AUTH_PROVIDERS") or "dev_password").split(",") if p.strip()]


def insecure_production(env: Mapping[str, str]) -> list[str]:
    """Rules that make production refuse to start unless ALLOW_INSECURE_PRODUCTION=true."""
    if (env.get("APP_ENV") or "development") != "production" or _true(env.get("ALLOW_INSECURE_PRODUCTION")):
        return []
    errs = []
    if "dev_password" in providers(env):
        errs.append("AUTH_PROVIDERS contains dev_password in production")
    if _true(env.get("SEED_DEMO_DATA")):
        errs.append("SEED_DEMO_DATA=true in production")
    return errs


DEPRECATED = {"MINIO_ROOT_USER": "S3_ADMIN_ACCESS_KEY_ID", "MINIO_ROOT_PASSWORD": "S3_ADMIN_SECRET_ACCESS_KEY", "MINIO_IMAGE": "SEAWEEDFS_IMAGE"}


def _internal_host(host: str) -> bool:
    import ipaddress

    if "." not in host or host in ("localhost",) or host.endswith((".internal", ".local", ".svc", ".cluster.local")):
        return True
    try:
        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def storage_checks(env: Mapping[str, str], errors: list[str], warns: list[str]) -> tuple[list[str], list[str]]:
    """Object storage: s3 (SeaweedFS profile, DO Spaces, AWS S3, Garage …) or local. MinIO-named variables are deprecated aliases."""
    from urllib.parse import urlparse

    for old, new in DEPRECATED.items():
        if env.get(old):
            warns.append(f"{old} is deprecated (MinIO was removed) – use {new}; the old name is still read as a fallback")
    profiles = env.get("COMPOSE_PROFILES") or ""
    for prof, key in (("keycloak", "KEYCLOAK_ADMIN_PASSWORD"), ("monitoring", "GRAFANA_ADMIN_PASSWORD")):
        if prof in profiles and not env.get(key):
            errors.append(f"{key} is required when the {prof} profile is enabled")
    driver = env.get("STORAGE_DRIVER") or ""
    seaweed_on = "seaweedfs" in {p.strip() for p in profiles.split(",")}
    endpoint_host = urlparse(env.get("S3_ENDPOINT_URL") or "").hostname
    if driver not in ("s3", "local"):
        errors.append(f"STORAGE_DRIVER must be s3 or local (got {driver!r})" if driver else "STORAGE_DRIVER is required (s3 or local)")
    if driver == "local" and seaweed_on:
        errors.append("STORAGE_DRIVER=local does not use the object store – remove seaweedfs from COMPOSE_PROFILES")
    if driver == "s3" and endpoint_host in (None, "seaweedfs") and not seaweed_on:
        errors.append("COMPOSE_PROFILES=seaweedfs is required when using the built-in object store (STORAGE_DRIVER=s3 with "
                      "S3_ENDPOINT_URL empty) – or set S3_ENDPOINT_URL for external S3, or use STORAGE_DRIVER=local")
    if driver == "s3" and endpoint_host not in (None, "seaweedfs") and seaweed_on:
        errors.append(f"S3_ENDPOINT_URL points to external S3 ({endpoint_host}) – remove seaweedfs from COMPOSE_PROFILES")
    if driver == "s3":
        for k in ("S3_BUCKET", "S3_REGION"):
            if not env.get(k):
                errors.append(f"{k} is required for STORAGE_DRIVER=s3")
        for k in ("S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"):
            if not env.get(k):
                errors.append(f"{k} is required for STORAGE_DRIVER=s3 (application identity – a new key, distinct from any old MinIO root user)")
        if "seaweedfs" in (env.get("COMPOSE_PROFILES") or ""):
            for k, alias in (("S3_ADMIN_ACCESS_KEY_ID", "MINIO_ROOT_USER"), ("S3_ADMIN_SECRET_ACCESS_KEY", "MINIO_ROOT_PASSWORD")):
                if not env.get(k) and not env.get(alias):
                    errors.append(f"{k} is required with the seaweedfs profile")
            if env.get("S3_ADMIN_ACCESS_KEY_ID") and env.get("S3_ADMIN_ACCESS_KEY_ID") == env.get("S3_ACCESS_KEY_ID"):
                errors.append("S3_ADMIN_ACCESS_KEY_ID must differ from S3_ACCESS_KEY_ID (least privilege)")
        if (env.get("S3_ADDRESSING_STYLE") or "path") not in ("path", "virtual", "auto"):
            errors.append("S3_ADDRESSING_STYLE must be path, virtual or auto")
        for k in ("S3_ENDPOINT_URL", "OFFSITE_S3_ENDPOINT_URL"):
            u = urlparse(env.get(k) or "")
            if u.scheme == "http" and u.hostname and not _internal_host(u.hostname):
                warns.append(f"{k} uses plain http to a non-internal host ({u.hostname}) – use https")
        if "digitaloceanspaces.com" in (env.get("S3_ENDPOINT_URL") or "") and (env.get("S3_ADDRESSING_STYLE") or "path") == "path":
            warns.append("DigitalOcean Spaces: set S3_ADDRESSING_STYLE=virtual")
    return errors, warns


def validate(env: Mapping[str, str], deployed: bool = True) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    profile = env.get("APP_ENV") or "development"
    if profile not in ("development", "staging", "production"):
        errors.append(f"APP_ENV must be development|staging|production (got {profile!r})")
    for k in REQUIRED + (REQUIRED_DEPLOYED if deployed else []):
        if not env.get(k):
            errors.append(f"{k} is required")
    if "*" in [o.strip() for o in (env.get("CORS_ORIGINS") or "").split(",")]:
        errors.append("CORS_ORIGINS='*' is refused – list explicit origins (credentials are never combined with a wildcard)")
    strict = profile in ("staging", "production")
    storage_checks(env, errors, warns)
    if strict:
        for k, n in (("JWT_SECRET", 32), ("POSTGRES_PASSWORD", 16), ("S3_SECRET_ACCESS_KEY", 16), ("S3_ADMIN_SECRET_ACCESS_KEY", 16)):
            if env.get(k) and _weak(env[k], n):
                errors.append(f"{k} is weak or a placeholder (min {n} chars, generate with openssl rand)")
        if env.get("SECRET_STORE_KEY") and not _fernet_ok(env["SECRET_STORE_KEY"]):
            errors.append("SECRET_STORE_KEY is not a valid Fernet key")
        for k in ("DEMO_USER_PASSWORD", "STAGING_DEMO_PASSWORD"):
            if env.get(k) == DOCUMENTED_DEMO_PASSWORD:
                errors.append(f"{k} uses the publicly documented demo password")
        if (env.get("AI_PROVIDER") or "none") == "emergent":
            errors.append("AI_PROVIDER=emergent is preview-only; use openrouter, anthropic, openai_compatible or none")
        if not (env.get("FRONTEND_URL") or "").startswith("https://"):
            errors.append("FRONTEND_URL must be https://")
        origins = [o.strip() for o in (env.get("CORS_ORIGINS") or "").split(",") if o.strip()]
        if any("localhost" in o or "127.0.0.1" in o or not o.startswith("https://") for o in origins):
            errors.append("CORS_ORIGINS must only contain https:// public origins (no localhost)")
        if not _true(env.get("TRUST_PROXY_HEADERS")):
            warns.append("TRUST_PROXY_HEADERS should be true behind the edge proxy (correct client IPs for rate limiting)")
        if env.get("RATE_LIMIT_ENABLED", "true").lower() in ("0", "false", "no", "off"):
            errors.append("RATE_LIMIT_ENABLED must not be disabled")
        if env.get("HSTS_ENABLED", "true").lower() in ("0", "false", "no", "off"):
            warns.append("HSTS_ENABLED is off")
    errors += insecure_production(env)
    if profile == "production" and _true(env.get("ALLOW_SIGNUP")):
        warns.append("ALLOW_SIGNUP=true in production – public self sign-up creates sandbox tenants; keep it false for production")
    if profile == "production" and _true(env.get("ALLOW_DEMO_LOGIN")):
        if _true(env.get("ALLOW_DEMO_LOGIN_IN_PRODUCTION")):
            warns.append("ALLOW_DEMO_LOGIN=true in production (override set) – anyone can open the shared demo workspace without a password")
        else:
            errors.append("ALLOW_DEMO_LOGIN=true is refused in production (passwordless shared demo login); set ALLOW_DEMO_LOGIN_IN_PRODUCTION=true to override")
    if profile == "production" and (env.get("SIGNUP_RATE_LIMIT_EXEMPT_CIDRS") or "").strip():
        warns.append("SIGNUP_RATE_LIMIT_EXEMPT_CIDRS is set in production – listed addresses bypass the sign-up limit; use only for test runners")
    if profile == "production" and _true(env.get("ALLOW_INSECURE_PRODUCTION")):
        warns.append("ALLOW_INSECURE_PRODUCTION=true – production guards are overridden")
    if profile == "staging":
        if _true(env.get("SEED_DEMO_DATA")) and not env.get("STAGING_DEMO_PASSWORD"):
            errors.append("staging with SEED_DEMO_DATA=true requires STAGING_DEMO_PASSWORD")
        if _true(env.get("DEV_USER_PICKER", "true")) and not (env.get("STAGING_BASIC_AUTH_HTPASSWD") or env.get("STAGING_ALLOW_CIDRS")):
            warns.append("staging exposes the dev user picker without basic auth/IP allowlist – set DEV_USER_PICKER=false or protect the host")
    prov = providers(env)
    if "oidc" in prov:
        errors += [f"{k} is required when oidc is enabled" for k in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_REDIRECT_URI") if not env.get(k)]
    if "mtls_header" in prov and not env.get("MTLS_TRUSTED_PROXIES"):
        errors.append("MTLS_TRUSTED_PROXIES is required when mtls_header is enabled")
    ai = env.get("AI_PROVIDER") or "none"
    if ai == "anthropic":
        errors += [f"{k} is required for AI_PROVIDER=anthropic" for k in ("ANTHROPIC_API_KEY", "AI_MODEL") if not env.get(k)]
    elif ai == "openai_compatible":
        errors += [f"{k} is required for AI_PROVIDER=openai_compatible" for k in ("OPENAI_COMPAT_BASE_URL", "AI_MODEL") if not env.get(k)]
    elif ai == "openrouter":
        errors += [f"{k} is required for AI_PROVIDER=openrouter" for k in ("OPENAI_COMPAT_API_KEY", "AI_MODEL") if not env.get(k)]
        if env.get("ANTHROPIC_API_KEY"):
            warns.append("ANTHROPIC_API_KEY is set but never used with AI_PROVIDER=openrouter – remove it from the env file")
        base = env.get("OPENAI_COMPAT_BASE_URL") or "https://openrouter.ai/api/v1"
        if strict and not base.startswith("https://"):
            errors.append("OPENAI_COMPAT_BASE_URL must be https:// in staging/production")
    if ai in ("openrouter", "openai_compatible", "anthropic"):
        for k in ("AI_MODEL", "AI_MODEL_DRAFTING", "AI_MODEL_POLICY", "AI_MODEL_MAPPING", "AI_MODEL_SUMMARY"):
            if env.get(k) and any(c.isspace() for c in env[k]):
                errors.append(f"{k} must be a single model slug without spaces (e.g. openai/gpt-4o)")
    elif ai not in ("none", "emergent"):
        errors.append(f"AI_PROVIDER {ai!r} is not supported")
    if (env.get("SECRET_STORE_BACKEND") or "env_key") == "vault":
        if not env.get("VAULT_ADDR") or not (env.get("VAULT_TOKEN") or (env.get("VAULT_ROLE_ID") and env.get("VAULT_SECRET_ID"))):
            errors.append("SECRET_STORE_BACKEND=vault requires VAULT_ADDR and VAULT_TOKEN or VAULT_ROLE_ID+VAULT_SECRET_ID")
    if (env.get("UPLOAD_SCANNER") or "none") == "none" and strict:
        warns.append("UPLOAD_SCANNER=none – uploads are recorded as not_scanned (consider --profile clamav)")
    return errors, warns


def production_guard() -> None:
    errs = insecure_production(os.environ)
    if errs:
        raise RuntimeError("Refusing to start: " + "; ".join(errs) + " (set ALLOW_INSECURE_PRODUCTION=true only for a controlled exception)")
