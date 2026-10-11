from app.services.content.loader import parse_cci_reference
from tests.conftest import auth


def _stats(client, token):
    return client.get("/api/v1/content/stats", headers=auth(token("isso@aegisrmf.demo"))).json()


def test_catalog_counts(client, token):
    s = _stats(client, token)
    assert s["loaded"] is True
    assert s["controls_total"] == 1196
    assert s["enhancements"] == 872
    assert s["base_controls"] == 324
    assert s["baselines"] == {"low": 149, "moderate": 287, "high": 370, "privacy": 96}
    assert s["assessment_objectives"] > 3000


def test_cci_counts(client, token):
    s = _stats(client, token)
    assert s["ccis"] == 5137
    assert s["cci_rev5_mappings"] == 3838
    assert s["cci_rev5_mappings_resolved"] == s["cci_rev5_mappings"]


def test_content_versions_pinned(client, token):
    rows = client.get("/api/v1/content/versions", headers=auth(token("isso@aegisrmf.demo"))).json()
    by_key = {r["content_key"]: r for r in rows}
    cat = by_key["sp800-53r5-catalog"]
    assert cat["release_tag"] == "v1.5.0"
    assert cat["commit_sha"] == "78650f02ad9321bb7b817846f8fbd4f2bcd620de"
    assert cat["sha256"] == "01f37cf90ea99d92242c936cbfbdebcc338eef1f71454e2acac36cc56e9bc062"
    assert by_key["disa-cci-list"]["version"] == "2025-01-23"
    assert len([r for r in rows if r["content_type"] not in ("stig_benchmark", "kev_catalog")]) == 6


def test_control_search_and_filters(client, token):
    h = auth(token("isso@aegisrmf.demo"))
    r = client.get("/api/v1/controls", params={"q": "ac-2", "limit": 5}, headers=h).json()
    assert r["items"][0]["control_id"] == "ac-2"
    mod = client.get("/api/v1/controls", params={"baseline": "moderate", "limit": 1}, headers=h).json()
    assert mod["total"] == 287
    fam = client.get("/api/v1/controls", params={"family": "au", "include_withdrawn": True, "limit": 1}, headers=h).json()
    assert fam["total"] > 0


def test_control_detail(client, token):
    d = client.get("/api/v1/controls/ac-2", headers=auth(token("isso@aegisrmf.demo"))).json()
    assert d["title"] == "Account Management"
    assert set(d["baselines"]) == {"low", "moderate", "high"}
    assert d["objectives"] and d["ccis"] and d["parameters"]
    assert "[Assignment:" in d["statement"]


def test_parse_cci_reference():
    assert parse_cci_reference("AC-2 (3) (d)") == ("ac-2.3", "(d)")
    assert parse_cci_reference("AC-1 a 1 (a)") == ("ac-1", "a 1 (a)")
    assert parse_cci_reference("SC-7") == ("sc-7", None)
