"""
Email Reader - Gmail API interface for klmn800alerts@gmail.com

Full inbox access for the options scanner system. Used by Claude Code
to check for messages from Ben, newsletter subscriptions, etc.

This is a READ-ONLY tool by design. No send capability.
Outbound email is handled by email_notifier.py.

Usage:
    python tools/email_reader.py --auth                  # Run/verify OAuth flow
    python tools/email_reader.py --check                 # Quick inbox summary
    python tools/email_reader.py --list [--count N]      # List recent messages
    python tools/email_reader.py --read MSG_ID           # Read a specific message
    python tools/email_reader.py --search "query"        # Gmail search syntax
    python tools/email_reader.py --process               # Save unread to memory, mark read
    python tools/email_reader.py --mark-read MSG_ID      # Mark as read
    python tools/email_reader.py --mark-unread MSG_ID    # Mark as unread
    python tools/email_reader.py --trash MSG_ID          # Move to trash
    python tools/email_reader.py --labels                # List all labels

Gmail search syntax examples:
    "from:ben"                  Messages from Ben
    "subject:trading"           Subject contains 'trading'
    "is:unread after:2026/02/01"  Unread since Feb 1
    "has:attachment"            Messages with attachments
    "label:newsletters"         Messages with specific label
"""

import argparse
import base64
import html as html_module
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.timezone_utils import now_eastern

# Gmail API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Suppress "file_cache is only supported with oauth2client<4.0.0" noise
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

# Full access scope (read, label, trash, etc. - but we only build read operations)
SCOPES = ['https://mail.google.com/']

# Memory inbox directory for saving processed emails
MEMORY_INBOX = Path(r'C:\Users\TRO\.claude\projects\E--options-scanner\memory\inbox')


class GmailReader:
    """Gmail API interface with full inbox access.

    Designed for:
    - On-demand use during Claude Code conversations (--check, --read)
    - Scheduled batch processing (--process saves to memory/inbox/)
    - Programmatic use by importing and calling methods directly

    Example:
        from tools.email_reader import GmailReader
        reader = GmailReader()
        for msg in reader.get_unread():
            print(msg['subject'])
    """

    def __init__(self, config_path=None):
        if config_path is None:
            config_path = PROJECT_ROOT / 'config.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        gmail_config = config.get('gmail_api', {})
        self.client_secret_file = PROJECT_ROOT / gmail_config.get(
            'client_secret_file',
            'client_secret_923797423221-jt0utor5k9mg3jjrc8m2jtkcbb65oqmb.apps.googleusercontent.com.json'
        )
        self.token_file = PROJECT_ROOT / gmail_config.get('token_file', 'gmail_token.json')
        self.account = gmail_config.get('account', 'klmn800alerts@gmail.com')

        self._service = None

    def authenticate(self, interactive=False):
        """Run OAuth2 authentication flow. Returns True if successful.

        Args:
            interactive: If True, fall back to a blocking browser/local-server
                OAuth flow when no valid token exists. Only the `--auth` CLI
                passes True. Background callers (orchestrator, lazy `service`
                property) pass False so a missing/revoked token returns False
                cleanly instead of hanging waiting for an OAuth callback.
        """
        creds = None

        if self.token_file.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)
            except Exception as e:
                print(f"Warning: Could not load token file: {e}")
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logging.debug("Refreshing expired token for {}...".format(self.account))
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logging.warning("Token refresh failed: {}".format(e))
                    creds = None

            if not creds:
                if not interactive:
                    logging.warning(
                        "Gmail token missing/revoked and interactive=False; "
                        "skipping browser OAuth flow. Run `python tools/email_reader.py --auth` to re-authenticate."
                    )
                    return False
                if not self.client_secret_file.exists():
                    print(f"ERROR: Client secret file not found: {self.client_secret_file}")
                    return False
                print(f"Starting OAuth flow for {self.account}...")
                print("A browser window will open. Sign in with the system account.")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secret_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save token
            with open(self.token_file, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
            logging.debug("Token saved to {}".format(self.token_file))

        self._service = build('gmail', 'v1', credentials=creds)
        return True

    @property
    def service(self):
        """Lazy-authenticated Gmail service. Non-interactive — never opens a browser."""
        if self._service is None:
            if not self.authenticate(interactive=False):
                raise RuntimeError("Gmail authentication failed (token missing/revoked; run --auth)")
        return self._service

    # ── Message listing ─────────────────────────────────────────────

    def list_messages(self, query='', max_results=10, label_ids=None):
        """List messages matching query. Returns list of message metadata dicts."""
        kwargs = {'userId': 'me', 'maxResults': max_results}
        if query:
            kwargs['q'] = query
        if label_ids:
            kwargs['labelIds'] = label_ids

        result = self.service.users().messages().list(**kwargs).execute()
        messages = result.get('messages', [])

        detailed = []
        for msg_meta in messages:
            msg = self.service.users().messages().get(
                userId='me', id=msg_meta['id'], format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()
            headers = {h['name']: h['value'] for h in msg['payload']['headers']}
            detailed.append({
                'id': msg['id'],
                'threadId': msg['threadId'],
                'from': headers.get('From', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'snippet': msg.get('snippet', ''),
                'labels': msg.get('labelIds', []),
                'is_unread': 'UNREAD' in msg.get('labelIds', [])
            })

        return detailed

    def get_message(self, msg_id):
        """Get full message by ID. Returns dict with headers + body text."""
        msg = self.service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()

        headers = {h['name']: h['value'] for h in msg['payload']['headers']}
        body = self._extract_body(msg['payload'])

        return {
            'id': msg['id'],
            'threadId': msg['threadId'],
            'from': headers.get('From', ''),
            'to': headers.get('To', ''),
            'subject': headers.get('Subject', ''),
            'date': headers.get('Date', ''),
            'labels': msg.get('labelIds', []),
            'is_unread': 'UNREAD' in msg.get('labelIds', []),
            'body': body,
            'snippet': msg.get('snippet', '')
        }

    def get_unread(self, max_results=20, label_filter=None):
        """Get unread messages, optionally filtered by label name."""
        query = 'is:unread'
        if label_filter:
            query += f' label:{label_filter}'
        return self.list_messages(query=query, max_results=max_results)

    def search(self, query, max_results=20):
        """Search with Gmail query syntax. Returns message metadata list."""
        return self.list_messages(query=query, max_results=max_results)

    # ── Message actions ─────────────────────────────────────────────

    def mark_read(self, msg_id):
        """Mark message as read (remove UNREAD label)."""
        self.service.users().messages().modify(
            userId='me', id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()

    def mark_unread(self, msg_id):
        """Mark message as unread (add UNREAD label)."""
        self.service.users().messages().modify(
            userId='me', id=msg_id,
            body={'addLabelIds': ['UNREAD']}
        ).execute()

    def trash(self, msg_id):
        """Move message to trash."""
        self.service.users().messages().trash(userId='me', id=msg_id).execute()

    # ── Labels ──────────────────────────────────────────────────────

    def get_labels(self):
        """List all labels. Returns list of label dicts (id, name, type)."""
        result = self.service.users().labels().list(userId='me').execute()
        return result.get('labels', [])

    def add_label(self, msg_id, label_id):
        """Add label to message by label ID."""
        self.service.users().messages().modify(
            userId='me', id=msg_id,
            body={'addLabelIds': [label_id]}
        ).execute()

    def remove_label(self, msg_id, label_id):
        """Remove label from message by label ID."""
        self.service.users().messages().modify(
            userId='me', id=msg_id,
            body={'removeLabelIds': [label_id]}
        ).execute()

    # ── Batch processing ────────────────────────────────────────────

    def process_new(self, save_dir=None, label_filter=None, mark_as_read=True):
        """
        Save unread messages to markdown files and optionally mark read.

        Args:
            save_dir: Directory to save markdown files (default: memory/inbox/)
            label_filter: Only process messages with this label
            mark_as_read: Mark processed messages as read (default: True)

        Returns:
            List of saved file paths.
        """
        if save_dir is None:
            save_dir = MEMORY_INBOX
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        messages = self.get_unread(label_filter=label_filter)
        if not messages:
            print("No unread messages.")
            return []

        saved = []
        for msg_meta in messages:
            msg = self.get_message(msg_meta['id'])

            # Build filename: YYYY-MM-DD_HHMMSS_subject-slug.md
            now = now_eastern()
            subject_slug = re.sub(r'[^\w\s-]', '', msg['subject'][:50]).strip()
            subject_slug = re.sub(r'[\s]+', '-', subject_slug).lower()
            if not subject_slug:
                subject_slug = 'no-subject'
            filename = f"{now.strftime('%Y-%m-%d_%H%M%S')}_{subject_slug}.md"
            filepath = save_dir / filename

            # Build markdown content
            content = f"# {msg['subject']}\n\n"
            content += f"- **From:** {msg['from']}\n"
            content += f"- **To:** {msg['to']}\n"
            content += f"- **Date:** {msg['date']}\n"
            content += f"- **Labels:** {', '.join(msg['labels'])}\n"
            content += f"- **Message ID:** {msg['id']}\n\n"
            content += "---\n\n"
            content += msg['body']

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            if mark_as_read:
                self.mark_read(msg['id'])

            saved.append(filepath)
            print(f"  Saved: {filename}")

        print(f"\nProcessed {len(saved)} message(s) -> {save_dir}")
        return saved

    # ── Body extraction (private) ───────────────────────────────────

    def _extract_body(self, payload):
        """Extract plain text body from Gmail message payload."""
        # Simple message with body directly in payload
        if payload.get('body', {}).get('data'):
            return base64.urlsafe_b64decode(
                payload['body']['data']
            ).decode('utf-8', errors='replace')

        # Multipart - prefer text/plain, fall back to text/html
        parts = payload.get('parts', [])
        for mime_pref in ['text/plain', 'text/html']:
            body = self._find_body_in_parts(parts, mime_pref)
            if body:
                return body

        return '[No readable body content]'

    def _find_body_in_parts(self, parts, mime_type):
        """Recursively search message parts for a specific MIME type."""
        for part in parts:
            if part.get('mimeType') == mime_type and part.get('body', {}).get('data'):
                text = base64.urlsafe_b64decode(
                    part['body']['data']
                ).decode('utf-8', errors='replace')
                if mime_type == 'text/html':
                    text = self._strip_html(text)
                return text
            # Recurse into nested multipart
            if part.get('parts'):
                result = self._find_body_in_parts(part['parts'], mime_type)
                if result:
                    return result
        return None

    @staticmethod
    def _strip_html(html_text):
        """Simple HTML to plain text conversion."""
        # Preserve structure
        text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
        text = re.sub(r'</?p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</?div[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '\n- ', text, flags=re.IGNORECASE)
        text = re.sub(r'</li>', '', text, flags=re.IGNORECASE)
        # Extract link URLs
        text = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                       r'\2 (\1)', text, flags=re.IGNORECASE)
        # Strip remaining tags
        text = re.sub(r'<[^>]+>', '', text)
        text = html_module.unescape(text)
        # Collapse excessive blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# ── CLI formatting ──────────────────────────────────────────────────

def _format_message_row(msg, idx=None):
    """Format a message as a one-line summary for terminal display."""
    prefix = f"{idx:>3}. " if idx is not None else "  "
    unread_marker = "*" if msg['is_unread'] else " "
    sender = msg['from'].split('<')[0].strip()[:25]
    subject = msg['subject'][:55]
    return f"{prefix}[{unread_marker}] {msg['id']}  {sender:<25}  {subject}"


# ── CLI entry point ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Gmail inbox reader for klmn800alerts@gmail.com',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Gmail search syntax examples:
  "from:ben"                    Messages from Ben
  "subject:trading alerts"      Subject contains phrase
  "is:unread after:2026/02/01"  Unread since Feb 1
  "has:attachment filename:pdf"  PDF attachments
  "label:newsletters"           Messages with label
  "newer_than:2d"               Last 2 days
        """
    )

    # Commands (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--auth', action='store_true',
                       help='Run/verify OAuth authentication')
    group.add_argument('--check', action='store_true',
                       help='Quick inbox summary (unread count + subjects)')
    group.add_argument('--list', action='store_true',
                       help='List recent messages')
    group.add_argument('--read', metavar='MSG_ID',
                       help='Read a specific message by ID')
    group.add_argument('--search', metavar='QUERY',
                       help='Search with Gmail query syntax')
    group.add_argument('--process', action='store_true',
                       help='Save unread messages to memory/inbox/ and mark read')
    group.add_argument('--mark-read', metavar='MSG_ID',
                       help='Mark message as read')
    group.add_argument('--mark-unread', metavar='MSG_ID',
                       help='Mark message as unread')
    group.add_argument('--trash', metavar='MSG_ID',
                       help='Move message to trash')
    group.add_argument('--labels', action='store_true',
                       help='List all labels')

    # Options
    parser.add_argument('--count', type=int, default=10,
                        help='Number of messages to show (default: 10)')
    parser.add_argument('--label', metavar='LABEL',
                        help='Filter by label name (for --check, --process)')
    parser.add_argument('--no-mark-read', action='store_true',
                        help='With --process: do not mark messages as read')

    args = parser.parse_args()

    # UTF-8 output (Windows)
    sys.stdout.reconfigure(encoding='utf-8')

    try:
        reader = GmailReader()

        if args.auth:
            success = reader.authenticate(interactive=True)
            if success:
                profile = reader.service.users().getProfile(userId='me').execute()
                print(f"Authenticated as: {profile['emailAddress']}")
                print(f"Total messages:   {profile.get('messagesTotal', 'N/A')}")
                print(f"Total threads:    {profile.get('threadsTotal', 'N/A')}")
                print(f"Token file:       {reader.token_file}")
            else:
                print("Authentication failed.")
                sys.exit(1)

        elif args.check:
            unread = reader.get_unread(max_results=20, label_filter=args.label)
            label_note = f" (label: {args.label})" if args.label else ""
            print(f"=== Inbox: {len(unread)} unread{label_note} ===\n")
            if unread:
                for i, msg in enumerate(unread, 1):
                    print(_format_message_row(msg, i))
            else:
                print("  No unread messages.")

        elif args.list:
            messages = reader.list_messages(max_results=args.count)
            print(f"=== Recent {len(messages)} messages ===\n")
            for i, msg in enumerate(messages, 1):
                print(_format_message_row(msg, i))

        elif args.read:
            msg = reader.get_message(args.read)
            print(f"From:    {msg['from']}")
            print(f"To:      {msg['to']}")
            print(f"Subject: {msg['subject']}")
            print(f"Date:    {msg['date']}")
            print(f"Labels:  {', '.join(msg['labels'])}")
            print(f"ID:      {msg['id']}")
            print(f"{'=' * 60}")
            print(msg['body'])

        elif args.search:
            messages = reader.search(args.search, max_results=args.count)
            print(f"=== Search: '{args.search}' ({len(messages)} results) ===\n")
            for i, msg in enumerate(messages, 1):
                print(_format_message_row(msg, i))

        elif args.process:
            print("Processing unread messages...")
            saved = reader.process_new(
                label_filter=args.label,
                mark_as_read=not args.no_mark_read
            )
            if saved:
                print(f"\nDone. {len(saved)} message(s) saved to memory/inbox/")

        elif args.mark_read:
            reader.mark_read(args.mark_read)
            print(f"Marked as read: {args.mark_read}")

        elif args.mark_unread:
            reader.mark_unread(args.mark_unread)
            print(f"Marked as unread: {args.mark_unread}")

        elif args.trash:
            reader.trash(args.trash)
            print(f"Moved to trash: {args.trash}")

        elif args.labels:
            labels = reader.get_labels()
            print(f"=== Labels ({len(labels)}) ===\n")
            for label in sorted(labels, key=lambda l: l['name']):
                ltype = label.get('type', '')
                print(f"  {label['name']:<35}  {label['id']:<30}  {ltype}")

    except HttpError as e:
        print(f"Gmail API error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
