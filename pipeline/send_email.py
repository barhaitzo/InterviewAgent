"""SMTP email delivery via Gmail App Password."""
import logging
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self) -> None:
        load_dotenv()
        self.host = os.environ["SMTP_HOST"]
        self.port = int(os.environ["SMTP_PORT"])
        self.user = os.environ["SMTP_USER"]
        self.password = os.environ["SMTP_APP_PASSWORD"]
        self.to = os.environ["EMAIL_TO"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(self, subject: str, body_html: str, body_text: str | None = None) -> None:
        """Send via Gmail SMTP with STARTTLS. body_text is a plain-text fallback."""
        if body_text is None:
            body_text = body_html

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.user
        msg["To"] = self.to
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(self.host, self.port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(self.user, self.password)
            smtp.sendmail(self.user, [self.to], msg.as_string())

        logger.info("Email sent to %s", self.to)

    @staticmethod
    def build_html(anecdote: str, question: str, topic: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<body style="font-family: Georgia, serif; max-width: 620px; margin: 40px auto; color: #1a1a1a; line-height: 1.75;">
  <p style="font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 2px;">
    Today&rsquo;s Topic
  </p>
  <p style="font-size: 14px; color: #555; margin-top: 0; margin-bottom: 32px;">
    {topic}
  </p>

  <h2 style="font-size: 18px; font-weight: bold; margin-bottom: 8px; border-bottom: 2px solid #eee; padding-bottom: 6px;">
    Concept Refresher
  </h2>
  <p style="margin-top: 12px;">{anecdote}</p>

  <h2 style="font-size: 18px; font-weight: bold; margin-top: 36px; margin-bottom: 8px; border-bottom: 2px solid #eee; padding-bottom: 6px;">
    Interview Question
  </h2>
  <p style="margin-top: 12px; font-style: italic; color: #333;">{question}</p>

  <p style="font-size: 11px; color: #bbb; margin-top: 48px; border-top: 1px solid #f0f0f0; padding-top: 16px;">
    Generated locally by your interview agent &middot; Ollama + Qwen&nbsp;2.5&nbsp;7B
  </p>
</body>
</html>"""


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sender = EmailSender()
    sender.send(
        subject="[TEST] Interview Agent — Daily Prep",
        body_html="<p>This is a test email from the interview agent. If you see this, SMTP is working.</p>",
        body_text="This is a test email from the interview agent.",
    )
    logger.info("Done. Check your inbox.")
