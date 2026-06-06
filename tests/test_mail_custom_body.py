from backend.routers import job as job_router


class FakeDB:
    def close(self):
        pass


def test_send_mail_uses_custom_body_without_generating_ai(monkeypatch):
    captured = {}

    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    monkeypatch.setattr(job_router, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(
        job_router,
        "_candidate_email_body",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("AI body should not be generated")),
    )
    monkeypatch.setattr(job_router, "_mark_mail_sent", lambda *args, **kwargs: None)

    def fake_gmail(recruiter_email, to_email, subject, body, db):
        captured.update(
            {
                "recruiter_email": recruiter_email,
                "to_email": to_email,
                "subject": subject,
                "body": body,
            }
        )
        return {"sender_email": recruiter_email, "id": "gmail-1"}

    monkeypatch.setattr(job_router, "_send_with_recruiter_gmail", fake_gmail)

    result = job_router.send_mail(
        {
            "email": "candidate@example.com",
            "name": "Candidate",
            "job_id": "job-1",
            "job_title": "Data Analyst",
            "recruiter_email": "sachin.yadav@infometry.net",
            "subject": "Custom subject",
            "body": "Custom pasted body",
        }
    )

    assert result["provider"] == "gmail"
    assert captured["subject"] == "Custom subject"
    assert captured["body"] == "Custom pasted body"
    assert captured["recruiter_email"] == "sachin.yadav@infometry.net"
