"""Promote an existing LeadWise account to administrator.

Usage:
    python leadwise_promote_admin.py your-email@example.com

Run this from the LeadWise project root. It never creates or resets passwords.
"""

from pathlib import Path
import sqlite3
import sys

ROOT = Path.cwd()
DB = ROOT / "data" / "app" / "leadwise_users.db"

if len(sys.argv) != 2:
    raise SystemExit("Usage: python leadwise_promote_admin.py your-email@example.com")

email = sys.argv[1].strip().lower()

if not DB.exists():
    raise SystemExit(f"LeadWise database not found: {DB}")

with sqlite3.connect(DB) as connection:
    connection.row_factory = sqlite3.Row
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
    if "role" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'reader'")

    row = connection.execute(
        "SELECT user_id, full_name, email, role FROM users WHERE email = ? COLLATE NOCASE",
        (email,),
    ).fetchone()

    if row is None:
        raise SystemExit("No existing LeadWise account found for that email.")

    connection.execute(
        "UPDATE users SET role = 'admin' WHERE user_id = ?",
        (row["user_id"],),
    )

print(f"Admin role granted to: {row['full_name']} <{row['email']}>")
print("The existing account password is unchanged.")
