#!/usr/bin/env python3
"""Measures memory (RSS and PSS, MiB) of the IronVision AI processes at idle and during scripts/perf_smoke.py.
Groups: postgres (all backends), backend (uvicorn app.main), worker (python -m app.worker). Writes docs/sizing/measurements.json.
Usage: PERF_PASSWORD=<demo pw> python3 scripts/measure_memory.py [--no-load] [--build]"""
import json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS = {"postgres": re.compile(r"^postgres"), "backend": re.compile(r"uvicorn (app\.main|server):app"),
          "worker": re.compile(r"-m (app\.)?worker"), "frontend_build": re.compile(r"(craco|react-scripts)\S* build")}


def sample():
    out = {g: {"rss": 0, "pss": 0, "procs": 0} for g in GROUPS}
    rows = [l.strip().split(None, 3) for l in subprocess.run(["ps", "-eo", "pid=,ppid=,rss=,args="], capture_output=True, text=True).stdout.splitlines()]
    owner = {}
    for pid, ppid, rss, cmd in rows:
        for g, rx in GROUPS.items():
            if rx.search(cmd):
                owner[pid] = g
    for _ in range(3):  # include children (uvicorn --reload / multiprocessing workers, build sub-processes)
        for pid, ppid, rss, cmd in rows:
            if pid not in owner and ppid in owner:
                owner[pid] = owner[ppid]
    for pid, ppid, rss, cmd in rows:
        for g in [owner[pid]] if pid in owner else []:
            if True:
                try:  # PSS splits shared pages (postgres shared_buffers) fairly; falls back to RSS when unreadable
                    pss = int(re.search(r"^Pss:\s+(\d+) kB", Path(f"/proc/{pid}/smaps_rollup").read_text(), re.M).group(1))
                except (OSError, AttributeError):
                    pss = int(rss)
                out[g]["rss"] += int(rss); out[g]["pss"] += pss; out[g]["procs"] += 1
    return {g: {"rss_mib": round(v["rss"] / 1024), "pss_mib": round(v["pss"] / 1024), "procs": v["procs"]} for g, v in out.items()}


def peak(samples):
    return {g: {k: max(s[g][k] for s in samples) for k in ("rss_mib", "pss_mib", "procs")} for g in GROUPS}


idle = [sample() for _ in range(5) if not time.sleep(1)]
result = {"idle": peak(idle)}
if "--build" in sys.argv:  # peak memory of a production frontend build
    t0 = time.time()
    env = dict(os.environ, REACT_APP_BACKEND_URL="", GENERATE_SOURCEMAP="false", INLINE_RUNTIME_CHUNK="false")
    proc = subprocess.Popen(["yarn", "build"], cwd=ROOT / "frontend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    load = []
    while proc.poll() is None:
        load.append(sample()); time.sleep(0.5)
    result["frontend_build"] = peak(load)["frontend_build"] | {"duration_s": round(time.time() - t0, 1), "exit": proc.returncode}
    subprocess.run(["rm", "-rf", str(ROOT / "frontend/build")])
if "--no-load" not in sys.argv:
    t0 = time.time()
    proc = subprocess.Popen([sys.executable, str(ROOT / "scripts/perf_smoke.py")], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    load = []
    while proc.poll() is None:
        load.append(sample()); time.sleep(0.5)
    result["perf_smoke"] = peak(load) | {"duration_s": round(time.time() - t0, 1), "exit": proc.returncode, "samples": len(load)}
result["measured_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
result["host"] = {"cpus": os.cpu_count(), "note": "Emergent preview pod (shared host); single uvicorn worker; postgres 16 default config"}
(ROOT / "docs/sizing").mkdir(parents=True, exist_ok=True)
out_file = ROOT / ("docs/sizing/measurements-build.json" if "--build" in sys.argv else "docs/sizing/measurements.json")
out_file.write_text(json.dumps(result, indent=1))
print(json.dumps(result, indent=1))
