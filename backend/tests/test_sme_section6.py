"""SME section 6: action → role matrix comes from the enforced RBAC table; 403s carry the roles that may act."""
import uuid

from app.security.rbac import ROLE_PERMISSIONS
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


def test_role_matrix_matches_rbac_and_403_names_roles(client, signup_on):  # noqa: F811
    t = _signup(client, f"s6-{uuid.uuid4().hex[:6]}@example.com", "S6 Org")
    h = auth(t["access_token"])
    r = client.get("/api/v1/reference/role-matrix", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert {x["key"] for x in d["roles"]} == set(ROLE_PERMISSIONS)
    by = {a["permission"]: a for a in d["actions"]}
    assert set(by["implementation.write"]["roles"]) == {k for k, p in ROLE_PERMISSIONS.items() if "implementation.write" in p}
    assert "implementation status" in by["implementation.write"]["action"]
    assert by["authorization.decide"]["roles"] == ["ao"]
    sid = client.post("/api/v1/systems", json={"name": "Section Six", "acronym": "S6", "baseline_key": "low"}, headers=h).json()["id"]
    act = client.post("/api/v1/sandbox/act-as", json={"role": "leadership_viewer"}, headers=h)
    assert act.status_code == 200, act.text
    lv = auth(act.json()["access_token"])
    den = client.post(f"/api/v1/systems/{sid}/select/tailor", headers=lv, json={"action": "add", "control_ids": ["ac-2.11"], "justification": "x" * 12})
    assert den.status_code == 403
    det = den.json()["detail"]
    assert det["code"] == "missing_permission" and det["permission"] == "system.write" and "isso" in det["roles"]
