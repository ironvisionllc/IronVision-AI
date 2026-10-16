#!/usr/bin/env python3
"""Guards against requirements drift (a missing python-multipart once took production down).

DEFAULT = STATIC manifest check, host-safe: stdlib only; packages installed on the host are NEVER consulted. Module→distribution
and the dependency graph come from committed lockfiles generated in a clean venv (--write-lock):
  backend/requirements.prod.lock.json, deploy/recovery/requirements.recovery.lock.json
Rules (exit 1 on any violation):
  1. every package in backend/requirements.txt is in requirements.prod.txt with the SAME pin, unless excluded with a reason;
  2. an excluded package is not also in requirements.prod.txt; every exclusion has a reason;
  3. lock freshness (manifest sha256) and completeness: the lock's distributions == the manifest's pins (same versions) and
     every dependency of every locked distribution is pinned (full transitive closure);
  4. import coverage: every third-party import of container code (backend/app, worker, alembic) maps (via the prod lock) to a
     pinned distribution; lazy imports may map to an exclusion marked "[optional]"; implicit runtime deps present;
  5. recovery: pins ⊆ prod pins (same versions), never a private/preview package, every import of the recovery import closure
     covered (via the recovery lock);
  6. no Dockerfile installs backend/requirements.txt or uses a non-PyPI index.
--in-env --target prod|recovery [--app-dir DIR]: run INSIDE the image / clean venv: pip check, installed distributions ==
  manifest pins == lock (no unpinned transitive dependency), and every module imports (selfcheck).
--write-lock --target prod|recovery: (re)generate the lock in a clean venv after `pip install --no-deps -r <manifest>`.
--pypi: also ask pypi.org that every recovery pin exists (network).
Usage: python3 scripts/check_requirements.py [--in-env|--write-lock --target T] [--pypi]"""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
RECOVERY_REQ = ROOT / "deploy" / "recovery" / "requirements.recovery.txt"
TARGETS = {"prod": BACKEND / "requirements.prod.txt", "recovery": RECOVERY_REQ}
LOCKS = {"prod": BACKEND / "requirements.prod.lock.json", "recovery": ROOT / "deploy" / "recovery" / "requirements.recovery.lock.json"}
TOOLING = {"pip", "setuptools", "wheel"}
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


def regen_cmd(target: str) -> str:
    return (f"python3 -m venv --clear /tmp/lock-{target} && /tmp/lock-{target}/bin/pip install --no-deps --index-url https://pypi.org/simple "
            f"-r {TARGETS[target].relative_to(ROOT)} && /tmp/lock-{target}/bin/python scripts/check_requirements.py --write-lock --target {target}")


def load_lock(target: str) -> tuple[dict | None, list[str]]:
    lf, mf = LOCKS[target], TARGETS[target]
    if not lf.exists():
        return None, [f"{target}: lockfile {lf.relative_to(ROOT)} missing – generate it: {regen_cmd(target)}"]
    lock = json.loads(lf.read_text())
    if lock.get("manifest_sha256") != hashlib.sha256(mf.read_bytes()).hexdigest():
        return lock, [f"{target}: lockfile {lf.name} is STALE ({mf.name} changed) – regenerate it: {regen_cmd(target)}"]
    return lock, []


def check_lock(target: str, pins: dict, lock: dict) -> list[str]:
    errors, dists = [], lock["distributions"]
    for n, ver in sorted(pins.items()):
        if n not in dists:
            errors.append(f"{target}: {n}=={ver} is pinned but not in the lock – regenerate: {regen_cmd(target)}")
        elif dists[n]["version"] != ver:
            errors.append(f"{target}: {n} pinned {ver} but locked {dists[n]['version']} – regenerate: {regen_cmd(target)}")
    for n in sorted(set(dists) - set(pins)):
        errors.append(f"{target}: {n}=={dists[n]['version']} is in the resolved environment but not pinned in {TARGETS[target].name}")
    for n, d in sorted(dists.items()):
        for r in d["requires"]:
            if r not in pins:
                errors.append(f"{target}: {r} (required by {n}) is not pinned in {TARGETS[target].name} – transitive closure incomplete")
    return errors


def check_imports(prod: dict, excl: dict, lock: dict) -> list[str]:
    errors, pd = [], lock["modules"]
    for root in CONTAINER_CODE:
        for mod, f, lazy in imports(BACKEND / root):
            dists = set(pd.get(mod, []))
            rel = f.relative_to(BACKEND.parent)
            if not dists and lazy and "[optional]" in excl.get(norm(mod), ""):
                continue                                  # preview-only optional module, never installed in images
            if not dists:
                errors.append(f"{rel}: imports '{mod}' which no locked prod distribution provides")
            elif dists & set(prod) or (lazy and any("[optional]" in excl.get(d, "") for d in dists)):
                continue
            else:
                errors.append(f"{rel}: imports '{mod}' (distribution {', '.join(sorted(dists))}) which is not in requirements.prod.txt")
    return errors


def check_implicit(prod: dict) -> list[str]:
    return [f"{k} is required in requirements.prod.txt: {why}" for k, why in IMPLICIT.items() if norm(k) not in prod]


def check_recovery(prod: dict, excl: dict, lock: dict, req: Path = RECOVERY_REQ, backend: Path = BACKEND) -> list[str]:
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
    for mod, files in sorted(third.items()):
        dists = set(lock["modules"].get(mod, []))
        if norm(mod) in PRIVATE or dists & PRIVATE:
            errors.append(f"recovery: Emergent-only module '{mod}' is reachable from the recovery code ({sorted(files)[0]})")
        elif not dists:
            errors.append(f"recovery: '{mod}' (imported by {sorted(files)[0]}) is provided by no locked recovery distribution")
        elif not dists & set(rec):
            errors.append(f"recovery: '{mod}' (imported by {sorted(files)[0]}) needs {', '.join(sorted(dists))} in requirements.recovery.txt")
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
    for n, v in sorted(prod.items()):
        if n in PRIVATE:
            errors.append(f"prod: {n} is private/preview-only – never in requirements.prod.txt")
        if not v:
            errors.append(f"prod: {n} is not pinned exactly (==)")
    if with_imports and backend == BACKEND:
        rec = parse_requirements(RECOVERY_REQ)
        errors += [f"recovery: {n} is not pinned exactly (==)" for n, v in sorted(rec.items()) if not v]
        for target, pins in (("prod", prod), ("recovery", rec)):
            lock, errs = load_lock(target)
            errors += errs
            if lock and not errs:
                errors += check_lock(target, pins, lock)
                errors += check_imports(prod, excl, lock) if target == "prod" else check_recovery(prod, excl, lock)
        errors += check_dockerfiles()
    return errors


def _env_dists() -> dict:
    import importlib.metadata as md
    return {norm(d.metadata["Name"]): d for d in md.distributions() if norm(d.metadata["Name"]) not in TOOLING}


def write_lock(target: str) -> int:
    import importlib.metadata as md

    try:
        from packaging.requirements import Requirement
    except ImportError:  # clean venv: packaging may not be a pinned dependency; pip vendors it
        from pip._vendor.packaging.requirements import Requirement
    if subprocess.run([sys.executable, "-m", "pip", "check"]).returncode:
        print(f"[write-lock {target}] pip check failed – the manifest is not a complete, consistent closure")
        return 1
    pins, dists = parse_requirements(TARGETS[target]), _env_dists()
    if set(dists) != set(pins):
        print(f"[write-lock {target}] environment != manifest: extra {sorted(set(dists) - set(pins))}, missing {sorted(set(pins) - set(dists))}"
              " – install with: pip install --no-deps -r <manifest> into a CLEAN venv")
        return 1
    out = {}
    for n, d in sorted(dists.items()):
        reqs = sorted({norm(Requirement(r).name) for r in d.requires or []
                       if not Requirement(r).marker or Requirement(r).marker.evaluate({"extra": ""})})
        out[n] = {"version": d.version, "requires": reqs}
    mods = {m: sorted({norm(x) for x in ds} & set(out)) for m, ds in md.packages_distributions().items()}
    lock = {"target": target, "manifest": str(TARGETS[target].relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(TARGETS[target].read_bytes()).hexdigest(),
            "generated_by": regen_cmd(target), "python": sys.version.split()[0], "platform": f"{sys.platform}-{os.uname().machine}",
            "distributions": out, "modules": {m: v for m, v in sorted(mods.items()) if v}}
    LOCKS[target].write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
    print(f"[write-lock {target}] {LOCKS[target].relative_to(ROOT)}: {len(out)} distributions, pip check OK")
    return 0


def in_env(target: str, app_dir: Path) -> list[str]:
    ctx = f"in-env {target} ({sys.prefix}, python {sys.version.split()[0]})"
    errors = []
    pc = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
    if pc.returncode:
        errors.append(f"[{ctx}] pip check: {pc.stdout.strip()[-400:]}")
    pins, dists = parse_requirements(TARGETS[target]), _env_dists()
    lock, lerr = load_lock(target)
    errors += [f"[{ctx}] {e}" for e in lerr]
    for n in sorted(set(dists) - set(pins)):
        errors.append(f"[{ctx}] {n}=={dists[n].version} is installed but not pinned in {TARGETS[target].name} (unpinned transitive dependency)")
    for n, v in sorted(pins.items()):
        if n not in dists:
            errors.append(f"[{ctx}] {n}=={v} is pinned but not installed")
        elif dists[n].version != v:
            errors.append(f"[{ctx}] {n}: installed {dists[n].version}, pinned {v}")
        elif lock and lock["distributions"].get(n, {}).get("version") != v:
            errors.append(f"[{ctx}] {n}: lock has {lock['distributions'].get(n, {}).get('version')}, pinned {v}")
    flag = ["--recovery"] if target == "recovery" else []
    sc = subprocess.run([sys.executable, "-m", "app.tools.selfcheck", *flag], cwd=app_dir, capture_output=True, text=True)
    if sc.returncode:
        errors.append(f"[{ctx}] selfcheck failed: {(sc.stdout + sc.stderr).strip()[-600:]}")
    return errors


def _arg(name: str, default: str | None = None) -> str | None:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else default


if __name__ == "__main__":
    target = _arg("--target")
    if "--write-lock" in sys.argv:
        sys.exit(write_lock(target or "recovery"))
    if "--in-env" in sys.argv:
        if target not in TARGETS:
            sys.exit("usage: check_requirements.py --in-env --target prod|recovery [--app-dir DIR]")
        app_dir = Path(_arg("--app-dir") or str(BACKEND))
        errs = in_env(target, app_dir)
        for e in errs:
            print(f"  ERROR {e}")
        print(f"check_requirements [in-env {target}: installed packages of THIS environment checked] – "
              + ("RESULT: PASS" if not errs else f"RESULT: FAIL ({len(errs)} errors)"))
        sys.exit(1 if errs else 0)
    errs = run() + (check_pypi() if "--pypi" in sys.argv else [])
    for e in errs:
        print(f"  ERROR [host static] {e}")
    prod_n = len(parse_requirements(BACKEND / "requirements.prod.txt"))
    excl_n = len(parse_exclusions(BACKEND / "requirements.prod-exclude.txt")[0])
    print(f"check_requirements [host: static manifest check – host packages not used]: {prod_n} production pins, "
          f"{len(parse_requirements(RECOVERY_REQ))} recovery pins, {excl_n} documented exclusions – "
          + ("RESULT: PASS" if not errs else f"RESULT: FAIL ({len(errs)} errors)"))
    sys.exit(1 if errs else 0)
