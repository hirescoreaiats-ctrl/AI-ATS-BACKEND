from fastapi.testclient import TestClient

from backend.api import support as support_api
from backend.main import app


def support_payload(**overrides):
    payload = {
        "full_name": "Asha Sharma",
        "email": "asha.support@example.com",
        "company_name": "Hiring Tech",
        "issue_type": "Dashboard/Data Issue",
        "priority": "High",
        "subject": "Dashboard numbers look stale",
        "message": "The dashboard is showing old counts after refreshing the page.",
    }
    payload.update(overrides)
    return payload


def test_support_endpoint_sends_email_and_returns_success(monkeypatch):
    sent = {}
    support_api._SUPPORT_RATE_LIMIT.clear()

    def fake_send(case_data):
        sent.update(case_data)
        return {"provider": "test", "to": "hirescoreaiats@gmail.com"}

    monkeypatch.setattr(support_api, "send_support_case_email", fake_send)

    response = TestClient(app).post("/api/v1/support/case", json=support_payload())

    assert response.status_code == 200
    assert response.json()["message"] == "Support case submitted successfully."
    assert response.json()["case_id"]
    assert sent["email"] == "asha.support@example.com"
    assert sent["issue_type"] == "Dashboard/Data Issue"
    assert sent["priority"] == "High"
    assert sent["environment"]
    assert sent["case_id"] == response.json()["case_id"]


def test_support_endpoint_validates_required_fields(monkeypatch):
    support_api._SUPPORT_RATE_LIMIT.clear()
    monkeypatch.setattr(support_api, "send_support_case_email", lambda _payload: None)

    payload = support_payload(subject="")
    response = TestClient(app).post("/api/v1/support/case", json=payload)

    assert response.status_code == 422


def test_support_endpoint_returns_generic_error_on_email_failure(monkeypatch):
    support_api._SUPPORT_RATE_LIMIT.clear()

    def fail_send(_case_data):
        raise RuntimeError("smtp username/password rejected")

    monkeypatch.setattr(support_api, "send_support_case_email", fail_send)

    response = TestClient(app).post(
        "/api/v1/support/case",
        json=support_payload(email="email.failure@example.com"),
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to submit support case right now. Please try again."
    assert "smtp" not in str(response.json()).lower()
