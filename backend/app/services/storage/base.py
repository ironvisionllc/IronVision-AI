import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    sha256: str
    content_type: str


class StorageService(ABC):
    driver: str

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredObject: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    def health(self) -> dict:
        key = "_health/probe.txt"
        payload = b"aegisrmf-storage-probe"
        self.put(key, payload, "text/plain")
        ok = self.get(key) == payload
        self.delete(key)
        return {"ok": ok, "driver": self.driver}

    @staticmethod
    def _meta(key: str, data: bytes, content_type: str) -> StoredObject:
        return StoredObject(key=key, size=len(data), sha256=hashlib.sha256(data).hexdigest(), content_type=content_type)


def build_storage(driver: str, **opts) -> StorageService:
    if driver == "local":
        from app.services.storage.local import LocalStorage

        return LocalStorage(root=opts["root"])
    if driver == "s3":
        from app.services.storage.s3 import S3Storage

        return S3Storage(**opts)
    raise ValueError(f"Unknown STORAGE_DRIVER '{driver}' (expected 'local' or 's3')")


@lru_cache
def get_storage() -> StorageService:
    s = get_settings()
    if s.storage_driver == "local":
        if not s.storage_local_root:
            raise RuntimeError("STORAGE_LOCAL_ROOT is required for the local storage driver")
        return build_storage("local", root=s.storage_local_root)
    return build_storage(
        s.storage_driver,
        endpoint_url=s.s3_endpoint_url,
        bucket=s.s3_bucket,
        region=s.s3_region,
        access_key_id=s.s3_access_key_id,
        secret_access_key=s.s3_secret_access_key,
        addressing_style=s.s3_addressing_style,
    )
