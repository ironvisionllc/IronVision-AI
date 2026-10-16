"""Static import closure of the recovery tool image (stdlib only, nothing is imported).

Entry points = what deploy/recovery/Dockerfile runs: recover.sh → app.tools.recovery / objsync / minio_xl / keycloak_* /
app.cli (keycloak-migrate), alembic migrations, scripts/e2e_sso.py. Function-level imports are followed too (they run).
Used by scripts/check_requirements.py (requirements.recovery.txt coverage) and `python -m app.tools.selfcheck --recovery`."""
import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
RECOVERY_ENTRIES = ("app.tools.recovery", "app.tools.objsync", "app.tools.minio_xl", "app.tools.keycloak_migrate",
                    "app.tools.keycloak_config", "app.tools.keycloak_doctor", "app.tools.selfcheck", "app.cli")
LOCAL = {"app", "worker", "tests"}


def _file(backend: Path, mod: str) -> Path | None:
    p = backend / Path(*mod.split("."))
    return next((c for c in (p.with_suffix(".py"), p / "__init__.py") if c.exists()), None)


def _imports(f: Path, mod: str) -> list[str]:
    pkg = mod if f.name == "__init__.py" else mod.rpartition(".")[0]
    out = []
    for n in ast.walk(ast.parse(f.read_text(), str(f))):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = ".".join(pkg.split(".")[:len(pkg.split(".")) - n.level + 1] + ([n.module] if n.module else []))
            else:
                base = n.module
            out += [base] + [f"{base}.{a.name}" for a in n.names]
    return out


def closure(backend: Path = BACKEND, entries=RECOVERY_ENTRIES, extra_files=None) -> tuple[set[str], dict[str, set[str]]]:
    """(local modules, {third-party top-level module: {importing files}})."""
    files = [(str(p), "alembic") for p in sorted((backend / "alembic").rglob("*.py"))]
    e2e = backend.parent / "scripts" / "e2e_sso.py"
    files += [(str(p), "scripts") for p in (extra_files if extra_files is not None else [e2e] if e2e.exists() else [])]
    local, third, stack, seen_files = set(), {}, [(m, "entry") for m in entries], set()
    for f, mod in files:
        stack += [(m, f) for m in _imports(Path(f), mod)]
        seen_files.add(f)
    while stack:
        m, via = stack.pop()
        top = m.split(".")[0]
        if top in sys.stdlib_module_names or (top not in LOCAL and top in ("__future__",)):
            continue
        if top not in LOCAL:
            third.setdefault(top, set()).add(str(Path(via).relative_to(backend.parent)) if via.startswith("/") else via)
            continue
        f = _file(backend, m)
        if f is None or m in local:
            continue
        local.add(m)
        parts = m.split(".")
        stack += [(".".join(parts[:k]), str(f)) for k in range(1, len(parts))]  # importing a.b.c runs a/__init__, a/b/__init__
        stack += [(d, str(f)) for d in _imports(f, m)]
    return local, third
