"""Check Gmail access step by step:   uv run python -m jobtracker.check_gmail [--create-test]

Tells you which step fails: credentials file, saved login, refresh, Gmail account, and (with --create-test) whether a
draft can really be created. The test draft is titled 'JobTracker TEST - delete me' and is never sent.
"""

import sys

from . import config, gmail


def main() -> None:
    print(f"1. client_secret.json present: {gmail.client_secret_present()}  ({config.GMAIL_CLIENT_SECRET})")
    print(f"2. saved login (token.json) present: {gmail.token_present()}  ({config.GMAIL_TOKEN})")
    if not gmail.token_present():
        sys.exit("   -> No saved login. In the app: Settings -> Connect Gmail.")
    try:
        service = gmail.get_service(interactive=False)
    except gmail.GmailError as e:
        sys.exit(f"3. login refresh FAILED: {e}\n   -> Delete token.json and use Settings -> Connect Gmail again "
                 "(in Google's 'Testing' mode the login expires every 7 days).")
    print("3. login valid / refreshed: OK")
    account = gmail.account_email(service)
    print(f"4. Gmail account: {account or 'could not read (drafts may still work)'}")
    if "--create-test" in sys.argv:
        try:
            draft_id, message_id = gmail.create_draft(service, account or "me@example.com", "JobTracker TEST - delete me",
                                                      "This is a test draft created by JobTracker. It was NOT sent. Delete it.", None)
        except gmail.GmailError as e:
            sys.exit(f"5. test draft FAILED: {e}")
        print(f"5. test draft created: id {draft_id}\n   -> Open Gmail -> Drafts and look for 'JobTracker TEST - delete me'.")
        print(f"   direct link: {gmail.draft_url(message_id)}")
    else:
        print("5. (skipped) add --create-test to create a harmless test draft in Gmail")


if __name__ == "__main__":
    main()
