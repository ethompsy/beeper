"""Email channel integration for Beeper notifications.

Sends investigation notification emails via SMTP with HTML and plain-text
alternatives. Supports immediate delivery for critical alerts and digest
mode for periodic investigation summaries.

Implements FR12: Email alert digests and investigation summaries.
"""

import hashlib
import logging
import smtplib
import socket
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)

# SMTP non-retryable error types
_NON_RETRYABLE_SMTP_ERRORS = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPDataError,
    smtplib.SMTPNotSupportedError,
)

# Max email subject length (RFC 2822 recommendation)
_MAX_SUBJECT_LENGTH = 998


class EmailNotifierError(Exception):
    """Error sending email notification."""

    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class EmailNotifier:
    """Sends email notifications for Beeper investigations.

    Supports immediate single-investigation emails and digest emails
    summarizing multiple investigations over a time period.
    Uses smtplib (Python stdlib) — no additional dependencies required.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 587,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        from_addr: str = "",
    ) -> None:
        """Initialize the email notifier.

        Args:
            smtp_host: SMTP server hostname.
            smtp_port: SMTP server port (587 for STARTTLS, 465 for implicit TLS).
            username: SMTP authentication username.
            password: SMTP authentication password.
            use_tls: Whether to use TLS (STARTTLS for 587, implicit for 465).
            from_addr: Sender email address. Defaults to username if not set.
        """
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_addr = from_addr or username

    def send_email(
        self,
        recipients: list[str],
        subject: str,
        body_html: str,
        body_text: str,
    ) -> dict[str, Any]:
        """Send an email via SMTP.

        Args:
            recipients: List of recipient email addresses.
            subject: Email subject line.
            body_html: HTML email body.
            body_text: Plain-text email body.

        Returns:
            Dict with 'status' and 'message_id'.

        Raises:
            EmailNotifierError: If the SMTP operation fails.
        """
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject[:_MAX_SUBJECT_LENGTH]
        msg["From"] = self._from_addr
        msg["To"] = ", ".join(recipients)

        # Generate a message ID for tracking
        msg_hash = hashlib.md5(
            f"{subject}{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]
        message_id = f"<beeper-{msg_hash}@{self._smtp_host}>"
        msg["Message-ID"] = message_id

        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(body_html, "html"))

        try:
            if self._smtp_port == 465:
                server = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30)
                if self._use_tls:
                    server.starttls()

            try:
                if self._username and self._password:
                    server.login(self._username, self._password)
                server.sendmail(self._from_addr, recipients, msg.as_string())
                logger.info(
                    "Email sent: subject=%s recipients=%s message_id=%s",
                    subject[:80],
                    ", ".join(recipients),
                    message_id,
                )
                return {"status": "sent", "message_id": message_id}
            finally:
                server.quit()

        except _NON_RETRYABLE_SMTP_ERRORS as e:
            error_msg = f"Email delivery failed (non-retryable): {e}"
            logger.error(error_msg)
            raise EmailNotifierError(error_msg, retryable=False) from e
        except (
            smtplib.SMTPServerDisconnected,
            smtplib.SMTPConnectError,
            smtplib.SMTPException,
            socket.timeout,
            OSError,
        ) as e:
            error_msg = f"Email delivery failed (retryable): {e}"
            logger.error(error_msg)
            raise EmailNotifierError(error_msg, retryable=True) from e

    def send_investigation_email(
        self,
        recipients: list[str],
        investigation_id: str,
        payload: dict[str, Any],
        base_url: str = "",
    ) -> dict[str, Any]:
        """Send an immediate email for a single investigation.

        Args:
            recipients: List of recipient email addresses.
            investigation_id: Beeper investigation ID.
            payload: Outbox entry payload with investigation details.
            base_url: Base URL for Beeper UI links.

        Returns:
            Dict with 'status' and 'message_id'.

        Raises:
            EmailNotifierError: If delivery fails.
        """
        subject, body_html, body_text = _build_investigation_email(
            investigation_id, payload, base_url
        )
        return self.send_email(recipients, subject, body_html, body_text)

    def send_digest(
        self,
        recipients: list[str],
        investigations: list[dict[str, Any]],
        period_label: str = "Daily",
        base_url: str = "",
    ) -> dict[str, Any]:
        """Send a digest email summarizing multiple investigations.

        Args:
            recipients: List of recipient email addresses.
            investigations: List of investigation dicts with id, severity,
                           service, summary, status fields.
            period_label: Label for the digest period (e.g., "Daily", "Weekly").
            base_url: Base URL for Beeper UI links.

        Returns:
            Dict with 'status', 'message_id', 'investigation_count'.

        Raises:
            EmailNotifierError: If delivery fails.
        """
        subject, body_html, body_text = _build_digest_email(
            investigations, period_label, base_url
        )
        result = self.send_email(recipients, subject, body_html, body_text)
        result["investigation_count"] = len(investigations)
        return result


def _build_investigation_email(
    investigation_id: str,
    payload: dict[str, Any],
    base_url: str = "",
) -> tuple[str, str, str]:
    """Build email content for a single investigation.

    Returns:
        Tuple of (subject, body_html, body_text).
    """
    severity = payload.get("severity", "unknown").upper()
    service = payload.get("service", "unknown-service")
    summary = payload.get("summary", "Investigation started")
    evidence = payload.get("evidence", [])
    confidence = payload.get("confidence")
    event_type = payload.get("event_type", "investigation_started")

    subject = f"[Beeper] [{severity}] {service} — {investigation_id}"

    investigation_url = f"{base_url}/investigations/{investigation_id}" if base_url else ""

    # Plain text body
    text_parts = [
        f"[{severity}] {service}",
        f"Investigation: {investigation_id}",
        f"Event: {event_type}",
        "",
        summary,
    ]
    if evidence:
        text_parts.append("")
        text_parts.append("Evidence:")
        for item in evidence[:10]:
            text_parts.append(f"  - {item}")
    if confidence is not None:
        conf_pct = f"{confidence * 100:.0f}%" if isinstance(confidence, float) else str(confidence)
        text_parts.append(f"\nConfidence: {conf_pct}")
    if investigation_url:
        text_parts.append(f"\nView investigation: {investigation_url}")

    body_text = "\n".join(text_parts)

    # HTML body
    severity_color = _severity_color(severity)
    evidence_html = ""
    if evidence:
        items = "".join(f"<li>{_escape_html(str(e))}</li>" for e in evidence[:10])
        evidence_html = f"<h3>Evidence</h3><ul>{items}</ul>"

    confidence_html = ""
    if confidence is not None:
        conf_pct = f"{confidence * 100:.0f}%" if isinstance(confidence, float) else str(confidence)
        confidence_html = f"<p><strong>Confidence:</strong> {conf_pct}</p>"

    link_html = ""
    if investigation_url:
        link_html = (
            f'<p><a href="{_escape_html(investigation_url)}" '
            f'style="display:inline-block;padding:8px 16px;background:{severity_color};'
            f'color:#fff;text-decoration:none;border-radius:4px;">'
            f"View Investigation</a></p>"
        )

    body_html = f"""<div style="font-family:sans-serif;max-width:600px;">
<div style="background:{severity_color};color:#fff;padding:12px 16px;border-radius:4px 4px 0 0;">
<h2 style="margin:0;">[{severity}] {_escape_html(service)}</h2>
</div>
<div style="padding:16px;border:1px solid #ddd;border-top:none;">
<p><strong>Investigation:</strong> <code>{_escape_html(investigation_id)}</code></p>
<p><strong>Event:</strong> {_escape_html(event_type)}</p>
<p>{_escape_html(summary)}</p>
{evidence_html}
{confidence_html}
{link_html}
</div>
<div style="padding:8px 16px;color:#666;font-size:12px;">
Sent by Beeper Notification Engine
</div>
</div>"""

    return subject, body_html, body_text


def _build_digest_email(
    investigations: list[dict[str, Any]],
    period_label: str = "Daily",
    base_url: str = "",
) -> tuple[str, str, str]:
    """Build email content for a digest of multiple investigations.

    Returns:
        Tuple of (subject, body_html, body_text).
    """
    count = len(investigations)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    plural = "s" if count != 1 else ""
    subject = (
        f"[Beeper] {period_label} Digest"
        f" — {count} investigation{plural} ({now})"
    )

    # Count by severity
    severity_counts: dict[str, int] = {}
    for inv in investigations:
        sev = inv.get("severity", "unknown").lower()
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # Plain text body
    text_parts = [
        f"Beeper {period_label} Digest — {now}",
        f"Total investigations: {count}",
        "",
        "Severity breakdown:",
    ]
    for sev in ["critical", "high", "medium", "low"]:
        if sev in severity_counts:
            text_parts.append(f"  {sev.upper()}: {severity_counts[sev]}")

    text_parts.append("")
    text_parts.append("Investigations:")
    text_parts.append("-" * 60)
    for inv in investigations:
        sev = inv.get("severity", "unknown").upper()
        service = inv.get("service", "unknown")
        inv_id = inv.get("investigation_id", inv.get("id", "unknown"))
        summary = inv.get("summary", "No summary")
        status = inv.get("status", "unknown")
        text_parts.append(f"[{sev}] {service} — {inv_id}")
        text_parts.append(f"  Summary: {summary}")
        text_parts.append(f"  Status: {status}")
        if base_url:
            text_parts.append(f"  Link: {base_url}/investigations/{inv_id}")
        text_parts.append("")

    body_text = "\n".join(text_parts)

    # HTML body — rows for table
    rows_html = ""
    for inv in investigations:
        sev = inv.get("severity", "unknown").upper()
        service = inv.get("service", "unknown")
        inv_id = inv.get("investigation_id", inv.get("id", "unknown"))
        summary = inv.get("summary", "No summary")
        status = inv.get("status", "unknown")
        color = _severity_color(sev)
        link = f"{base_url}/investigations/{inv_id}" if base_url else "#"
        rows_html += f"""<tr>
<td style="padding:8px;border-bottom:1px solid #eee;">
<span style="background:{color};color:#fff;padding:2px 6px;border-radius:3px;
font-size:11px;">{sev}</span>
</td>
<td style="padding:8px;border-bottom:1px solid #eee;">{_escape_html(service)}</td>
<td style="padding:8px;border-bottom:1px solid #eee;">{_escape_html(summary[:100])}</td>
<td style="padding:8px;border-bottom:1px solid #eee;">{_escape_html(status)}</td>
<td style="padding:8px;border-bottom:1px solid #eee;">
<a href="{_escape_html(link)}">View</a>
</td>
</tr>"""

    # Severity summary badges
    badges_html = ""
    for sev in ["critical", "high", "medium", "low"]:
        if sev in severity_counts:
            color = _severity_color(sev.upper())
            badges_html += (
                f'<span style="background:{color};color:#fff;padding:4px 10px;'
                f'border-radius:12px;margin-right:8px;font-size:13px;">'
                f"{sev.upper()}: {severity_counts[sev]}</span>"
            )

    body_html = f"""<div style="font-family:sans-serif;max-width:700px;">
<div style="background:#1a1a2e;color:#fff;padding:16px;border-radius:4px 4px 0 0;">
<h2 style="margin:0;">Beeper {_escape_html(period_label)} Digest</h2>
<p style="margin:4px 0 0;opacity:0.8;">{now} — {count} investigation{'s' if count != 1 else ''}</p>
</div>
<div style="padding:16px;border:1px solid #ddd;border-top:none;">
<div style="margin-bottom:16px;">{badges_html}</div>
<table style="width:100%;border-collapse:collapse;">
<thead>
<tr style="background:#f5f5f5;">
<th style="padding:8px;text-align:left;">Severity</th>
<th style="padding:8px;text-align:left;">Service</th>
<th style="padding:8px;text-align:left;">Summary</th>
<th style="padding:8px;text-align:left;">Status</th>
<th style="padding:8px;text-align:left;">Link</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>
<div style="padding:8px 16px;color:#666;font-size:12px;">
Sent by Beeper Notification Engine
</div>
</div>"""

    return subject, body_html, body_text


def _severity_color(severity: str) -> str:
    """Map severity level to a CSS color for email styling."""
    mapping = {
        "CRITICAL": "#dc3545",
        "HIGH": "#fd7e14",
        "MEDIUM": "#ffc107",
        "LOW": "#28a745",
    }
    return mapping.get(severity.upper(), "#6c757d")


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
