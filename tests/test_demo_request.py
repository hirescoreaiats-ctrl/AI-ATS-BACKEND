from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api import demo as demo_api
from backend.main import app


def demo_payload(**overrides):
    payload = {
        "name": "Asha Sharma",
        "workEmail": "asha@example.com",
        "companyName": "Hiring Tech",
        "hiringVolume": "6 to 20 roles",
        "message": "We want to evaluate HireScoreAI.",
        "sourcePage": "https://hirescoreai.com/contact",
    }
    payload.update(overrides)
    return payload


def test_demo_endpoint_sends_email_before_returning_success(monkeypatch):
    captured = {}
    demo_api._DEMO_RATE_LIMIT.clear()

    def fake_delivery(payload, submitted_at):
        captured.update(payload=payload, submitted_at=submitted_at)
        return {"provider": "brevo", "message_id": "test-message"}

    monkeypatch.setattr(demo_api, "_deliver_demo_request", fake_delivery)
    response = TestClient(app).post("/api/v1/demo/request", json=demo_payload())

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert response.json()["provider"] == "brevo"
    assert captured["payload"].name == "Asha Sharma"
    assert captured["payload"].workEmail == "asha@example.com"
    assert captured["payload"].companyName == "Hiring Tech"
    assert captured["payload"].hiringVolume == "6 to 20 roles"
    assert captured["payload"].message == "We want to evaluate HireScoreAI."
    assert captured["payload"].sourcePage == "https://hirescoreai.com/contact"
    assert captured["submitted_at"]


def test_demo_email_contains_every_required_field(monkeypatch):
    sent = {}
    payload = demo_api.DemoRequest(**demo_payload())
    monkeypatch.setattr(demo_api, "get_settings", lambda: SimpleNamespace(demo_request_to_email="info@hirescoreai.com"))
    monkeypatch.setattr(demo_api, "send_transactional_email", lambda **kwargs: sent.update(kwargs) or {"provider": "brevo"})

    result = demo_api._deliver_demo_request(payload, "2026-08-26T12:30:00+00:00")

    assert result["provider"] == "brevo"
    assert sent["to_email"] == "info@hirescoreai.com"
    assert sent["subject"] == "New HireScoreAI Demo Request — Hiring Tech"
    for expected in (
        "Name: Asha Sharma",
        "Work Email: asha@example.com",
        "Company: Hiring Tech",
        "Hiring Volume: 6 to 20 roles",
        "Message: We want to evaluate HireScoreAI.",
        "Submitted At: 2026-08-26T12:30:00+00:00",
        "Source Page: https://hirescoreai.com/contact",
    ):
        assert expected in sent["text_body"]


def test_demo_endpoint_validates_required_fields():
    demo_api._DEMO_RATE_LIMIT.clear()
    response = TestClient(app).post("/api/v1/demo/request", json=demo_payload(workEmail="not-an-email"))
    assert response.status_code == 422


def test_demo_endpoint_does_not_report_success_when_email_fails(monkeypatch):
    demo_api._DEMO_RATE_LIMIT.clear()
    monkeypatch.setattr(demo_api, "_deliver_demo_request", lambda *_args: (_ for _ in ()).throw(RuntimeError("provider secret")))

    response = TestClient(app).post("/api/v1/demo/request", json=demo_payload(workEmail="failure@example.com"))

    assert response.status_code == 502
    assert response.json()["detail"] == "Unable to send your demo request right now. Please try again."
    assert "secret" not in str(response.json()).lower()
