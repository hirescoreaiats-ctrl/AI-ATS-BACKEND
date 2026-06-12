from __future__ import annotations

import os
import re
import smtplib
from email.mime.text import MIMEText

import requests


SUPPORT_DEFAULT_TO_EMAIL = "hirescoreaiats@gmail.com"


def sanitize_email_text(value: object, limit: int = 6000) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()[:limit]


def _smtp_config() -> dict:
    username = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER")
    from_email = os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_FROM") or username
    return {
        "host": os.getenv("SMTP_HOST"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "username": username,
        "password": os.getenv("SMTP_PASSWORD"),
        "from_email": from_email,
        "to_email": os.getenv("SUPPORT_TO_EMAIL") or SUPPORT_DEFAULT_TO_EMAIL,
    }


def build_support_email(case_data: dict) -> tuple[str, str]:
    priority = sanitize_email_text(case_data.get("priority"), 80)
    issue_type = sanitize_email_text(case_data.get("issue_type"), 120)
    subject = sanitize_email_text(case_data.get("subject"), 160)
    email_subject = f"[HireScore AI Support] {priority} - {issue_type} - {subject}"

    fields = [
        ("Full Name", case_data.get("full_name")),
        ("Email", case_data.get("email")),
        ("Company Name", case_data.get("company_name") or "Not provided"),
        ("Issue Type", issue_type),
        ("Priority", priority),
        ("Subject", subject),
        ("Message", case_data.get("message")),
        ("Logged-in User Email", case_data.get("logged_in_user_email") or "Not available"),
        ("Logged-in User ID", case_data.get("logged_in_user_id") or "Not available"),
        ("Submitted Timestamp", case_data.get("submitted_at")),
        ("App Environment", case_data.get("environment")),
        ("Support Case ID", case_data.get("case_id") or "Not stored"),
    ]
    body = "\n\n".join(f"{label}:\n{sanitize_email_text(value)}" for label, value in fields)
    return email_subject, body


def send_support_case_email(case_data: dict) -> dict:
    resend_key = os.getenv("RESEND_API_KEY")
    resend_from = os.getenv("RESEND_FROM")
    config = _smtp_config()
    subject, body = build_support_email(case_data)

    if resend_key and resend_from:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            json={
                "from": resend_from,
                "to": [config["to_email"]],
                "subject": subject,
                "html": f"<pre style='font-family:Arial,sans-serif;white-space:pre-wrap'>{sanitize_email_text(body, 12000)}</pre>",
            },
            timeout=20,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Support Resend delivery failed with status {response.status_code}")
        return {"provider": "resend", "to": config["to_email"], "from": resend_from}

    if not (config["host"] and config["username"] and config["password"] and config["from_email"]):
        raise RuntimeError("Support SMTP is not configured")

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = config["from_email"]
    message["To"] = config["to_email"]

    if config["port"] == 465:
        with smtplib.SMTP_SSL(config["host"], config["port"], timeout=20) as server:
            server.login(config["username"], config["password"])
            server.send_message(message)
    else:
        with smtplib.SMTP(config["host"], config["port"], timeout=20) as server:
            server.starttls()
            server.login(config["username"], config["password"])
            server.send_message(message)

    return {"provider": "smtp", "to": config["to_email"], "from": config["from_email"]}
