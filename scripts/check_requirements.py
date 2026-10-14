#!/usr/bin/env python3
"""Guards against requirements.prod.txt drift (a missing python-multipart once took production down).

Rules (exit 1 on any violation):
  1. every package in backend/requirements.txt is in backend/requirements.prod.txt with the SAME pinned version,
     unless it is listed in backend/requirements.prod-exclude.txt with a reason;
  2. an excluded package must not also be in requirements.prod.txt, and every exclusion needs a reason;
  3. import coverage: every third-party module imported by container code (backend/app, backend/worker,
     backend/alembic) resolves (importlib.metadata.packages_distributions) to a distribution in requirements.prod.txt.
     Function-level (lazy) imports may instead resolve to an exclusion marked "[optional]" (preview-only paths);
  4. implicit runtime dependencies (not visible as imports) are present.
Usage: python3 scripts/check_requirements.py [--quiet]"""
import ast
import importlib.metadata as md
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
CONTAINER_CODE = ("app", "worker", "alembic")
LOCAL_TOP = {"app", "worker", "tests"}
IMPLICIT = {
    "python-multipart": "FastAPI Form/UploadFile parsing (imported by FastAPI at route definition, not by our code)",
    "uvicorn": "backend container CMD",
    "psycopg": "SQLAlchemy driver for DATABASE_URL=postgresql+psycopg://",
}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(path: Path) -> dict[str, str | None]:
    out = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"([A-Za-z0-9_.\-]+)(\[[^\]]*\])?\s*(?:==\s*([^\s;]+)|@\s*(\S+))?", line)
        out[norm(m.group(1))] = m.group(3) or m.group(4)
    return out


def parse_exclusions(path: Path) -> tuple[dict[str, str], list[str]]:
    excl, errors = {}, []
    for n, raw in enumerate(path.read_text().splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        name, _, reason = raw.partition("#")
        if not reason.strip():
            errors.append(f"{path.name}:{n}: '{name.strip()}' has no reason (format: <name>  # <reason>)")
        excl[norm(name.strip())] = reason.strip()
    return excl, errors


def check_pins(dev: dict, prod: dict, excl: dict) -> list[str]:
    errors = []
    for name, ver in sorted(dev.items()):
        if name in excl:
            if name in prod:
                errors.append(f"{name} is both excluded and in requirements.prod.txt – pick one")
            continue
        if name not in prod:
            errors.append(f"{name}=={ver} is in requirements.txt but missing from requirements.prod.txt "
                          f"(add it with the same pin, or exclude it with a reason in requirements.prod-exclude.txt)")
        elif prod[name] != ver:
            errors.append(f"{name}: version mismatch – requirements.txt {ver} vs requirements.prod.txt {prod[name]}")
    for name in sorted(set(excl) - set(dev)):
        errors.append(f"{name} is excluded but not in requirements.txt – remove the stale exclusion")
    return errors


def imports(root: Path) -> list[tuple[str, Path, bool]]:
    """(top-level module, file, lazy) for every non-stdlib, non-local absolute import under root."""
    found = []
    for f in sorted(root.rglob("*.py")):
        tree = ast.parse(f.read_text(), str(f))
        lazy_nodes = {id(n) for fn in ast.walk(tree) if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                      for n in ast.walk(fn)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            else:
                continue
            for m in mods:
                if m not in sys.stdlib_module_names and m not in LOCAL_TOP:
                    found.append((m, f, id(node) in lazy_nodes))
    return found


def check_imports(prod: dict, excl: dict) -> list[str]:
    errors, pd = [], md.packages_distributions()
    for root in CONTAINER_CODE:
        for mod, f, lazy in imports(BACKEND / root):
            dists = {norm(d) for d in pd.get(mod, [])}
            rel = f.relative_to(BACKEND.parent)
            if not dists and lazy and "[optional]" in excl.get(norm(mod), ""):
                continue                                  # preview-only optional module, not installed in this env
            if not dists:
                errors.append(f"{rel}: imports '{mod}' which no installed distribution provides")
            elif dists & set(prod):
                continue
            elif lazy and any("[optional]" in excl.get(d, "") for d in dists):
                continue
            else:
                errors.append(f"{rel}: imports '{mod}' (distribution {', '.join(sorted(dists))}) which is not in requirements.prod.txt")
    return errors


def check_implicit(prod: dict) -> list[str]:
    return [f"{k} is required in requirements.prod.txt: {why}" for k, why in IMPLICIT.items() if norm(k) not in prod]


def run(backend: Path = BACKEND, with_imports: bool = True) -> list[str]:
    dev = parse_requirements(backend / "requirements.txt")
    prod = parse_requirements(backend / "requirements.prod.txt")
    excl, errors = parse_exclusions(backend / "requirements.prod-exclude.txt")
    errors += check_pins(dev, prod, excl) + check_implicit(prod)
    if with_imports:
        errors += check_imports(prod, excl)
    return errors


if __name__ == "__main__":
    errs = run()
    for e in errs:
        print(f"  ERROR {e}")
    prod_n = len(parse_requirements(BACKEND / "requirements.prod.txt"))
    excl_n = len(parse_exclusions(BACKEND / "requirements.prod-exclude.txt")[0])
    print(f"check_requirements: {prod_n} production pins, {excl_n} documented exclusions – "
          + ("RESULT: PASS" if not errs else f"RESULT: FAIL ({len(errs)} errors)"))
    sys.exit(1 if errs else 0)
