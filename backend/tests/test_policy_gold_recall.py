"""Gold-set regression for the RA demo policy: a stored AI analysis (snapshot of the re-analysed result) reports no paragraph language missing."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from score_policy_gold import score  # noqa: E402

HERE = os.path.dirname(__file__)
GOLD = os.path.join(HERE, "..", "..", "docs", "perf", "corpus", "ra_raven.gold.json")
SNAP = os.path.join(HERE, "fixtures", "policies", "ra_raven_v2_results.json")


def test_ra_gold_recall_is_100_percent():
    rows = {(r["control_id"], r["requirement_id"]): r["status"] for r in json.load(open(SNAP))}
    res = score(json.load(open(GOLD)), rows)["ra"]
    assert res["recall"] == 1.0, res["missed"]
    assert res["precision"] >= 0.95, res


def test_scorer_counts_a_silent_miss():
    gold = {"requirements": [{"control_id": "ra-5", "requirement_id": "CCI-1", "label": "met"}, {"control_id": "ra-5", "requirement_id": "CCI-2", "label": "met"}]}
    res = score(gold, {("ra-5", "CCI-1"): "met", ("ra-5", "CCI-2"): "missing"})["ra"]
    assert res["recall"] == 0.5 and res["missed"] == ["ra-5 CCI-2"]
