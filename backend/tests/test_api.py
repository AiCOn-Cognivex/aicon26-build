"""End-to-end API tests on a fresh SQLite database with the seeded demo company.

  .venv/Scripts/python -m pytest backend/tests -q
"""
from datetime import date

from backend.tests.conftest import ROOT, login

SAMPLE = ROOT / "frontend" / "public" / "demo" / "validation_0.jpg"   # model: AUTO_POST
UNSURE = ROOT / "frontend" / "public" / "demo" / "validation_21.jpg"  # model: HUMAN_REVIEW


def test_auth_required_and_wrong_password(client):
    assert client.get("/me/dashboard").status_code == 401
    r = client.post("/auth/token", data={"username": "ayesha@northwind.example", "password": "nope"})
    assert r.status_code == 401
    assert client.get("/me/dashboard", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_roles(client, ayesha, sara):
    assert client.get("/admin/overview", headers=ayesha).status_code == 403
    assert client.get("/admin/overview", headers=sara).status_code == 200
    me = client.get("/auth/me", headers=ayesha).json()
    assert me["role"] == "employee" and me["company"]["currency"] == "PKR"


def test_dashboard_shape(client, ayesha):
    d = client.get("/me/dashboard", headers=ayesha).json()
    assert d["payday"]["days_left"] >= 0 and d["payday"]["net"] > 0
    assert {w["code"] for w in d["wallets"]} == {"meals", "fuel", "medical", "mobile", "learning"}
    assert len(d["paychecks"]) == 12 and d["pf"]["balance"] > 0
    assert d["advance"]["available"] >= 0 and d["activity"]


def _scan(client, headers, path):
    r = client.post("/claims/scan", headers=headers, files={"file": (path.name, path.read_bytes(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def test_auto_approve_then_duplicate(client, ayesha):
    s = _scan(client, ayesha, SAMPLE)
    assert s["status"] == "draft" and s["model_decision"] == "AUTO_POST" and s["model_total"]
    assert s["suggestions"]["amount_source"] == "model"
    body = {"wallet": "meals", "amount": s["model_total"], "currency": "IDR", "receipt_date": date.today().isoformat()}
    r = client.post(f"/claims/{s['id']}/submit", headers=ayesha, json=body).json()
    assert r["status"] == "auto_approved", r["reasons"]
    assert r["pay_date"]
    # the same photo again is caught as a duplicate and goes to a person
    s2 = _scan(client, ayesha, SAMPLE)
    assert any(f["type"] == "duplicate_image" for f in s2["flags"])
    r2 = client.post(f"/claims/{s2['id']}/submit", headers=ayesha, json=body).json()
    assert r2["status"] == "in_review"
    assert any("duplicate" in x.lower() for x in r2["reasons"])


def test_edited_amount_and_policy_go_to_review(client, ayesha):
    s = _scan(client, ayesha, UNSURE)
    body = {"wallet": "fuel", "amount": (s["model_total"] or 1000) + 5000, "currency": "IDR",
            "receipt_date": date.today().isoformat()}
    r = client.post(f"/claims/{s['id']}/submit", headers=ayesha, json=body).json()
    assert r["status"] == "in_review"
    text = " ".join(r["reasons"])
    assert "changed by the employee" in text and "always checked by a person" in text


def test_review_approve_with_correction_and_payroll(client, ayesha, sara):
    q = client.get("/admin/queue", headers=sara).json()["claims"]
    mine = [c for c in q if c["employee"]["name"] == "Ayesha Khan"]
    assert mine
    cid = mine[0]["id"]
    assert client.post(f"/admin/claims/{cid}/decide", headers=sara, json={"action": "reject"}).status_code == 422
    r = client.post(f"/admin/claims/{cid}/decide", headers=sara,
                    json={"action": "approve", "amount": 50000, "note": "Corrected to the printed total"}).json()
    assert r["status"] == "approved" and r["corrected_amount"] == 50000 and r["pay_date"]
    p = client.get("/admin/payroll", headers=sara, params={"pay_date": r["pay_date"]}).json()
    assert any(row["name"] == "Ayesha Khan" for row in p["rows"])
    csv = client.get("/admin/payroll.csv", headers=sara, params={"pay_date": r["pay_date"]})
    assert csv.status_code == 200 and "reimbursements_pkr" in csv.text
    timeline = client.get(f"/claims/{cid}", headers=ayesha).json()["timeline"]
    assert [e["kind"] for e in timeline][-2:] == ["claim_corrected", "claim_approved"]


def test_cannot_see_others_claims(client, ayesha, sara):
    bilal = login(client, "bilal@northwind.example")
    mine = client.get("/claims", headers=ayesha).json()["claims"]
    assert client.get(f"/claims/{mine[0]['id']}", headers=bilal).status_code == 404
    assert client.get(f"/claims/{mine[0]['id']}", headers=sara).status_code == 200  # finance can


def test_advance_within_cap(client):
    fatima = login(client, "fatima@northwind.example")
    st = client.get("/advances", headers=fatima).json()
    too_much = st["available"] + 5000
    assert client.post("/advances", headers=fatima, json={"amount": too_much}).status_code == 422
    if st["available"] >= 1000:
        r = client.post("/advances", headers=fatima, json={"amount": 1000, "reason": "test"}).json()
        assert r["history"][0]["status"] == "approved"
        assert r["outstanding"] >= 1000


def test_policy_update_and_audit(client, sara):
    ws = client.get("/admin/wallets", headers=sara).json()["wallets"]
    meals = next(w for w in ws if w["code"] == "meals")
    body = {"limits": meals["limits"], "auto_approve": True, "per_claim_cap": 9000, "max_age_days": 60}
    assert client.put(f"/admin/wallets/{meals['id']}", headers=sara, json=body).status_code == 200
    ov = client.get("/admin/overview", headers=sara).json()
    assert ov["events"][0]["kind"] == "policy_changed"


def test_demo_reset(client, sara):
    assert client.post("/admin/demo/reset", headers=sara).status_code == 200
    fresh = login(client, "sara@northwind.example")
    q = client.get("/admin/queue", headers=fresh).json()["claims"]
    assert len(q) == 3  # back to the seeded state


def test_fingerprint_fits_column():
    from PIL import Image
    from backend.app.services.receipts import dhash
    for name in ("validation_0", "validation_3", "validation_21", "validation_5"):
        h = dhash(Image.open(ROOT / "frontend" / "public" / "demo" / f"{name}.jpg"))
        assert len(h) == 16 and all(c in "0123456789abcdef" for c in h), h
    for f in (ROOT / "backend" / "seed_assets").glob("*.jpg"):
        assert len(dhash(Image.open(f))) == 16
