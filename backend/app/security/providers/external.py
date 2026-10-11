from app.security.providers.base import AuthenticationError, AuthProvider


class ExternalProvider(AuthProvider):
    """Placeholder used when password sign-in is disabled; sign-in happens via /auth/oidc/* or /auth/mtls/login."""
    is_simulated = False

    def __init__(self, enabled: list[str]):
        self.name = enabled[0] if enabled else "none"
        self.display_label = {"oidc": "Enterprise single sign-on (OIDC)", "mtls_header": "CAC/PIV via trusted reverse proxy"}.get(self.name, self.name)

    def authenticate(self, db, credentials):
        raise AuthenticationError("password_signin_disabled")
