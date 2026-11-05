#!/usr/bin/env python3
"""Send an admin email to its recipients. The admin page starts this in the
background (app/services/broadcast_email_service.py), and the two share a lock,
so only one send can run at a time.

Usage:
    python scripts/send_broadcast_email.py --id 7 --base-url https://turnushjelper.no/

The send has to be started from the admin page first, which is what checks the
test email and the recipient count. This script refuses one that wasn't.
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Deliberately no os.environ.setdefault("DB_TYPE", ...) here — see the comment
# in scripts/import_innplassering.py for the incident that rule comes from.


def main():
    parser = argparse.ArgumentParser(description="Send an admin email to its recipients")
    parser.add_argument("--id", type=int, required=True, help="The email's id")
    parser.add_argument("--base-url", required=True, help="The site's URL, for the unsubscribe links")
    args = parser.parse_args()

    from app.services import broadcast_email_service

    return broadcast_email_service.run(args.id, args.base_url)


if __name__ == "__main__":
    sys.exit(main())
