#!/usr/bin/env python3
"""Image digest pinning (stdlib only).
  python3 scripts/image_digest.py resolve REF            print the multi-arch index digest + platform digests from the registry
  python3 scripts/image_digest.py check REF RUNNING_REPO_DIGESTS...   is the running image the pinned one?
check accepts the pinned index digest itself or any platform manifest digest listed in that index. Exit 0 match, 1 mismatch,
3 REF is tag-only (no @sha256 pin), 4 registry unreachable (could not resolve platform digests)."""
import json
import sys
import urllib.request

ACCEPT = ("application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, "
          "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json")


def split(ref: str) -> tuple[str, str, str, str | None]:
    ref, _, digest = ref.partition("@")
    name, _, tag = ref.rpartition(":") if ":" in ref.split("/")[-1] else (ref, "", "latest")
    first = name.split("/")[0]
    if "." in first or ":" in first:
        reg, repo = first, name.split("/", 1)[1]
    else:
        reg, repo = "registry-1.docker.io", name if "/" in name else f"library/{name}"
    return reg, repo, tag, digest or None


def _get(url: str, headers: dict) -> tuple[dict, str]:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.load(r), r.headers.get("Docker-Content-Digest") or ""


def resolve(ref: str) -> dict:
    reg, repo, tag, digest = split(ref)
    h = {"Accept": ACCEPT}
    if reg == "registry-1.docker.io":
        with urllib.request.urlopen(f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull", timeout=20) as r:
            h["Authorization"] = "Bearer " + json.load(r)["token"]
    body, dg = _get(f"https://{reg}/v2/{repo}/manifests/{digest or tag}", h)
    return {"index": digest or dg, "platforms": [m["digest"] for m in body.get("manifests", [])]}


def matches(pinned: str, platforms: list[str], repo_digests: list[str]) -> bool:
    got = {d.split("@", 1)[-1] for d in repo_digests}
    return pinned in got or bool(got & set(platforms))


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "resolve":
        print(json.dumps(resolve(argv[1])))
        return 0
    if len(argv) >= 2 and argv[0] == "check":
        ref, running = argv[1], [x for a in argv[2:] for x in a.split()]
        pinned = split(ref)[3]
        if not pinned:
            print(f"TAG-ONLY {ref}: not pinned by digest")
            return 3
        if matches(pinned, [], running):
            print(f"OK {ref}: running image is the pinned digest")
            return 0
        try:
            plats = resolve(ref)["platforms"]
        except OSError as e:
            print(f"UNKNOWN {ref}: registry unreachable ({e}); running {running}")
            return 4
        if matches(pinned, plats, running):
            print(f"OK {ref}: running image is a platform manifest of the pinned index")
            return 0
        print(f"MISMATCH {ref}: running {running or ['<no repo digest>']} is not the pinned image")
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
