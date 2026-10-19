#!/usr/bin/env python3
"""Review a keycloak-migrate dry-run report for the demo deploy: ONLY the demo launcher may be linked.
Usage: python3 scripts/demo_link_guard.py REPORT_JSON
Prints one line on stdout: `apply <plan_hash>` · `skip` (launcher already linked). Exit 0 ok · 1 refused (reason on stderr).
Other users (e.g. restored @aegisrmf.demo accounts) are never linked or created here."""
import json
import sys

DEMO_EMAIL = "demo@ironvision.ai"


def decide(report: dict) -> tuple[str, str]:
    rows = report.get("users") or []
    demo = [r for r in rows if r["email"] == DEMO_EMAIL]
    others = [r["email"] for r in rows if r["email"] != DEMO_EMAIL and r["action"].split("+")[-1] == "link"]
    if others:
        return "refuse", f"{len(others)} non-launcher user(s) would be linked by --link – refusing (launcher only): {', '.join(others)}"
    if not demo:
        return "refuse", f"{DEMO_EMAIL} is not in the app database – the demo seed (migrate) did not provision it"
    act = demo[0]["action"]
    if act == "ok":
        return "skip", f"{DEMO_EMAIL} already linked to its Keycloak identity"
    if act == "link":
        return "apply", report["plan_hash"]
    return "refuse", f"{DEMO_EMAIL} plan action is '{act}' ({demo[0].get('reason')}) – fix: scripts/keycloak.sh ENV doctor"


def main(argv: list[str]) -> int:
    kind, detail = decide(json.loads(open(argv[0]).read()))
    if kind == "refuse":
        print(f"demo_link_guard: REFUSED {detail}", file=sys.stderr)
        return 1
    print(f"apply {detail}" if kind == "apply" else "skip")
    print(f"demo_link_guard: {kind.upper()} {'launcher link, plan ' + detail if kind == 'apply' else detail}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
