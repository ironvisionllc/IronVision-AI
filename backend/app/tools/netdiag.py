"""Network diagnostic (stdlib only, read-only): where am I, which networks, does each name resolve here.

    python -m app.tools.netdiag [--out FILE] HOST [HOST ...]

Run by recover.sh inside the recovery container AND inside the rehearsal-backend container before any rehearsal probe, so a
"Temporary failure in name resolution" is explained (container, resolv.conf, per-name result) instead of guessed."""
import json
import socket
import sys
from pathlib import Path


def lookup(host: str) -> dict:
    try:
        return {"host": host, "resolves": True, "addresses": sorted({i[4][0] for i in socket.getaddrinfo(host, None)})}
    except OSError as exc:
        return {"host": host, "resolves": False, "error": f"{type(exc).__name__}: {exc}"}


def main(argv: list[str]) -> int:
    out = None
    if "--out" in argv:
        i = argv.index("--out")
        out, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    rc = Path("/etc/resolv.conf")
    d = {"container": socket.gethostname(), "nameservers": [ln.split()[1] for ln in rc.read_text().splitlines() if ln.startswith("nameserver")] if rc.is_file() else [],
         "lookups": [lookup(h) for h in argv if h]}
    s = json.dumps(d, indent=1)
    if out:
        Path(out).write_text(s)
    print(s)
    for x in d["lookups"]:
        print(f"[netdiag] {d['container']}: {x['host']} → {', '.join(x['addresses']) if x['resolves'] else 'NOT RESOLVABLE (' + x['error'] + ')'}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
