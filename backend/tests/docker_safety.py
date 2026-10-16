"""Classifies docker calls recorded by tests/docker_shim.py."""
def destructive_calls(calls: list[str]) -> list[str]:
    """Docker calls that could delete legacy state. `run --rm -v dir:/out` of OUR recovery helper is a bind mount + throwaway container."""
    bad = []
    for c in filter(None, calls):
        t = c.split()
        sub = t[0]
        if sub in ("rm", "rmi", "volume", "system", "prune", "kill") or "prune" in t or " down" in f" {c}":
            bad.append(c)
        elif sub in ("stop", "compose") and ("-v" in t or "--volumes" in t or "rm" in t):
            bad.append(c)
        elif sub == "container" and len(t) > 1 and t[1] in ("rm", "prune"):
            bad.append(c)
        elif sub == "run" and "ironvision/recovery:local" not in t:
            bad.append(c)
    return bad
