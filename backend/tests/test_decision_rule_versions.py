from types import SimpleNamespace

from app.services import workflow as wf


def test_validate_rules_ignores_inactive_history_versions():
    o = "org"
    hist = [SimpleNamespace(org_id=o, request_type="risk_acceptance", is_active=False, version=v) for v in range(1, 7)]
    active = SimpleNamespace(org_id=o, request_type="risk_acceptance", is_active=True, version=7)
    assert wf.validate_rules(hist + [active]) == [], "editing a rule with older inactive versions must not be an overlap"
    assert wf.validate_rules(hist + [active, SimpleNamespace(org_id=o, request_type="risk_acceptance", is_active=True, version=8)])
