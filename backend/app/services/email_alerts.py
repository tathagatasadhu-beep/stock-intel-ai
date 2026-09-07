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


def send_portfolio_digest_email(to_email: str, flags: list[tuple[str, str, str]]) -> None:
    """One email per user per day summarizing every newly-raised portfolio flag (see
    services/portfolio_monitor.py), rather than a separate email per flag — a portfolio
    with several holdings flagged the same day would otherwise spam the inbox.
    `flags` is [(ticker, severity, message), ...]."""
    if not settings.smtp_host:
        raise EmailNotConfigured("SMTP_HOST is not configured.")
    if not flags:
        return

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    flags = sorted(flags, key=lambda f: severity_order.get(f[1], 3))

    lines = [f"{len(flags)} new flag(s) on your portfolio:", ""]
    for ticker, severity, message in flags:
        lines.append(f"[{severity.upper()}] {ticker}: {message}")
    lines.append("")
    lines.append("These are algorithmic technical/fundamental/news signals, not financial advice — review before acting.")

    msg = EmailMessage()
    msg["Subject"] = f"[Stock Intelligence] {len(flags)} portfolio flag(s) today"
    msg["From"] = settings.alert_from_email
    msg["To"] = to_email
    msg.set_content("\n".join(lines))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
