"""Read-only: RA policy copies (any org) with analyzer/version/date and per-control coverage counts (met/partial/missing, source)."""
import json
import os
import sys

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")
from sqlalchemy import create_engine, text  # noqa: E402

e = create_engine(os.environ.get("DATABASE_URL") or os.environ["POSTGRES_URL"])
out = []
with e.connect() as c:
    pols = c.execute(text("""select p.id, p.title, o.name, p.updated_at, p.analysis->>'coverage_version', p.analysis->>'analyzer', p.analysis->'ai'
        from policies p join organizations o on o.id=p.org_id where p.file_name ilike 'ra%%.docx' or p.file_name ilike '%%ra_policy%%' order by p.updated_at""")).fetchall()
    for p in pols:
        rows = c.execute(text("""select control_id, status, source, left(reason, 140), snippets from policy_requirement_coverage where policy_id=:p and control_id like 'ra-%%' order by control_id, label"""), {"p": p[0]}).fetchall()
        per = {}
        for cid, st, src, reason, snips in rows:
            d = per.setdefault(cid, {"met": 0, "partial": 0, "missing": 0, "src": set(), "missing_reason": None, "quote": None})
            d[st] += 1
            d["src"].add(src)
            if st == "missing" and not d["missing_reason"]:
                d["missing_reason"] = reason
            if st != "missing" and not d["quote"] and snips:
                d["quote"] = (snips[0].get("text") if isinstance(snips[0], dict) else str(snips[0]))[:140]
        out.append({"policy": str(p[0]), "title": p[1], "org": p[2][:40], "updated": str(p[3])[:19], "version": p[4], "analyzer": p[5],
                    "controls": {k: {**v, "src": sorted(v["src"])} for k, v in per.items()}})
json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ra_report.json", "w"), indent=1, default=str)
for o in out:
    summ = " ".join(f"{k}:{v['met']}/{v['partial']}/{v['missing']}{'D' if v['src'] == ['deterministic'] else ''}" for k, v in sorted(o["controls"].items()))
    print(o["policy"][:8], o["analyzer"], o["updated"], o["org"][:28], "|", summ)
