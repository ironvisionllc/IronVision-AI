#!/usr/bin/env python3
"""Guards against requirements.prod.txt drift (a missing python-multipart once took production down).

Rules (exit 1 on any violation):
  1. every package in backend/requirements.txt is in backend/requirements.prod.txt with the SAME pinned version,
     unless it is listed in backend/requirements.prod-exclude.txt with a reason;
  2. an excluded package must not also be in requirements.prod.txt, and every exclusion needs a reason;
  3. import coverage: every third-party module imported by container code (backend/app, backend/worker,
     backend/alembic) resolves (importlib.metadata.packages_distributions) to a distribution in requirements.prod.txt.
     Function-level (lazy) imports may instead resolve to an exclusion marked "[optional]" (preview-only paths);
  4. implicit runtime dependencies (not visible as imports) are present;
  5. recovery image (deploy/recovery/requirements.recovery.txt): every package pinned exactly as in requirements.prod.txt,
     never a private/preview-only package (emergentintegrations lives only on Emergent's private index), every third-party
     import of the recovery import closure covered, every dependency of a listed package listed too;
  6. no Dockerfile installs backend/requirements.txt (dev/preview freeze) or uses a non-PyPI package index.
     --pypi additionally asks pypi.org that every recovery pin exists there (network).
Usage: python3 scripts/check_requirements.py [--quiet]"""
import ast
import importlib.metadata as md
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
RECOVERY_REQ = ROOT / "deploy" / "recovery" / "requirements.recovery.txt"
PRIVATE = {"emergentintegrations"}  # Emergent private index only – never in a production or recovery image
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


def check_recovery(prod: dict, excl: dict, req: Path = RECOVERY_REQ, backend: Path = BACKEND) -> list[str]:
    sys.path.insert(0, str(BACKEND))
    from app.tools.import_closure import closure
    rec, errors = parse_requirements(req), []
    for name, ver in sorted(rec.items()):
        if name in PRIVATE or "[optional]" in excl.get(name, ""):
            errors.append(f"recovery: {name} is private/preview-only (not on public PyPI) – never in the recovery image")
        elif name not in prod:
            errors.append(f"recovery: {name}=={ver} is not in requirements.prod.txt (add it there first, same pin)")
        elif prod[name] != ver:
            errors.append(f"recovery: {name} version mismatch – requirements.recovery.txt {ver} vs requirements.prod.txt {prod[name]}")
    errors += [f"recovery: {k} is required in requirements.recovery.txt: {why}" for k, why in IMPLICIT.items()
               if k != "uvicorn" and norm(k) not in rec]  # app.api.v1 (Form routes) is in the closure via app.cli
    _, third = closure(backend)
    pd = md.packages_distributions()
    for mod, files in sorted(third.items()):
        dists = {norm(d) for d in pd.get(mod, [])}
        if norm(mod) in PRIVATE or dists & PRIVATE:
            errors.append(f"recovery: Emergent-only module '{mod}' is reachable from the recovery code ({sorted(files)[0]})")
        elif not dists:
            errors.append(f"recovery: '{mod}' (imported by {sorted(files)[0]}) is provided by no installed distribution")
        elif not dists & set(rec):
            errors.append(f"recovery: '{mod}' (imported by {sorted(files)[0]}) needs {', '.join(sorted(dists))} in requirements.recovery.txt")
    from packaging.requirements import Requirement
    for name in sorted(rec):
        try:
            reqs = md.distribution(name).requires or []
        except md.PackageNotFoundError:
            continue
        for r in map(Requirement, reqs):
            if (not r.marker or r.marker.evaluate({"extra": ""})) and norm(r.name) not in rec:
                errors.append(f"recovery: {norm(r.name)} (required by {name}) is missing from requirements.recovery.txt")
    return errors


def check_dockerfiles(root: Path = ROOT) -> list[str]:
    errors = []
    for f in sorted(root.rglob("Dockerfile*")):
        if {"node_modules", ".git"} & set(f.parts):
            continue
        txt, rel = "\n".join(ln for ln in f.read_text().splitlines() if not ln.lstrip().startswith("#")), f.relative_to(root)
        if re.search(r"(?<![\w.-])requirements\.txt", txt):
            errors.append(f"{rel}: installs requirements.txt (dev/preview freeze with private packages) – use requirements.prod.txt "
                          "or deploy/recovery/requirements.recovery.txt")
        for m in re.finditer(r"--(?:extra-)?index-url[ =](\S+)", txt):
            if m.group(1) != "https://pypi.org/simple":
                errors.append(f"{rel}: non-PyPI package index {m.group(1)}")
    return errors


def check_pypi(req: Path = RECOVERY_REQ) -> list[str]:
    import urllib.request
    errors = []
    for name, ver in sorted(parse_requirements(req).items()):
        try:
            urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{ver}/json", timeout=20)
        except Exception as e:  # noqa: BLE001
            errors.append(f"recovery: {name}=={ver} not found on public PyPI ({e})")
    return errors


def run(backend: Path = BACKEND, with_imports: bool = True) -> list[str]:
    dev = parse_requirements(backend / "requirements.txt")
    prod = parse_requirements(backend / "requirements.prod.txt")
    excl, errors = parse_exclusions(backend / "requirements.prod-exclude.txt")
    errors += check_pins(dev, prod, excl) + check_implicit(prod)
    if with_imports:
        errors += check_imports(prod, excl)
        if backend == BACKEND:
            errors += check_recovery(prod, excl) + check_dockerfiles()
    return errors


if __name__ == "__main__":
    errs = run() + (check_pypi() if "--pypi" in sys.argv else [])
    for e in errs:
        print(f"  ERROR {e}")
    prod_n = len(parse_requirements(BACKEND / "requirements.prod.txt"))
    excl_n = len(parse_exclusions(BACKEND / "requirements.prod-exclude.txt")[0])
    print(f"check_requirements: {prod_n} production pins, {excl_n} documented exclusions – "
          + ("RESULT: PASS" if not errs else f"RESULT: FAIL ({len(errs)} errors)"))
    sys.exit(1 if errs else 0)
