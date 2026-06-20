from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

import requests


def _sender_details() -> tuple[str, str]:
    configured = (
        os.getenv("DEFAULT_FROM_EMAIL")
        or os.getenv("HIRESCORE_DEFAULT_FROM_EMAIL")
        or os.getenv("SMTP_FROM_EMAIL")
        or os.getenv("SMTP_FROM")
        or os.getenv("RESEND_FROM")
        or os.getenv("SMTP_USERNAME")
        or os.getenv("SMTP_USER")
        or "Info@hirescoreai.com"
    )
    display_name, address = parseaddr(configured)
    return (
        os.getenv("DEFAULT_FROM_NAME") or os.getenv("HIRESCORE_DEFAULT_FROM_NAME") or display_name or "HireScore AI",
        address or configured,
    )


def send_transactional_email(
    *,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    to_name: str = "",
) -> dict:
    """Send platform-owned transactional mail using Brevo, Resend, or SMTP."""
    sender_name, sender_email = _sender_details()
    brevo_key = (os.getenv("BREVO_API_KEY") or os.getenv("SENDINBLUE_API_KEY") or "").strip()
    resend_key = (os.getenv("RESEND_API_KEY") or "").strip()

    if brevo_key:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"accept": "application/json", "api-key": brevo_key, "content-type": "application/json"},
            json={
                "sender": {"name": sender_name, "email": sender_email},
                "to": [{"email": to_email, "name": to_name or to_email}],
                "subject": subject,
                "htmlContent": html_body,
                "textContent": text_body,
            },
            timeout=25,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Brevo delivery failed ({response.status_code}): {response.text[:300]}")
        payload = response.json() if response.content else {}
        return {"provider": "brevo", "message_id": payload.get("messageId")}

    if resend_key:
        resend_from = os.getenv("RESEND_FROM") or f"{sender_name} <{sender_email}>"
        response = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            json={
                "from": resend_from,
                "to": [to_email],
                "subject": subject,
                "html": html_body,
                "text": text_body,
            },
            timeout=25,
        )
        if response.status_code >= 300:
            raise RuntimeError(f"Resend delivery failed ({response.status_code}): {response.text[:300]}")
        payload = response.json() if response.content else {}
        return {"provider": "resend", "message_id": payload.get("id")}

    smtp_host = os.getenv("SMTP_HOST")
    smtp_username = os.getenv("SMTP_USERNAME") or os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    if not (smtp_host and smtp_username and smtp_password and sender_email):
        raise RuntimeError("Transactional email provider is not configured")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"{sender_name} <{sender_email}>"
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=25) as server:
            server.login(smtp_username, smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=25) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(message)
    return {"provider": "smtp", "message_id": None}
