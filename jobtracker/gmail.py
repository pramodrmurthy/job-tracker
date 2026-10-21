"""Gmail draft creation via the Gmail API. Drafts only: nothing in this module sends mail."""

import base64
import mimetypes
from email.message import EmailMessage
from pathlib import Path

from . import config


class GmailError(Exception):
    pass


def client_secret_present() -> bool:
    return config.GMAIL_CLIENT_SECRET.exists()


def token_present() -> bool:
    return config.GMAIL_TOKEN.exists()


def get_service(interactive: bool = False):
    """Build a Gmail service. With interactive=True a browser consent flow may run (blocks until finished)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(config.GMAIL_TOKEN), config.GMAIL_SCOPES) if token_present() else None
    try:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif not creds or not creds.valid:
            if not interactive:
                raise GmailError("Gmail is not connected. Use Settings → Connect Gmail.")
            if not client_secret_present():
                raise GmailError(f"{config.GMAIL_CLIENT_SECRET.name} is missing.")
            from google_auth_oauthlib.flow import InstalledAppFlow
            creds = InstalledAppFlow.from_client_secrets_file(str(config.GMAIL_CLIENT_SECRET),
                                                              config.GMAIL_SCOPES).run_local_server(port=0)
    except GmailError:
        raise
    except Exception as e:  # revoked/expired refresh token, network, consent denied
        raise GmailError(f"Gmail authorisation failed ({type(e).__name__}). Reconnect Gmail in Settings.") from e
    config.GMAIL_TOKEN.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def account_email(service) -> str | None:
    try:
        return service.users().getProfile(userId="me").execute().get("emailAddress")
    except Exception:
        return None


def disconnect() -> None:
    config.GMAIL_TOKEN.unlink(missing_ok=True)


def build_message(to: str, subject: str, body: str, attachment: Path | None) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment and attachment.exists():
        mime, _ = mimetypes.guess_type(attachment.name)
        maintype, subtype = (mime or "application/octet-stream").split("/", 1)
        msg.add_attachment(attachment.read_bytes(), maintype=maintype, subtype=subtype, filename=attachment.name)
    return msg


def create_draft(service, to: str, subject: str, body: str, attachment: Path | None) -> tuple[str, str | None]:
    """Create one Gmail draft. Returns (draft_id, message_id). Never sends."""
    raw = base64.urlsafe_b64encode(bytes(build_message(to, subject, body, attachment))).decode()
    try:
        draft = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    except Exception as e:
        raise GmailError(f"Gmail rejected the draft: {type(e).__name__}: {str(e)[:200]}") from e
    return draft["id"], (draft.get("message") or {}).get("id")


def draft_url(message_id: str | None) -> str | None:
    return f"https://mail.google.com/mail/u/0/#drafts?compose={message_id}" if message_id else None
