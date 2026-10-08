"""Outgoing email over SMTP, for password resets and sign-ups.

Any SMTP server works: your own, your mailbox provider's, or a sending service (Resend, Postmark,
Amazon SES and others offer SMTP). Email features switch on when INSKECT_SMTP_HOST,
INSKECT_MAIL_FROM and INSKECT_PUBLIC_URL are all set; without them, password
resets go through admin-issued links only.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings, get_settings

_TIMEOUT_SECONDS = 15


def is_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.smtp_host and settings.mail_from and settings.public_url)


def public_link(path: str, settings: Settings | None = None) -> str:
    """An absolute link to this app. Always built from PUBLIC_URL, never from a request's Host
    header, so nobody can get a reset email sent that points at their own site."""
    settings = settings or get_settings()
    return settings.public_url.rstrip("/") + path


def send(to: str, subject: str, text: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not is_configured(settings):
        raise RuntimeError("Email isn't configured on this server")

    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    # Plain 7-bit text keeps each link on one unbroken line, even for readers that show the raw
    # message (quoted-printable, the default for long lines, would wrap it).
    message.set_content(text, cte="7bit")

    context = ssl.create_default_context()
    if settings.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=_TIMEOUT_SECONDS, context=context
        )
    else:
        client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=_TIMEOUT_SECONDS)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls(context=context)
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


def send_password_reset(to: str, path: str, *, hours: int) -> None:
    send(
        to,
        "Reset your Inskect password",
        f"""Someone asked to reset the password for {to} on Inskect.

Choose a new password here (the link works once, for {hours} hours):

{public_link(path)}

Choosing a new password signs you out everywhere and revokes your API tokens.

If you didn't ask for this, ignore this email: your password stays the same.
""",
    )


def send_signup_confirmation(to: str, path: str, *, hours: int) -> None:
    send(
        to,
        "Finish creating your Inskect account",
        f"""Someone asked to create an account for {to} on Inskect.

Finish creating it here (the link works once, for {hours} hours):

{public_link(path)}

If you didn't ask for this, ignore this email: no account is created.
""",
    )


def send_account_exists(to: str, *, login_path: str, reset_path: str) -> None:
    send(
        to,
        "You already have an Inskect account",
        f"""Someone tried to create an account for {to} on Inskect, but this email already has one.

Sign in here:

{public_link(login_path)}

Forgot your password? Choose a new one here:

{public_link(reset_path)}

If you didn't try to sign up, ignore this email: your account hasn't changed.
""",
    )
