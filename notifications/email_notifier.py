"""
Email notification system using SMTP.
Sends alerts for session expiry, cycle completion, and pending approvals.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config.settings import SMTP_HOST, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD, NOTIFICATION_EMAIL


def send_email(subject: str, body_html: str):
    """Send an HTML email notification."""
    if not all([SMTP_EMAIL, SMTP_PASSWORD, NOTIFICATION_EMAIL]):
        print("⚠️ Email not configured. Skipping notification.")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"AI Career Optimizer <{SMTP_EMAIL}>"
    msg["To"] = NOTIFICATION_EMAIL
    msg["Subject"] = subject

    # Wrap body in a styled container
    styled_body = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 600px; margin: 0 auto;
                padding: 20px; background: #1a1a2e; color: #e0e0e0; border-radius: 12px;">
        <h2 style="color: #00d4ff; margin-top: 0;">🤖 AI Career Optimizer</h2>
        <hr style="border: 1px solid #333;">
        {body_html}
        <hr style="border: 1px solid #333;">
        <p style="color: #888; font-size: 12px;">
            Sent at {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}
        </p>
    </div>
    """
    msg.attach(MIMEText(styled_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, NOTIFICATION_EMAIL, msg.as_string())
        print(f"✅ Email sent: {subject}")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False


# ── Pre-built notification templates ──────────────────

def notify_session_expired():
    """Alert user that Naukri session has expired and manual re-login is needed."""
    send_email(
        subject="🔴 ACTION REQUIRED: Naukri Session Expired",
        body_html="""
        <h3 style="color: #ff4444;">Session Expired</h3>
        <p>Your Naukri login session has expired. The bot cannot proceed without a valid session.</p>
        <h4>What to do:</h4>
        <ol>
            <li>Run <code style="background:#333;padding:2px 6px;border-radius:4px;">python -m core.auth --login</code> on your machine</li>
            <li>Complete the OTP verification manually in the browser</li>
            <li>The session will be saved automatically</li>
        </ol>
        <p>Automated updates are <strong>paused</strong> until you re-login.</p>
        """
    )


def notify_cycle_complete(actions_taken: list, next_run: str):
    """Send summary after a successful automation cycle."""
    actions_html = "".join(f"<li>{a}</li>" for a in actions_taken)
    send_email(
        subject="✅ Profile Update Cycle Complete",
        body_html=f"""
        <h3 style="color: #00ff88;">Cycle Completed Successfully</h3>
        <h4>Actions taken:</h4>
        <ul>{actions_html}</ul>
        <p><strong>Next scheduled run:</strong> {next_run}</p>
        """
    )


def notify_pending_suggestions(suggestions: list):
    """Send pending skill suggestions for approval."""
    rows = ""
    for s in suggestions:
        rows += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #333;">{s['suggestion_text']}</td>
            <td style="padding:8px;border-bottom:1px solid #333;">{s['suggestion_type']}</td>
            <td style="padding:8px;border-bottom:1px solid #333;">{s.get('ai_reasoning', 'N/A')}</td>
        </tr>
        """
    send_email(
        subject=f"🔔 {len(suggestions)} Skill Suggestions Awaiting Approval",
        body_html=f"""
        <h3 style="color: #ffaa00;">Pending Suggestions</h3>
        <p>The AI has generated {len(suggestions)} new suggestions based on market trends:</p>
        <table style="width:100%;border-collapse:collapse;margin:12px 0;">
            <tr style="background:#333;">
                <th style="padding:8px;text-align:left;">Suggestion</th>
                <th style="padding:8px;text-align:left;">Type</th>
                <th style="padding:8px;text-align:left;">Reasoning</th>
            </tr>
            {rows}
        </table>
        <p>Visit the <strong>Dashboard</strong> to approve or reject these suggestions.</p>
        """
    )


def notify_error(error_message: str, step: str):
    """Alert user about a failure during automation."""
    send_email(
        subject=f"❌ Automation Error: {step}",
        body_html=f"""
        <h3 style="color: #ff4444;">Error During: {step}</h3>
        <pre style="background:#333;padding:12px;border-radius:8px;overflow-x:auto;color:#ff6b6b;">
{error_message}
        </pre>
        <p>The automation cycle has been aborted. Check logs for details.</p>
        """
    )
