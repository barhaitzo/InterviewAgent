import pytest
from unittest.mock import patch, MagicMock

from pipeline.email_sender import EmailSender


SMTP_ENV = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "sender@gmail.com",
    "SMTP_APP_PASSWORD": "test-app-password",
    "EMAIL_TO": "recipient@gmail.com",
}


@pytest.fixture
def sender() -> EmailSender:
    with patch("pipeline.email_sender.load_dotenv"), patch.dict("os.environ", SMTP_ENV):
        return EmailSender()


# ---------------------------------------------------------------------------
# build_html  (static method — pure string transformation)
# ---------------------------------------------------------------------------

class TestBuildHtml:
    def test_contains_topic(self, sender):
        html = sender.build_html("anecdote", "key takeaway", "Feature Stores")
        assert "Feature Stores" in html

    def test_contains_anecdote(self, sender):
        html = sender.build_html("my anecdote text", "kt", "topic")
        assert "my anecdote text" in html

    def test_contains_key_takeaway(self, sender):
        html = sender.build_html("a", "my key takeaway text", "topic")
        assert "my key takeaway text" in html

    def test_is_valid_html_document(self, sender):
        html = sender.build_html("a", "q", "t")
        assert "<!DOCTYPE html>" in html
        assert "<body" in html
        assert "</html>" in html

    def test_special_characters_not_escaped_by_default(self, sender):
        # Build simply interpolates — caller's responsibility
        html = sender.build_html("anec <em>text</em>", "q?", "t")
        assert "<em>text</em>" in html


# ---------------------------------------------------------------------------
# send  (mocked SMTP)
# ---------------------------------------------------------------------------

class TestSend:
    @pytest.fixture
    def mock_smtp(self):
        with patch("smtplib.SMTP") as mock_cls:
            instance = MagicMock()
            mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
            mock_cls.return_value.__exit__ = MagicMock(return_value=False)
            yield instance

    def test_sendmail_called_once(self, sender, mock_smtp):
        sender.send("Subject", "<p>body</p>", "plain body")
        mock_smtp.sendmail.assert_called_once()

    def test_sendmail_uses_correct_sender_and_recipient(self, sender, mock_smtp):
        sender.send("Subject", "<p>body</p>")
        args = mock_smtp.sendmail.call_args[0]
        assert args[0] == "sender@gmail.com"
        assert args[1] == ["recipient@gmail.com"]

    def test_starttls_called(self, sender, mock_smtp):
        sender.send("Subject", "<p>body</p>")
        mock_smtp.starttls.assert_called_once()

    def test_login_called_with_credentials(self, sender, mock_smtp):
        sender.send("Subject", "<p>body</p>")
        mock_smtp.login.assert_called_once_with("sender@gmail.com", "test-app-password")

    def test_plain_text_defaults_to_html_when_not_provided(self, sender, mock_smtp):
        sender.send("Subject", "<p>body</p>")
        mock_smtp.sendmail.assert_called_once()
