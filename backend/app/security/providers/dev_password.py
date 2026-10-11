from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthIdentity
from app.security.passwords import verify_password
from app.security.providers.base import AuthenticatedPrincipal, AuthenticationError, AuthProvider

_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO5Q7Fq4c0N1Yb6cX9y3wJb7Xh1u0m6aW"


class DevPasswordProvider(AuthProvider):
    name = "dev_password"
    display_label = "DEVELOPMENT AUTHENTICATION – SIMULATED, NOT CAC/PIV"
    is_simulated = True

    def authenticate(self, db: Session, credentials: dict) -> AuthenticatedPrincipal:
        email = (credentials.get("email") or "").strip().lower()
        password = credentials.get("password") or ""
        identity = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == self.name, AuthIdentity.subject == email))
        if identity is None or not identity.secret_hash:
            verify_password(password, _DUMMY_HASH)
            raise AuthenticationError("unknown_subject")
        if not verify_password(password, identity.secret_hash):
            raise AuthenticationError("bad_password")
        identity.last_used_at = datetime.now(timezone.utc)
        return AuthenticatedPrincipal(provider=self.name, subject=email, email=email)
