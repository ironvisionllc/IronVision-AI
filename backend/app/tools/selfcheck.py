"""Image self-check: import every module (prod: app + worker; --recovery: the recovery import closure); exit 1 on any failure.

    python -m app.tools.selfcheck [--recovery] [-v]

The imports run in a CHILD process with a scrubbed environment: only PATH/HOME/LANG plus the documented BUILD PROFILE below
(never written to an image ENV, backend/.env is not loaded) and with ALL network blocked (socket connect / create_connection /
getaddrinfo raise). So a module that reads a required setting or connects at import time fails here – in the image build –
instead of passing only because a developer/pod environment happened to provide it. Failure classes (all FAIL):
  missing-module   ModuleNotFoundError/ImportError – a package or internal module is missing/broken
  import-config    a required setting read at import time that the build profile does not provide (make it lazy, or – only for a
                   genuine build-time-only setting – add it to BUILD_PROFILE with a reason)
  import-network   the module tried to open a network connection while importing
  import-error     anything else (syntax error, …)
Run by deploy/recovery/Dockerfile, scripts/deploy.sh and check_requirements.py --in-env."""
import importlib
import json
import os
import pkgutil
import re
import subprocess
import sys
import traceback

PACKAGES = ("app", "worker")
RUNTIME_MODULES = ("multipart", "uvicorn", "psycopg")   # implicit deps (FastAPI forms, container CMD, SQLAlchemy driver)
# Documented allowlist of build-time-only settings: dummy, non-secret, unroutable (.invalid never resolves; network is blocked anyway).
BUILD_PROFILE = {
    "IRONVISION_SELFCHECK": "1",  # marks the profile; app.config skips backend/.env
    "DATABASE_URL": "postgresql+psycopg://selfcheck:selfcheck@selfcheck.invalid:5432/selfcheck",  # resolved lazily; never connected
}
# Prod target only: app.main is the ASGI entrypoint and resolves settings at import BY DESIGN (that import is service startup,
# which must fail fast). These dummies let the import be checked; they are never written to an image and never connect.
PROD_ENTRYPOINT_PROFILE = {
    "JWT_SECRET": "selfcheck-dummy-not-a-secret",
    "STORAGE_DRIVER": "local",
}


class NetworkBlocked(RuntimeError):
    pass


def _block_network() -> None:
    import socket

    def deny(*a, **kw):
        raise NetworkBlocked(f"network access at import time: {a[1:2] or a[:1]}")
    socket.socket.connect = deny
    socket.socket.connect_ex = deny
    socket.create_connection = deny
    socket.getaddrinfo = deny


def _classify(exc: BaseException) -> str:
    if isinstance(exc, NetworkBlocked) or isinstance(exc.__context__, NetworkBlocked):
        return "import-network"
    if isinstance(exc, ImportError):
        return "missing-module"
    if re.search(r"Required environment variable \w+ is not set|must be set", str(exc)):
        return "import-config"
    return "import-error"


def _modules(recovery: bool) -> list[str]:
    if recovery:
        from app.tools.import_closure import closure
        local, third = closure()
        return sorted(local) + sorted(third) + ["psycopg"]
    names = list(RUNTIME_MODULES)
    for pkg_name in PACKAGES:
        names.append(pkg_name)
        try:
            pkg = importlib.import_module(pkg_name)
        except Exception:  # noqa: BLE001 – reported by the import loop
            continue
        names += [i.name for i in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}.")]
    return names


def child(recovery: bool) -> int:
    _block_network()
    res = []
    try:
        names = _modules(recovery)
    except SyntaxError as exc:  # the closure scan parses sources first – attribute the error to its module
        rel = os.path.relpath(exc.filename or "?", os.getcwd())
        mod = rel[:-3].replace(os.sep, ".").removesuffix(".__init__") if rel.endswith(".py") else rel
        res.append({"module": mod, "ok": False, "class": "import-error", "error": f"SyntaxError: {exc}"[:300], "trace": ""})
        names = []
    for name in names:
        try:
            importlib.import_module(name)
            res.append({"module": name, "ok": True})
        except BaseException as exc:  # noqa: BLE001
            res.append({"module": name, "ok": False, "class": _classify(exc), "error": f"{type(exc).__name__}: {exc}"[:300],
                        "trace": traceback.format_exc()[-1500:] if "-v" in sys.argv else ""})
    leaked = sorted(m for m in sys.modules if m.split(".")[0] == "emergentintegrations") if recovery else []
    print("SELFCHECK-JSON " + json.dumps({"results": res, "leaked": leaked}))
    return 0


def run() -> int:
    recovery = "--recovery" in sys.argv
    tag = "[selfcheck --recovery]" if recovery else "[selfcheck]"
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/nonexistent", "LANG": "C.UTF-8", **BUILD_PROFILE,
           **({} if recovery else PROD_ENTRYPOINT_PROFILE)}
    r = subprocess.run([sys.executable, "-m", "app.tools.selfcheck", "--child", *(a for a in sys.argv[1:] if a in ("--recovery", "-v"))],
                       env=env, capture_output=True, text=True, check=False)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("SELFCHECK-JSON ")), None)
    if line is None:
        print(f"{tag} FAIL: the import child crashed (exit {r.returncode}): {(r.stderr or r.stdout)[-800:]}")
        return 1
    out = json.loads(line.split(" ", 1)[1])
    bad = [x for x in out["results"] if not x["ok"]]
    for x in bad:
        hint = {"import-config": " – a required setting is read at import time and is not in the build profile; make it lazy",
                "import-network": " – the module connects while importing; defer the connection to first use",
                "missing-module": " – a package/module is missing (python3 scripts/check_requirements.py)"}.get(x["class"], "")
        print(f"{tag} FAIL [{x['class']}] import {x['module']}: {x['error']}{hint}")
        if x.get("trace"):
            print(x["trace"])
    for m in out["leaked"]:
        print(f"{tag} FAIL Emergent-only module imported: {m}")
    n = len(out["results"])
    print(f"{tag} {n - len(bad)}/{n} modules import (scrubbed env + build profile {sorted(k for k in env if k not in ('PATH', 'HOME', 'LANG'))}, network blocked)"
          + (" – RESULT: FAIL" if bad or out["leaked"] else " – RESULT: PASS"))
    return 1 if bad or out["leaked"] else 0


if __name__ == "__main__":
    sys.exit(child("--recovery" in sys.argv) if "--child" in sys.argv else run())
