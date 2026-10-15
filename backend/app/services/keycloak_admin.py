"""Minimal Keycloak Admin REST client (httpx). Auth order: configurator service account (client_credentials) → bootstrap admin.

Env: KEYCLOAK_URL (internal, e.g. http://keycloak:8080), KEYCLOAK_CONFIGURATOR_CLIENT_ID (ironvision-configurator),
KEYCLOAK_CONFIGURATOR_CLIENT_SECRET, KC_BOOTSTRAP_ADMIN_USERNAME / KC_BOOTSTRAP_ADMIN_PASSWORD (first run only).
"""
import os

import httpx


class KeycloakError(RuntimeError):
    pass


class KeycloakAdmin:
    def __init__(self, base: str | None = None, http: httpx.Client | None = None):
        self.base = (base or os.environ["KEYCLOAK_URL"]).rstrip("/")
        self.http = http or httpx.Client(timeout=20)
        self.mode = ""
        self._token = ""

    # --- auth ---
    def _grant(self, data: dict) -> str | None:
        r = self.http.post(f"{self.base}/realms/master/protocol/openid-connect/token", data=data)
        return r.json()["access_token"] if r.status_code == 200 else None

    def login(self) -> "KeycloakAdmin":
        sa_secret = os.environ.get("KEYCLOAK_CONFIGURATOR_CLIENT_SECRET")
        if sa_secret:
            t = self._grant({"grant_type": "client_credentials", "client_id": configurator_id(), "client_secret": sa_secret})
            if t:
                self._token, self.mode = t, "service-account"
                return self
        user, pw = os.environ.get("KC_BOOTSTRAP_ADMIN_USERNAME"), os.environ.get("KC_BOOTSTRAP_ADMIN_PASSWORD")
        if user and pw:
            t = self._grant({"grant_type": "password", "client_id": "admin-cli", "username": user, "password": pw})
            if t:
                self._token, self.mode = t, "bootstrap-admin"
                return self
        raise KeycloakError("cannot authenticate to the Keycloak admin API: configurator service account and bootstrap admin both "
                            "rejected (see docs/KEYCLOAK.md → 'Admin API access')")

    def login_service(self, realm: str, client_id: str, secret: str) -> "KeycloakAdmin":
        """Service account of an application realm (admin REST limited to that realm's realm-management roles)."""
        t = self._grant_at(realm, {"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
        if not t:
            raise KeycloakError(f"service account {client_id} rejected by realm {realm}")
        self._token, self.mode = t, "realm-service-account"
        return self

    def _grant_at(self, realm: str, data: dict) -> str | None:
        r = self.http.post(f"{self.base}/realms/{realm}/protocol/openid-connect/token", data=data)
        return r.json()["access_token"] if r.status_code == 200 else None

    # --- http ---
    def req(self, method: str, path: str, ok=(200, 201, 204), **kw):
        r = self.http.request(method, f"{self.base}/admin/realms{path}", headers={"Authorization": f"Bearer {self._token}"}, **kw)
        if r.status_code not in ok:
            raise KeycloakError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r

    def get(self, path: str, **kw):
        r = self.req("GET", path, ok=(200, 404), **kw)
        return None if r.status_code == 404 else r.json()

    def post(self, path: str, json) -> httpx.Response:
        return self.req("POST", path, json=json)

    def put(self, path: str, json) -> httpx.Response:
        return self.req("PUT", path, json=json)

    def delete(self, path: str) -> httpx.Response:
        return self.req("DELETE", path)

    # --- helpers ---
    def realm(self, realm: str) -> dict | None:
        return self.get(f"/{realm}")

    def client(self, realm: str, client_id: str) -> dict | None:
        rows = self.get(f"/{realm}/clients", params={"clientId": client_id}) or []
        return rows[0] if rows else None

    def users_by(self, realm: str, **params) -> list[dict]:
        return self.get(f"/{realm}/users", params={**params, "exact": "true", "briefRepresentation": "false"}) or []

    def user(self, realm: str, uid: str) -> dict | None:
        return self.get(f"/{realm}/users/{uid}")

    def set_password(self, realm: str, uid: str, password: str, temporary: bool) -> None:
        self.put(f"/{realm}/users/{uid}/reset-password", {"type": "password", "value": password, "temporary": temporary})

    def credentials(self, realm: str, uid: str) -> list[dict]:
        return self.get(f"/{realm}/users/{uid}/credentials") or []

    def logout_user(self, realm: str, uid: str) -> None:
        self.post(f"/{realm}/users/{uid}/logout", None)


def configurator_id() -> str:
    return os.environ.get("KEYCLOAK_CONFIGURATOR_CLIENT_ID", "ironvision-configurator")


def created_id(resp: httpx.Response) -> str:
    return resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]
