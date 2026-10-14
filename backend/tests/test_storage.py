import boto3
import pytest
from moto import mock_aws

from app.services.storage.base import build_storage

PAYLOAD = b"synthetic evidence artifact \x00\x01"


def _round_trip(store):
    meta = store.put("evidence/test/a.bin", PAYLOAD, "application/octet-stream")
    assert meta.size == len(PAYLOAD) and len(meta.sha256) == 64
    assert store.exists("evidence/test/a.bin")
    assert store.get("evidence/test/a.bin") == PAYLOAD
    store.delete("evidence/test/a.bin")
    assert not store.exists("evidence/test/a.bin")
    assert store.health()["ok"] is True


def test_local_round_trip(tmp_path):
    _round_trip(build_storage("local", root=str(tmp_path)))


def test_local_rejects_path_traversal(tmp_path):
    store = build_storage("local", root=str(tmp_path / "root"))
    with pytest.raises(ValueError):
        store.put("../escape.txt", b"x")


def test_s3_round_trip_moto():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="aegis-test")
        _round_trip(build_storage("s3", bucket="aegis-test", region="us-east-1", access_key_id="test",
                                  secret_access_key="test"))


@pytest.mark.skipif(not __import__("os").environ.get("IV_LIVE_S3_ENDPOINT"), reason="set IV_LIVE_S3_* to run against a real S3 backend (e.g. SeaweedFS)")
def test_s3_round_trip_live():
    import os
    _round_trip(build_storage("s3", bucket=os.environ["IV_LIVE_S3_BUCKET"], endpoint_url=os.environ["IV_LIVE_S3_ENDPOINT"], region="us-east-1",
                              access_key_id=os.environ["IV_LIVE_S3_KEY"], secret_access_key=os.environ["IV_LIVE_S3_SECRET"],
                              addressing_style="path"))
