from __future__ import annotations

import argparse
import os
from pathlib import Path

from target.store import TargetStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Target-local maintenance commands")
    parser.add_argument("command", choices=["reset"])
    args = parser.parse_args()
    default_database = Path(__file__).resolve().parents[1] / "data" / "target.sqlite3"
    store = TargetStore(
        os.getenv("TARGET_DATABASE_PATH", str(default_database)),
        mode=os.getenv("TARGET_MODE", "vulnerable"),
        passwords={
            "user-a": os.getenv("LAB_USER_A_PASSWORD") or "local-a-password",
            "user-b": os.getenv("LAB_USER_B_PASSWORD") or "local-b-password",
            "admin": os.getenv("LAB_ADMIN_PASSWORD") or "local-admin-password",
        },
    )
    if args.command == "reset":
        store.reset()
        print("Synthetic sessions and observations reset. Documents were reseeded unchanged.")


if __name__ == "__main__":
    main()
