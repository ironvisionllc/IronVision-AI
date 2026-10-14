"""Upload hardening: size limit, extension allow-list, magic-byte checks, zip-bomb guard, optional malware scanning."""
import io
import os
import socket
import struct
import zipfile

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "50")) * 1024 * 1024
ZIP_MAX_RATIO, ZIP_MAX_TOTAL, ZIP_MAX_MEMBERS = 100, 200 * 1024 * 1024, 1000

KINDS = {
    "scan": {".nessus", ".ckl", ".cklb", ".csv", ".xml", ".sarif", ".json"},
    "policy": {".pdf", ".docx", ".txt"},
    "evidence": {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".json", ".csv", ".xml"},
}


class UploadRejected(ValueError):
    pass


def _ext(name: str) -> str:
    return os.path.splitext(name.lower())[1]


def _magic_ok(ext: str, data: bytes) -> bool:
    head = data[:8]
    if ext == ".pdf":
        return head.startswith(b"%PDF-")
    if ext == ".docx":
        return head.startswith(b"PK\x03\x04")
    if ext == ".png":
        return head.startswith(b"\x89PNG")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".cklb":
        return data.lstrip()[:1] in (b"{", b"[") or head.startswith(b"PK\x03\x04")
    if ext in (".nessus", ".ckl", ".xml"):
        return data.lstrip()[:1] == b"<" or data.startswith(b"\xef\xbb\xbf<")
    if ext in (".txt", ".csv", ".json", ".sarif"):
        return b"\x00" not in data[:4096]
    return False


def check_zip(data: bytes) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UploadRejected("Corrupt ZIP container") from exc
    infos = zf.infolist()
    total = sum(i.file_size for i in infos)
    if len(infos) > ZIP_MAX_MEMBERS or total > ZIP_MAX_TOTAL or (total / max(len(data), 1)) > ZIP_MAX_RATIO:
        raise UploadRejected("Archive rejected: possible zip bomb (too many members or excessive compression ratio)")
    if any(i.filename.startswith("/") or ".." in i.filename for i in infos):
        raise UploadRejected("Archive rejected: unsafe member path")


def scan(data: bytes) -> str:
    """UPLOAD_SCANNER=clamav uses clamd INSTREAM (CLAMAV_HOST/CLAMAV_PORT); none skips scanning (recorded as 'not_scanned')."""
    mode = os.environ.get("UPLOAD_SCANNER", "none")
    if mode == "none":
        return "not_scanned"
    if mode != "clamav":
        raise RuntimeError(f"Unsupported UPLOAD_SCANNER {mode}")
    with socket.create_connection((os.environ.get("CLAMAV_HOST", "clamav"), int(os.environ.get("CLAMAV_PORT", "3310"))), timeout=30) as s:
        s.sendall(b"zINSTREAM\0")
        for i in range(0, len(data), 65536):
            chunk = data[i:i + 65536]
            s.sendall(struct.pack("!L", len(chunk)) + chunk)
        s.sendall(struct.pack("!L", 0))
        reply = s.recv(4096).decode(errors="ignore")
    if "FOUND" in reply:
        raise UploadRejected(f"Malware scanner rejected file: {reply.strip()}")
    return "clean"


def validate_upload(file_name: str, data: bytes, kind: str) -> str:
    if not data:
        raise UploadRejected("Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected(f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    ext = _ext(file_name)
    if ext not in KINDS[kind]:
        raise UploadRejected(f"File type {ext or '(none)'} not allowed here. Allowed: {', '.join(sorted(KINDS[kind]))}")
    if not _magic_ok(ext, data):
        raise UploadRejected(f"File content does not match its {ext} extension")
    if data.startswith(b"PK\x03\x04"):
        check_zip(data)
    return scan(data)
