"""Outbound email delivery for triggered alerts (spec section 3 — Email delivery only in
this MVP; the Alert.delivery_method column already models push/telegram/discord for later)."""
import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailNotConfigured(RuntimeError):
    pass


def send_alert_email(to_email: str, ticker: str, alert_type: str, message: str) -> None:
    if not settings.smtp_host:
        raise EmailNotConfigured("SMTP_HOST is not configured.")

    msg = EmailMessage()
    msg["Subject"] = f"[Stock Intelligence] {ticker} alert: {alert_type.replace('_', ' ').title()}"
    msg["From"] = settings.alert_from_email
    msg["To"] = to_email
    msg.set_content(message)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
