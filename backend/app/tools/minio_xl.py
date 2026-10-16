"""Read objects from a MinIO single-drive (xl-single) data directory – no MinIO binary needed.

Supported (MinIO on-disk format, xl.meta v1.0 – v1.3): unversioned (null versionId) or versioned objects, EcM=1/EcN=0 (single drive),
inline data (small objects stored inside xl.meta) and part files <obj>/<DataDir>/part.N with streaming bitrot framing
(32-byte HighwayHash per shard block; hashes are skipped – integrity is proven by the evidence SHA-256 instead).
Multiple versions: the newest object version by MTime is read; a newer delete marker is reported (latest_is_delete_marker),
never hidden – the evidence SHA-256 decides whether the bytes count.
Refused with a clear error: erasure-coded multi-drive sets, SSE-encrypted, compressed, delete markers only, legacy xl.json.
LIMITATION: written against the published format; fixtures here are constructed per that format (MinIO binaries are no longer
distributed, so no real MinIO-produced archive could be generated in the pod).
"""
import struct
from pathlib import Path

import msgpack

MAGIC = b"XL2 "
BITROT_HASH = 32


class MinioFormatError(Exception):
    pass


def _versions(raw: bytes) -> tuple[list[dict], bytes]:
    if raw[:4] != MAGIC:
        raise MinioFormatError("not an xl.meta file (missing 'XL2 ' magic; legacy xl.json is not supported)")
    major, minor = struct.unpack("<HH", raw[4:8])
    if major != 1 or minor > 3:
        raise MinioFormatError(f"unsupported xl.meta version {major}.{minor} (supported: 1.0 – 1.3)")
    up = msgpack.Unpacker(raw=False, strict_map_key=False)
    up.feed(raw[8:])
    first = up.unpack()
    if isinstance(first, dict):  # v1.0: the xlMetaV2 struct itself, {"Versions": [...]}
        return list(first.get("Versions") or []), raw[8 + up.tell():]
    pos = up.tell()
    try:  # v1.1+: indexed block, then a CRC (uint32), then optional inline data
        crc = up.unpack()
        if isinstance(crc, int):
            pos = up.tell()
    except msgpack.OutOfData:
        pass
    inline = raw[8 + pos:]
    inner = msgpack.Unpacker(raw=False, strict_map_key=False)
    inner.feed(first)
    _hdr_ver, _meta_ver, n = inner.unpack(), inner.unpack(), inner.unpack()
    out = []
    for _ in range(n):
        _vhdr = inner.unpack()
        out.append(msgpack.unpackb(inner.unpack(), raw=False, strict_map_key=False))
    return out, inline


def _mtime(v: dict) -> int:
    return int((v.get("V2Obj") or v.get("DelObj") or {}).get("MTime") or 0)


def describe(obj_dir: Path) -> dict:
    versions, _ = _versions((obj_dir / "xl.meta").read_bytes())
    vs = sorted(versions, key=_mtime, reverse=True)
    objs = [v for v in vs if v.get("Type") == 1 and v.get("V2Obj")]
    return {"versions": len(vs), "object_versions": len(objs), "delete_markers": sum(1 for v in vs if v.get("Type") == 2),
            "latest_is_delete_marker": bool(vs) and vs[0].get("Type") == 2,
            "version_id": _uuid_str(objs[0]["V2Obj"].get("ID")) if objs else None}


def _inline_map(inline: bytes) -> dict:
    if not inline:
        return {}
    if inline[0] != 1:
        raise MinioFormatError(f"unsupported inline-data version {inline[0]}")
    return msgpack.unpackb(inline[1:], raw=False, strict_map_key=False)


def _unframe(raw: bytes, size: int, shard: int) -> bytes:
    out, pos = bytearray(), 0
    while len(out) < size:
        pos += BITROT_HASH
        n = min(shard, size - len(out))
        if pos + n > len(raw):
            raise MinioFormatError("part data truncated")
        out += raw[pos:pos + n]
        pos += n
    return bytes(out)


def _uuid_str(b) -> str:
    import uuid
    return str(uuid.UUID(bytes=bytes(b))) if b and any(bytes(b)) else "null"


def read_object(obj_dir: Path) -> bytes:
    versions, inline = _versions((obj_dir / "xl.meta").read_bytes())
    objs = sorted((v for v in versions if v.get("Type") == 1 and v.get("V2Obj")), key=_mtime, reverse=True)
    if not objs:
        raise MinioFormatError("no object version (delete marker or legacy object only)")
    o = objs[0]["V2Obj"]  # newest object version by MTime (on-disk order is not trusted)
    if o.get("EcM", 1) != 1 or o.get("EcN", 0) != 0:
        raise MinioFormatError(f"erasure-coded object (EcM={o.get('EcM')}, EcN={o.get('EcN')}): only single-drive xl-single is supported")
    meta_sys = {k.lower(): v for k, v in (o.get("MetaSys") or {}).items()}
    if any("server-side-encryption" in k or k.endswith("-sealed-key") for k in meta_sys):
        raise MinioFormatError("SSE-encrypted object: refusing (decryption keys are not part of the backup)")
    if any("compression" in k for k in meta_sys):
        raise MinioFormatError("compressed object: refusing (MinIO S2 compression not supported)")
    shard = int(o.get("EcBSize") or 1048576)
    if meta_sys.get("x-minio-internal-inline-data") in (b"true", "true"):
        data = _inline_map(inline).get(_uuid_str(o.get("ID")))
        if data is None:
            raise MinioFormatError("inline data missing for version")
        return _unframe(bytes(data), int(o["Size"]), shard)
    ddir = obj_dir / _uuid_str(o.get("DDir"))
    out = bytearray()
    for num, size in zip(o.get("PartNums") or [1], o.get("PartASizes") or o.get("PartSizes") or [o["Size"]]):
        p = ddir / f"part.{num}"
        if not p.exists():
            raise MinioFormatError(f"missing {p.relative_to(obj_dir.parent)}")
        out += _unframe(p.read_bytes(), int(size), shard)
    return bytes(out)


def check_format(root: Path) -> str:
    """xl-single → ok. Multi-drive erasure sets → refuse."""
    import json
    f = next(iter(root.rglob(".minio.sys/format.json")), None)
    if f is None:
        return "no .minio.sys/format.json (assuming xl-single)"
    j = json.loads(f.read_text())
    fmt = j.get("format")
    sets = (j.get("xl") or {}).get("sets") or []
    if fmt == "xl" and sum(len(s) for s in sets) > 1:
        raise MinioFormatError(f"erasure-coded multi-drive MinIO ({sum(len(s) for s in sets)} drives): back up via 'mc mirror' instead")
    return f"format {fmt}"
