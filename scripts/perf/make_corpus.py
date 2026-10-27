#!/usr/bin/env python3
"""Builder-authored SYNTHETIC Policy Auditor benchmark corpus with gold labels (NEEDS SME REVIEW).
Each mapped control gets a headed section; each requirement is deterministically ADDRESSED (statement with a concrete value),
PARTIAL (statement without the organization-defined value) or NOT ADDRESSED (omitted). Page markers every 3 sections.
Usage: python scripts/perf/make_corpus.py  → docs/perf/corpus/*.txt + *.gold.json"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Control, ControlAssignment, System  # noqa: E402
from app.services import policy_coverage as pc  # noqa: E402

OUT = Path("/app/docs/perf/corpus")
ODP = re.compile(r"\[(?:Assignment|Selection)[^\]]*\]|organization-defined [a-z ]+", re.I)
VALUES = ["every 90 days", "within 24 hours", "the ISSO and ISSM", "annually", "FIPS 140-3 validated cryptography", "15 minutes", "three attempts"]


def _label(rid: str) -> str:
    h = int(hashlib.sha256(rid.encode()).hexdigest(), 16) % 10
    return "addressed" if h < 6 else "partial" if h < 8 else "not_addressed"


def _sentence(text: str, label: str, i: int) -> str:
    t = re.sub(r"\s+", " ", text.strip().rstrip("."))
    t = ODP.sub(VALUES[i % len(VALUES)] if label == "addressed" else "as determined by the organization", t)
    return f"The organization ensures that {t[0].lower() + t[1:]}."


def build(name: str, controls: list[str], title: str) -> dict:
    gold, parts, page = {}, [f"SYNTHETIC {title} (benchmark data – builder-authored, needs SME review)\n\n--- Page 1 ---\n"], 1
    with SessionLocal() as db:
        titles = dict(db.execute(select(Control.control_id, Control.title)).all())
        for n, cid in enumerate(controls):
            if n and n % 3 == 0:
                page += 1
                parts.append(f"\n--- Page {page} ---\n")
            base, _, enh = cid.partition(".")
            heading = f"{base.upper()}{f'({enh})' if enh else ''} {titles.get(cid, '')}".strip()  # standard notation: AC-2(1)
            lines = [f"\n## {heading}\n"]
            for i, req in enumerate(pc.requirements(db, cid)):
                lab = _label(f"{cid}|{req['id']}")
                if lab == "partial" and not ODP.search(req["text"]):
                    lab = "addressed"  # no organization-defined value to withhold → the generated sentence is a full statement
                g = {"control_id": cid, "label": lab, "section": heading, "page": page}
                if lab != "not_addressed":
                    s = _sentence(req["text"], lab, i)
                    lines.append(s + " ")
                    g["quote"] = s
                gold[f"{cid}|{req['id']}"] = g
            sec = "".join(lines).rstrip() + "\n"
            start = sum(map(len, parts))
            for k_ in [k for k, v in gold.items() if v["section"] == heading]:
                gold[k_]["span"] = [start, start + len(sec)]
            parts.append(sec)
    text = "".join(parts)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.txt").write_text(text)
    (OUT / f"{name}.gold.json").write_text(json.dumps({"policy": name, "controls": controls, "requirements": gold,
                                                     "note": "builder-authored gold labels – NOT SME reviewed"}, indent=0))
    return {"name": name, "controls": len(controls), "requirements": len(gold), "chars": len(text)}


def main() -> None:
    with SessionLocal() as db:
        sid = db.scalar(select(System.id).where(System.acronym == "LTP").limit(1))
        ctl = sorted(set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == sid))),
                     key=lambda c: (c.split("-")[0], [int(x) if x.isdigit() else 0 for x in re.split(r"[-.]", c)[1:]]))
    fam = lambda f: [c for c in ctl if c.startswith(f + "-")]  # noqa: E731
    print(build("p20_ac", fam("ac")[:20], "Access Control Policy"))
    print(build("p100_multi", (fam("ac") + fam("au") + fam("cm") + fam("ia") + fam("ir"))[:100], "Information Security Policy"))
    print(build("p284_broad", ctl[:284], "Enterprise Security Policy"))
    print(build("neg_ra", fam("ra"), "Risk Assessment Policy"))
    neg = ("SYNTHETIC Travel and Expense Policy (benchmark negative – no security content)\n\n--- Page 1 ---\n\n## 1 Purpose\n"
           "Employees book economy airfare at least 14 days before travel. Meal receipts over 25 dollars are submitted within 30 days. "
           "Mileage is reimbursed at the published federal rate.\n\n## 2 Approvals\nManagers approve travel requests in the finance portal.\n")
    (OUT / "neg_unrelated.txt").write_text(neg)
    (OUT / "neg_unrelated.gold.json").write_text(json.dumps({"policy": "neg_unrelated", "controls": [], "requirements": {}}))


if __name__ == "__main__":
    main()
