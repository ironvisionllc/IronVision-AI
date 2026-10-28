"""Policy index (built once per policy content hash, per tenant) + candidate-passage search for the "no silent misses" second look.

Similarity = local TF-IDF cosine over stemmed words (no external embedding model: nothing leaves the process, tenant-isolated by
construction) combined with a normalised keyword (BM25-style) score from the existing Retriever. Documented in docs/perf/policy_auditor_results.md."""
import hashlib
import math
import re
import threading
from collections import Counter, OrderedDict

_STOP = set("the a an and or of to in for on by with be is are shall must will may this that as at from it its any all each such which "
            "who their they when where than then not no into within upon".split())
_LOCK = threading.Lock()
_CACHE: "OrderedDict[str, Index]" = OrderedDict()


def _stem(w: str) -> str:
    for suf in ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ied", "ed", "es", "s", "ly"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def toks(s: str) -> list[str]:
    from app.services.policy_profile import qnorm
    return [_stem(w) for w in re.findall(r"[a-z0-9]{3,}", qnorm(s)) if w not in _STOP]


class Index:
    """Chunks = sentences grouped per section (heading/page kept); TF-IDF vectors; built once per (org, content hash)."""

    def __init__(self, text: str, secs: list[dict]):
        from app.services.rmf import split_sentences
        self.chunks = []
        for si, s in enumerate(secs):
            base = s.get("start", 0)
            for a, b in split_sentences(s["text"]):
                t = s["text"][a:b].strip()
                if len(t) >= 25:
                    self.chunks.append({"sec": si, "heading": s["heading"], "page": s["page"], "text": t, "start": base + a})
        df = Counter()
        self.tf = []
        for c in self.chunks:
            tf = Counter(toks(c["text"]))
            self.tf.append(tf)
            df.update(tf.keys())
        n = max(1, len(self.chunks))
        self.idf = {w: math.log((n + 1) / (d + 0.5)) for w, d in df.items()}
        self.norm = [math.sqrt(sum((v * self.idf[w]) ** 2 for w, v in tf.items())) or 1.0 for tf in self.tf]

    def search(self, query: str, k: int = 3, exclude_text: str | None = None) -> list[dict]:
        q = Counter(toks(query))
        qv = {w: v * self.idf.get(w, 0.0) for w, v in q.items()}
        qn = math.sqrt(sum(x * x for x in qv.values())) or 1.0
        ex = (exclude_text or "").strip()[:60]
        scored = []
        for i, tf in enumerate(self.tf):
            dot = sum(qv[w] * tf[w] * self.idf[w] for w in qv if w in tf)
            if dot:
                kw = len(set(q) & set(tf)) / max(1, len(q))  # normalised keyword overlap
                scored.append((0.7 * dot / (qn * self.norm[i]) + 0.3 * kw, i))
        out, seen = [], set()
        for s, i in sorted(scored, reverse=True):
            c = self.chunks[i]
            if (ex and ex in c["text"]) or c["text"] in seen:
                continue
            seen.add(c["text"])
            out.append({"text": c["text"][:300], "location": f"{c['heading']} · page {c['page']}" if c["page"] else c["heading"],
                        "section": c["heading"], "sec": c["sec"], "score": round(s, 2)})
            if len(out) >= k:
                break
        return out


def index_for(org_id, text: str, secs: list[dict]) -> tuple[Index, bool]:
    """(index, reused?) – one build per tenant + policy content hash (re-uploading an unchanged policy reuses it)."""
    key = f"{org_id}:{hashlib.sha256(text.encode()).hexdigest()}"
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key], True
    idx = Index(text, secs)
    with _LOCK:
        _CACHE[key] = idx
        while len(_CACHE) > 64:
            _CACHE.popitem(last=False)
    return idx, False


THRESHOLD = 0.30  # combined similarity at/above which a passage is "plausible" → Needs manual review instead of "not present"
