#!/usr/bin/env python3
"""Archive old unresolved demo incidents in Firestore.

The command is dry-run by default. Pass --apply to persist changes. It only
matches one explicit service and only incident records older than the cutoff.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

from google.cloud import firestore


ACTIVE_STATUSES = {"accepted", "analyzed"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", default="demo-api")
    parser.add_argument("--older-than-hours", type=float, default=2.0)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")
    if not project:
        raise SystemExit("Set GOOGLE_CLOUD_PROJECT before running this utility")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(args.older_than_hours, 0.0))
    client = firestore.Client(
        project=project,
        database=os.getenv("FIRESTORE_DATABASE", "(default)"),
    )
    collection = client.collection("incidents")
    matches: list[tuple[object, dict[str, object]]] = []
    for snapshot in collection.stream():
        data = snapshot.to_dict() or {}
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if not isinstance(created_at, datetime):
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if (
            data.get("service") == args.service
            and data.get("status") in ACTIVE_STATUSES
            and created_at < cutoff
        ):
            matches.append((snapshot.reference, data))

    action = "ARCHIVE" if args.apply else "DRY RUN"
    print(f"{action}: {len(matches)} stale unresolved incident(s) for {args.service}")
    for reference, data in sorted(matches, key=lambda item: str(item[1].get("created_at"))):
        print(f"- {reference.id}  {data.get('created_at')}  {data.get('approval_status')}")

    if not args.apply:
        print("No data changed. Re-run with --apply after reviewing the list.")
        return 0

    batch = client.batch()
    archived_at = datetime.now(timezone.utc)
    for reference, _ in matches:
        batch.update(reference, {"status": "archived", "archived_at": archived_at})
    if matches:
        batch.commit()
    print(f"Archived {len(matches)} incident(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
