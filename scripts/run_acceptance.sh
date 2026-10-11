#!/usr/bin/env bash
# Runs the acceptance suite (AT-1..AT-12) in a fresh test DB and writes docs/TEST_RESULTS.md.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
python -m pytest -c pytest.aegis.ini tests/acceptance -v -p no:logging -rA > /tmp/aegis_acceptance.txt 2>&1; ACC=$?
python -m pytest -c pytest.aegis.ini tests -q -p no:logging > /tmp/aegis_full.txt 2>&1; FULL=$?
python3 - "$ACC" "$FULL" <<'EOF'
import re, sys, datetime, pathlib
acc = pathlib.Path("/tmp/aegis_acceptance.txt").read_text(); full = pathlib.Path("/tmp/aegis_full.txt").read_text()
rows = re.findall(r"tests/acceptance/test_acceptance.py::(test_at\d+\w*) (PASSED|FAILED|ERROR)", acc)
doc = {m.group(1): m.group(2).strip() for m in re.finditer(r'def (test_at\d+\w*)\(.*?\n\s+"""(.*?)(?:\n|""")', pathlib.Path("tests/acceptance/test_acceptance.py").read_text(), re.S)}
out = [f"# Test results\n\nGenerated {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')} by `scripts/run_acceptance.sh` (pod run, PostgreSQL 16).\n",
       "## Acceptance suite (AT-1 … AT-12)\n| # | Test | Scenario | Result |\n|---|---|---|---|"]
for name, res in dict(rows).items():
    out.append(f"| {name[7:9]} | `{name}` | {doc.get(name, '')} | **{res}** |")
tail = lambda t: [l for l in t.strip().splitlines() if re.search(r"passed|failed", l)][-1:] or ["(no summary)"]
out += ["", f"Acceptance summary: `{tail(acc)[0]}`", "", "## Full regression suite (`pytest tests`)", f"`{tail(full)[0]}`", "",
        "## Manual persistence check (AT-12, restart)", "1. Create a POA&M milestone in the UI.  2. `docker compose restart backend worker` (pod: `supervisorctl restart backend worker`).",
        "3. Reload the POA&M – the milestone and its audit event are present.  (Automated part: AT-12 disposes the connection pool and reads back via a new engine.)",
        "", "## Not executed here", "- Docker image builds / `docker compose up` (no Docker daemon in the build pod) – see CI workflow and verify_portability.sh.",
        "- OIDC against a real IdP (Keycloak profile provided, untested here); ClamAV scanning (profile provided, untested); GitHub Actions CI (not runnable here)."]
pathlib.Path("../docs/TEST_RESULTS.md").write_text("\n".join(out) + "\n")
print("\n".join(out[:16]))
sys.exit(int(sys.argv[1]) or int(sys.argv[2]))
EOF
