"""Idempotent Keycloak configurator. Shows a plan (diff) first; secrets are always masked.

python -m app.tools.keycloak_config plan
python -m app.tools.keycloak_config apply [--if-realm-absent] [--yes]

Master realm hardening (needs bootstrap admin on first run): configurator service account (client_credentials) + named permanent
admin with CONFIGURE_TOTP, OTP *required* in the master browser flow, then the bootstrap admin is disabled.
Realm KEYCLOAK_REALM (ironvision-demo): confidential client OIDC_CLIENT_ID, PKCE S256, standard flow only, password policy,
brute-force detection, no registration / reset-by-email / verify-email, 5-min access tokens, SSO idle/max = app session timeouts,
optional per-user OTP (default conditional flow) or required OTP with KEYCLOAK_REQUIRE_MFA=true.
"""
import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from app.services.keycloak_admin import KeycloakAdmin, KeycloakError, configurator_id, created_id

MFA_FLOW = "browser-otp-required"
APP_BROWSER_FLOW = "ironvision-browser"          # username → deny demo-launcher users → password → OTP (conditional or required)
LAUNCHER_FLOW = "direct-grant-demo-launcher"     # username → deny everyone WITHOUT demo_launcher=true → password
DEMO_ATTR = "demo_launcher"


def _attr_cond(alias: str, negate: bool) -> dict:
    return {"alias": alias, "config": {"attribute_name": DEMO_ATTR, "attribute_expected_value": "true", "not": str(negate).lower(),
                                       "regex": "false", "include_group_attributes": "false"}}


def browser_flow_spec(mfa: bool) -> list:
    return [("exec", "auth-cookie", "ALTERNATIVE"),
            ("flow", f"{APP_BROWSER_FLOW} forms", "ALTERNATIVE", [
                ("exec", "auth-username-form", "REQUIRED"),
                ("flow", f"{APP_BROWSER_FLOW} deny demo launcher users", "CONDITIONAL", [
                    ("cond", "conditional-user-attribute", "REQUIRED", _attr_cond("ivb-demo-user", False)),
                    ("exec", "deny-access-authenticator", "REQUIRED")]),
                ("exec", "auth-password-form", "REQUIRED"),
                ("flow", f"{APP_BROWSER_FLOW} otp", "REQUIRED" if mfa else "CONDITIONAL", [
                    ("cond", "conditional-user-configured", "DISABLED" if mfa else "REQUIRED", None),
                    ("exec", "auth-otp-form", "REQUIRED")])])]


def launcher_flow_spec() -> list:
    return [("exec", "direct-grant-validate-username", "REQUIRED"),
            ("flow", f"{LAUNCHER_FLOW} deny non-demo users", "CONDITIONAL", [
                ("cond", "conditional-user-attribute", "REQUIRED", _attr_cond("dgl-not-demo-user", True)),
                ("exec", "deny-access-authenticator", "REQUIRED")]),
            ("exec", "direct-grant-validate-password", "REQUIRED")]


def demo_email(handle: str) -> str:
    return f"{handle}@demo-launcher.invalid"  # non-routable; the public demo e-mail must not resolve to this user


def launcher_enabled() -> bool:
    return bool(os.environ.get("KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"))


def registration_enabled() -> bool:
    return _bool("KEYCLOAK_ALLOW_REGISTRATION")


BACKEND_ROLES = ["view-users", "query-users", "manage-users", "view-events"]  # JIT check (REGISTER events) + purge offboarding
PROFILE_ATTRS = [DEMO_ATTR, "self_registered", "reserved"]  # admin view/edit only: users can neither see nor set them
RESERVED_USERS = ["demo@ironvision.ai"]  # disabled placeholders: the registration page rejects these identifiers ("already exists")


def desired_backend_client() -> dict:
    return {"clientId": os.environ.get("KEYCLOAK_BACKEND_CLIENT_ID") or "ironvision-backend",
            "name": "IronVision backend (service account: registration check, sandbox purge)", "enabled": True,
            "protocol": "openid-connect", "publicClient": False, "clientAuthenticatorType": "client-secret",
            "standardFlowEnabled": False, "implicitFlowEnabled": False, "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": True, "redirectUris": [], "webOrigins": [], "fullScopeAllowed": True}  # token carries only the 4 assigned roles


def desired_launcher_client(flow_id: str) -> dict:
    return {"clientId": os.environ.get("KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID") or "ironvision-demo-launcher",
            "name": "IronVision Explore-the-demo launcher (server-side only)", "enabled": True, "protocol": "openid-connect",
            "publicClient": False, "clientAuthenticatorType": "client-secret", "standardFlowEnabled": False, "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": True, "serviceAccountsEnabled": False, "bearerOnly": False, "consentRequired": False,
            "redirectUris": [], "webOrigins": [], "fullScopeAllowed": False,
            "authenticationFlowBindingOverrides": {"direct_grant": flow_id},
            "attributes": {"standard.token.exchange.enabled": "false", "oauth2.device.authorization.grant.enabled": "false",
                           "oidc.ciba.grant.enabled": "false", "use.refresh.tokens": "true"}}
SA_REALM_MGMT_ROLES = ["manage-realm", "manage-users", "manage-clients", "view-realm", "view-users", "view-clients", "query-users",
                       "query-clients", "query-groups", "view-events", "view-authorization"]
MASTER_READ_ROLES = ["view-realm", "view-users", "view-clients", "query-users", "query-clients"]  # read-only: lets later runs verify hardening


@dataclass
class Step:
    desc: str
    run: Callable[[], None]


def _bool(k: str) -> bool:
    return os.environ.get(k, "").strip().lower() in ("1", "true", "yes", "on")


def realm_name() -> str:
    return os.environ.get("KEYCLOAK_REALM", "ironvision-demo")


def desired_realm() -> dict:
    idle = int(os.environ.get("SESSION_IDLE_MINUTES", "30")) * 60
    absolute = int(os.environ.get("SESSION_ABSOLUTE_HOURS", "12")) * 3600
    return {"realm": realm_name(), "enabled": True, "displayName": os.environ.get("KEYCLOAK_REALM_DISPLAY_NAME", "IronVision AI"),
            "sslRequired": "external", "registrationAllowed": registration_enabled(), "registrationEmailAsUsername": False,
            "resetPasswordAllowed": False, "verifyEmail": False,
            "rememberMe": False, "loginWithEmailAllowed": True, "duplicateEmailsAllowed": False, "editUsernameAllowed": False,
            "bruteForceProtected": True, "permanentLockout": False, "failureFactor": 5, "waitIncrementSeconds": 60,
            "maxFailureWaitSeconds": 900, "maxDeltaTimeSeconds": 43200, "minimumQuickLoginWaitSeconds": 60,
            "quickLoginCheckMilliSeconds": 1000,
            "passwordPolicy": "length(12) and notUsername(undefined) and notEmail(undefined) and passwordHistory(5)",
            "accessTokenLifespan": 300, "ssoSessionIdleTimeout": idle, "ssoSessionMaxLifespan": absolute,
            "otpPolicyType": "totp", "otpPolicyAlgorithm": "HmacSHA1", "otpPolicyDigits": 6, "otpPolicyPeriod": 30,
            "browserFlow": APP_BROWSER_FLOW}


def desired_client() -> dict:
    redirect = os.environ["OIDC_REDIRECT_URI"]
    post_logout = os.environ.get("OIDC_POST_LOGOUT_REDIRECT_URI") or f"{os.environ['FRONTEND_URL'].rstrip('/')}/login"
    u = urlsplit(os.environ.get("FRONTEND_URL") or redirect)
    return {"clientId": os.environ["OIDC_CLIENT_ID"], "name": "IronVision AI web app", "enabled": True, "protocol": "openid-connect",
            "publicClient": False, "clientAuthenticatorType": "client-secret", "standardFlowEnabled": True, "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False, "bearerOnly": False, "consentRequired": False,
            "redirectUris": [redirect], "webOrigins": [f"{u.scheme}://{u.netloc}"], "rootUrl": f"{u.scheme}://{u.netloc}",
            "attributes": {"pkce.code.challenge.method": "S256", "post.logout.redirect.uris": post_logout,
                           "oauth2.device.authorization.grant.enabled": "false", "oidc.ciba.grant.enabled": "false",
                           "backchannel.logout.session.required": "true"}}


def _diff(current: dict, want: dict, prefix: str) -> list[str]:
    out = []
    for k, v in want.items():
        if isinstance(v, dict):
            out += _diff(current.get(k) or {}, v, f"{prefix}.{k}")
        elif current.get(k) != v:
            out.append(f"{prefix}.{k}: {current.get(k)!r} -> {v!r}")
    return out


class Planner:
    def __init__(self, kc: KeycloakAdmin):
        self.kc = kc
        self.steps: list[Step] = []

    def add(self, desc: str, fn: Callable[[], None]) -> None:
        self.steps.append(Step(desc, fn))

    # ---------- master realm hardening ----------
    def master(self) -> None:
        kc = self.kc
        cid = configurator_id()
        secret = os.environ.get("KEYCLOAK_CONFIGURATOR_CLIENT_SECRET", "")
        want = {"clientId": cid, "enabled": True, "publicClient": False, "serviceAccountsEnabled": True, "standardFlowEnabled": False,
                "implicitFlowEnabled": False, "directAccessGrantsEnabled": False, "secret": secret,
                "description": "IronVision configurator (client_credentials). Secret only in .env.production."}
        sa_mode = kc.mode == "service-account"
        n0 = len(self.steps)
        cur = kc.client("master", cid)
        if cur is None:
            if not secret:
                raise KeycloakError("KEYCLOAK_CONFIGURATOR_CLIENT_SECRET is empty – run ./deploy.sh (gen_env_secrets) first")
            self.add(f"+ master client {cid} (service account, client_credentials, secret=***)", lambda: kc.post("/master/clients", want))
        elif not sa_mode and secret and kc.get(f"/master/clients/{cur['id']}/client-secret").get("value") != secret:
            self.add(f"~ master client {cid}: secret -> *** (from env)", lambda: kc.put(f"/master/clients/{cur['id']}", {**cur, "secret": secret}))
        if not sa_mode:
            self.add(f"= master client {cid}: ensure realm role create-realm + read-only master roles", self._sa_master_roles)

        admin = os.environ.get("KEYCLOAK_ADMIN_USERNAME", "")
        if not admin:
            raise KeycloakError("KEYCLOAK_ADMIN_USERNAME is empty (named permanent master admin)")
        if not kc.users_by("master", username=admin):
            self.add(f"+ master user {admin} (permanent admin, role admin, required action CONFIGURE_TOTP, password=***)", self._create_admin)
        self._otp_flow("master", required=True)
        boot = os.environ.get("KC_BOOTSTRAP_ADMIN_USERNAME", "")
        rows = kc.users_by("master", username=boot) if boot else []
        if rows and rows[0].get("enabled") and boot != admin:
            self.add(f"- master user {boot}: disable bootstrap admin (after the steps above succeed)",
                     lambda: kc.put(f"/master/users/{rows[0]['id']}", {**rows[0], "enabled": False}))
        if sa_mode:  # the service account can only read master; drift there needs a human admin (docs/KEYCLOAK.md)
            for st in self.steps[n0:]:
                if not st.desc.startswith("= "):
                    st.desc = f"! {st.desc}  [needs master admin – not applied by service account]"
                    st.run = lambda: None

    def _sa_user(self) -> dict:
        c = self.kc.client("master", configurator_id())
        return self.kc.get(f"/master/clients/{c['id']}/service-account-user")

    def _sa_master_roles(self) -> None:
        uid = self._sa_user()["id"]
        have = {r["name"] for r in self.kc.get(f"/master/users/{uid}/role-mappings/realm") or []}
        if "create-realm" not in have:
            self.kc.post(f"/master/users/{uid}/role-mappings/realm", [self.kc.get("/master/roles/create-realm")])
        mr = self.kc.client("master", "master-realm")
        have = {r["name"] for r in self.kc.get(f"/master/users/{uid}/role-mappings/clients/{mr['id']}") or []}
        missing = [self.kc.get(f"/master/clients/{mr['id']}/roles/{n}") for n in MASTER_READ_ROLES if n not in have]
        if missing:
            self.kc.post(f"/master/users/{uid}/role-mappings/clients/{mr['id']}", missing)

    def _create_admin(self) -> None:
        kc, name = self.kc, os.environ["KEYCLOAK_ADMIN_USERNAME"]
        pw = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
        if len(pw) < 16:
            raise KeycloakError("KEYCLOAK_ADMIN_PASSWORD must be >= 16 characters")
        uid = created_id(kc.post("/master/users", {"username": name, "enabled": True, "requiredActions": ["CONFIGURE_TOTP"],
                                                   "credentials": [{"type": "password", "value": pw, "temporary": False}]}))
        kc.post(f"/master/users/{uid}/role-mappings/realm", [kc.get("/master/roles/admin")])

    def _otp_flow(self, realm: str, required: bool) -> None:
        kc = self.kc
        r = kc.realm(realm) or {}
        if not required:
            return
        if not any(f["alias"] == MFA_FLOW for f in kc.get(f"/{realm}/authentication/flows") or []):
            self.add(f"+ {realm} flow {MFA_FLOW} (copy of browser; OTP REQUIRED for every user)",
                     lambda: (kc.post(f"/{realm}/authentication/flows/browser/copy", {"newName": MFA_FLOW}), self._require_otp(realm)))
        else:
            self.add(f"= {realm} flow {MFA_FLOW}: ensure OTP REQUIRED", lambda: self._require_otp(realm))
        if r.get("browserFlow") != MFA_FLOW:
            self.add(f"~ {realm}.browserFlow: {r.get('browserFlow')!r} -> {MFA_FLOW!r}",
                     lambda: kc.put(f"/{realm}", {"browserFlow": MFA_FLOW}))

    def _require_otp(self, realm: str) -> None:
        ex = self.kc.get(f"/{realm}/authentication/flows/{MFA_FLOW}/executions")
        otp = next(i for i, e in enumerate(ex) if e.get("providerId") == "auth-otp-form")
        parent = next(i for i in range(otp - 1, -1, -1) if ex[i].get("authenticationFlow") and ex[i]["level"] == ex[otp]["level"] - 1)
        changes = {parent: "REQUIRED", otp: "REQUIRED"}
        for i in range(parent + 1, len(ex)):
            if ex[i]["level"] <= ex[parent]["level"]:
                break
            if ex[i]["level"] == ex[otp]["level"] and str(ex[i].get("providerId", "")).startswith("conditional-"):
                changes[i] = "DISABLED"
        for i, req in changes.items():
            if ex[i]["requirement"] != req:
                self.kc.put(f"/{realm}/authentication/flows/{MFA_FLOW}/executions", {**ex[i], "requirement": req})

    # ---------- application realm ----------
    def app_realm(self) -> bool:
        kc, name, want = self.kc, realm_name(), desired_realm()
        cur = kc.realm(name)
        mfa = _bool("KEYCLOAK_REQUIRE_MFA")
        if cur is None:
            self.add(f"+ realm {name} ({len(want)} settings; browserFlow={APP_BROWSER_FLOW}, OTP {'REQUIRED' if mfa else 'optional per user'})",
                     lambda: kc.post("", {**want, "browserFlow": "browser"}))
        else:
            diffs = _diff(cur, {k: v for k, v in want.items() if k != "browserFlow"}, name)
            if diffs:
                self.add("~ " + "\n  ~ ".join(diffs), lambda: kc.put(f"/{name}", {k: v for k, v in want.items() if k != "browserFlow"}))
        self._flow(name, APP_BROWSER_FLOW, browser_flow_spec(mfa), cur is None)
        if cur is None or cur.get("browserFlow") != APP_BROWSER_FLOW:
            self.add(f"~ {name}.browserFlow: {(cur or {}).get('browserFlow')!r} -> {APP_BROWSER_FLOW!r}",
                     lambda: kc.put(f"/{name}", {"browserFlow": APP_BROWSER_FLOW}))
        self._client(name, cur is None)
        self.add(f"= master client {configurator_id()}: ensure {name}-realm management roles", lambda: self._sa_realm_roles(name))
        if launcher_enabled() or registration_enabled():
            self._profile_attr(name, cur is None)
        if launcher_enabled():
            self._flow(name, LAUNCHER_FLOW, launcher_flow_spec(), cur is None)
            self._launcher_client(name, cur is None)
            self._demo_user(name, cur is None)
        if os.environ.get("KEYCLOAK_BACKEND_CLIENT_SECRET"):
            self._backend_client(name, cur is None)
        if registration_enabled():
            self._events(name, cur is None)
            for r in RESERVED_USERS:
                self._reserved_user(name, r, cur is None)
        return cur is None

    # ---------- custom authentication flows ----------
    def _flow(self, realm: str, alias: str, spec: list, realm_new: bool) -> None:
        exists = not realm_new and any(f["alias"] == alias for f in self.kc.get(f"/{realm}/authentication/flows") or [])
        if not exists:
            self.add(f"+ {realm} flow {alias}", lambda: self._build_flow(realm, alias, spec))
        else:
            self.add(f"= {realm} flow {alias}: ensure requirements", lambda: self._set_requirements(realm, alias, spec))

    def _build_flow(self, realm: str, alias: str, spec: list) -> None:
        kc = self.kc
        kc.post(f"/{realm}/authentication/flows", {"alias": alias, "providerId": "basic-flow", "topLevel": True, "builtIn": False,
                                                   "description": "managed by app.tools.keycloak_config"})

        def add(parent: str, items: list) -> None:
            for it in items:
                if it[0] == "flow":
                    kc.post(f"/{realm}/authentication/flows/{parent}/executions/flow",
                            {"alias": it[1], "type": "basic-flow", "provider": "registration-page-form", "description": it[1]})
                    add(it[1], it[3])
                else:
                    kc.post(f"/{realm}/authentication/flows/{parent}/executions/execution", {"provider": it[1]})
        add(alias, spec)
        self._set_requirements(realm, alias, spec)

    def _set_requirements(self, realm: str, alias: str, spec: list) -> None:
        kc = self.kc
        ex = kc.get(f"/{realm}/authentication/flows/{alias}/executions")

        def walk(items: list, parent_display: str | None):
            for it in items:
                if it[0] == "flow":
                    e = next(x for x in ex if x.get("authenticationFlow") and x["displayName"] == it[1])
                else:
                    e = next(x for x in ex if x.get("providerId") == it[1] and _parent(ex, x) == parent_display)
                if e["requirement"] != it[2]:
                    kc.put(f"/{realm}/authentication/flows/{alias}/executions", {**e, "requirement": it[2]})
                if it[0] == "cond" and it[3] and not e.get("authenticationConfig"):
                    kc.post(f"/{realm}/authentication/executions/{e['id']}/config", it[3])
                if it[0] == "flow":
                    walk(it[3], it[1])
        walk(spec, None)

    # ---------- Explore-the-demo launcher (Option B) ----------
    def _launcher_client(self, realm: str, realm_new: bool) -> None:
        kc = self.kc
        secret = os.environ["KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"]
        if len(secret) < 32:
            raise KeycloakError("KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET must be >= 32 characters")
        cid = os.environ.get("KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID") or "ironvision-demo-launcher"

        def flow_id() -> str:
            return next(f["id"] for f in kc.get(f"/{realm}/authentication/flows") if f["alias"] == LAUNCHER_FLOW)
        cur = None if realm_new else kc.client(realm, cid)
        if cur is None:
            self.add(f"+ {realm} client {cid} (confidential, direct grant ONLY, flow {LAUNCHER_FLOW}, no redirect URIs, secret=***)",
                     lambda: kc.post(f"/{realm}/clients", {**desired_launcher_client(flow_id()), "secret": secret}))
            return
        want = desired_launcher_client(flow_id())
        diffs = _diff(cur, want, f"{realm}.client.{cid}")
        if kc.get(f"/{realm}/clients/{cur['id']}/client-secret").get("value") != secret:
            diffs.append(f"{realm}.client.{cid}.secret: *** -> *** (from env)")
        if diffs:
            self.add("~ " + "\n  ~ ".join(diffs), lambda: kc.put(f"/{realm}/clients/{cur['id']}", {
                **cur, **want, "attributes": {**cur.get("attributes", {}), **want["attributes"]}, "secret": secret}))

    def _demo_user(self, realm: str, realm_new: bool) -> None:
        kc = self.kc
        name = os.environ.get("KEYCLOAK_DEMO_USERNAME", "").lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{11,62}", name):
            raise KeycloakError("KEYCLOAK_DEMO_USERNAME must be an unpublished handle (12+ chars, a-z 0-9 -), not an e-mail – gen_env_secrets fills it")
        email = demo_email(name)
        pw = os.environ.get("KEYCLOAK_DEMO_PASSWORD", "")
        if len(pw) < 16:
            raise KeycloakError("KEYCLOAK_DEMO_PASSWORD must be >= 16 characters (gen_env_secrets fills it)")
        rows = [] if realm_new else kc.users_by(realm, username=name)
        want = {"enabled": True, "emailVerified": True, "requiredActions": [], "attributes": {DEMO_ATTR: ["true"]}}
        if not rows:
            self.add(f"+ {realm} user {name} (demo launcher user: {DEMO_ATTR}=true, no default roles, password=*** from env)",
                     lambda: self._create_demo_user(realm, name, email, pw))
            return
        u = rows[0]
        drift = [k for k in ("enabled", "emailVerified") if u.get(k) is not True] + (["requiredActions"] if u.get("requiredActions") else []) \
            + (["firstName/lastName"] if not (u.get("firstName") and u.get("lastName")) else []) \
            + (["email"] if (u.get("email") or "").lower() != email else []) \
            + (["attributes"] if (u.get("attributes") or {}).get(DEMO_ATTR) != ["true"] else [])
        if drift:
            # full representation: with the declarative user profile a partial "attributes" map would drop firstName/lastName
            self.add(f"~ {realm} user {name}: {', '.join(drift)}", lambda: kc.put(f"/{realm}/users/{u['id']}", {
                **u, **want, "email": email, "firstName": u.get("firstName") or "Demo", "lastName": u.get("lastName") or "Visitor",
                "attributes": {**(u.get("attributes") or {}), DEMO_ATTR: ["true"]}}))
        self.add(f"= {realm} user {name}: ensure no default roles / no OTP credential", lambda: self._strip_demo_user(realm, u["id"]))

    def _profile_attr(self, realm: str, realm_new: bool) -> None:
        """Keycloak 26 drops undeclared attributes: declare ours as admin-only (users can neither see nor set them)."""
        kc = self.kc

        def spec(n: str) -> dict:
            return {"name": n, "displayName": f"{n} (managed by IronVision)", "multivalued": False,
                    "permissions": {"view": ["admin"], "edit": ["admin"]}, "validations": {}, "annotations": {}}

        def apply() -> None:
            prof = kc.get(f"/{realm}/users/profile")
            prof["attributes"] = [a for a in prof["attributes"] if a["name"] not in PROFILE_ATTRS] + [spec(n) for n in PROFILE_ATTRS]
            kc.put(f"/{realm}/users/profile", prof)
        prof = None if realm_new else kc.get(f"/{realm}/users/profile")
        have = {a["name"]: a for a in (prof or {}).get("attributes", [])}
        if any(have.get(n, {}).get("permissions") != spec(n)["permissions"] for n in PROFILE_ATTRS):
            self.add(f"+ {realm} user profile attributes {', '.join(PROFILE_ATTRS)} (admin view/edit only)", apply)

    def _backend_client(self, realm: str, realm_new: bool) -> None:
        kc, want, secret = self.kc, desired_backend_client(), os.environ["KEYCLOAK_BACKEND_CLIENT_SECRET"]
        if len(secret) < 32:
            raise KeycloakError("KEYCLOAK_BACKEND_CLIENT_SECRET must be >= 32 characters (gen_env_secrets fills it)")
        cur = None if realm_new else kc.client(realm, want["clientId"])
        if cur is None:
            self.add(f"+ {realm} client {want['clientId']} (service account only: {', '.join(BACKEND_ROLES)}; secret=***)",
                     lambda: (kc.post(f"/{realm}/clients", {**want, "secret": secret}), self._backend_roles(realm)))
            return
        diffs = _diff(cur, want, f"{realm}.client.{want['clientId']}")
        if kc.get(f"/{realm}/clients/{cur['id']}/client-secret").get("value") != secret:
            diffs.append(f"{realm}.client.{want['clientId']}.secret: *** -> *** (from env)")
        if diffs:
            self.add("~ " + "\n  ~ ".join(diffs), lambda: kc.put(f"/{realm}/clients/{cur['id']}", {**cur, **want, "secret": secret}))
        self.add(f"= {realm} client {want['clientId']}: ensure roles {', '.join(BACKEND_ROLES)}", lambda: self._backend_roles(realm))

    def _backend_roles(self, realm: str) -> None:
        kc = self.kc
        c = kc.client(realm, desired_backend_client()["clientId"])
        uid = kc.get(f"/{realm}/clients/{c['id']}/service-account-user")["id"]
        rm = kc.client(realm, "realm-management")
        have = {r["name"] for r in kc.get(f"/{realm}/users/{uid}/role-mappings/clients/{rm['id']}") or []}
        missing = [kc.get(f"/{realm}/clients/{rm['id']}/roles/{n}") for n in BACKEND_ROLES if n not in have]
        if missing:
            kc.post(f"/{realm}/users/{uid}/role-mappings/clients/{rm['id']}", missing)

    def _events(self, realm: str, realm_new: bool) -> None:
        """Keycloak records REGISTER events – the authoritative 'self-registered' marker for just-in-time provisioning."""
        kc = self.kc
        cur = {} if realm_new else (kc.realm(realm) or {})  # realm representation: needs manage-realm only (not manage-events)
        types = set(cur.get("enabledEventTypes") or []) if cur.get("eventsEnabled") else set()
        if cur.get("eventsEnabled") and "REGISTER" in types and int(cur.get("eventsExpiration") or 0) >= 7776000:
            return
        self.add(f"~ {realm} events: eventsEnabled=true, REGISTER recorded, 90-day expiry",
                 lambda: kc.put(f"/{realm}", {"eventsEnabled": True, "eventsExpiration": 7776000,
                                              "enabledEventTypes": sorted(types | {"REGISTER"})}))

    def _reserved_user(self, realm: str, name: str, realm_new: bool) -> None:
        kc = self.kc
        rows = [] if realm_new else kc.users_by(realm, username=name)
        if not rows:
            self.add(f"+ {realm} user {name} (DISABLED reserved placeholder – registration rejects this identifier)",
                     lambda: kc.post(f"/{realm}/users", {"username": name, "email": name, "firstName": "Reserved", "lastName": "Identifier",
                                                         "enabled": False, "attributes": {"reserved": ["true"]}}))
        elif rows[0].get("enabled") or (rows[0].get("attributes") or {}).get("reserved") != ["true"]:
            u = rows[0]
            self.add(f"~ {realm} user {name}: disable reserved placeholder",
                     lambda: kc.put(f"/{realm}/users/{u['id']}", {**u, "enabled": False, "attributes": {**(u.get("attributes") or {}), "reserved": ["true"]}}))

    def _create_demo_user(self, realm: str, name: str, email: str, pw: str) -> None:
        uid = created_id(self.kc.post(f"/{realm}/users", {"username": name, "email": email, "firstName": "Demo", "lastName": "Visitor",
                                                          "enabled": True, "emailVerified": True, "attributes": {DEMO_ATTR: ["true"]}}))
        self.kc.set_password(realm, uid, pw, False)
        self._strip_demo_user(realm, uid)

    def _strip_demo_user(self, realm: str, uid: str) -> None:
        kc = self.kc
        roles = [r for r in kc.get(f"/{realm}/users/{uid}/role-mappings/realm") or [] if r["name"].startswith("default-roles-")]
        if roles:
            kc.req("DELETE", f"/{realm}/users/{uid}/role-mappings/realm", json=roles)  # no account-console roles (manage-account …)
        for c in kc.credentials(realm, uid):
            if c.get("type") == "otp":
                kc.delete(f"/{realm}/users/{uid}/credentials/{c['id']}")

    def _client(self, realm: str, realm_new: bool) -> None:
        kc, want = self.kc, desired_client()
        secret = os.environ.get("OIDC_CLIENT_SECRET", "")
        if len(secret) < 32:
            raise KeycloakError("OIDC_CLIENT_SECRET must be >= 32 characters (gen_env_secrets fills it)")
        cur = None if realm_new else kc.client(realm, want["clientId"])
        if cur is None:
            self.add(f"+ {realm} client {want['clientId']} (confidential, PKCE S256, standard flow only, secret=***)",
                     lambda: kc.post(f"/{realm}/clients", {**want, "secret": secret}))
            return
        diffs = _diff(cur, want, f"{realm}.client.{want['clientId']}")
        if kc.get(f"/{realm}/clients/{cur['id']}/client-secret").get("value") != secret:
            diffs.append(f"{realm}.client.{want['clientId']}.secret: *** -> *** (from env)")
        if diffs:
            self.add("~ " + "\n  ~ ".join(diffs), lambda: kc.put(f"/{realm}/clients/{cur['id']}",
                                             {**cur, **want, "attributes": {**cur.get("attributes", {}), **want["attributes"]}, "secret": secret}))

    def _sa_realm_roles(self, realm: str) -> None:
        mgmt = self.kc.client("master", f"{realm}-realm")
        uid = self._sa_user()["id"]
        have = {r["name"] for r in self.kc.get(f"/master/users/{uid}/role-mappings/clients/{mgmt['id']}") or []}
        missing = [self.kc.get(f"/master/clients/{mgmt['id']}/roles/{n}") for n in SA_REALM_MGMT_ROLES if n not in have]
        if missing:
            self.kc.post(f"/master/users/{uid}/role-mappings/clients/{mgmt['id']}", missing)


def _parent(ex: list[dict], e: dict) -> str | None:
    """displayName of the sub-flow that directly contains execution e (None at top level)."""
    i = ex.index(e)
    for j in range(i - 1, -1, -1):
        if ex[j]["level"] == e["level"] - 1 and ex[j].get("authenticationFlow"):
            return ex[j]["displayName"]
    return None


def build_plan(kc: KeycloakAdmin) -> tuple[list[Step], bool]:
    p = Planner(kc)
    p.master()
    boot = [s for s in p.steps if s.desc.startswith("- master user")]  # disabling the bootstrap admin always runs last
    p.steps = [s for s in p.steps if s not in boot]
    realm_absent = p.app_realm()
    p.steps += boot
    return p.steps, realm_absent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.tools.keycloak_config")
    ap.add_argument("action", choices=["plan", "apply"])
    ap.add_argument("--if-realm-absent", action="store_true", help="apply only when the realm does not exist yet (deploy.sh default)")
    ap.add_argument("--yes", action="store_true", help="do not prompt (non-interactive apply)")
    a = ap.parse_args(argv)
    try:
        kc = KeycloakAdmin().login()
        steps, realm_absent = build_plan(kc)
    except (KeycloakError, KeyError) as e:
        print(f"[keycloak-config] ERROR: {e}", file=sys.stderr)
        return 1
    actionable = [s for s in steps if not s.desc.startswith("= ")]
    print(f"[keycloak-config] admin API auth: {kc.mode}; realm {realm_name()}: {'ABSENT' if realm_absent else 'present'}")
    print("[keycloak-config] plan:" if actionable else "[keycloak-config] plan: no changes (in sync)")
    for s in actionable:
        print(f"  {s.desc}")
    if a.action == "plan":
        return 0
    if a.if_realm_absent and not realm_absent:
        print("[keycloak-config] realm exists – not applying (re-run with: ./deploy.sh --apply-realm, or keycloak_config apply)")
        return 0
    if not a.yes and sys.stdin.isatty() and input("Apply this plan? type APPLY: ").strip() != "APPLY":
        print("[keycloak-config] aborted")
        return 1
    try:
        for s in steps:
            s.run()
    except KeycloakError as e:
        print(f"[keycloak-config] APPLY FAILED at '{s.desc}': {e}", file=sys.stderr)
        return 1
    print(f"[keycloak-config] applied {len(actionable)} change(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
