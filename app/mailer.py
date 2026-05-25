from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def smtp_configured() -> bool:
    required = ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "MAIL_TO", "MAIL_FROM"]
    return all(os.getenv(name) for name in required)


def send_mail(subject: str, text_content: str, html_content: str) -> str:
    if not smtp_configured():
        raise RuntimeError("SMTP is not configured")

    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    mail_to = os.environ["MAIL_TO"]
    mail_from = os.environ["MAIL_FROM"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(text_content)
    msg.add_alternative(html_content, subtype="html")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(msg)
    return mail_to

