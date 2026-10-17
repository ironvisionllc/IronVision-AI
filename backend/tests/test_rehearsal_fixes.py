"""Droplet rehearsal failures (commit 9b7b7f7): embedded-python SyntaxError on python3 3.12, frontend URL audit false positives,
probe DNS failure, evidence key/SHA mapping, plan-hash / tool-version gate. No Docker daemon here: the DNS case is reproduced by
probing an unresolvable compose service name from a process where it does not resolve (what the old probe did)."""
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PY312 = sorted(glob.glob("/root/.local/share/uv/python/cpython-3.12.*/bin/python3.12"))
INTERPRETERS = [sys.executable] + PY312[:1]
OLD_AUDIT_SNIPPET = '''import json,sys,re
c=json.load(sys.stdin)
for n,s in sorted(c["services"].items()):
    print(f"  {n}: image={s.get(\\"image\\",\\"(build)\\")}")
'''


def snippets() -> list[tuple[str, str]]:
    """Every python3 -c '…' / python3 - <<'EOF' … EOF in recover.sh and scripts/*.sh, unquoted the way bash passes it."""
    out = []
    for f in [ROOT / "recover.sh", *sorted((ROOT / "scripts").glob("*.sh"))]:
        t = f.read_text()
        for m in re.finditer(r"python3? -c '([^']*)'", t):
            out.append((f"{f.name}:-c'", m.group(1)))
        for m in re.finditer(r'python3? -c "((?:[^"\\]|\\.)*)"', t):
            s = m.group(1).replace('\\"', '"').replace("\\$", "$").replace("\\\\", "\\")
            out.append((f"{f.name}:-c\"", re.sub(r"\$\{?[A-Za-z_0-9]+\}?", "0", s)))
        for m in re.finditer(r"python3? - [^\n]*<<'?(\w+)'?\n(.*?)\n\1\n", t, re.S):
            out.append((f"{f.name}:heredoc", m.group(2)))
    return out


@pytest.mark.parametrize("py", INTERPRETERS)
def test_every_embedded_python_snippet_compiles_on_host_interpreters(py, tmp_path):
    found = snippets()
    assert len(found) >= 8
    for name, code in found:
        p = tmp_path / "s.py"
        p.write_text(code)
        r = subprocess.run([py, "-c", "import sys;compile(open(sys.argv[1]).read(),sys.argv[1],'exec')", str(p)], capture_output=True, text=True)
        assert r.returncode == 0, f"{name} does not compile on {py}: {r.stderr[-400:]}"


@pytest.mark.parametrize("py", ["/usr/local/bin/python3.11"] + PY312[:1])
def test_all_scripts_and_app_modules_compile_on_311_image_and_312_host(py):
    """The recovery image runs 3.11, the Droplet host 3.12: f-string backslash rules differ (PEP 701) – compile with both."""
    files = sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "backend" / "app").rglob("*.py"))
    code = "import sys\nfor f in sys.argv[1:]:\n    compile(open(f).read(), f, 'exec')"
    r = subprocess.run([py, "-c", code, *map(str, files)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-600:]


@pytest.mark.skipif(not PY312, reason="python3.12 (uv) not installed")
def test_old_inline_audit_snippet_reproduces_the_droplet_syntaxerror_on_312(tmp_path):
    p = tmp_path / "old.py"
    p.write_text(OLD_AUDIT_SNIPPET)
    r = subprocess.run([PY312[0], str(p)], input="{}", capture_output=True, text=True)
    assert "SyntaxError" in r.stderr and "line continuation" in r.stderr


@pytest.mark.parametrize("py", INTERPRETERS)
def test_compose_audit_script_runs_and_redacts(py):
    cfg = {"services": {"backend": {"image": "x/backend:1", "ports": [{"published": "8001", "host_ip": "127.0.0.1", "target": 8001}],
                                    "environment": {"DATABASE_URL": "postgresql+psycopg://u:topsecret@postgres/db", "S3_SECRET_ACCESS_KEY": "s3cr3t",
                                                    "APP_DOMAIN": "demo.ironvisionai.com", "S3_BUCKET": "evidence"}, "networks": {"default": None}},
                        "frontend": {"build": {}}}}
    r = subprocess.run([py, "-I", "-S", str(ROOT / "scripts/compose_audit.py")], input=json.dumps(cfg), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "backend: image=x/backend:1 ports=['127.0.0.1:8001->8001']" in r.stdout and "frontend: image=(build)" in r.stdout
    assert "topsecret" not in r.stdout and "s3cr3t" not in r.stdout and "u:***@postgres" in r.stdout


def _fe(tmp_path, js: str) -> subprocess.CompletedProcess:
    (tmp_path / "main.js").write_text(js)
    return subprocess.run([sys.executable, str(ROOT / "scripts/frontend_url_audit.py"), str(tmp_path)], capture_output=True, text=True)


def test_frontend_audit_planted_localhost_api_base_fails(tmp_path):
    r = _fe(tmp_path, 'const e={baseURL:"http://localhost:8001/api/v1"};axios.create(e);')
    assert r.returncode == 1 and "FAIL http://localhost:8001/api/v1" in r.stdout


@pytest.mark.parametrize("js", ['var u="https://preview-x.preview.emergentagent.com";fetch(u+"/api")', 'new WebSocket("ws://127.0.0.1:8001/ws")'])
def test_frontend_audit_other_dev_targets_fail(tmp_path, js):
    assert _fe(tmp_path, js).returncode == 1


def test_frontend_audit_library_doc_links_and_parsing_bases_pass_as_info(tmp_path):
    js = ('throw Error("Minified React error #"+e+"; visit https://react.dev/errors/"+e);'
          'console.warn("see https://reactrouter.com/en/main/routers/picking-a-router.");x="https://redux.js.org/Errors?code="+e;'
          'y="https://redux-toolkit.js.org/Errors?code="+e;z="https://bit.ly/3cXEKWf";'
          'function w(e){let r="http://localhost";e&&(r="null"!==e.location.origin?e.location.origin:e.location.href);return new URL(t,r)}'
          'var re=new URL("http://localhost");Sr=br&&window.location.href||"http://localhost"')
    r = _fe(tmp_path, js)
    assert r.returncode == 0, r.stdout
    for h in ("react.dev", "reactrouter.com", "redux.js.org", "redux-toolkit.js.org", "bit.ly", "http://localhost "):
        assert re.search(rf"INFO .*{re.escape(h.strip())}", r.stdout), h
    assert "0 FAIL" in r.stdout


# ---------------- evidence integrity
def _m(statuses):
    from app.tools import recovery as rv
    ev = [{"id": i, "storage_key": f"ev/{i}.pdf", "sha256": f"{i:064x}", "status": s} for i, s in enumerate(statuses)]
    return rv, {"evidence": ev, "orphans": ["evidence/extra.txt"], "extra": [{"key": "evidence/extra.txt", "bytes": 3, "sha256": f"{1:064x}", "kind": "x"}]}


def test_key_variants_find_bucket_prefixed_and_url_style_keys():
    from app.tools import recovery as rv
    idx = {"evidence/sys1/a.pdf": 1, "b%20c.pdf": 2, "plain/k.txt": 3}
    assert rv._locate("evidence/sys1/a.pdf", idx, {"evidence"})[0] == "evidence/sys1/a.pdf"
    assert rv._locate("s3://legacy-bucket/evidence/sys1/a.pdf", idx, set())[0] == "evidence/sys1/a.pdf"
    assert rv._locate("/plain/k.txt", idx, set())[0] == "plain/k.txt"
    assert rv._locate("sys1/a.pdf", idx, set())[0] == "evidence/sys1/a.pdf"         # exported per bucket: <bucket>/<key>
    assert rv._locate("evidence/plain/k.txt", idx, {"evidence"}) == ("plain/k.txt", "bucket prefix 'evidence/' stripped")
    assert rv._locate("nope.pdf", idx, {"evidence"}) == (None, None)


def test_integrity_complete_only_when_all_verified():
    rv, m = _m(["recovered", "present_in_production", "recovered"])
    ig = rv.evidence_integrity(m, {"index": {"a": 0, "b": 0}})
    assert ig["complete"] and ig["verified"] == 3 and ig["exceptions_hash"] is None and ig["orphans"] == 1
    rv.evidence_gate(ig, None)
    with pytest.raises(rv.RecoveryError, match="nothing to acknowledge"):
        rv.evidence_gate(ig, "abc")


def test_integrity_exceptions_listed_and_require_exact_ack():
    rv, m = _m(["recovered", "missing", "hash_mismatch", "unreadable"])
    m["evidence"][2]["actual_sha256"] = "f" * 64
    ig = rv.evidence_integrity(m, {"index": {}})
    assert (ig["verified"], ig["missing"], ig["mismatch"], ig["unreadable"], ig["complete"]) == (1, 1, 1, 1, False)
    st = {r["storage_key"]: r for r in ig["per_record"]}
    assert st["ev/1.pdf"]["status"] == "MISSING" and "evidence/extra.txt" in st["ev/1.pdf"]["hint"]      # same bytes elsewhere: NOT counted
    assert st["ev/2.pdf"]["status"] == "MISMATCH" and st["ev/2.pdf"]["actual_sha256"] == "f" * 64
    for bad in (None, "0" * 16):
        with pytest.raises(rv.RecoveryError, match="INCOMPLETE"):
            rv.evidence_gate(ig, bad)
    rv.evidence_gate(ig, ig["exceptions_hash"])


# ---------------- plan hash / tool version gate
GOOD = {"plan_hash": "aaaa", "passed": True, "failures": [], "probe_passed": True, "e2e_ran": True}


@pytest.mark.parametrize("reh,msg", [
    ({**GOOD, "plan_hash": "e4c831f4a432b3b4", "tool_version": None}, "no rehearsal recorded"),
    ({**GOOD}, "pre-versioning"),
    ({**GOOD, "tool_version": "2026.10.16-old"}, "tool version 2026.10.16-old"),
    ({**GOOD, "tool_version": "CUR", "passed": False, "failures": ["rehearsal backend probe failed"]}, "did not pass"),
    ({**GOOD, "tool_version": "CUR", "probe_passed": False}, "no passing backend probe"),
    ({**GOOD, "tool_version": "CUR", "e2e_ran": False}, "no passing backend probe"),
])
def test_cutover_refuses_unpassed_or_old_rehearsals(reh, msg):
    from app.tools import recovery as rv
    reh = {**reh, "tool_version": rv.TOOL_VERSION if reh.get("tool_version") == "CUR" else reh.get("tool_version")}
    with pytest.raises(rv.RecoveryError, match=msg):
        rv.rehearsal_gate(reh, "aaaa")
    rv.rehearsal_gate({**GOOD, "tool_version": rv.TOOL_VERSION}, "aaaa")


def test_plan_hash_depends_on_tool_version(monkeypatch):
    from app.tools import recovery as rv
    for f, v in (("counts", {}), ("inputs", {}), ("revision", "0013"), ("catalog_fingerprint", {}), ("live_url", lambda: "postgresql://x@h/ironvision")):
        monkeypatch.setattr(rv, f, (lambda *a, _v=v: _v) if not callable(v) else v)
    h1 = rv.plan()["plan_hash"]
    monkeypatch.setattr(rv, "TOOL_VERSION", "2026.10.16-old")
    assert rv.plan()["plan_hash"] != h1 and h1 != "e4c831f4a432b3b4"


# ---------------- DNS reproduction: probe where the compose name does not resolve
def test_probe_from_a_process_where_the_service_name_does_not_resolve_fails_with_full_diagnostics(tmp_path):
    rdir = tmp_path / "rec"
    rdir.mkdir()
    (rdir / "rehearsal-20261017t000000.json").write_text(json.dumps({"ts": "20261017t000000", "plan_hash": "aaaa", "failures": [], "passed": True}))
    env = {"PATH": os.environ["PATH"], "HOME": "/tmp", "RECOVERY_DIR": str(rdir), "IRONVISION_SELFCHECK": "1"}
    nd = subprocess.run([sys.executable, "-m", "app.tools.netdiag", "--out", str(rdir / "nd.json"), "rehearsal-backend"], cwd=ROOT / "backend",
                        env=env, capture_output=True, text=True)
    d = json.loads((rdir / "nd.json").read_text())
    assert d["lookups"][0]["resolves"] is False and "NOT RESOLVABLE" in nd.stderr
    r = subprocess.run([sys.executable, "-m", "app.tools.recovery", "rehearse-probe", "--url", "http://rehearsal-backend:8001", "--e2e",
                        "--where", "separate container not attached to the backend's network", "--netdiag", str(rdir / "nd.json")],
                       cwd=ROOT / "backend", env=env, capture_output=True, text=True, timeout=300)
    body = json.loads((rdir / "rehearsal-20261017t000000.json").read_text())
    assert r.returncode == 1 and body["passed"] is False and body["probe_passed"] is False
    assert all(str(v).startswith("error ConnectError") for k, v in body["backend_probe"].items() if k.startswith("/"))
    steps = body["backend_probe"]["e2e_sso"]["steps"]
    assert any(s["step"].startswith("aborted: ConnectError") and not s["pass"] for s in steps)
    assert Path(body["backend_probe"]["e2e_sso"]["stdout_stderr"]).is_file() and Path(body["backend_probe"]["e2e_sso"]["transcript"]).is_file()
    assert body["probe_context"]["netdiag"]["lookups"][0]["host"] == "rehearsal-backend"
    md = (rdir / "rehearsal-20261017t000000.md").read_text()
    assert "rehearsal backend probe failed (separate container not attached" in md


def test_e2e_redaction():
    sys.path.insert(0, str(ROOT / "scripts"))
    import e2e_sso
    s = e2e_sso.redact('GET https://kc/x?code=abc&state=def&session_state=ghi → 302 {"access_token": "eyJx", "id_token": "eyJy"} Bearer eyJz password=hunter2')
    for leak in ("abc", "def", "ghi", "eyJx", "eyJy", "eyJz", "hunter2"):
        assert leak not in s
