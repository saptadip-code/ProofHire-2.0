"""End-to-end smoke test against a RUNNING API (guidebook D1/D9).

    python scripts/e2e_smoke.py [--base-url http://localhost:8000/api/v1] [--admin-email E --admin-password P]

Flow: health -> register -> assess (anonymous + logged in) -> get -> checklist PATCH -> compare -> report
-> (optional admin approve) -> dashboard. Needs only httpx. Prints PASS/FAIL per step; exit code 1 on any failure.
"""
import argparse
import sys
import uuid

import httpx

LISTING = {
    "title": "Data Entry Intern - Earn 40000 per month!!", "company_name": "Brightpath Careers",
    "description": "Work from home. No experience needed. Pay registration fee of Rs 1499 to confirm your seat. Apply today, limited seats!",
    "salary_min": 40000, "salary_max": 40000, "pay_period": "month", "contact_email": "brightpath.hr@gmail.com",
    "application_channel": "whatsapp", "upfront_fee_amount": 1499, "interview_mode": "chat_only",
}
GOOD = {
    "title": "Software Engineering Intern", "company_name": "Nexora Labs",
    "description": "Join our platform team for six months. You will build and review features with a mentor and present your work.",
    "requirements": "Python or JavaScript, data structures, version control, willingness to learn and ask questions in code review.",
    "salary_min": 25000, "salary_max": 30000, "contact_email": "careers@nexoralabs.com",
    "company_website": "https://nexoralabs.com", "application_channel": "email", "interview_mode": "video_call",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000/api/v1")
    ap.add_argument("--admin-email")
    ap.add_argument("--admin-password")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.base_url.rstrip("/"), timeout=30)
    failures = []

    def step(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
        if not ok:
            failures.append(name)

    r = c.get("/health"); step("health", r.status_code == 200 and r.json().get("model_loaded") is True, r.text[:120])
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    r = c.post("/auth/register", json={"email": email, "password": "smoke-pass-123", "display_name": "Smoke"})
    step("register", r.status_code == 201, r.text[:120])
    token = r.json().get("access_token") if r.status_code == 201 else None
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    r = c.get("/auth/me", headers=auth); step("auth/me", r.status_code == 200 and r.json().get("email") == email)
    r = c.get("/auth/me"); step("auth/me without token is 401", r.status_code == 401)

    r = c.post("/assessments", json=LISTING); step("assess anonymous (201 + owner_token)", r.status_code == 201 and bool(r.json().get("owner_token")), r.text[:160])
    anon = r.json() if r.status_code == 201 else {}
    r = c.post("/assessments", json=GOOD, headers=auth); step("assess logged in (201)", r.status_code == 201, r.text[:160])
    good = r.json() if r.status_code == 201 else {}
    ida, idb = anon.get("assessment_id"), good.get("assessment_id")
    if ida:
        r = c.get(f"/assessments/{ida}"); step("get assessment", r.status_code == 200 and r.json().get("risk_level") in ("low", "medium", "high"))
        items = anon.get("checklist") or []
        step("checklist is not empty (library present)", len(items) > 0)
        if items:
            r = c.patch(f"/assessments/{ida}/checklist/{items[0]['id']}", json={"done": True}, headers={"X-Owner-Token": anon["owner_token"]})
            step("checklist PATCH with owner token", r.status_code == 200 and r.json().get("done") is True, r.text[:120])
        r = c.post("/reports", json={"assessment_id": ida, "report_type": "advance_fee", "description": "Asked for a Rs 1499 registration fee over WhatsApp."})
        step("report create (201 pending)", r.status_code == 201 and r.json().get("status") == "pending", r.text[:120])
        rid = r.json().get("id") if r.status_code == 201 else None
        r = c.post("/reports", json={"assessment_id": ida, "report_type": "advance_fee", "description": "Asked for a Rs 1499 registration fee over WhatsApp."})
        step("duplicate report is 409", r.status_code == 409)
        if a.admin_email and a.admin_password and rid:
            r = c.post("/auth/login", json={"email": a.admin_email, "password": a.admin_password})
            adm = {"Authorization": f"Bearer {r.json().get('access_token')}"} if r.status_code == 200 else {}
            r = c.get("/admin/reports", headers=auth); step("admin list as non-admin is 403", r.status_code == 403)
            r = c.patch(f"/admin/reports/{rid}", json={"status": "approved", "moderator_note": "smoke"}, headers=adm)
            step("admin approve", r.status_code == 200 and r.json().get("status") == "approved", r.text[:120])
    if ida and idb:
        r = c.post("/assessments/compare", json={"assessment_id_a": ida, "assessment_id_b": idb})
        step("compare", r.status_code == 200 and "rows" in r.json() and "title" in r.json()["a"], r.text[:120])
    r = c.get("/assessments", headers=auth); step("list mine", r.status_code == 200 and r.json().get("total", 0) >= 1)
    r = c.get("/dashboard/summary"); step("dashboard summary", r.status_code == 200 and "by_level" in r.json())
    r = c.get("/dashboard/trends"); step("dashboard trends", r.status_code == 200 and isinstance(r.json(), list))
    r = c.get("/dashboard/model-metrics"); step("dashboard model-metrics", r.status_code == 200 and "synthetic_test" in r.json())
    r = c.post("/assessments", json={"title": "x"}); step("invalid body is 422 with error envelope", r.status_code == 422 and "error" in r.json())
    print(f"\n{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
