from abc import ABC, abstractmethod
from functools import lru_cache

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings


class AuthenticationError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class AuthenticatedPrincipal(BaseModel):
    """Provider-neutral result of authentication; mapped to a local user via auth_identities(provider, subject)."""

    provider: str
    subject: str
    email: str | None = None
    claims: dict = {}


class AuthProvider(ABC):
    """Authentication only. Authorization (RBAC) never lives here."""

    name: str
    display_label: str
    is_simulated: bool

    @abstractmethod
    def authenticate(self, db: Session, credentials: dict) -> AuthenticatedPrincipal: ...


@lru_cache
def get_auth_provider() -> AuthProvider:
    from app.security.sessions import enabled_providers
    name = "dev_password" if "dev_password" in enabled_providers() else get_settings().auth_provider
    if name == "dev_password" and "dev_password" in enabled_providers():
        from app.security.providers.dev_password import DevPasswordProvider

        return DevPasswordProvider()
    from app.security.providers.external import ExternalProvider
    return ExternalProvider(enabled_providers())
