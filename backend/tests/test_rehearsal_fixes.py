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


# ---------------- scratch SSO: cleanup on failure, no secret output, wrong-password accounting
def test_scratch_sso_cleanup_runs_after_failed_setup_and_never_prints_secrets(tmp_path):
    ts = "20991231t235959"
    env = {**os.environ, "RECOVERY_DIR": str(tmp_path)}
    run = lambda *a: subprocess.run([sys.executable, "-m", "app.tools.recovery", "scratch-sso", *a, "--ts", ts],  # noqa: E731
                                    cwd=ROOT / "backend", env=env, capture_output=True, text=True, timeout=120)
    run("cleanup-finish", "--container-rc", "0")  # leftovers of an earlier aborted test run
    p = run("prepare")
    assert p.returncode == 0, p.stderr
    kc_env = (tmp_path / f"scratch-sso-{ts}" / "kc.env").read_text()
    assert oct((tmp_path / f"scratch-sso-{ts}" / "kc.env").stat().st_mode)[-3:] == "600"
    secret = re.search(r"KC_DB_PASSWORD=(\S+)", kc_env).group(1).strip("'")
    (tmp_path / f"rehearsal-{ts}.json").write_text(json.dumps({"ts": ts, "plan_hash": "x", "failures": [], "passed": True}))
    s = run("setup", "--kc-url", "http://127.0.0.1:1", "--app-url", "http://127.0.0.1:2")    # scratch Keycloak never came up
    assert s.returncode != 0
    f = run("cleanup-finish", "--container-rc", "0")
    body = json.loads((tmp_path / f"rehearsal-{ts}.json").read_text())
    assert body["passed"] is False and any("setup failed" in x for x in body["failures"])
    assert body["scratch_sso"]["cleanup_steps"]["3 scratch Keycloak DB + role dropped"]["status"] == "done"
    assert body["scratch_sso"]["cleanup_steps"]["6 secret files + dir deleted (LAST)"]["status"] == "done"
    assert list(body["scratch_sso"]["cleanup_steps"])[-1].startswith("6 ")   # secret files are removed LAST
    assert not (tmp_path / f"scratch-sso-{ts}").exists()
    from sqlalchemy import create_engine, text

    from app.tools import recovery as rv
    with create_engine(rv.admin_url()).connect() as c:
        assert c.execute(text("select count(*) from pg_roles where rolname = :r"), {"r": f"rec_kc_{ts}"}).scalar() == 0
        assert c.execute(text("select count(*) from pg_database where datname = :r"), {"r": f"rec_kc_{ts}"}).scalar() == 0
    for blob in [p.stdout + p.stderr, s.stdout + s.stderr, f.stdout + f.stderr, *(x.read_text() for x in tmp_path.rglob("*") if x.is_file())]:
        assert secret not in blob


def _fake_e2e(monkeypatch, wrong_accepted: bool, right_accepted: bool):
    import httpx
    sys.path.insert(0, str(ROOT / "scripts"))
    import e2e_sso as e
    e.R.clear()
    app = httpx.Client(base_url="http://reh", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"oidc_enabled": True, "demo_login_enabled": False})))
    monkeypatch.setattr(e, "client", lambda **kw: app)

    def drive(_app, _b, _start, fields):
        ok = right_accepted if not fields["password"].endswith("-wrong") else wrong_accepted
        path = e.CALLBACK if ok else "/realms/x/login-actions/authenticate"
        return httpx.Response(302 if ok else 200, headers={"location": "/c?oidc_code=1"} if ok else {},
                              request=httpx.Request("GET", f"http://reh{path}"))
    monkeypatch.setattr(e, "drive", drive)
    monkeypatch.setattr(e, "exchange", lambda *_: None)
    monkeypatch.setenv("E2E_PASSWORD", "pw")
    a = type("A", (), {"base": "http://reh", "user": "u", "insecure_cookies": False, "no_wrong_password": False, "demo": False,
                       "protected": "/p", "restricted": "/r", "register": False})()
    e.run(a)
    return {n: ok for n, ok, _ in e.R}


def test_wrong_password_accepted_by_keycloak_is_a_fail_not_a_pass(monkeypatch):
    st = _fake_e2e(monkeypatch, wrong_accepted=True, right_accepted=True)
    assert st["negative: wrong password rejected by Keycloak (expected rejection, NOT a login)"] is False


def test_rejected_positive_login_is_a_fail(monkeypatch):
    st = _fake_e2e(monkeypatch, wrong_accepted=False, right_accepted=False)
    assert st["negative: wrong password rejected by Keycloak (expected rejection, NOT a login)"] is True
    assert st["login: Keycloak accepted credentials → callback (auth code + PKCE)"] is False



# ---------------- Droplet bugs: uvicorn missing in the rehearsal-backend image, JWT_SECRET unset, cleanup order ----------------
def _ss(tmp_path, *a, **env):
    e = {**os.environ, "RECOVERY_DIR": str(tmp_path), **env}
    return subprocess.run([sys.executable, "-m", "app.tools.recovery", "scratch-sso", *a], cwd=ROOT / "backend", env=e,
                          capture_output=True, text=True, timeout=120, check=False)


def test_static_check_flags_uvicorn_missing_from_the_image_that_runs_it(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_requirements as cr
    cur = (ROOT / "deploy/compose/recovery.yml").read_text()
    old = cur.replace("    build: {context: ./backend, dockerfile: Dockerfile}\n    image: ironvision/rehearsal-backend:local",
                      '    image: ironvision/recovery:local\n    command: ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]')
    assert old != cur
    (tmp_path / "recovery.yml").write_text(old)                       # the Droplet's config (commit before this fix)
    errs = cr.check_entrypoints(compose=tmp_path / "recovery.yml")
    assert errs and "rehearsal-backend" in errs[0] and "uvicorn is missing from deploy/recovery/requirements.recovery.txt" in errs[0]
    assert cr.check_entrypoints() == []                               # now: backend/Dockerfile + requirements.prod.txt
    svc = cr._compose_services(ROOT / "deploy/compose/recovery.yml")["rehearsal-backend"]
    assert svc["dockerfile"] == "backend/Dockerfile" and "command" not in svc
    assert "uvicorn app.main:app" in cr._dockerfile_cmd((ROOT / "backend/Dockerfile").read_text())
    assert "RUN python -m app.tools.selfcheck --startup" in (ROOT / "backend/Dockerfile").read_text()


def test_selfcheck_startup_imports_uvicorn_and_app_main_and_serves_health_live():
    r = subprocess.run([sys.executable, "-m", "app.tools.selfcheck", "--startup"], cwd=ROOT / "backend", capture_output=True,
                       text=True, timeout=180, check=False)
    assert r.returncode == 0, r.stdout[-800:]
    assert "startup smoke (uvicorn" in r.stdout and "PASS 200" in r.stdout and "RESULT: PASS" in r.stdout


def test_scratch_app_env_reproduces_then_fixes_the_droplet_jwt_secret_failure(tmp_path):
    from app.tools import scratch_sso as ss
    code = "from app.config import get_settings; get_settings(); print('SETTINGS-OK')"
    tgt = "postgresql+psycopg://u:p@127.0.0.1:5432/rec_target_20991231t235958"
    base = {"PATH": os.environ["PATH"], "HOME": "/tmp", "IRONVISION_DOTENV": "0", "DATABASE_URL": tgt, "STORAGE_DRIVER": "local"}
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", env=base, capture_output=True, text=True, check=False)
    assert r.returncode != 0 and "Required environment variable JWT_SECRET is not set" in r.stderr   # the Droplet failure
    d = tmp_path / "scratch-sso-20991231t235958"
    d.mkdir()
    ss._env_file(d / "app.env", {"JWT_SECRET": "scratch-only-" + "x" * 40})
    env = ss._scratch_app_env(d, tgt, {"FRONTEND_URL": "http://127.0.0.1:8001", "KEYCLOAK_URL": "http://rehearsal-keycloak:8080"})
    assert env["IRONVISION_DOTENV"] == "0" and env["JWT_SECRET"].startswith("scratch-only-") and env["DATABASE_URL"] == tgt
    assert os.environ.get("JWT_SECRET", "-") != env["JWT_SECRET"]
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", env=env, capture_output=True, text=True, check=False)
    assert r.returncode == 0 and "SETTINGS-OK" in r.stdout, r.stderr[-400:]


def test_scratch_guard_refuses_production_db_and_keycloak(monkeypatch):
    from sqlalchemy.engine import make_url

    from app.tools import recovery as rv
    from app.tools import scratch_sso as ss
    live = make_url(rv.live_url())
    monkeypatch.setenv("KEYCLOAK_URL", "http://keycloak:8080")
    monkeypatch.setenv("OIDC_ISSUER", "https://auth.demo.ironvisionai.com/realms/ironvision-demo")
    monkeypatch.setenv("REHEARSAL_FORBIDDEN_HOSTS", "auth.demo.ironvisionai.com,demo.ironvisionai.com")
    ok = rv.db_url("rec_target_20991231t235958")
    ss.assert_scratch_targets("t", ok, "http://rehearsal-keycloak:8080")
    for bad_db in (live.render_as_string(hide_password=False), rv.db_url("ironvision"), rv.db_url("keycloak")):
        with pytest.raises(rv.RecoveryError, match="not a scratch rehearsal DB"):
            ss.assert_scratch_targets("t", bad_db, None)
    for bad_kc in ("http://keycloak:8080", "https://auth.demo.ironvisionai.com", "https://auth.demo.ironvisionai.com:443/x", "http://demo.ironvisionai.com"):
        with pytest.raises(rv.RecoveryError, match="production Keycloak/app host"):
            ss.assert_scratch_targets("t", None, bad_kc)


def test_cleanup_admin_env_gone_users_moot_when_scratch_keycloak_and_db_dropped(tmp_path):
    ts = "20991231t235957"
    _ss(tmp_path, "cleanup-finish", "--ts", ts)
    assert _ss(tmp_path, "prepare", "--ts", ts).returncode == 0
    r = json.loads((tmp_path / f"scratch-sso-{ts}.json").read_text())
    r["kc_users"] = {"e2e": {"username": "rehearsal-e2e-gone", "id": "00000000-0000-0000-0000-000000000000"}}
    (tmp_path / f"scratch-sso-{ts}.json").write_text(json.dumps(r))
    assert not (tmp_path / f"scratch-sso-{ts}" / "admin.env").exists()       # like Droplet 20261017t214603
    lo = _ss(tmp_path, "leftovers")
    assert ts in lo.stdout.split()
    _ss(tmp_path, "cleanup-users", "--ts", ts, "--kc-url", "http://127.0.0.1:9")
    f = _ss(tmp_path, "cleanup-finish", "--ts", ts, "--container-rc", "0")
    st = json.loads((tmp_path / f"scratch-sso-{ts}.json").read_text())["cleanup_steps"]
    assert st["1 scratch Keycloak users deleted"]["status"] == "moot" and "admin.env missing" in st["1 scratch Keycloak users deleted"]["detail"]
    assert st["3 scratch Keycloak DB + role dropped"]["status"] == "done" and f.returncode == 0
    f2 = _ss(tmp_path, "cleanup-finish", "--ts", ts, "--container-rc", "0")      # idempotent: everything already gone = success
    st2 = json.loads((tmp_path / f"scratch-sso-{ts}.json").read_text())["cleanup_steps"]
    assert f2.returncode == 0 and st2["3 scratch Keycloak DB + role dropped"]["status"] == "already-gone"
    assert st2["6 secret files + dir deleted (LAST)"]["status"] == "already-gone"
    assert ts not in _ss(tmp_path, "leftovers").stdout.split()
    # a REAL leftover (DB still there because the container could not be removed) is never hidden
    assert _ss(tmp_path, "prepare", "--ts", ts).returncode == 0
    r = json.loads((tmp_path / f"scratch-sso-{ts}.json").read_text())
    r["kc_users"] = {"e2e": {"username": "rehearsal-e2e-gone", "id": "x"}}
    r.pop("cleanup_steps", None)
    (tmp_path / f"scratch-sso-{ts}.json").write_text(json.dumps(r))
    _ss(tmp_path, "cleanup-users", "--ts", ts, "--kc-url", "http://127.0.0.1:9")
    f3 = _ss(tmp_path, "cleanup-finish", "--ts", ts, "--container-rc", "1")
    st3 = json.loads((tmp_path / f"scratch-sso-{ts}.json").read_text())["cleanup_steps"]
    assert f3.returncode == 1 and st3["1 scratch Keycloak users deleted"]["status"] == "failed"
    assert st3["2 scratch Keycloak container removed"]["status"] == "failed"
