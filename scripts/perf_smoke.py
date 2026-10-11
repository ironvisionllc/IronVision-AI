"""Performance smoke test (asyncio + httpx). Generates a synthetic .nessus file (default 200 hosts × 25 findings = 5,000 findings),
ingests it through the real upload → worker pipeline, then measures p50/p95 for key read endpoints.

  python scripts/perf_smoke.py --base http://localhost:8001 --hosts 200 --per-host 25 --requests 40 --out docs/PERFORMANCE.md
Env: PERF_USER, PERF_PASSWORD (a synthetic ISSO account). All hosts use RFC 5737 addresses / .demo names.
"""
import argparse
import asyncio
import os
import statistics
import time
from datetime import datetime, timezone

import httpx


def nessus(hosts: int, per_host: int) -> bytes:
    sev = ["0", "1", "2", "3", "4"]
    parts = [f'<?xml version="1.0"?><NessusClientData_v2><Report name="perf-synthetic-{time.time_ns()}">']
    for h in range(hosts):
        ip = f"198.51.{100 + h // 250}.{h % 250 + 1}"
        parts.append(f'<ReportHost name="{ip}"><HostProperties><tag name="host-ip">{ip}</tag><tag name="host-fqdn">perf-host-{h:03d}.demo</tag>'
                     '<tag name="operating-system">Demo Linux</tag></HostProperties>')
        for i in range(per_host):
            pid = 900000 + i
            parts.append(f'<ReportItem port="443" svc_name="https" protocol="tcp" severity="{sev[(i % 4) + 1]}" pluginID="{pid}" '
                         f'pluginName="Synthetic perf finding {i}" pluginFamily="General"><risk_factor>Medium</risk_factor>'
                         f'<synopsis>Synthetic</synopsis><description>Synthetic perf finding {i} (SYNTHETIC)</description>'
                         f'<solution>Apply synthetic fix</solution>{"<cve>CVE-2021-44228</cve>" if i == 0 else ""}</ReportItem>')
        parts.append("</ReportHost>")
    parts.append("</Report></NessusClientData_v2>")
    return "".join(parts).encode()


async def timed(c: httpx.AsyncClient, path: str, n: int, conc: int = 8, headers: dict | None = None) -> dict:
    lat, errors, sem = [], 0, asyncio.Semaphore(conc)

    async def one():
        nonlocal errors
        async with sem:
            t = time.perf_counter()
            r = await c.get(path, headers=headers)
            lat.append((time.perf_counter() - t) * 1000)
            errors += r.status_code >= 400
    await asyncio.gather(*[one() for _ in range(n)])
    lat.sort()
    return {"path": path, "n": n, "p50": statistics.median(lat), "p95": lat[int(len(lat) * 0.95) - 1], "max": lat[-1], "errors": errors}


async def main(a):
    async with httpx.AsyncClient(base_url=a.base + "/api/v1", timeout=300) as c:
        tok = (await c.post("/auth/login", json={"email": os.environ.get("PERF_USER", "isso@aegisrmf.demo"),
                                                 "password": os.environ["PERF_PASSWORD"]})).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {tok}"
        systems = (await c.get("/systems")).json()
        systems = systems.get("items", systems) if isinstance(systems, dict) else systems
        sid = next(s["id"] for s in systems if s["acronym"] == a.system)
        srcs = (await c.get(f"/systems/{sid}/sources")).json()
        src = next(s for s in (srcs.get("items", srcs) if isinstance(srcs, dict) else srcs) if s["source_type"] == "acas")
        data = nessus(a.hosts, a.per_host)
        t0 = time.perf_counter()
        up = (await c.post(f"/systems/{sid}/uploads", files={"file": ("perf_synthetic.nessus", data, "application/xml")},
                           data={"source_id": src["id"]})).json()
        if "id" not in up:
            raise SystemExit(f"Upload rejected: {up}")
        run_id = up["id"]
        status = None
        while time.perf_counter() - t0 < 900:
            r = (await c.get(f"/ingest-runs/{run_id}")).json()["run"]
            status = r.get("status")
            if status not in ("queued", "processing", "received"):
                break
            await asyncio.sleep(2)
        ingest = {"bytes": len(data), "findings": a.hosts * a.per_host, "hosts": a.hosts, "seconds": round(time.perf_counter() - t0, 1),
                  "status": status, "summary": {k: r.get(k) for k in ("records_total", "findings_new", "findings_updated", "assets_matched", "assets_unmatched") if k in r}}
        lead = (await c.post("/auth/login", json={"email": os.environ.get("PERF_LEADER", "leadership.viewer@aegisrmf.demo"),
                                                  "password": os.environ["PERF_PASSWORD"]})).json()["access_token"]
        lead_res = await timed(c, "/dashboard/leadership", a.requests, headers={"Authorization": f"Bearer {lead}"})
        paths = [f"/systems/{sid}/workbench/controls?page=1", f"/poams?system_id={sid}", f"/systems/{sid}/workbench/summary",
                 f"/systems/{sid}/rmf-workflow", f"/search?q=ac-2&system_id={sid}"]
        res = [await timed(c, p, a.requests) for p in paths] + [lead_res]
    lines = [f"# Performance smoke test\n\nRun {datetime.now(timezone.utc).isoformat(timespec='seconds')} against `{a.base}` "
             f"(single uvicorn process + 1 worker, preview pod; not a capacity benchmark).\n",
             f"## Ingest\nSynthetic `.nessus`: **{ingest['hosts']} hosts × {a.per_host} = {ingest['findings']} findings** "
             f"({ingest['bytes'] / 1e6:.1f} MB) → status **{ingest['status']}** in **{ingest['seconds']} s** (upload + worker parse/normalize/dedup/map/evaluate). {ingest['summary']}\n",
             f"## Read endpoints ({a.requests} requests each, concurrency 8)\n| Endpoint | p50 ms | p95 ms | max ms | errors |\n|---|---|---|---|---|"]
    lines += [f"| `{r['path']}` | {r['p50']:.0f} | {r['p95']:.0f} | {r['max']:.0f} | {r['errors']} |" for r in res]
    open(a.out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--system", default="LTP")
    ap.add_argument("--hosts", type=int, default=200)
    ap.add_argument("--per-host", type=int, default=25)
    ap.add_argument("--requests", type=int, default=40)
    ap.add_argument("--out", default="docs/PERFORMANCE.md")
    asyncio.run(main(ap.parse_args()))
