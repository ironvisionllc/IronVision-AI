import os
import uuid

from cryptography.fernet import Fernet


class EnvKeySecretStore:
    """Fernet (AES-128-CBC + HMAC-SHA256) using SECRET_STORE_KEY from the environment. Ciphertext is stored in the DB."""
    backend = "env_key"

    def __init__(self, key: str | None = None):
        key = key or os.environ.get("SECRET_STORE_KEY")
        if not key:
            raise RuntimeError("SECRET_STORE_KEY is required to store connector credentials")
        self._f = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._f.decrypt(ciphertext.encode()).decode()


class VaultSecretStore:
    """HashiCorp Vault KV v2. The DB stores only a reference ('vault:<path>'); the secret value lives in Vault.
    Config: VAULT_ADDR, VAULT_TOKEN (or VAULT_ROLE_ID/VAULT_SECRET_ID for AppRole), VAULT_KV_MOUNT, VAULT_KV_PREFIX."""
    backend = "vault"

    def __init__(self):
        import hvac
        self.client = hvac.Client(url=os.environ["VAULT_ADDR"], token=os.environ.get("VAULT_TOKEN"),
                                  namespace=os.environ.get("VAULT_NAMESPACE"))
        if not os.environ.get("VAULT_TOKEN") and os.environ.get("VAULT_ROLE_ID"):
            self.client.auth.approle.login(role_id=os.environ["VAULT_ROLE_ID"], secret_id=os.environ["VAULT_SECRET_ID"])
        self.mount = os.environ.get("VAULT_KV_MOUNT", "secret")
        self.prefix = os.environ.get("VAULT_KV_PREFIX", "aegisrmf")

    def encrypt(self, plaintext: str) -> str:
        path = f"{self.prefix}/{uuid.uuid4()}"
        self.client.secrets.kv.v2.create_or_update_secret(path=path, secret={"value": plaintext}, mount_point=self.mount)
        return f"vault:{path}"

    def decrypt(self, ref: str) -> str:
        if not ref.startswith("vault:"):
            return EnvKeySecretStore().decrypt(ref)  # migrating from env_key: old ciphertext remains readable
        r = self.client.secrets.kv.v2.read_secret_version(path=ref[6:], mount_point=self.mount, raise_on_deleted_version=True)
        return r["data"]["data"]["value"]


def SecretStore(key: str | None = None):  # noqa: N802 – kept as the historical call-site name
    backend = os.environ.get("SECRET_STORE_BACKEND", "env_key")
    if backend == "vault":
        return VaultSecretStore()
    if backend == "env_key":
        return EnvKeySecretStore(key)
    raise RuntimeError(f"Unsupported SECRET_STORE_BACKEND '{backend}' (env_key | vault; AWS Secrets Manager: see docs/SECURITY.md)")
