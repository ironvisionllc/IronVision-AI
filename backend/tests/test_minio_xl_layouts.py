"""xl-single reader against fixtures built per MinIO's on-disk format (xl.meta v1.0 – v1.3, inline + part.1, null and real
version IDs, multiple versions, delete markers). LIMITATION: no MinIO binary is downloadable in the pod, so fixtures are
constructed per the published format, not produced by a MinIO RELEASE build."""
import hashlib
import os
import struct
import uuid

import msgpack
import pytest

from app.tools import minio_xl
from app.tools.recovery import classify_extra

SHARD = 1048576


def frame(data: bytes) -> bytes:
    return b"".join(os.urandom(32) + data[i:i + SHARD] for i in range(0, max(len(data), 1), SHARD))


def obj_version(data: bytes, mtime: int, inline: bool, vid: bytes, ddir: uuid.UUID) -> dict:
    return {"Type": 1, "V2Obj": {"ID": vid, "DDir": ddir.bytes, "EcAlgo": 1, "EcM": 1, "EcN": 0, "EcBSize": SHARD, "EcIndex": 1,
                                 "EcDist": [1], "CSumAlgo": 1, "PartNums": [1], "PartSizes": [len(data)], "PartASizes": [len(data)],
                                 "Size": len(data), "MTime": mtime, "MetaSys": {"x-minio-internal-inline-data": b"true"} if inline else {},
                                 "MetaUsr": {"etag": hashlib.md5(data).hexdigest()}}}


def delete_marker(mtime: int) -> dict:
    return {"Type": 2, "DelObj": {"ID": uuid.uuid4().bytes, "MTime": mtime}}


def write(obj_dir, versions: list[tuple[dict, bytes | None, bool]], minor: int = 3, order=None):
    """versions: (version dict, data, inline). Written in `order` (default as given) to prove MTime – not order – decides."""
    obj_dir.mkdir(parents=True)
    vs = [v for v, _, _ in versions]
    vs = [vs[k] for k in order] if order else vs
    inline_map = {}
    for v, data, inline in versions:
        if v["Type"] != 1:
            continue
        vid = str(uuid.UUID(bytes=v["V2Obj"]["ID"])) if any(v["V2Obj"]["ID"]) else "null"
        if inline:
            inline_map[vid] = frame(data)
        else:
            d = obj_dir / str(uuid.UUID(bytes=v["V2Obj"]["DDir"]))
            d.mkdir()
            (d / "part.1").write_bytes(frame(data))
    if minor == 0:
        raw = b"XL2 " + struct.pack("<HH", 1, 0) + msgpack.packb({"Versions": vs})
    else:
        block = msgpack.packb(3) + msgpack.packb(2) + msgpack.packb(len(vs))
        for v in vs:
            block += msgpack.packb(msgpack.packb([b"\0" * 16, 0, b"\0\0\0\0", v["Type"], 0])) + msgpack.packb(msgpack.packb(v))
        raw = b"XL2 " + struct.pack("<HH", 1, minor) + msgpack.packb(block) + msgpack.packb(0xC0FFEE)
    if inline_map:
        raw += bytes([1]) + msgpack.packb(inline_map)
    (obj_dir / "xl.meta").write_bytes(raw)
    return obj_dir


NULL = b"\0" * 16


@pytest.mark.parametrize("minor", [0, 1, 2, 3])
@pytest.mark.parametrize("inline", [True, False])
def test_single_version_null_id_all_format_versions(tmp_path, minor, inline):
    data = os.urandom(3000 if inline else 2 * SHARD + 17)
    d = write(tmp_path / "evidence" / "org" / "a.pdf", [(obj_version(data, 1, inline, NULL, uuid.uuid4()), data, inline)], minor)
    assert minio_xl.read_object(d) == data
    assert minio_xl.describe(d)["version_id"] == "null"


def test_multiple_versions_newest_by_mtime_not_disk_order(tmp_path):
    old, new = b"old bytes", os.urandom(5000)
    v_old = obj_version(old, 100, True, uuid.uuid4().bytes, uuid.uuid4())
    v_new = obj_version(new, 200, False, uuid.uuid4().bytes, uuid.uuid4())
    d = write(tmp_path / "b" / "k", [(v_old, old, True), (v_new, new, False)], order=[0, 1])  # oldest first on disk
    assert minio_xl.read_object(d) == new
    info = minio_xl.describe(d)
    assert info["versions"] == 2 and info["object_versions"] == 2 and not info["latest_is_delete_marker"]


def test_delete_marker_newest_is_reported_and_latest_object_version_read(tmp_path):
    data = b"evidence bytes"
    d = write(tmp_path / "b" / "gone", [(delete_marker(300), None, False), (obj_version(data, 100, True, uuid.uuid4().bytes, uuid.uuid4()), data, True)])
    assert minio_xl.read_object(d) == data
    assert minio_xl.describe(d)["latest_is_delete_marker"] is True


def test_only_delete_markers_and_unsupported_layouts_refused(tmp_path):
    d = write(tmp_path / "b" / "dm", [(delete_marker(1), None, False)])
    with pytest.raises(minio_xl.MinioFormatError, match="delete marker"):
        minio_xl.read_object(d)
    data = b"x" * 10
    for name, patch, msg in (("ec", {"EcM": 2, "EcN": 2}, "erasure-coded"),
                             ("sse", {"MetaSys": {"X-Minio-Internal-Server-Side-Encryption-Sealed-Key": b"k"}}, "SSE-encrypted"),
                             ("cmp", {"MetaSys": {"X-Minio-Internal-compression": b"klauspost/compress/s2"}}, "compressed")):
        v = obj_version(data, 1, False, NULL, uuid.uuid4())
        v["V2Obj"].update(patch)
        with pytest.raises(minio_xl.MinioFormatError, match=msg):
            minio_xl.read_object(write(tmp_path / name / "k", [(v, data, False)]))
    bad = tmp_path / "v4" / "k"
    bad.mkdir(parents=True)
    (bad / "xl.meta").write_bytes(b"XL2 " + struct.pack("<HH", 1, 4))
    with pytest.raises(minio_xl.MinioFormatError, match="unsupported xl.meta version 1.4"):
        minio_xl.read_object(bad)


def test_extra_objects_classified_and_never_counted():
    ev_bytes = b"the real evidence"
    index = {"evidence/_bootstrap/marker": lambda: b"", "evidence/exports/2025-q4.zip": lambda: b"zip",
             "evidence/policies/p1.json": lambda: b"{}", "evidence/copy/of-evidence.pdf": lambda: ev_bytes,
             "evidence/random.bin": lambda: b"r"}
    out = {d["key"]: d["kind"] for d in classify_extra({"index": index}, sorted(index), {hashlib.sha256(ev_bytes).hexdigest(): "org/e1.pdf"})}
    assert out["evidence/_bootstrap/marker"] == "bootstrap marker" and out["evidence/exports/2025-q4.zip"] == "export file"
    assert out["evidence/policies/p1.json"] == "policy upload" and out["evidence/random.bin"] == "not referenced by any evidence record"
    assert out["evidence/copy/of-evidence.pdf"].startswith("same bytes as evidence org/e1.pdf under another key (not counted)")
