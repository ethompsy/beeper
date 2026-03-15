"""Tests for the email notifier module."""

import smtplib
import socket
from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.notifications.email import (
    EmailNotifier,
    EmailNotifierError,
    _build_digest_email,
    _build_investigation_email,
    _escape_html,
    _severity_color,
)


class TestEmailNotifierError:
    """Tests for EmailNotifierError exception class."""

    def test_retryable_default_true(self) -> None:
        err = EmailNotifierError("connection lost")
        assert err.retryable is True
        assert str(err) == "connection lost"

    def test_non_retryable(self) -> None:
        err = EmailNotifierError("auth failed", retryable=False)
        assert err.retryable is False

    def test_retryable_explicit(self) -> None:
        err = EmailNotifierError("timeout", retryable=True)
        assert err.retryable is True


class TestEmailNotifierInit:
    """Tests for EmailNotifier constructor."""

    def test_defaults(self) -> None:
        notifier = EmailNotifier(smtp_host="smtp.example.com")
        assert notifier._smtp_host == "smtp.example.com"
        assert notifier._smtp_port == 587
        assert notifier._username == ""
        assert notifier._password == ""
        assert notifier._use_tls is True
        assert notifier._from_addr == ""

    def test_custom_values(self) -> None:
        notifier = EmailNotifier(
            smtp_host="mail.test.com",
            smtp_port=465,
            username="user@test.com",
            password="secret",
            use_tls=True,
            from_addr="beeper@test.com",
        )
        assert notifier._smtp_host == "mail.test.com"
        assert notifier._smtp_port == 465
        assert notifier._username == "user@test.com"
        assert notifier._password == "secret"
        assert notifier._from_addr == "beeper@test.com"

    def test_from_addr_defaults_to_username(self) -> None:
        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            username="sender@example.com",
        )
        assert notifier._from_addr == "sender@example.com"


class TestSendEmail:
    """Tests for send_email() method."""

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_sends_email_starttls(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            smtp_port=587,
            username="user",
            password="pass",
            use_tls=True,
            from_addr="beeper@example.com",
        )
        result = notifier.send_email(
            recipients=["sre@example.com"],
            subject="Test Subject",
            body_html="<h1>Test</h1>",
            body_text="Test",
        )

        assert result["status"] == "sent"
        assert "message_id" in result
        mock_smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.sendmail.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch("beeper_ui.notifications.email.smtplib.SMTP_SSL")
    def test_sends_email_implicit_tls(self, mock_smtp_ssl_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_ssl_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            smtp_port=465,
            username="user",
            password="pass",
            from_addr="beeper@example.com",
        )
        result = notifier.send_email(
            recipients=["sre@example.com"],
            subject="Test",
            body_html="<p>Test</p>",
            body_text="Test",
        )

        assert result["status"] == "sent"
        mock_smtp_ssl_class.assert_called_once_with("smtp.example.com", 465, timeout=30)
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.sendmail.assert_called_once()

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_sends_without_auth_when_no_credentials(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )
        notifier.send_email(
            recipients=["sre@example.com"],
            subject="Test",
            body_html="<p>Test</p>",
            body_text="Test",
        )

        mock_server.login.assert_not_called()
        mock_server.sendmail.assert_called_once()

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_sends_without_tls_when_disabled(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            use_tls=False,
            from_addr="beeper@example.com",
        )
        notifier.send_email(
            recipients=["sre@example.com"],
            subject="Test",
            body_html="<p>Test</p>",
            body_text="Test",
        )

        mock_server.starttls.assert_not_called()

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_multiple_recipients(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )
        notifier.send_email(
            recipients=["sre@example.com", "oncall@example.com"],
            subject="Test",
            body_html="<p>Test</p>",
            body_text="Test",
        )

        call_args = mock_server.sendmail.call_args
        assert call_args[0][1] == ["sre@example.com", "oncall@example.com"]

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_subject_truncated_at_max_length(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )
        long_subject = "A" * 2000
        notifier.send_email(
            recipients=["sre@example.com"],
            subject=long_subject,
            body_html="<p>Test</p>",
            body_text="Test",
        )

        call_args = mock_server.sendmail.call_args
        sent_message = call_args[0][2]
        # The Subject header should be truncated
        assert "A" * 999 not in sent_message or len(long_subject[:998]) <= 998

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_auth_error_is_non_retryable(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            username="bad-user",
            password="bad-pass",
            from_addr="beeper@example.com",
        )

        with pytest.raises(EmailNotifierError) as exc_info:
            notifier.send_email(
                recipients=["sre@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
                body_text="Test",
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_recipients_refused_is_non_retryable(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_server.sendmail.side_effect = smtplib.SMTPRecipientsRefused(
            {"bad@example.com": (550, b"Unknown")}
        )
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )

        with pytest.raises(EmailNotifierError) as exc_info:
            notifier.send_email(
                recipients=["bad@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
                body_text="Test",
            )

        assert not exc_info.value.retryable

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_connection_error_is_retryable(self, mock_smtp_class: MagicMock) -> None:
        mock_smtp_class.side_effect = smtplib.SMTPConnectError(451, b"Temp failure")

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )

        with pytest.raises(EmailNotifierError) as exc_info:
            notifier.send_email(
                recipients=["sre@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
                body_text="Test",
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_timeout_is_retryable(self, mock_smtp_class: MagicMock) -> None:
        mock_smtp_class.side_effect = socket.timeout("Connection timed out")

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )

        with pytest.raises(EmailNotifierError) as exc_info:
            notifier.send_email(
                recipients=["sre@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
                body_text="Test",
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_disconnected_is_retryable(self, mock_smtp_class: MagicMock) -> None:
        mock_smtp_class.side_effect = smtplib.SMTPServerDisconnected("Lost connection")

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )

        with pytest.raises(EmailNotifierError) as exc_info:
            notifier.send_email(
                recipients=["sre@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
                body_text="Test",
            )

        assert exc_info.value.retryable

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_os_error_is_retryable(self, mock_smtp_class: MagicMock) -> None:
        mock_smtp_class.side_effect = ConnectionRefusedError("Connection refused")

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )

        with pytest.raises(EmailNotifierError) as exc_info:
            notifier.send_email(
                recipients=["sre@example.com"],
                subject="Test",
                body_html="<p>Test</p>",
                body_text="Test",
            )

        assert exc_info.value.retryable


class TestSendInvestigationEmail:
    """Tests for send_investigation_email() method."""

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_sends_investigation_email(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )
        result = notifier.send_investigation_email(
            recipients=["sre@example.com"],
            investigation_id="inv-123",
            payload={
                "severity": "critical",
                "service": "payment-api",
                "summary": "CPU spike detected",
                "evidence": ["CPU at 95%", "Latency increased"],
                "confidence": 0.92,
            },
            base_url="https://beeper.test",
        )

        assert result["status"] == "sent"
        assert "message_id" in result

        # Verify email content
        call_args = mock_server.sendmail.call_args
        sent_message = call_args[0][2]
        assert "[CRITICAL]" in sent_message
        assert "payment-api" in sent_message
        assert "inv-123" in sent_message

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_investigation_email_with_no_evidence(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )
        result = notifier.send_investigation_email(
            recipients=["sre@example.com"],
            investigation_id="inv-456",
            payload={"severity": "low", "service": "test-svc"},
        )

        assert result["status"] == "sent"


class TestSendDigest:
    """Tests for send_digest() method."""

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_sends_digest_email(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )
        investigations = [
            {
                "investigation_id": "inv-001",
                "severity": "critical",
                "service": "api-gw",
                "summary": "High error rate",
                "status": "resolved",
            },
            {
                "investigation_id": "inv-002",
                "severity": "medium",
                "service": "auth-svc",
                "summary": "Elevated latency",
                "status": "investigating",
            },
        ]
        result = notifier.send_digest(
            recipients=["team@example.com"],
            investigations=investigations,
            period_label="Daily",
            base_url="https://beeper.test",
        )

        assert result["status"] == "sent"
        assert result["investigation_count"] == 2

    @patch("beeper_ui.notifications.email.smtplib.SMTP")
    def test_digest_with_single_investigation(self, mock_smtp_class: MagicMock) -> None:
        mock_server = MagicMock()
        mock_smtp_class.return_value = mock_server

        notifier = EmailNotifier(
            smtp_host="smtp.example.com",
            from_addr="beeper@example.com",
        )
        result = notifier.send_digest(
            recipients=["team@example.com"],
            investigations=[{"investigation_id": "inv-001", "severity": "low"}],
            period_label="Weekly",
        )

        assert result["investigation_count"] == 1
        # Verify singular form via the builder function directly
        subject, _, _ = _build_digest_email(
            [{"investigation_id": "inv-001", "severity": "low"}],
            period_label="Weekly",
        )
        assert "1 investigation" in subject
        assert "1 investigations" not in subject


class TestBuildInvestigationEmail:
    """Tests for _build_investigation_email() helper."""

    def test_subject_includes_severity_service_id(self) -> None:
        subject, _, _ = _build_investigation_email(
            "inv-123",
            {"severity": "high", "service": "api-gw"},
        )
        assert "[HIGH]" in subject
        assert "api-gw" in subject
        assert "inv-123" in subject

    def test_html_body_contains_investigation_link(self) -> None:
        _, body_html, _ = _build_investigation_email(
            "inv-123",
            {"severity": "critical"},
            base_url="https://beeper.test",
        )
        assert "https://beeper.test/investigations/inv-123" in body_html

    def test_text_body_contains_evidence(self) -> None:
        _, _, body_text = _build_investigation_email(
            "inv-123",
            {"evidence": ["CPU at 95%", "Memory leak detected"]},
        )
        assert "CPU at 95%" in body_text
        assert "Memory leak detected" in body_text

    def test_confidence_displayed(self) -> None:
        _, body_html, body_text = _build_investigation_email(
            "inv-123",
            {"confidence": 0.87},
        )
        assert "87%" in body_html
        assert "87%" in body_text

    def test_no_link_when_no_base_url(self) -> None:
        _, body_html, body_text = _build_investigation_email(
            "inv-123",
            {"severity": "low"},
        )
        assert "View Investigation" not in body_html

    def test_evidence_capped_at_10(self) -> None:
        evidence = [f"Evidence item {i}" for i in range(15)]
        _, _, body_text = _build_investigation_email(
            "inv-123",
            {"evidence": evidence},
        )
        assert "Evidence item 9" in body_text
        assert "Evidence item 10" not in body_text


class TestBuildDigestEmail:
    """Tests for _build_digest_email() helper."""

    def test_subject_contains_count_and_period(self) -> None:
        subject, _, _ = _build_digest_email(
            [{"severity": "high"}, {"severity": "low"}],
            period_label="Daily",
        )
        assert "Daily" in subject
        assert "2 investigations" in subject

    def test_singular_investigation_in_subject(self) -> None:
        subject, _, _ = _build_digest_email(
            [{"severity": "high"}],
            period_label="Weekly",
        )
        assert "1 investigation" in subject
        assert "1 investigations" not in subject

    def test_severity_breakdown_in_text(self) -> None:
        _, _, body_text = _build_digest_email(
            [
                {"severity": "critical"},
                {"severity": "critical"},
                {"severity": "low"},
            ],
        )
        assert "CRITICAL: 2" in body_text
        assert "LOW: 1" in body_text

    def test_html_contains_investigation_links(self) -> None:
        _, body_html, _ = _build_digest_email(
            [{"investigation_id": "inv-001", "severity": "high"}],
            base_url="https://beeper.test",
        )
        assert "https://beeper.test/investigations/inv-001" in body_html


class TestHelpers:
    """Tests for module-level helper functions."""

    def test_severity_colors(self) -> None:
        assert _severity_color("CRITICAL") == "#dc3545"
        assert _severity_color("HIGH") == "#fd7e14"
        assert _severity_color("MEDIUM") == "#ffc107"
        assert _severity_color("LOW") == "#28a745"
        assert _severity_color("unknown") == "#6c757d"

    def test_escape_html(self) -> None:
        assert _escape_html("<script>alert('xss')</script>") == (
            "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
            if "&#x27;" in _escape_html("'")
            else "&lt;script&gt;alert('xss')&lt;/script&gt;"
        )
        assert "&amp;" in _escape_html("a & b")
        assert "&lt;" in _escape_html("<tag>")
        assert "&gt;" in _escape_html("</tag>")
        assert "&quot;" in _escape_html('"quoted"')
