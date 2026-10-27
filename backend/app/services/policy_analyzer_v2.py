"""Policy Auditor analyzer v2: extract/normalize once → section retrieval (BM25 + explicit control IDs) → batched strict-JSON AI over only
the retrieved sections → validation → tenant-scoped cache. Output has the same shape as v-current ({control: {requirement: verdict}}),
so stage 3 (verbatim quote verification, never MET without a verified quote, readable deterministic fallback) is unchanged.
No DB session/transaction is held while AI calls run; every DB touch is a short own session."""
import hashlib
import json
import logging
import math
import os
import random
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)
ANALYZER = "v2.0"
PROMPT = ("policy.coverage_refine", "2.1.0")
STOP = set("the and for with that this shall must are any all its from into each such has have been being which when where or of to in on by be is as an at it not".split())
PAGE = re.compile(r"^\s*(?:-{2,}\s*)?page\s+(\d+)(?:\s*-{2,})?\s*$|\f", re.I | re.M)
HEAD = re.compile(r"^\s*(?:#{1,4}\s+.+|(?:\d+(?:\.\d+)*\.?\s+)[A-Z][^\n]{2,90}|[A-Z]{2}-\d+(?:\(\d+\))?\s[^\n]{2,90})\s*$", re.M)


def env_int(k: str, d: int) -> int:
    return int(os.environ.get(k) or d)


def _is_head(line: str) -> bool:
    """Table rows ("RA-6 | … | Not selected") and prose starting with an ID ("RA-10 is outside …") are not headings – as headings they
    became one-row sections whose ID boost outranked the real policy section in retrieval."""
    t = line.strip()
    if "|" in t:
        return False
    return not (re.match(r"[A-Z]{2}-\d", t) and (t.endswith(".") or len(t) > 80 or re.search(r"\b(?:is|are|was|were|shall|must)\b", t)))


def sections(text: str) -> list[dict]:
    """Sections keep heading, page and character offsets; content-hashed. Headless text is windowed at paragraph boundaries."""
    pages = [(m.start(), int(m.group(1)) if m.group(1) else None) for m in PAGE.finditer(text)]
    heads = [m.start() for m in HEAD.finditer(text) if _is_head(m.group(0))]
    if len(heads) < 2:
        heads, pos = [0], 0
        while pos + 3500 < len(text):
            cut = text.rfind("\n\n", pos + 1500, pos + 3500)
            pos = cut if cut > pos else pos + 3500
            heads.append(pos)
    bounds = sorted(set([0] + heads)) + [len(text)]
    out = []
    for a, b in zip(bounds, bounds[1:]):
        body = text[a:b]
        if not body.strip():
            continue
        first = body.strip().split("\n", 1)[0].lstrip("# ").strip()[:120]
        pg = None
        for i, (off, n) in enumerate(pages):
            if off <= a:
                pg = n if n is not None else i + 2
        out.append({"id": f"S{len(out) + 1}", "heading": first, "page": pg or 1, "start": a, "end": b, "text": body,
                    "hash": hashlib.sha256(body.encode()).hexdigest()[:16]})
    return out


def _tok(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z][a-z0-9]{2,}", s.lower()) if w not in STOP]


def _cid_rx(cid: str) -> re.Pattern:
    base, _, enh = cid.partition(".")
    b = re.escape(base.upper())
    return re.compile(rf"\b{b}\s*\(\s*{enh}\s*\)" if enh else rf"\b{b}(?!\d|\s*\(|\.\d)", re.I)


class Retriever:
    """BM25 (k1=1.2, b=0.75) over an inverted index + a strong boost for sections naming the control ID (heading +25, body +8)."""

    def __init__(self, secs: list[dict]):
        self.secs = secs
        toks = [Counter(_tok(s["heading"] + " " + s["heading"] + " " + s["text"])) for s in secs]
        lens = [sum(t.values()) or 1 for t in toks]
        avg = sum(lens) / max(1, len(secs))
        n = len(secs)
        self.post: dict = {}
        for i, t in enumerate(toks):
            for w, f in t.items():
                self.post.setdefault(w, []).append((i, f * 2.2 / (f + 1.2 * (0.25 + 0.75 * lens[i] / avg))))
        self.idf = {w: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for w, p in self.post.items()}
        self._cid: dict = {}

    def _boost(self, cid: str) -> dict:
        if cid not in self._cid:
            rx = _cid_rx(cid)
            self._cid[cid] = {i: 25 if rx.search(s["heading"]) else 8 for i, s in enumerate(self.secs) if rx.search(s["text"])}
        return self._cid[cid]

    def scores(self, query: str, cid: str) -> list[tuple[float, int]]:
        sc: Counter = Counter(self._boost(cid))
        for w in set(_tok(query)):
            idf = self.idf.get(w)
            if idf:
                for i, tfn in self.post[w]:
                    sc[i] += idf * tfn
        return sorted(((v, i) for i, v in sc.items()), reverse=True)


class Bucket:
    """Provider-aware RPM + TPM token buckets (POLICY_AI_RPM / POLICY_AI_TPM)."""

    def __init__(self, rpm: int, tpm: int):
        self.rpm, self.tpm, self.lock = rpm, tpm, threading.Lock()
        self.r, self.t, self.ts, self.waited = float(rpm), float(tpm), time.monotonic(), 0.0

    def take(self, tokens: int) -> None:
        tokens = min(tokens, self.tpm)
        while True:
            with self.lock:
                now = time.monotonic()
                el, self.ts = now - self.ts, now
                self.r = min(self.rpm, self.r + el * self.rpm / 60)
                self.t = min(self.tpm, self.t + el * self.tpm / 60)
                if self.r >= 1 and self.t >= tokens:
                    self.r -= 1
                    self.t -= tokens
                    return
                need = max((1 - self.r) * 60 / self.rpm, (tokens - self.t) * 60 / self.tpm, 0.05)
            self.waited += need
            time.sleep(need)


def _render(secs: list[dict]) -> str:
    return "\n\n".join(f"[{s['id']} | {s['heading']} | page {s['page']}]\n{s['text'].strip()}" for s in secs)


def _key(org_id, model, catalog, items, secs) -> str:
    raw = json.dumps([str(org_id), ANALYZER, PROMPT, model, catalog, sorted((i["control_id"], i["requirement_id"], i["text"], i["deterministic"]) for i in items),
                      sorted(s["hash"] for s in secs)])
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_on() -> bool:
    return os.environ.get("POLICY_AI_CACHE", "1") != "0"  # 0 only for benchmark concurrency sweeps


def _cache_get(org_id, key):
    from sqlalchemy import select
    if not _cache_on():
        return None

    from app.db import SessionLocal
    from app.models import PolicyAiCache
    with SessionLocal() as db:
        row = db.scalar(select(PolicyAiCache).where(PolicyAiCache.org_id == org_id, PolicyAiCache.cache_key == key))
        if row is None:
            return None
        row.hits += 1
        db.commit()
        return row.result


def _cache_put(org_id, key, model, result, prov) -> None:
    from sqlalchemy.dialects.postgresql import insert

    from app.db import SessionLocal
    from app.models import PolicyAiCache
    if not _cache_on():
        return
    with SessionLocal() as db:
        db.execute(insert(PolicyAiCache).values(org_id=org_id, cache_key=key, analyzer_version=ANALYZER, model=model, result=result,
                                                provenance=prov).on_conflict_do_nothing(constraint="uq_policy_ai_cache_org_key"))
        db.commit()


def with_history(prev: dict | None, data: dict) -> dict:
    """Every emitted stage is kept (stage, pct, time) so short stages remain visible after the fact."""
    hist = list((prev or {}).get("history") or [])
    if data.get("stage") and (not hist or hist[-1]["stage"] != data["stage"]):
        hist.append({"stage": data["stage"], "pct": data.get("pct"), "at": time.strftime("%H:%M:%S")})
    return {**data, "history": hist[-30:]}


def queued_progress(db, policy, job) -> None:
    """At enqueue: 'Queued – waiting for a worker' (0%), with how many policy analyses are ahead of it."""
    from sqlalchemy import func, select

    from app.models import Job
    ahead = db.scalar(select(func.count()).select_from(Job).where(Job.job_type == "policy.analyze", Job.status.in_(("queued", "running")),
                                                                  Job.id != job.id, Job.created_at <= job.created_at)) or 0
    stage = "Queued – waiting for a worker" + (f" (queued behind {ahead} analysis job{'s' if ahead != 1 else ''})" if ahead else "")
    policy.analysis = {**(policy.analysis or {}), "progress": with_history(None, {"phase": "queued", "stage": stage, "pct": 0, "queued_behind": ahead,
                                                                               "label": "analysis queued"})}


def _progress(policy_id, data: dict) -> None:
    """Live progress on the policy row (short own transaction; the analysis itself holds none while AI runs)."""
    from app.db import SessionLocal
    from app.models import Policy
    try:
        with SessionLocal() as db:
            p = db.get(Policy, policy_id)
            if p is not None:
                p.analysis = {**(p.analysis or {}), "progress": with_history((p.analysis or {}).get("progress"), data)}
                db.commit()
    except Exception:  # noqa: BLE001 – progress is best-effort
        log.debug("progress update failed", exc_info=True)


class Run:
    def __init__(self, svc, org_id, policy_id, model, catalog, secs, stats):
        self.svc, self.org, self.pid, self.model, self.catalog, self.secs, self.st = svc, org_id, policy_id, model, catalog, secs, stats
        self.bucket = Bucket(env_int("POLICY_AI_RPM", 300), env_int("POLICY_AI_TPM", 2_000_000))
        self.lock = threading.Lock()

    def call(self, items: list[dict], secs: list[dict], depth: int = 0) -> dict:
        """One batch → {(control, requirement): verdict}. Cache first; truncation splits; 429/timeouts back off with jitter; missing answers re-asked once."""
        import asyncio

        from app.services.ai.service import AIOutputTruncatedError
        key = _key(self.org, self.model, self.catalog, items, secs)
        hit = _cache_get(self.org, key)
        if hit is not None:
            with self.lock:
                self.st["cache_hits"] += 1
                self.st["reused_requirements"] += len(items)
            return {tuple(k.split("|", 1)): v for k, v in hit.items()}
        ctx = _render(secs)
        reqs = json.dumps([{k: i[k] for k in ("control_id", "requirement_id", "text", "deterministic")} for i in items])
        est_in = (len(ctx) + len(reqs)) // 3 + 600
        for attempt in range(4):
            self.bucket.take(est_in + 120 * len(items))
            try:
                with self.lock:
                    self.st["calls"] += 1
                res = asyncio.run(self.svc.run(*PROMPT, {"requirements": reqs, "sections": ctx}, max_tokens=min(8000, 160 * len(items) + 400)))
                break
            except AIOutputTruncatedError:
                with self.lock:
                    self.st["truncated"] += 1
                if len(items) == 1:
                    return {}
                h = len(items) // 2
                both = {**self.call(items[:h], secs, depth + 1), **self.call(items[h:], secs, depth + 1)}
                if len(both) == len(items):  # cache the split result under the parent key too (repeat runs hit, no re-truncation)
                    _cache_put(self.org, key, self.model, {"|".join(k): v for k, v in both.items()},
                               {"policy_id": str(self.pid), "sections": [s["id"] + ":" + s["hash"] for s in secs], "split": True, "at": time.time()})
                return both
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if attempt < 3 and any(x in msg for x in ("429", "rate", "timed out", "timeout", "502", "503", "overloaded")):
                    with self.lock:
                        self.st["retries"] += 1
                    time.sleep(min(30, 2 ** attempt + random.random() * 2))
                    continue
                with self.lock:
                    self.st["failed_batches"] += 1
                log.warning("v2 coverage batch failed (%d requirements): %s – deterministic results kept", len(items), str(exc)[:200])
                return {}
        want = {(i["control_id"], i["requirement_id"]) for i in items}
        sec_by = {s["id"]: s for s in secs}
        got: dict = {}
        for it in res.output.items:
            k = (it.control_id.lower(), it.requirement_id)
            if k not in want or k in got:  # validation: only requested IDs, each answered once
                with self.lock:
                    self.st["invalid_items"] += 1
                continue
            v = {"status": it.status, "quote": it.quote, "rationale": it.rationale[:400]}
            s = sec_by.get(it.section.strip().split()[0].strip("[]|") if it.section else "")
            if it.quote and it.status != "missing":
                real = next((x for x in secs if it.quote.strip()[:80] in x["text"]), None)
                if real is not None:
                    v.update(section=real["heading"], page=real["page"], offset=real["start"] + real["text"].find(it.quote.strip()[:80]))
                    if s is None or s["id"] != real["id"]:
                        with self.lock:
                            self.st["citation_section_fixed"] += 1
            got[k] = v
        missing = [i for i in items if (i["control_id"], i["requirement_id"]) not in got]
        if missing and depth == 0:
            with self.lock:
                self.st["reasked"] += len(missing)
            got.update(self.call(missing, secs, depth + 1))
        if not missing or depth == 0:
            _cache_put(self.org, key, res.model if hasattr(res, "model") else self.model, {"|".join(k): v for k, v in got.items()},
                       {"policy_id": str(self.pid), "sections": [s["id"] + ":" + s["hash"] for s in secs], "at": time.time()})
        return got


def analyze_ai(text: str, policy_id, org_id, todo: list, titles: dict, catalog, in_scope: int | None = None) -> tuple[dict, dict]:
    """todo = [(control_id, reqs, results)] → ({control: {requirement: verdict}}, stats). Unretrieved requirements are recorded as
    not examined (never satisfied/failed/N-A); a sample of them still gets a cheap verification pass to measure screening misses."""
    from app.services.ai.service import get_ai_service
    svc = get_ai_service()
    st = Counter()
    t0 = time.perf_counter()
    secs = sections(text)
    rt = Retriever(secs)
    k, min_score = env_int("POLICY_AI_TOPK", 3), float(os.environ.get("POLICY_AI_MIN_SCORE") or 4.0)
    examined, not_examined = [], []
    for cid, reqs, results in todo:
        for q, (_, r) in zip(reqs, results):
            item = {"control_id": cid, "requirement_id": q["id"], "text": q["text"][:500], "deterministic": r["status"], "family": cid.split("-")[0]}
            sc = rt.scores(f"{titles.get(cid, '')} {q['text']}", cid)
            top = [i for s_, i in sc[:k] if s_ >= min_score and s_ >= 0.6 * sc[0][0]] if sc else []  # near-best sections only (keeps batches dense)
            (examined if top else not_examined).append((item, top or [i for _, i in sc[:2]] or [0]))
    t1 = time.perf_counter()
    n_verify = min(len(not_examined), max(0, math.ceil(len(not_examined) * float(os.environ.get("POLICY_AI_VERIFY_FRACTION") or 0.1))))
    verify = sorted(not_examined, key=lambda x: hashlib.sha256((x[0]["control_id"] + x[0]["requirement_id"]).encode()).hexdigest())[:n_verify]
    max_reqs, max_ctx = env_int("POLICY_AI_BATCH_REQS", 25), env_int("POLICY_AI_BATCH_CHARS", 9000)
    max_reqs, max_ctx = env_int("POLICY_AI_BATCH_REQS", 25), env_int("POLICY_AI_BATCH_CHARS", 16000)
    groups: dict = {}  # section affinity: requirements sharing a primary section travel together (small incremental re-runs)
    for item, top in examined + verify:
        groups.setdefault((item["family"], top[0]), []).append((item, top))
    batches, cur, cur_secs = [], [], set()
    for (fam, _), members in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        for item, top in members:
            add = cur_secs | set(top)
            while len(add) > len(cur_secs) + 1 and sum(len(secs[i]["text"]) for i in add) > max_ctx:
                add.discard(max(add - cur_secs - {top[0]}, key=lambda i: len(secs[i]["text"])))
            if cur and (len(cur) >= max_reqs or item["family"] != cur[0]["family"] or sum(len(secs[i]["text"]) for i in add) > max_ctx):
                batches.append((cur, sorted(cur_secs)))
                cur, add = [], set(top[:1])
            cur.append(item)
            cur_secs = add
    if cur:
        batches.append((cur, sorted(cur_secs)))
    st.update(sections=len(secs), requirements=len(examined) + len(not_examined), examined=len(examined), not_examined=len(not_examined) - len(verify),
              verification_sample=len(verify), batches=len(batches), screening_s=round(t1 - t0, 2))
    for k_ in ("calls", "cache_hits", "reused_requirements", "retries", "truncated", "failed_batches", "invalid_items", "reasked", "citation_section_fixed"):
        st.setdefault(k_, 0)
    run = Run(svc, org_id, policy_id, svc.provider.model if svc.provider else None, str(catalog), secs, st)
    out: dict = {}
    done = Counter()
    started = time.perf_counter()
    base = {"analyzer": ANALYZER, "controls_screened": len(todo), "requirements_total": st["requirements"], "batches_total": len(batches),
            "requirements_in_scope": in_scope if in_scope is not None else st["requirements"], "label": "analysis in progress"}
    _progress(policy_id, {**base, "phase": "screen", "stage": "2/4 relevance screening done – AI review starting", "pct": 10, "batches_done": 0,
                          "requirements_analyzed": 0, "requirement_gaps_so_far": 0, "elapsed_s": round(time.perf_counter() - t0, 1)})

    def one(b):
        items, sidx = b
        res = run.call(items, [secs[i] for i in sidx])
        with run.lock:
            done["batches"] += 1
            done["requirements"] += len(items)
            done["gaps"] += sum(1 for v in res.values() if v["status"] in ("missing", "partial"))
            el = time.perf_counter() - started
            _progress(policy_id, {**base, "phase": "AI review", "stage": f"3/4 AI review – batch {done['batches']} of {len(batches)}",
                                  "pct": 10 + round(75 * done["batches"] / max(1, len(batches))), "requirements_analyzed": done["requirements"],
                                  "requirement_gaps_so_far": done["gaps"], "batches_done": done["batches"], "failed_batches": st["failed_batches"],
                                  "retries": st["retries"], "elapsed_s": round(time.perf_counter() - t0, 1),
                                  "eta_s": round(el / done["batches"] * (len(batches) - done["batches"]), 1)})
        return res

    workers = env_int("POLICY_AI_WORKERS", 16)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(one, batches):
            for (cid, rid), v in res.items():
                out.setdefault(cid, {})[rid] = v
    vfound = sum(1 for item, _ in verify if out.get(item["control_id"], {}).get(item["requirement_id"], {}).get("status") in ("met", "partial"))
    st.update(workers=workers, ai_s=round(time.perf_counter() - started, 2), rate_limit_wait_s=round(run.bucket.waited, 2),
              verification_found=vfound)
    st["not_examined_ids"] = [f"{i['control_id']}|{i['requirement_id']}" for i, _ in not_examined if i not in [v[0] for v in verify]][:5000]
    return out, dict(st)
