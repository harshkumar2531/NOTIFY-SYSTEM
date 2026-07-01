import logging
from email.message import EmailMessage
import aiosmtplib
from jinja2 import Template
from app.config import settings

logger = logging.getLogger("email")

_TEMPLATE = Template(
    """\
<div style="font-family: system-ui, sans-serif; max-width: 480px;">
  <h2 style="margin:0 0 8px;">{{ title }}</h2>
  <p style="margin:0 0 12px; color:#333;">{{ body }}</p>
  <p style="color:#888; font-size:12px;">Type: {{ type }}</p>
</div>
"""
)

async def send_email(to_email: str, notification: dict) -> None:

    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = notification.get("title", "Notification")

    msg.set_content(notification.get("body", ""))
    msg.add_alternative(_TEMPLATE.render(**notification), subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        start_tls=False,
    )
    logger.info("Email sent to %s (%s)", to_email, notification.get("id"))
