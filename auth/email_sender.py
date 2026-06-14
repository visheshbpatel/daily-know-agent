"""Send OTP verification emails via Gmail SMTP (smtplib)."""

from __future__ import annotations

import os
import random
import smtplib
import string
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")


def generate_otp() -> str:
    """Returns a random 6-digit string like '482910'."""
    return "".join(random.choices(string.digits, k=6))


def get_otp_expiry() -> str:
    """Returns a datetime string 10 minutes from now (local naive time)."""
    expiry = datetime.now() + timedelta(minutes=10)
    return expiry.strftime("%Y-%m-%d %H:%M:%S")


def send_otp_email(to_email: str, otp: str) -> tuple[bool, str]:
    """
    Sends OTP to the given email address.
    Returns (True, "sent") on success, (False, error_message) on failure.
    """
    if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
        return (
            False,
            "Email is not configured. Set EMAIL_ADDRESS and EMAIL_APP_PASSWORD in `.env`.",
        )

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Your Daily Knowledge Agent verification code"
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        plain_text = f"""
Hi there,

Your verification code for Daily Knowledge Agent is:

{otp}

This code expires in 10 minutes.
If you did not request this, ignore this email.

— Daily Knowledge Agent
"""

        html_content = f"""
<html>
  <body style="font-family: Arial, sans-serif; max-width: 480px; margin: auto; padding: 24px;">
    <h2 style="color: #1a1a2e;">Daily Knowledge Agent</h2>
    <p style="color: #444;">Thanks for signing up! Enter this code to verify your email:</p>
    <div style="
      background: #f0f4ff;
      border-radius: 12px;
      padding: 24px;
      text-align: center;
      margin: 24px 0;
    ">
      <span style="
        font-size: 40px;
        font-weight: bold;
        letter-spacing: 10px;
        color: #2d46b9;
      ">{otp}</span>
    </div>
    <p style="color: #888; font-size: 14px;">This code expires in <strong>10 minutes</strong>.</p>
    <p style="color: #888; font-size: 14px;">If you did not create an account, you can safely ignore this email.</p>
  </body>
</html>
"""

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            smtp.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())

        return True, "sent"

    except smtplib.SMTPAuthenticationError:
        return False, "Email authentication failed. Check EMAIL_APP_PASSWORD in `.env`."
    except smtplib.SMTPException as e:
        return False, f"Failed to send email: {e!s}"
    except Exception as e:
        return False, f"Unexpected error: {e!s}"
