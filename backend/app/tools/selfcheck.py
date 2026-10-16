"""Image self-check: import every module of the app and worker packages; exit 1 on any import failure.

    python -m app.tools.selfcheck

Run by scripts/deploy.sh right after `build` (backend and worker images) and before anything starts, so a package missing
from requirements.prod.txt fails the deploy instead of taking the running service down."""
import importlib
import pkgutil
import sys
import traceback

PACKAGES = ("app", "worker")
RUNTIME_MODULES = ("multipart", "uvicorn", "psycopg")   # implicit deps (FastAPI forms, container CMD, SQLAlchemy driver)


def run_recovery() -> int:
    """Recovery image: import every module of the recovery import closure (no Emergent/preview-only module is reachable)."""
    from app.tools.import_closure import closure
    local, third = closure()
    failures = []
    for name in sorted(local) + sorted(third) + ["psycopg"]:
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append((name, f"{type(exc).__name__}: {exc}"))
    for mod, err in failures:
        print(f"[selfcheck --recovery] FAIL import {mod}: {err}")
    leaked = sorted(m for m in sys.modules if m.split(".")[0] == "emergentintegrations")
    if leaked:
        print(f"[selfcheck --recovery] FAIL Emergent-only module imported: {leaked[0]}")
    n = len(local) + len(third) + 1
    print(f"[selfcheck --recovery] {n - len(failures)}/{n} modules import" + (" – RESULT: FAIL" if failures or leaked else " – RESULT: PASS"))
    return 1 if failures or leaked else 0


def run() -> int:
    if "--recovery" in sys.argv:
        return run_recovery()
    failures, count = [], 0
    for name in RUNTIME_MODULES:
        try:
            importlib.import_module(name)
            count += 1
        except Exception as exc:
            failures.append((name, f"{type(exc).__name__}: {exc}"))
    for pkg_name in PACKAGES:
        try:
            pkg = importlib.import_module(pkg_name)
        except Exception as exc:
            failures.append((pkg_name, f"{type(exc).__name__}: {exc}"))
            continue
        for info in pkgutil.walk_packages(pkg.__path__, prefix=f"{pkg_name}."):
            try:
                importlib.import_module(info.name)
                count += 1
            except Exception as exc:
                failures.append((info.name, f"{type(exc).__name__}: {exc}"))
                if "-v" in sys.argv:
                    traceback.print_exc()
    for mod, err in failures:
        print(f"[selfcheck] FAIL import {mod}: {err}")
    if failures:
        print(f"[selfcheck] {len(failures)} module(s) failed to import – a package is probably missing from requirements.prod.txt "
              "(run python3 scripts/check_requirements.py)")
        return 1
    print(f"[selfcheck] OK – {count} modules imported")
    return 0


if __name__ == "__main__":
    sys.exit(run())
