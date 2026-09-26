# LeadWise Administrator Control Center
# Version 18.58.2 — Inbox Reply Workflow — Administrative Governance & Internal Analytics

from pathlib import Path
import os
import json
import sqlite3
import hashlib
import hmac
import secrets
import re
import html
import urllib.request
import urllib.error
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import joblib
import numpy as np
from scipy.sparse import csr_matrix

from db_utils import (
    connect_database,
    get_database_url,
    get_database_backend,
    validate_required_schema,
    query_dataframe,
    insert_returning_id,
    get_table_columns,
)

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent if APP_DIR.name == "app" else APP_DIR

# ---------------------------------------------------------
# PORTABLE DEPLOYMENT CONFIGURATION
# ---------------------------------------------------------
APP_ENV = os.getenv("LEADWISE_ENV", "local").strip().lower()
USER_DATA_DIR = Path(
    os.getenv(
        "LEADWISE_DATA_DIR",
        str(PROJECT_ROOT / "data" / "app"),
    )
).expanduser()
USER_DB_PATH = Path(
    os.getenv(
        "LEADWISE_SQLITE_PATH",
        str(USER_DATA_DIR / "leadwise_users.db"),
    )
).expanduser()
DATABASE_URL = get_database_url()
DATABASE_BACKEND = get_database_backend(DATABASE_URL)

PBKDF2_ITERATIONS = 310_000
CATALOG_CSV_PATH = PROJECT_ROOT / "data" / "processed" / "leadwise_streamlit_catalog.csv"

st.set_page_config(
    page_title="LeadWise Administrator",
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --lw-navy:#0B1F33;
        --lw-midnight:#102A43;
        --lw-gold:#D8A84E;
        --lw-cream:#F8F4EC;
        --lw-text:#14213D;
    }
    .lw-admin-hero {
        background:linear-gradient(135deg,#0B1F33,#102A43);
        color:white;
        border:1px solid #D8A84E;
        border-radius:18px;
        padding:1.25rem 1.4rem;
        margin-bottom:1rem;
    }
    .lw-admin-hero h1 {margin:0;color:white;font-size:2rem;}
    .lw-admin-hero p {margin:.35rem 0 0;color:#F0C96B;}
    </style>
    """,
    unsafe_allow_html=True,
)


ADMIN_REQUIRED_SCHEMA = {
    "users": {
        "user_id", "full_name", "email", "password_hash", "password_salt",
        "created_at", "is_active", "role", "admin_account_status",
        "admin_status_note", "admin_status_changed_at", "admin_status_changed_by",
    },
    "user_library": {
        "library_id", "user_id", "book_id", "reading_status", "personal_rating",
        "private_notes", "key_takeaways", "practical_application", "date_finished",
        "saved_at", "updated_at",
    },
    "user_reviews": {
        "review_id", "user_id", "book_id", "rating", "review_text",
        "created_at", "updated_at", "is_published", "published_at",
    },
    "leadwise_events": {
        "event_id", "user_id", "session_id", "event_type", "page", "book_id",
        "related_book_id", "query_id", "metadata_json", "created_at",
    },
    "leadwise_feedback": {
        "feedback_id", "user_id", "feedback_type", "subject", "message",
        "contact_email", "created_at", "status",
    },
    "ask_leadwise_queries": {
        "query_id", "user_id", "query_text", "intent", "result_count",
        "top_book_id", "created_at",
    },
    "leadwise_inquiries": {
        "inquiry_id", "user_id", "inquiry_type", "full_name", "email", "subject",
        "message", "suggested_title", "suggested_author", "suggested_isbn_or_link",
        "related_book_id", "created_at", "status", "replied_at", "replied_by",
    },
    "leadwise_inquiry_replies": {
        "reply_id", "inquiry_id", "admin_user_id", "reply_message",
        "sent_to_email", "delivery_status", "external_message_id",
        "created_at", "sent_at",
    },
    "featured_reading": {
        "feature_id", "book_id", "feature_message", "display_order", "start_date",
        "end_date", "is_active", "created_by", "created_at", "updated_at",
    },
    "live_catalog_books": {
        "live_book_id", "book_id", "base_book_id", "record_origin", "title",
        "authors", "description", "publisher", "publication_date", "publication_year",
        "isbn10", "isbn13", "page_count", "categories", "language", "cover_url",
        "source_url", "source_type", "source_rating", "source_rating_count",
        "catalog_status", "intelligence_status", "admin_note", "created_by",
        "updated_by", "created_at", "updated_at",
    },
    "catalog_book_overrides": {
        "override_id", "book_id", "title", "authors", "description", "publisher",
        "publication_date", "publication_year", "isbn10", "isbn13", "page_count",
        "categories", "language", "cover_url", "source_url", "source_type",
        "source_rating", "source_rating_count", "catalog_status", "admin_note",
        "updated_by", "updated_at",
    },
    "catalog_change_requests": {
        "request_id", "book_id", "record_type", "action_type", "before_json",
        "proposed_json", "reason", "status", "requested_by", "requested_at",
        "reviewed_by", "reviewed_at", "review_note",
    },
    "recommendation_book_vectors": {
        "book_id", "feature_indices_json", "feature_values_json", "feature_count",
        "vector_norm", "vectorizer_features", "processed_at", "processing_status",
        "processing_error", "vectorizer_version",
    },
    "recommendation_processing_history": {
        "history_id", "book_id", "action_type", "outcome", "feature_count",
        "vector_norm", "vectorizer_features", "vectorizer_version", "message",
        "processed_by", "processed_at",
    },
    "admin_access_requests": {
        "request_id", "full_name", "email", "organization_position", "reason",
        "password_hash", "password_salt", "requested_role", "status",
        "reviewed_by", "reviewed_at", "admin_note", "created_at",
    },
    "admin_audit_log": {
        "audit_id", "admin_user_id", "action", "entity_type", "entity_id",
        "details", "created_at",
    },
}


def db_connection():
    """Return the active LeadWise Admin database connection."""
    return connect_database(USER_DB_PATH, DATABASE_URL)


def migrate_admin_schema():
    """Initialize local SQLite or validate the shared Supabase schema.

    PostgreSQL mode never creates or alters the shared schema.
    """
    with db_connection() as connection:
        if connection.backend == "postgresql":
            problems = validate_required_schema(connection, ADMIN_REQUIRED_SCHEMA)
            if problems:
                raise RuntimeError(
                    "LeadWise PostgreSQL schema validation failed: "
                    + " | ".join(problems)
                )
            return
        # 18.57.2: bootstrap the base users table before Admin-only migrations.
        # Streamlit Community Cloud deploys the Reader and Admin as separate
        # app instances, so the Admin cannot assume the Reader has already
        # created the local SQLite schema.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            )
            """
        )

        user_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "role" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'reader'"
            )

        # 18.57.4: complete fresh-cloud bootstrap for Reader-facing operational
        # tables referenced by the Admin Control Center. Streamlit Community
        # Cloud Reader and Admin apps do not share a local SQLite filesystem.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_library (
                library_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id TEXT NOT NULL,
                reading_status TEXT NOT NULL DEFAULT 'Want to Read',
                personal_rating REAL,
                private_notes TEXT,
                key_takeaways TEXT,
                practical_application TEXT,
                date_finished TEXT,
                saved_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, book_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_reviews (
                review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id TEXT NOT NULL,
                rating REAL,
                review_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_published INTEGER NOT NULL DEFAULT 0,
                published_at TEXT,
                UNIQUE(user_id, book_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )

        # Non-destructive compatibility migrations for databases created by
        # earlier LeadWise Reader builds.
        library_columns = {
            row["name"] for row in connection.execute(
                "PRAGMA table_info(user_library)"
            ).fetchall()
        }
        for column_name, column_type in {
            "key_takeaways": "TEXT",
            "practical_application": "TEXT",
            "date_finished": "TEXT",
        }.items():
            if column_name not in library_columns:
                connection.execute(
                    f"ALTER TABLE user_library ADD COLUMN {column_name} {column_type}"
                )

        review_columns = {
            row["name"] for row in connection.execute(
                "PRAGMA table_info(user_reviews)"
            ).fetchall()
        }
        for column_name, column_type in {
            "is_published": "INTEGER NOT NULL DEFAULT 0",
            "published_at": "TEXT",
        }.items():
            if column_name not in review_columns:
                connection.execute(
                    f"ALTER TABLE user_reviews ADD COLUMN {column_name} {column_type}"
                )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leadwise_feedback (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                feedback_type TEXT NOT NULL,
                subject TEXT,
                message TEXT NOT NULL,
                contact_email TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ask_leadwise_queries (
                query_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query_text TEXT NOT NULL,
                intent TEXT NOT NULL,
                result_count INTEGER NOT NULL DEFAULT 0,
                top_book_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leadwise_inquiries (
                inquiry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                inquiry_type TEXT NOT NULL,
                full_name TEXT,
                email TEXT,
                subject TEXT,
                message TEXT NOT NULL,
                suggested_title TEXT,
                suggested_author TEXT,
                suggested_isbn_or_link TEXT,
                related_book_id TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'New',
                replied_at TEXT,
                replied_by INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
                FOREIGN KEY(replied_by) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )

        inquiry_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(leadwise_inquiries)"
            ).fetchall()
        }
        if "replied_at" not in inquiry_columns:
            connection.execute(
                "ALTER TABLE leadwise_inquiries ADD COLUMN replied_at TEXT"
            )
        if "replied_by" not in inquiry_columns:
            connection.execute(
                "ALTER TABLE leadwise_inquiries ADD COLUMN replied_by INTEGER"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leadwise_inquiry_replies (
                reply_id INTEGER PRIMARY KEY AUTOINCREMENT,
                inquiry_id INTEGER NOT NULL,
                admin_user_id INTEGER,
                reply_message TEXT NOT NULL,
                sent_to_email TEXT,
                delivery_status TEXT NOT NULL DEFAULT 'Pending',
                external_message_id TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                FOREIGN KEY(inquiry_id) REFERENCES leadwise_inquiries(inquiry_id)
                    ON DELETE CASCADE,
                FOREIGN KEY(admin_user_id) REFERENCES users(user_id)
                    ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inquiry_replies_inquiry_id "
            "ON leadwise_inquiry_replies(inquiry_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_inquiry_replies_created_at "
            "ON leadwise_inquiry_replies(created_at)"
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS featured_reading (
                feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id TEXT NOT NULL,
                feature_message TEXT,
                display_order INTEGER NOT NULL DEFAULT 1,
                start_date TEXT,
                end_date TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(created_by) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leadwise_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                page TEXT,
                book_id TEXT,
                related_book_id TEXT,
                query_id INTEGER,
                metadata_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_leadwise_events_created_at ON leadwise_events(created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_leadwise_events_event_type ON leadwise_events(event_type)")

        user_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "admin_account_status" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN admin_account_status TEXT DEFAULT 'Active'"
            )
        if "admin_status_note" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN admin_status_note TEXT"
            )
        if "admin_status_changed_at" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN admin_status_changed_at TEXT"
            )
        if "admin_status_changed_by" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN admin_status_changed_by INTEGER"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_access_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                organization_position TEXT,
                reason TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                requested_role TEXT NOT NULL DEFAULT 'admin',
                status TEXT NOT NULL DEFAULT 'Pending',
                reviewed_by INTEGER,
                reviewed_at TEXT,
                admin_note TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(reviewed_by) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )

        connection.execute(
            """
            UPDATE users
            SET role = 'super_admin'
            WHERE role = 'admin'
              AND user_id = (
                  SELECT MIN(user_id) FROM users WHERE role = 'admin'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM users WHERE role = 'super_admin'
              )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS live_catalog_books (
                live_book_id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id TEXT NOT NULL UNIQUE,
                base_book_id TEXT,
                record_origin TEXT NOT NULL DEFAULT 'admin',
                title TEXT NOT NULL,
                authors TEXT,
                description TEXT,
                publisher TEXT,
                publication_date TEXT,
                publication_year TEXT,
                isbn10 TEXT,
                isbn13 TEXT,
                page_count TEXT,
                categories TEXT,
                language TEXT,
                cover_url TEXT,
                source_url TEXT,
                source_type TEXT,
                source_rating TEXT,
                source_rating_count TEXT,
                catalog_status TEXT NOT NULL DEFAULT 'Draft',
                intelligence_status TEXT NOT NULL DEFAULT 'Needs Processing',
                admin_note TEXT,
                created_by INTEGER,
                updated_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(user_id) ON DELETE SET NULL,
                FOREIGN KEY(updated_by) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_book_overrides (
                override_id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id TEXT NOT NULL UNIQUE,
                title TEXT,
                authors TEXT,
                description TEXT,
                publisher TEXT,
                publication_date TEXT,
                publication_year TEXT,
                isbn10 TEXT,
                isbn13 TEXT,
                page_count TEXT,
                categories TEXT,
                language TEXT,
                cover_url TEXT,
                source_url TEXT,
                source_type TEXT,
                source_rating TEXT,
                source_rating_count TEXT,
                catalog_status TEXT NOT NULL DEFAULT 'Published',
                admin_note TEXT,
                updated_by INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(updated_by) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(admin_user_id) REFERENCES users(user_id) ON DELETE RESTRICT
            )
            """
        )


        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS catalog_change_requests (
                request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id TEXT NOT NULL,
                record_type TEXT NOT NULL,
                action_type TEXT NOT NULL,
                before_json TEXT,
                proposed_json TEXT,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                requested_by INTEGER NOT NULL,
                requested_at TEXT NOT NULL,
                reviewed_by INTEGER,
                reviewed_at TEXT,
                review_note TEXT,
                FOREIGN KEY(requested_by) REFERENCES users(user_id) ON DELETE RESTRICT,
                FOREIGN KEY(reviewed_by) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )


def hash_password(password, salt_hex):
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return digest.hex()


def _bootstrap_secret(name):
    """Read a bootstrap value from Streamlit secrets first, then environment."""
    value = ""
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()



def _leadwise_email_settings():
    """Return transactional email settings without exposing secret values."""
    api_key = _bootstrap_secret("RESEND_API_KEY")
    from_email = _bootstrap_secret("LEADWISE_REPLY_FROM_EMAIL")
    from_name = _bootstrap_secret("LEADWISE_REPLY_FROM_NAME") or "LeadWise"
    return {
        "api_key": api_key,
        "from_email": from_email,
        "from_name": from_name,
        "configured": bool(api_key and from_email),
    }


def _valid_email_address(value):
    email_value = str(value or "").strip()
    return (
        bool(email_value)
        and "@" in email_value
        and "." in email_value.split("@")[-1]
    )


def send_inquiry_reply_email(inquiry, reply_message):
    """Send one inquiry reply through Resend's HTTPS Email API."""
    reply_message = str(reply_message or "").strip()
    recipient = str(inquiry.get("email") or "").strip()

    if not reply_message:
        return False, None, "Enter a reply before sending.", False

    if not _valid_email_address(recipient):
        return False, None, "This inquiry does not have a valid reply email address.", False

    settings = _leadwise_email_settings()
    if not settings["configured"]:
        return (
            False,
            None,
            (
                "Email delivery is not configured yet. Add RESEND_API_KEY and "
                "LEADWISE_REPLY_FROM_EMAIL to the Admin Streamlit secrets."
            ),
            False,
        )

    original_subject = str(inquiry.get("subject") or "").strip()
    subject = original_subject or "Your LeadWise inquiry"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    sender_name = settings["from_name"].replace("\n", " ").strip() or "LeadWise"
    from_value = f"{sender_name} <{settings['from_email']}>"

    recipient_name = html.escape(
        str(inquiry.get("full_name") or "").strip() or "Reader"
    )
    safe_reply = html.escape(reply_message).replace("\n", "<br>")
    safe_original = html.escape(str(inquiry.get("message") or "")).replace(
        "\n", "<br>"
    )
    safe_sender_name = html.escape(sender_name)

    html_body = (
        f"<p>Hello {recipient_name},</p>"
        f"<p>{safe_reply}</p>"
        f"<p>Regards,<br>{safe_sender_name}</p>"
        "<hr>"
        "<p style='color:#66788A;font-size:12px;'>"
        "Your original LeadWise inquiry:</p>"
        f"<blockquote>{safe_original}</blockquote>"
    )

    text_body = (
        f"Hello {str(inquiry.get('full_name') or '').strip() or 'Reader'},\n\n"
        f"{reply_message}\n\n"
        f"Regards,\n{sender_name}\n\n"
        "Your original LeadWise inquiry:\n"
        f"{str(inquiry.get('message') or '').strip()}"
    )

    payload = {
        "from": from_value,
        "to": [recipient],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }

    inquiry_id = int(inquiry["inquiry_id"])
    fingerprint = hashlib.sha256(reply_message.encode("utf-8")).hexdigest()[:24]
    idempotency_key = f"leadwise-inquiry-{inquiry_id}-{fingerprint}"

    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings['api_key']}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            response_data = json.loads(response_body or "{}")
            external_message_id = str(response_data.get("id") or "").strip()
            if not external_message_id:
                return (
                    False,
                    None,
                    "The email provider accepted the request but returned no message ID.",
                    True,
                )
            return True, external_message_id, "Reply email sent.", True

    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
            error_data = json.loads(error_body or "{}")
            provider_message = (
                error_data.get("message")
                or error_data.get("name")
                or f"HTTP {exc.code}"
            )
        except Exception:
            provider_message = f"HTTP {exc.code}"

        return (
            False,
            None,
            f"Email provider rejected the message: {provider_message}",
            True,
        )

    except Exception as exc:
        return (
            False,
            None,
            f"Email delivery failed: {type(exc).__name__}.",
            True,
        )


def record_inquiry_reply(
    inquiry_id,
    reply_message,
    sent_to_email,
    delivery_status,
    external_message_id=None,
):
    """Persist an Admin reply attempt and update the inquiry when sent."""
    actor = admin_user()
    if not actor:
        raise RuntimeError("An authenticated administrator is required.")

    now = datetime.now(timezone.utc).isoformat()
    sent_at = now if delivery_status == "Sent" else None

    with db_connection() as connection:
        reply_id = insert_returning_id(
            connection,
            """
            INSERT INTO leadwise_inquiry_replies
                (inquiry_id, admin_user_id, reply_message, sent_to_email,
                 delivery_status, external_message_id, created_at, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(inquiry_id),
                int(actor["user_id"]),
                str(reply_message).strip(),
                str(sent_to_email or "").strip() or None,
                str(delivery_status),
                external_message_id,
                now,
                sent_at,
            ),
            "reply_id",
        )

        if delivery_status == "Sent":
            connection.execute(
                """
                UPDATE leadwise_inquiries
                SET status='Replied', replied_at=?, replied_by=?
                WHERE inquiry_id=?
                """,
                (now, int(actor["user_id"]), int(inquiry_id)),
            )

    log_admin_action(
        "inquiry_reply_sent" if delivery_status == "Sent" else "inquiry_reply_failed",
        "inquiry",
        str(inquiry_id),
        (
            f"reply_id={reply_id}; delivery_status={delivery_status}; "
            f"sent_to={str(sent_to_email or '').strip()}"
        ),
    )
    return reply_id


def update_inquiry_status(inquiry_id, status):
    allowed_statuses = {"New", "In Progress", "Replied", "Closed"}
    if status not in allowed_statuses:
        return False, "Invalid inquiry status."

    actor = admin_user()
    if not actor:
        return False, "Administrator authentication is required."

    with db_connection() as connection:
        exists = connection.execute(
            "SELECT inquiry_id FROM leadwise_inquiries WHERE inquiry_id=?",
            (int(inquiry_id),),
        ).fetchone()
        if not exists:
            return False, "Inquiry not found."

        connection.execute(
            "UPDATE leadwise_inquiries SET status=? WHERE inquiry_id=?",
            (status, int(inquiry_id)),
        )

    log_admin_action(
        "inquiry_status_updated",
        "inquiry",
        str(inquiry_id),
        f"status={status}",
    )
    return True, f"Inquiry marked {status}."


def bootstrap_super_admin():
    """Create the first Super Admin only when none exists.

    Credentials are supplied through Streamlit Secrets or environment variables.
    No plaintext bootstrap password is stored in the database or source code.
    """
    with db_connection() as connection:
        existing = connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM users
            WHERE role = 'super_admin'
              AND is_active = 1
              AND COALESCE(admin_account_status, 'Active') = 'Active'
            """
        ).fetchone()

        if existing and int(existing["n"] or 0) > 0:
            return False

    full_name = _bootstrap_secret("LEADWISE_SUPER_ADMIN_NAME")
    email = _bootstrap_secret("LEADWISE_SUPER_ADMIN_EMAIL").lower()
    password = _bootstrap_secret("LEADWISE_SUPER_ADMIN_PASSWORD")

    # Missing secrets are allowed: the Admin login page remains available,
    # but no bootstrap account is created.
    if not full_name or not email or not password:
        return False

    if "@" not in email or "." not in email.split("@")[-1]:
        raise RuntimeError("LEADWISE_SUPER_ADMIN_EMAIL is not a valid email address.")

    if len(password) < 8:
        raise RuntimeError(
            "LEADWISE_SUPER_ADMIN_PASSWORD must contain at least 8 characters."
        )

    salt_hex = secrets.token_bytes(16).hex()
    password_hash = hash_password(password, salt_hex)
    now = datetime.now(timezone.utc).isoformat()

    with db_connection() as connection:
        # Re-check inside the write transaction to keep the bootstrap idempotent.
        existing_super = connection.execute(
            """
            SELECT user_id
            FROM users
            WHERE role = 'super_admin'
              AND is_active = 1
              AND COALESCE(admin_account_status, 'Active') = 'Active'
            LIMIT 1
            """
        ).fetchone()
        if existing_super:
            return False

        existing_email = connection.execute(
            "SELECT user_id FROM users WHERE lower(email) = lower(?)",
            (email,),
        ).fetchone()

        if existing_email:
            connection.execute(
                """
                UPDATE users
                SET full_name = ?,
                    password_hash = ?,
                    password_salt = ?,
                    role = 'super_admin',
                    is_active = 1,
                    admin_account_status = 'Active',
                    admin_status_note = 'Secure bootstrap promotion'
                WHERE user_id = ?
                """,
                (full_name, password_hash, salt_hex, int(existing_email["user_id"])),
            )
        else:
            connection.execute(
                """
                INSERT INTO users
                    (full_name, email, password_hash, password_salt,
                     created_at, is_active, role, admin_account_status,
                     admin_status_note)
                VALUES (?, ?, ?, ?, ?, 1, 'super_admin', 'Active',
                        'Secure bootstrap account')
                """,
                (full_name, email, password_hash, salt_hex, now),
            )

    return True


def authenticate_admin(email, password):
    email = str(email or "").strip().lower()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT user_id, full_name, email, password_hash, password_salt, role, is_active, COALESCE(admin_account_status, 'Active') AS admin_account_status FROM users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()

    if row is None or row["role"] not in {"admin", "super_admin"}:
        return None
    if int(row["is_active"] or 0) != 1:
        return None
    if str(row["admin_account_status"] or "Active") != "Active":
        return None

    candidate = hash_password(password, row["password_salt"])
    if not hmac.compare_digest(candidate, row["password_hash"]):
        return None

    return {
        "user_id": row["user_id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
    }




def _catalog_csv_path():
    candidates = [
        CATALOG_CSV_PATH,
        PROJECT_ROOT / "data" / "leadwise_streamlit_catalog.csv",
        PROJECT_ROOT / "data" / "processed" / "leadwise_streamlit_catalog.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


@st.cache_data(show_spinner=False)
def load_frozen_catalog():
    path = _catalog_csv_path()
    if not path.exists():
        return pd.DataFrame(), path
    return pd.read_csv(path), path


def _first_existing(row, names, default=""):
    for name in names:
        if name in row.index and pd.notna(row[name]):
            value = str(row[name]).strip()
            if value and value.lower() != "nan":
                return value
    return default


def frozen_book_to_edit_record(row):
    return {
        "book_id": _first_existing(row, ["book_id"]),
        "title": _first_existing(row, ["display_title", "canonical_title", "title", "Title"]),
        "authors": _first_existing(row, ["display_authors", "authors", "author", "Authors"]),
        "description": _first_existing(row, ["display_description", "description", "synopsis", "description_raw"]),
        "publisher": _first_existing(row, ["display_publisher", "publisher"]),
        "publication_date": _first_existing(row, ["publication_date", "published_date"]),
        "publication_year": _first_existing(row, ["publication_year", "year"]),
        "isbn10": _first_existing(row, ["isbn10", "isbn_10"]),
        "isbn13": _first_existing(row, ["isbn13", "isbn_13"]),
        "page_count": _first_existing(row, ["display_page_count", "page_count", "pages"]),
        "categories": _first_existing(row, ["display_categories", "categories", "category"]),
        "language": _first_existing(row, ["display_language", "language"]),
        "cover_url": _first_existing(row, ["display_cover_url", "cover_url", "cover_image", "thumbnail"]),
        "source_url": _first_existing(row, ["source_url", "book_url"]),
        "source_type": _first_existing(row, ["source_type", "source"]),
        "source_rating": _first_existing(row, ["display_rating", "rating", "average_rating"]),
        "source_rating_count": _first_existing(row, ["rating_count", "ratings_count"]),
        "catalog_status": "Published",
        "admin_note": "",
    }


def get_catalog_override(book_id):
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM catalog_book_overrides WHERE book_id = ?",
            (str(book_id),),
        ).fetchone()
    return dict(row) if row else None



def _audit_clean(value):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _catalog_audit_snapshot(record, intelligence_status=None):
    fields = [
        "title", "authors", "publisher", "publication_year", "publication_date",
        "isbn10", "isbn13", "page_count", "categories", "language",
        "source_type", "source_url", "source_rating", "source_rating_count",
        "catalog_status"
    ]
    snap = {field: _audit_clean(record.get(field, "")) for field in fields}
    if intelligence_status is not None:
        snap["intelligence_status"] = _audit_clean(intelligence_status)
    return snap


def _catalog_audit_details(record, intelligence_status=None, before=None):
    after = _catalog_audit_snapshot(record, intelligence_status)
    parts = [
        f"title={after.get('title') or '—'}",
        f"authors={after.get('authors') or '—'}",
        f"status={after.get('catalog_status') or '—'}",
    ]
    if intelligence_status is not None:
        parts.append(f"intelligence={after.get('intelligence_status') or '—'}")
    for field in ["publisher","publication_year","isbn10","isbn13","categories","language","source_type"]:
        if after.get(field):
            parts.append(f"{field}={after[field]}")
    if before is not None:
        before_snap = _catalog_audit_snapshot(before, before.get("intelligence_status") if hasattr(before, "get") else None)
        changes = []
        for field, new_value in after.items():
            old_value = _audit_clean(before_snap.get(field, ""))
            if old_value != _audit_clean(new_value):
                changes.append(f"{field}: {old_value or '—'} -> {_audit_clean(new_value) or '—'}")
        if changes:
            parts.append("changes=[" + " | ".join(changes) + "]")
        else:
            parts.append("changes=[no field-level changes]")
    return "; ".join(parts)


def save_catalog_override(record):
    actor = admin_user()
    now = datetime.now(timezone.utc).isoformat()
    fields = [
        "title", "authors", "description", "publisher", "publication_date",
        "publication_year", "isbn10", "isbn13", "page_count", "categories",
        "language", "cover_url", "source_url", "source_type", "source_rating",
        "source_rating_count", "catalog_status", "admin_note"
    ]
    values = [str(record.get(f, "") or "").strip() for f in fields]
    with db_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO catalog_book_overrides
                (book_id, {", ".join(fields)}, updated_by, updated_at)
            VALUES (?, {", ".join(["?"] * len(fields))}, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                {", ".join([f"{f}=excluded.{f}" for f in fields])},
                updated_by=excluded.updated_by,
                updated_at=excluded.updated_at
            """,
            [str(record["book_id"])] + values + [int(actor["user_id"]), now],
        )
    log_admin_action(
        "catalog_book_edited", "book", str(record["book_id"]),
        _catalog_audit_details(record)
    )


def next_admin_book_id():
    frozen, _ = load_frozen_catalog()
    nums = []
    if not frozen.empty and "book_id" in frozen.columns:
        nums.extend(
            int(m.group(1))
            for value in frozen["book_id"].dropna().astype(str)
            if (m := re.fullmatch(r"BOOK(\d+)", value.strip()))
        )
    with db_connection() as connection:
        rows = connection.execute("SELECT book_id FROM live_catalog_books").fetchall()
        pending_adds = connection.execute(
            """SELECT book_id FROM catalog_change_requests
               WHERE action_type='Add' AND status='Pending'"""
        ).fetchall()
    nums.extend(
        int(m.group(1))
        for row in list(rows) + list(pending_adds)
        if (m := re.fullmatch(r"BOOK(\d+)", str(row["book_id"]).strip()))
    )
    return f"BOOK{(max(nums) + 1 if nums else 1):05d}"


def add_live_catalog_book(record):
    actor = admin_user()
    now = datetime.now(timezone.utc).isoformat()
    book_id = next_admin_book_id()
    fields = [
        "title", "authors", "description", "publisher", "publication_date",
        "publication_year", "isbn10", "isbn13", "page_count", "categories",
        "language", "cover_url", "source_url", "source_type", "source_rating",
        "source_rating_count", "catalog_status", "admin_note"
    ]
    values = [str(record.get(f, "") or "").strip() for f in fields]
    with db_connection() as connection:
        connection.execute(
            f"""
            INSERT INTO live_catalog_books
                (book_id, record_origin, {", ".join(fields)},
                 intelligence_status, created_by, updated_by, created_at, updated_at)
            VALUES (?, 'admin', {", ".join(["?"] * len(fields))},
                    'Needs Processing', ?, ?, ?, ?)
            """,
            [book_id] + values + [
                int(actor["user_id"]), int(actor["user_id"]), now, now
            ],
        )
    log_admin_action(
        "catalog_book_added", "book", book_id,
        _catalog_audit_details(record, intelligence_status="Needs Processing")
    )
    return book_id



def add_approved_live_catalog_book(book_id, record):
    """Create a live catalog row only after an Add request is approved."""
    actor = admin_user()
    now = datetime.now(timezone.utc).isoformat()
    fields = [
        "title", "authors", "description", "publisher", "publication_date",
        "publication_year", "isbn10", "isbn13", "page_count", "categories",
        "language", "cover_url", "source_url", "source_type", "source_rating",
        "source_rating_count", "catalog_status", "admin_note"
    ]
    clean = dict(record or {})
    clean["catalog_status"] = str(clean.get("catalog_status") or "Published")
    values = [str(clean.get(f, "") or "").strip() for f in fields]
    with db_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM live_catalog_books WHERE book_id=?", (str(book_id),)
        ).fetchone()
        if exists:
            raise RuntimeError(f"{book_id} already exists in the live catalog.")
        connection.execute(
            f"""
            INSERT INTO live_catalog_books
                (book_id, record_origin, {", ".join(fields)},
                 intelligence_status, created_by, updated_by, created_at, updated_at)
            VALUES (?, 'admin', {", ".join(["?"] * len(fields))},
                    'Needs Processing', ?, ?, ?, ?)
            """,
            [str(book_id)] + values + [
                int(actor["user_id"]), int(actor["user_id"]), now, now
            ],
        )
    log_admin_action(
        "catalog_book_added_approved", "book", str(book_id),
        _catalog_audit_details(clean, intelligence_status="Needs Processing")
    )
    return str(book_id)


def update_live_catalog_book(book_id, record):
    actor = admin_user()
    now = datetime.now(timezone.utc).isoformat()
    fields = [
        "title", "authors", "description", "publisher", "publication_date",
        "publication_year", "isbn10", "isbn13", "page_count", "categories",
        "language", "cover_url", "source_url", "source_type", "source_rating",
        "source_rating_count", "catalog_status", "admin_note"
    ]
    values = [str(record.get(f, "") or "").strip() for f in fields]
    with db_connection() as connection:
        before_row = connection.execute(
            "SELECT * FROM live_catalog_books WHERE book_id=?",
            (str(book_id),),
        ).fetchone()
        before = dict(before_row) if before_row else {}
        connection.execute(
            f"""
            UPDATE live_catalog_books
            SET {", ".join([f"{f}=?" for f in fields])},
                updated_by=?, updated_at=?
            WHERE book_id=?
            """,
            values + [int(actor["user_id"]), now, str(book_id)],
        )
    log_admin_action(
        "catalog_book_updated", "book", str(book_id),
        _catalog_audit_details(
            record,
            intelligence_status=before.get("intelligence_status", "Needs Processing"),
            before=before,
        )
    )


def change_catalog_status(book_id, record_type, new_status, reason=""):
    """Change catalog lifecycle state and preserve the action in the admin audit trail."""
    allowed = {"Draft", "Published", "Hidden", "Archived"}
    if new_status not in allowed:
        return False, "Invalid catalog status."

    actor = admin_user()
    if not actor:
        return False, "Administrator session is required."

    now = datetime.now(timezone.utc).isoformat()
    book_id = str(book_id).strip()
    reason = str(reason or "").strip()

    with db_connection() as connection:
        if record_type == "Admin Added":
            row = connection.execute(
                "SELECT * FROM live_catalog_books WHERE book_id=?",
                (book_id,),
            ).fetchone()
            if not row:
                return False, "Book could not be found."
            before = dict(row)
            old_status = str(before.get("catalog_status") or "Draft")
            connection.execute(
                """UPDATE live_catalog_books
                   SET catalog_status=?, updated_by=?, updated_at=?
                   WHERE book_id=?""",
                (new_status, int(actor["user_id"]), now, book_id),
            )
            title = str(before.get("title") or "")
            authors = str(before.get("authors") or "")
            intelligence = str(before.get("intelligence_status") or "Needs Processing")
        else:
            existing = connection.execute(
                "SELECT * FROM catalog_book_overrides WHERE book_id=?",
                (book_id,),
            ).fetchone()
            if existing:
                before = dict(existing)
                old_status = str(before.get("catalog_status") or "Published")
                connection.execute(
                    """UPDATE catalog_book_overrides
                       SET catalog_status=?, updated_by=?, updated_at=?
                       WHERE book_id=?""",
                    (new_status, int(actor["user_id"]), now, book_id),
                )
                title = str(before.get("title") or book_id)
                authors = str(before.get("authors") or "")
            else:
                frozen, _ = load_frozen_catalog()
                match = frozen[frozen["book_id"].astype(str).eq(book_id)]
                if match.empty:
                    return False, "Frozen book could not be found."
                base = frozen_record_for_edit(match.iloc[0])
                old_status = "Published"
                base["catalog_status"] = new_status
                save_catalog_override(base)
                # save_catalog_override already logs a generic edit; lifecycle event below is authoritative.
                title = str(base.get("title") or book_id)
                authors = str(base.get("authors") or "")
            intelligence = "Frozen Model"

    details = (
        f"title={title or '—'}; authors={authors or '—'}; "
        f"status: {old_status} -> {new_status}; intelligence={intelligence}"
    )
    if reason:
        details += f"; reason={reason}"
    log_admin_action(
        "catalog_status_changed", "book", book_id, details
    )
    return True, f"{book_id} changed from {old_status} to {new_status}."



def submit_catalog_change_request(book_id, record_type, action_type, before, proposed, reason):
    actor=admin_user()
    reason=str(reason or "").strip()
    if not reason:
        return False,"A reason is required for governed catalog changes."
    now=datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        pending=connection.execute(
            """SELECT request_id FROM catalog_change_requests
               WHERE book_id=? AND status='Pending'""",(str(book_id),)
        ).fetchone()
        if pending:
            return False,f"A pending request already exists for {book_id}."
        rid = insert_returning_id(
            connection,
            """INSERT INTO catalog_change_requests
               (book_id,record_type,action_type,before_json,proposed_json,reason,
                status,requested_by,requested_at)
               VALUES (?,?,?,?,?,?,'Pending',?,?)""",
            (str(book_id),str(record_type),str(action_type),
             json.dumps(before or {},default=str),json.dumps(proposed or {},default=str),
             reason,int(actor["user_id"]),now),
            "request_id",
        )
    log_admin_action("catalog_change_requested","book",str(book_id),
                     f"request_id={rid}; action={action_type}; reason={reason}")
    return True,f"Change request #{rid} submitted for Super Admin approval."


def _apply_approved_catalog_request(req):
    before=json.loads(req["before_json"] or "{}")
    proposed=json.loads(req["proposed_json"] or "{}")
    book_id=str(req["book_id"]); action=str(req["action_type"])
    record_type=str(req["record_type"])

    if action=="Add":
        proposed["catalog_status"] = "Published"
        add_approved_live_catalog_book(book_id, proposed)
    elif action=="Edit":
        if record_type=="Admin Added":
            update_live_catalog_book(book_id,proposed)
            # Semantic metadata may have changed; require a fresh vector before recommendations.
            with db_connection() as connection:
                connection.execute(
                    "UPDATE live_catalog_books SET intelligence_status='Needs Processing' WHERE book_id=?",
                    (book_id,)
                )
                connection.execute(
                    "DELETE FROM recommendation_book_vectors WHERE book_id=?",
                    (book_id,)
                )
        else:
            proposed["book_id"]=book_id
            save_catalog_override(proposed)
    elif action in {"Publish","Draft","Hide","Archive","Restore"}:
        target={"Publish":"Published","Draft":"Draft","Hide":"Hidden",
                "Archive":"Archived","Restore":"Published"}[action]
        ok,msg=change_catalog_status(book_id,record_type,target,req["reason"])
        if not ok: raise RuntimeError(msg)
    elif action=="Retire":
        # Soft retirement: preserve the record, references and audit history.
        ok,msg=change_catalog_status(book_id,record_type,"Archived",req["reason"])
        if not ok: raise RuntimeError(msg)
    else:
        raise ValueError(f"Unsupported catalog action: {action}")



def record_super_admin_catalog_action(book_id, record_type, action_type, before, proposed, reason):
    """Record an already-authorized Super Admin catalog action in governance history."""
    actor=admin_user()
    if not actor or actor.get("role")!="super_admin":
        return None
    now=datetime.now(timezone.utc).isoformat()
    reason=str(reason or "").strip() or "Super Admin direct action"
    with db_connection() as connection:
        request_id = insert_returning_id(
            connection,
            """INSERT INTO catalog_change_requests
               (book_id,record_type,action_type,before_json,proposed_json,reason,
                status,requested_by,requested_at,reviewed_by,reviewed_at,review_note)
               VALUES (?,?,?,?,?,?,'Approved',?,?,?,?,?)""",
            (
                str(book_id),str(record_type),str(action_type),
                json.dumps(before or {},default=str),
                json.dumps(proposed or {},default=str),
                reason,int(actor["user_id"]),now,int(actor["user_id"]),now,
                "Super Admin Direct Action — self-authorized and applied."
            ),
            "request_id",
        )
    log_admin_action(
        "catalog_super_admin_direct_action","book",str(book_id),
        f"request_id={request_id}; action={action_type}; reason={reason}"
    )
    return request_id


def review_catalog_change_request(request_id,decision,note=""):
    actor=admin_user()
    if not actor or actor.get("role")!="super_admin":
        return False,"Only a Super Admin can approve or reject catalog changes."
    if decision not in {"Approved","Rejected"}:
        return False,"Invalid review decision."
    with db_connection() as connection:
        row=connection.execute(
            "SELECT * FROM catalog_change_requests WHERE request_id=?",(int(request_id),)
        ).fetchone()
    if not row or row["status"]!="Pending":
        return False,"This request is no longer pending."
    req=dict(row)
    if decision=="Approved":
        _apply_approved_catalog_request(req)
    now=datetime.now(timezone.utc).isoformat()
    with db_connection() as connection:
        connection.execute(
            """UPDATE catalog_change_requests
               SET status=?,reviewed_by=?,reviewed_at=?,review_note=?
               WHERE request_id=?""",
            (decision,int(actor["user_id"]),now,str(note or "").strip(),int(request_id))
        )
    log_admin_action(f"catalog_change_{decision.lower()}","book",str(req["book_id"]),
                     f"request_id={request_id}; action={req['action_type']}; note={note}")
    return True,f"Request #{request_id} {decision.lower()}."


def current_live_book(book_id):
    with db_connection() as connection:
        row=connection.execute("SELECT * FROM live_catalog_books WHERE book_id=?",
                               (str(book_id),)).fetchone()
    return dict(row) if row else {}


def catalog_form(prefix, defaults=None, new_book=False):
    d = defaults or {}
    title = st.text_input("Title *", value=str(d.get("title", "")), key=f"{prefix}_title")
    authors = st.text_input("Author(s)", value=str(d.get("authors", "")), key=f"{prefix}_authors")
    description = st.text_area("Synopsis / Description", value=str(d.get("description", "")), height=150, key=f"{prefix}_description")
    c1, c2 = st.columns(2)
    publisher = c1.text_input("Publisher", value=str(d.get("publisher", "")), key=f"{prefix}_publisher")
    publication_year = c2.text_input("Publication Year", value=str(d.get("publication_year", "")), key=f"{prefix}_year")
    publication_date = st.text_input("Publication Date", value=str(d.get("publication_date", "")), key=f"{prefix}_date")
    c1, c2, c3 = st.columns(3)
    isbn10 = c1.text_input("ISBN-10", value=str(d.get("isbn10", "")), key=f"{prefix}_isbn10")
    isbn13 = c2.text_input("ISBN-13", value=str(d.get("isbn13", "")), key=f"{prefix}_isbn13")
    page_count = c3.text_input("Page Count", value=str(d.get("page_count", "")), key=f"{prefix}_pages")
    categories = st.text_input("Categories", value=str(d.get("categories", "")), key=f"{prefix}_categories")
    language = st.text_input("Language", value=str(d.get("language", "")), key=f"{prefix}_language")
    cover_url = st.text_input("Cover Image URL", value=str(d.get("cover_url", "")), key=f"{prefix}_cover")
    source_url = st.text_input("Source URL", value=str(d.get("source_url", "")), key=f"{prefix}_source_url")
    c1, c2, c3 = st.columns(3)
    source_type = c1.text_input("Source Type", value=str(d.get("source_type", "")), key=f"{prefix}_source_type")
    source_rating = c2.text_input("Source Rating", value=str(d.get("source_rating", "")), key=f"{prefix}_rating")
    source_rating_count = c3.text_input("Rating Count", value=str(d.get("source_rating_count", "")), key=f"{prefix}_rating_count")
    status_options = ["Draft", "Published", "Hidden", "Archived"] if new_book else ["Published", "Hidden", "Archived"]
    current = str(d.get("catalog_status", status_options[0]))
    if current not in status_options:
        current = status_options[0]
    catalog_status = st.selectbox("Catalog Status", status_options, index=status_options.index(current), key=f"{prefix}_status")
    admin_note = st.text_area("Internal Admin Note", value=str(d.get("admin_note", "")), key=f"{prefix}_note")
    return {
        "title": title, "authors": authors, "description": description,
        "publisher": publisher, "publication_date": publication_date,
        "publication_year": publication_year, "isbn10": isbn10, "isbn13": isbn13,
        "page_count": page_count, "categories": categories, "language": language,
        "cover_url": cover_url, "source_url": source_url, "source_type": source_type,
        "source_rating": source_rating, "source_rating_count": source_rating_count,
        "catalog_status": catalog_status, "admin_note": admin_note,
    }


def create_admin_access_request(full_name, email, organization_position, reason,
                                password, confirm_password):
    full_name = str(full_name or "").strip()
    email = str(email or "").strip().lower()
    organization_position = str(organization_position or "").strip()
    reason = str(reason or "").strip()

    if not full_name or not email or not reason:
        return False, "Full name, email and reason are required."
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Please enter a valid email address."
    if len(password or "") < 8:
        return False, "Password must contain at least 8 characters."
    if password != confirm_password:
        return False, "Passwords do not match."

    with db_connection() as connection:
        existing_user = connection.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(?)", (email,)
        ).fetchone()
        if existing_user:
            return False, "This email already belongs to a LeadWise account."

        existing_request = connection.execute(
            "SELECT status FROM admin_access_requests WHERE lower(email) = lower(?)",
            (email,),
        ).fetchone()
        if existing_request:
            return False, f"An administrator access request already exists with status: {existing_request['status']}."

        salt_hex = secrets.token_bytes(16).hex()
        password_hash = hash_password(password, salt_hex)
        connection.execute(
            """
            INSERT INTO admin_access_requests
                (full_name, email, organization_position, reason,
                 password_hash, password_salt, requested_role, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'admin', 'Pending', ?)
            """,
            (
                full_name, email, organization_position, reason,
                password_hash, salt_hex,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return True, "Your administrator access request has been submitted for Super Admin approval."


def review_admin_request(request_id, decision, admin_note=""):
    reviewer = admin_user()
    if not reviewer or reviewer.get("role") != "super_admin":
        return False, "Only a Super Admin can review administrator access requests."

    with db_connection() as connection:
        req = connection.execute(
            "SELECT * FROM admin_access_requests WHERE request_id = ?",
            (int(request_id),),
        ).fetchone()
        if not req:
            return False, "Request not found."
        if req["status"] != "Pending":
            return False, f"This request is already {req['status']}."

        now = datetime.now(timezone.utc).isoformat()

        if decision == "Approved":
            existing = connection.execute(
                "SELECT user_id FROM users WHERE lower(email) = lower(?)",
                (req["email"],),
            ).fetchone()
            if existing:
                return False, "A LeadWise user with this email already exists."

            connection.execute(
                """
                INSERT INTO users
                    (full_name, email, password_hash, password_salt,
                     created_at, is_active, role)
                VALUES (?, ?, ?, ?, ?, 1, 'admin')
                """,
                (
                    req["full_name"], req["email"], req["password_hash"],
                    req["password_salt"], now,
                ),
            )

        connection.execute(
            """
            UPDATE admin_access_requests
            SET status = ?, reviewed_by = ?, reviewed_at = ?, admin_note = ?
            WHERE request_id = ?
            """,
            (decision, int(reviewer["user_id"]), now, str(admin_note or "").strip(), int(request_id)),
        )

    log_admin_action(
        f"admin_request_{decision.lower()}",
        "admin_access_request",
        str(request_id),
        f"Decision={decision}",
    )
    return True, f"Administrator request {decision.lower()}."



def active_super_admin_count():
    with db_connection() as connection:
        return int(connection.execute(
            """
            SELECT COUNT(*) AS n
            FROM users
            WHERE role='super_admin'
              AND is_active=1
              AND COALESCE(admin_account_status,'Active')='Active'
            """
        ).fetchone()["n"])


def change_admin_lifecycle(user_id, new_status, note=""):
    actor = admin_user()
    if not actor or actor.get("role") != "super_admin":
        return False, "Only a Super Admin can manage administrator lifecycle status."

    allowed = {"Active", "Frozen", "Deactivated", "Retired"}
    if new_status not in allowed:
        return False, "Invalid administrator status."

    with db_connection() as connection:
        target = connection.execute(
            "SELECT user_id, full_name, email, role, is_active, admin_account_status FROM users WHERE user_id=?",
            (int(user_id),)
        ).fetchone()
        if not target or target["role"] not in {"admin", "super_admin"}:
            return False, "Administrator account not found."

        if int(target["user_id"]) == int(actor["user_id"]) and new_status != "Active":
            if target["role"] == "super_admin" and active_super_admin_count() <= 1:
                return False, "You cannot disable the only active Super Admin. Promote another Super Admin first."

        if target["role"] == "super_admin" and new_status != "Active":
            if active_super_admin_count() <= 1:
                return False, "The last active Super Admin cannot be frozen, deactivated or retired."

        now=datetime.now(timezone.utc).isoformat()
        is_active = 1 if new_status == "Active" else 0
        connection.execute(
            """
            UPDATE users
            SET is_active=?, admin_account_status=?, admin_status_note=?,
                admin_status_changed_at=?, admin_status_changed_by=?
            WHERE user_id=?
            """,
            (is_active,new_status,str(note or "").strip(),now,int(actor["user_id"]),int(user_id))
        )

    log_admin_action(
        f"administrator_{new_status.lower()}",
        "user", str(user_id),
        f"administrator={target['full_name']}; status={new_status}"
    )
    return True, f"{target['full_name']} is now {new_status}."


def promote_to_super_admin(user_id):
    actor=admin_user()
    if not actor or actor.get("role")!="super_admin":
        return False,"Only a Super Admin can promote another administrator."
    with db_connection() as connection:
        target=connection.execute(
            "SELECT user_id,full_name,role,is_active,admin_account_status FROM users WHERE user_id=?",
            (int(user_id),)
        ).fetchone()
        if not target or target["role"]!="admin":
            return False,"Select an Admin account to promote."
        if int(target["is_active"] or 0)!=1 or str(target["admin_account_status"] or "Active")!="Active":
            return False,"Only an active Admin can be promoted."
        connection.execute("UPDATE users SET role='super_admin' WHERE user_id=?",(int(user_id),))
    log_admin_action("administrator_promoted_super_admin","user",str(user_id),target["full_name"])
    return True,f"{target['full_name']} is now a Super Admin."


def retire_admin_login(user_id, confirmation, note=""):
    actor=admin_user()
    if not actor or actor.get("role")!="super_admin":
        return False,"Only a Super Admin can retire an administrator login."
    with db_connection() as connection:
        target=connection.execute(
            "SELECT user_id,full_name,role FROM users WHERE user_id=?",(int(user_id),)
        ).fetchone()
        if not target:
            return False,"Administrator not found."
        if target["role"]=="super_admin" and active_super_admin_count()<=1:
            return False,"The last active Super Admin cannot be retired."
        expected=f"RETIRE {target['full_name']}".upper()
        if str(confirmation or "").strip().upper()!=expected:
            return False,f"Type exactly: {expected}"
        now=datetime.now(timezone.utc).isoformat()
        # Preserve the row and audit relationships, but permanently remove login credentials.
        retired_email=f"retired-admin-{target['user_id']}@leadwise.invalid"
        connection.execute(
            """
            UPDATE users
            SET email=?, password_hash='', password_salt='', is_active=0,
                admin_account_status='Retired', admin_status_note=?,
                admin_status_changed_at=?, admin_status_changed_by=?
            WHERE user_id=?
            """,
            (retired_email,str(note or "").strip(),now,int(actor["user_id"]),int(user_id))
        )
    log_admin_action("administrator_login_retired","user",str(user_id),target["full_name"])
    return True,"Administrator login permanently retired. Historical audit attribution is preserved."


def set_admin_active(user_id, make_active):
    actor = admin_user()
    if not actor or actor.get("role") != "super_admin":
        return False, "Only a Super Admin can manage administrator accounts."
    if int(user_id) == int(actor["user_id"]):
        return False, "You cannot deactivate your own Super Admin account."

    with db_connection() as connection:
        target = connection.execute(
            "SELECT user_id, full_name, role FROM users WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
        if not target or target["role"] != "admin":
            return False, "Only standard Admin accounts can be changed here."
        connection.execute(
            "UPDATE users SET is_active = ? WHERE user_id = ?",
            (1 if make_active else 0, int(user_id)),
        )

    log_admin_action(
        "admin_activated" if make_active else "admin_deactivated",
        "user", str(user_id), target["full_name"],
    )
    return True, "Administrator account updated."


def admin_user():
    return st.session_state.get("leadwise_admin_user")


def log_admin_action(action, entity_type=None, entity_id=None, details=None):
    user = admin_user()
    if not user:
        return
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_audit_log
                (admin_user_id, action, entity_type, entity_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(user["user_id"]),
                str(action),
                entity_type,
                entity_id,
                details,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def scalar(query, params=()):
    with db_connection() as connection:
        row = connection.execute(query, params).fetchone()
    if not row:
        return 0
    if isinstance(row, dict):
        return next(iter(row.values()), 0)
    try:
        return row[0]
    except Exception:
        values = list(dict(row).values())
        return values[0] if values else 0


def dataframe(query, params=()):
    with db_connection() as connection:
        return query_dataframe(connection, query, params)


migrate_admin_schema()
bootstrap_super_admin()

# -----------------------------
# Authentication gate
# -----------------------------
if not admin_user():
    st.markdown(
        """
        <div class="lw-admin-hero">
            <h1>LeadWise Administrator</h1>
            <p>Authorized administrative access only</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sign_in_tab, request_tab = st.tabs(["Administrator Sign In", "Request Admin Access"])

    with sign_in_tab:
        st.info(
            "Sign in with an approved LeadWise administrator account. "
            "Pending requests cannot access the Control Center."
        )
        with st.form("admin_login"):
            email = st.text_input("Admin email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

        if submitted:
            user = authenticate_admin(email, password)
            if user:
                st.session_state["leadwise_admin_user"] = user
                log_admin_action("admin_login")
                st.rerun()
            else:
                st.error("Invalid credentials, inactive account, or administrator access has not been approved.")

    with request_tab:
        st.caption(
            "Submitting this form does not grant administrator access. "
            "A LeadWise Super Admin must approve the request."
        )
        with st.form("admin_access_request_form"):
            req_name = st.text_input("Full name *")
            req_email = st.text_input("Email *")
            req_position = st.text_input("Organization / Position (optional)")
            req_reason = st.text_area("Reason for requesting administrator access *")
            req_password = st.text_input("Create password *", type="password")
            req_confirm = st.text_input("Confirm password *", type="password")
            req_submit = st.form_submit_button("Submit Access Request", use_container_width=True)

        if req_submit:
            ok, message = create_admin_access_request(
                req_name, req_email, req_position, req_reason,
                req_password, req_confirm,
            )
            if ok:
                st.success(message)
            else:
                st.error(message)

    st.stop()

user = admin_user()

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("## LeadWise Admin")
    st.caption("Administrator Control Center")
    st.markdown(f"**{html.escape(user['full_name'])}**")
    st.caption(user["email"])
    st.caption("Super Admin" if user.get("role") == "super_admin" else "Admin")

    section = st.radio(
        "Administration",
        (
            [
                "Overview",
                "Usage Analytics",
                "Internal Operations",
                "Users",
                "Reader Insights",
                "Ask LeadWise",
                "Inbox",
                "Book Suggestions",
                "Catalog Management",
        "Featured Reading",
                "Admin Management",
                "System Monitoring",
            ]
            if user.get("role") == "super_admin"
            else [
                "Overview",
                "Usage Analytics",
                "Internal Operations",
                "Users",
                "Reader Insights",
                "Ask LeadWise",
                "Inbox",
                "Book Suggestions",
                "Catalog Management",
                "System Monitoring",
            ]
        ),
        label_visibility="collapsed",
    )

    st.markdown("---")
    if st.button("Sign Out", use_container_width=True):
        log_admin_action("admin_logout")
        st.session_state.pop("leadwise_admin_user", None)
        st.rerun()

st.markdown(
    """
    <div class="lw-admin-hero">
        <h1>LeadWise Administrator Control Center</h1>
        <p>Operations · Reader activity · Community · Support · Catalog</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Overview
# -----------------------------
if section == "Overview":
    total_users = scalar("SELECT COUNT(*) FROM users WHERE role = 'reader'")
    active_users = scalar("SELECT COUNT(*) FROM users WHERE role = 'reader' AND is_active = 1")
    published_reviews = scalar("SELECT COUNT(*) FROM user_reviews WHERE is_published = 1")
    new_inquiries = scalar("SELECT COUNT(*) FROM leadwise_inquiries WHERE status = 'New'")
    chatbot_queries = scalar("SELECT COUNT(*) FROM ask_leadwise_queries")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Readers", f"{total_users:,}")
    c2.metric("Active Readers", f"{active_users:,}")
    c3.metric("Published Reviews", f"{published_reviews:,}")
    c4.metric("New Inbox", f"{new_inquiries:,}")
    c5.metric("Ask LeadWise Queries", f"{chatbot_queries:,}")

    st.subheader("Operational snapshot")
    left, right = st.columns(2)

    with left:
        st.markdown("**Recent inquiries**")
        recent = dataframe(
            """
            SELECT inquiry_id, inquiry_type, full_name, subject, status, created_at
            FROM leadwise_inquiries
            ORDER BY inquiry_id DESC
            LIMIT 8
            """
        )
        st.dataframe(recent, use_container_width=True, hide_index=True)

    with right:
        st.markdown("**Ask LeadWise intents**")
        intents = dataframe(
            """
            SELECT intent, COUNT(*) AS queries
            FROM ask_leadwise_queries
            GROUP BY intent
            ORDER BY queries DESC
            """
        )
        st.dataframe(intents, use_container_width=True, hide_index=True)

elif section == "Usage Analytics":
    st.subheader("Usage Analytics")
    st.caption(
        "Privacy-conscious product analytics. Private notes, takeaways, application plans "
        "and passwords are not stored as analytics events."
    )

    total_events = scalar("SELECT COUNT(*) FROM leadwise_events")
    sessions = scalar("SELECT COUNT(DISTINCT session_id) FROM leadwise_events")
    signed_in_users = scalar("SELECT COUNT(DISTINCT user_id) FROM leadwise_events WHERE user_id IS NOT NULL")
    page_views = scalar("SELECT COUNT(*) FROM leadwise_events WHERE event_type = 'page_view'")
    assistant_queries = scalar("SELECT COUNT(*) FROM leadwise_events WHERE event_type = 'ask_leadwise_query'")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Tracked Events", f"{total_events:,}")
    c2.metric("Sessions", f"{sessions:,}")
    c3.metric("Active Signed-in Readers", f"{signed_in_users:,}")
    c4.metric("Page Views", f"{page_views:,}")
    c5.metric("Ask LeadWise", f"{assistant_queries:,}")

    st.markdown("### Feature usage")
    feature_usage = dataframe("""
        SELECT event_type, COUNT(*) AS events,
               COUNT(DISTINCT session_id) AS sessions,
               COUNT(DISTINCT user_id) AS signed_in_readers
        FROM leadwise_events
        GROUP BY event_type
        ORDER BY events DESC
    """)
    st.dataframe(feature_usage, use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("### Page activity")
        pages = dataframe("""
            SELECT COALESCE(page, 'Unknown') AS page,
                   COUNT(*) AS events,
                   COUNT(DISTINCT session_id) AS sessions
            FROM leadwise_events
            WHERE event_type = 'page_view'
            GROUP BY page
            ORDER BY events DESC
        """)
        st.dataframe(pages, use_container_width=True, hide_index=True)

    with right:
        st.markdown("### Ask LeadWise usage")
        ask_usage = dataframe("""
            SELECT intent, COUNT(*) AS questions,
                   COUNT(DISTINCT user_id) AS signed_in_readers
            FROM ask_leadwise_queries
            GROUP BY intent
            ORDER BY questions DESC
        """)
        st.dataframe(ask_usage, use_container_width=True, hide_index=True)

    st.markdown("### Recent events")
    recent_events = dataframe("""
        SELECT event_id, user_id, session_id, event_type, page,
               book_id, related_book_id, created_at
        FROM leadwise_events
        ORDER BY event_id DESC
        LIMIT 200
    """)
    st.dataframe(recent_events, use_container_width=True, hide_index=True)

    st.info(
        "The central event layer is active. Additional recommendation, book-view, "
        "comparison and library-action events will be connected as those UI actions "
        "are upgraded."
    )

elif section == "Internal Operations":
    st.subheader("Internal Operations")
    st.caption("Operational analytics derived from the LeadWise administrator audit trail.")

    total_actions = scalar("SELECT COUNT(*) FROM admin_audit_log")
    books_added = scalar("SELECT COUNT(*) FROM admin_audit_log WHERE action='catalog_book_added'")
    books_edited = scalar("""
        SELECT COUNT(*) FROM admin_audit_log
        WHERE action IN ('catalog_book_edited','catalog_book_updated')
    """)
    admin_changes = scalar("""
        SELECT COUNT(*) FROM admin_audit_log
        WHERE action LIKE 'administrator_%' OR action LIKE 'admin_request_%'
    """)
    active_admins = scalar("""
        SELECT COUNT(*) FROM users
        WHERE role IN ('admin','super_admin') AND is_active=1
          AND COALESCE(admin_account_status,'Active')='Active'
    """)

    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("Admin Actions",f"{total_actions:,}")
    c2.metric("Books Added",f"{books_added:,}")
    c3.metric("Books Edited",f"{books_edited:,}")
    c4.metric("Access Changes",f"{admin_changes:,}")
    c5.metric("Active Administrators",f"{active_admins:,}")

    overview_tab, people_tab, catalog_ops_tab, audit_tab = st.tabs(
        ["Activity Overview","Administrator Activity","Catalog Changes","Audit Trail"]
    )

    with overview_tab:
        action_summary=dataframe("""
            SELECT action, COUNT(*) AS actions,
                   COUNT(DISTINCT admin_user_id) AS administrators
            FROM admin_audit_log
            GROUP BY action
            ORDER BY actions DESC, action
        """)
        st.dataframe(action_summary,use_container_width=True,hide_index=True)


        st.markdown("#### Catalog Retirement Analytics")

        # 18.58.1: backend-neutral retirement reason parsing.
        # The previous SQL used SQLite instr(), which is not available in PostgreSQL.
        retirement_details = dataframe("""
            SELECT details
            FROM admin_audit_log
            WHERE action='catalog_book_retired'
        """)

        if retirement_details.empty:
            retirement_summary = pd.DataFrame(
                columns=["retirement_reason", "retired_books"]
            )
        else:
            def _retirement_reason_from_details(value):
                details_text = str(value or "")

                if "reason_category=" in details_text:
                    reason = details_text.split("reason_category=", 1)[1]
                    reason = reason.split(";", 1)[0].strip()
                    return reason or "Not Recorded"

                if "reason=" in details_text:
                    return "Legacy / Unstructured"

                return "Not Recorded"

            retirement_details["retirement_reason"] = (
                retirement_details["details"]
                .apply(_retirement_reason_from_details)
            )

            retirement_summary = (
                retirement_details
                .groupby("retirement_reason", dropna=False)
                .size()
                .reset_index(name="retired_books")
                .sort_values(
                    ["retired_books", "retirement_reason"],
                    ascending=[False, True],
                )
                .reset_index(drop=True)
            )

        if retirement_summary.empty:
            st.caption("No approved book retirements have been recorded yet.")
        else:
            st.dataframe(retirement_summary, use_container_width=True, hide_index=True)

        pending_retirements = scalar("""
            SELECT COUNT(*) FROM catalog_change_requests
            WHERE action_type='Retire' AND status='Pending'
        """)
        approved_retirements = scalar("""
            SELECT COUNT(*) FROM catalog_change_requests
            WHERE action_type='Retire' AND status='Approved'
        """)
        rejected_retirements = scalar("""
            SELECT COUNT(*) FROM catalog_change_requests
            WHERE action_type='Retire' AND status='Rejected'
        """)
        r1,r2,r3=st.columns(3)
        r1.metric("Pending Retirement Requests", f"{pending_retirements:,}")
        r2.metric("Approved Retirement Requests", f"{approved_retirements:,}")
        r3.metric("Rejected Retirement Requests", f"{rejected_retirements:,}")

    with people_tab:
        people=dataframe("""
            SELECT COALESCE(u.full_name,'Former / unavailable administrator') AS administrator,
                   u.role,
                   COALESCE(u.admin_account_status,'Active') AS account_status,
                   COUNT(a.audit_id) AS recorded_actions,
                   MAX(a.created_at) AS last_recorded_action
            FROM users u
            LEFT JOIN admin_audit_log a ON a.admin_user_id=u.user_id
            WHERE u.role IN ('admin','super_admin')
            GROUP BY u.user_id,u.full_name,u.role,u.admin_account_status
            ORDER BY recorded_actions DESC
        """)
        st.dataframe(people,use_container_width=True,hide_index=True)

    with catalog_ops_tab:
        catalog_changes=dataframe("""
            SELECT a.audit_id,
                   COALESCE(u.full_name,'Former / unavailable administrator') AS administrator,
                   a.action, a.entity_id AS book_id, a.details, a.created_at
            FROM admin_audit_log a
            LEFT JOIN users u ON u.user_id=a.admin_user_id
            WHERE a.entity_type='book'
            ORDER BY a.audit_id DESC
            LIMIT 1000
        """)
        st.dataframe(catalog_changes,use_container_width=True,hide_index=True)

    with audit_tab:
        audit=dataframe("""
            SELECT a.audit_id,
                   COALESCE(u.full_name,'Former / unavailable administrator') AS administrator,
                   u.role, a.action, a.entity_type, a.entity_id, a.details, a.created_at
            FROM admin_audit_log a
            LEFT JOIN users u ON u.user_id=a.admin_user_id
            ORDER BY a.audit_id DESC
            LIMIT 1500
        """)
        st.dataframe(audit,use_container_width=True,hide_index=True)

elif section == "Users":
    st.subheader("Users")
    st.caption("Administrative account monitoring. Private reading notes are not exposed here.")
    users = dataframe(
        """
        SELECT u.user_id, u.full_name, u.email, u.role, u.is_active, u.created_at,
               COUNT(DISTINCT l.library_id) AS saved_books,
               COUNT(DISTINCT CASE WHEN r.is_published = 1 THEN r.review_id END) AS published_reviews
        FROM users u
        LEFT JOIN user_library l ON l.user_id = u.user_id
        LEFT JOIN user_reviews r ON r.user_id = u.user_id
        GROUP BY u.user_id
        ORDER BY u.user_id DESC
        """
    )
    st.dataframe(users, use_container_width=True, hide_index=True)

elif section == "Reader Insights":
    st.subheader("Published Reader Insights")
    st.caption("Only published community reviews are shown. Private reflections are excluded.")
    reviews = dataframe(
        """
        SELECT r.review_id, r.book_id, u.full_name, r.rating, r.review_text,
               r.published_at, r.updated_at
        FROM user_reviews r
        JOIN users u ON u.user_id = r.user_id
        WHERE r.is_published = 1
        ORDER BY COALESCE(r.published_at, r.updated_at) DESC
        """
    )
    st.dataframe(reviews, use_container_width=True, hide_index=True)

elif section == "Ask LeadWise":
    st.subheader("Ask LeadWise Analytics")
    st.caption("Operational query analytics from the reader-facing assistant.")
    intents = dataframe(
        """
        SELECT intent, COUNT(*) AS query_count,
               COUNT(DISTINCT user_id) AS signed_in_readers
        FROM ask_leadwise_queries
        GROUP BY intent
        ORDER BY query_count DESC
        """
    )
    st.dataframe(intents, use_container_width=True, hide_index=True)

    st.markdown("**Recent queries**")
    queries = dataframe(
        """
        SELECT query_id, user_id, query_text, intent, result_count, created_at
        FROM ask_leadwise_queries
        ORDER BY query_id DESC
        LIMIT 100
        """
    )
    st.dataframe(queries, use_container_width=True, hide_index=True)

elif section == "Inbox":
    st.subheader("LeadWise Inbox")
    st.caption(
        "Review reader inquiries, reply by email, track response history, "
        "and manage inquiry status."
    )

    inbox_notice = st.session_state.pop("leadwise_inbox_notice", None)
    if inbox_notice:
        st.success(inbox_notice)

    inbox = dataframe(
        """
        SELECT inquiry_id, inquiry_type, full_name, email, subject, message,
               related_book_id, status, created_at, replied_at, replied_by
        FROM leadwise_inquiries
        WHERE inquiry_type <> 'Suggest a Book'
        ORDER BY inquiry_id DESC
        """
    )

    if inbox.empty:
        st.info("There are no reader inquiries in the Inbox.")
    else:
        inbox_display = inbox[
            [
                "inquiry_id",
                "inquiry_type",
                "full_name",
                "email",
                "subject",
                "status",
                "created_at",
                "replied_at",
            ]
        ].copy()
        st.dataframe(inbox_display, use_container_width=True, hide_index=True)

        inquiry_ids = inbox["inquiry_id"].astype(int).tolist()
        selected_inquiry_id = st.selectbox(
            "Open inquiry",
            inquiry_ids,
            format_func=lambda inquiry_id: (
                f"#{inquiry_id} · "
                + str(
                    inbox.loc[
                        inbox["inquiry_id"].astype(int) == int(inquiry_id),
                        "subject",
                    ].iloc[0]
                    or "No subject"
                )
            ),
            key="leadwise_inbox_selected_inquiry",
        )

        selected_row = inbox[
            inbox["inquiry_id"].astype(int) == int(selected_inquiry_id)
        ].iloc[0]
        inquiry = selected_row.to_dict()

        st.markdown("### Inquiry")
        with st.container(border=True):
            meta1, meta2, meta3 = st.columns(3)
            meta1.markdown(
                "**Type:** "
                + html.escape(str(inquiry.get("inquiry_type") or ""))
            )
            meta2.markdown(
                "**Status:** "
                + html.escape(str(inquiry.get("status") or ""))
            )
            meta3.markdown(
                "**Received:** "
                + html.escape(str(inquiry.get("created_at") or ""))
            )

            st.markdown(
                "**From:** "
                + html.escape(str(inquiry.get("full_name") or "Guest"))
            )
            st.markdown(
                "**Email:** "
                + html.escape(str(inquiry.get("email") or "Not provided"))
            )
            st.markdown(
                "**Subject:** "
                + html.escape(str(inquiry.get("subject") or "No subject"))
            )
            st.markdown("**Message**")
            st.write(str(inquiry.get("message") or ""))

        st.markdown("### Reply history")
        reply_history = dataframe(
            """
            SELECT r.reply_id,
                   COALESCE(u.full_name, 'Former / unavailable administrator')
                       AS administrator,
                   r.reply_message,
                   r.sent_to_email,
                   r.delivery_status,
                   r.external_message_id,
                   r.created_at,
                   r.sent_at
            FROM leadwise_inquiry_replies r
            LEFT JOIN users u ON u.user_id = r.admin_user_id
            WHERE r.inquiry_id=?
            ORDER BY r.reply_id DESC
            """,
            (int(selected_inquiry_id),),
        )

        if reply_history.empty:
            st.caption("No Admin replies have been recorded for this inquiry.")
        else:
            for _, reply in reply_history.iterrows():
                with st.container(border=True):
                    h1, h2, h3 = st.columns([1.5, 1, 1.5])
                    h1.markdown(
                        "**Admin:** "
                        + html.escape(str(reply["administrator"]))
                    )
                    h2.markdown(
                        "**Status:** "
                        + html.escape(str(reply["delivery_status"]))
                    )
                    h3.markdown(
                        "**Sent:** "
                        + html.escape(
                            str(reply["sent_at"] or reply["created_at"])
                        )
                    )
                    st.write(str(reply["reply_message"] or ""))
                    if str(reply.get("external_message_id") or "").strip():
                        st.caption(
                            "Provider message ID: "
                            + str(reply["external_message_id"])
                        )

        st.markdown("### Respond")
        recipient_email = str(inquiry.get("email") or "").strip()
        email_settings = _leadwise_email_settings()

        if not _valid_email_address(recipient_email):
            st.warning(
                "This inquiry does not contain a valid email address, so LeadWise "
                "cannot send an external reply."
            )
        elif not email_settings["configured"]:
            st.warning(
                "Email delivery is not configured yet. Add RESEND_API_KEY and "
                "LEADWISE_REPLY_FROM_EMAIL to the Admin Streamlit secrets. "
                "LEADWISE_REPLY_FROM_NAME is optional."
            )
        else:
            st.caption(
                "Reply delivery is configured. The API key remains in Streamlit "
                "Secrets and is never displayed in the Admin interface."
            )

        with st.form(
            f"leadwise_inquiry_reply_form_{int(selected_inquiry_id)}",
            clear_on_submit=True,
        ):
            reply_message = st.text_area(
                "Reply",
                placeholder="Write the response that will be emailed to the reader...",
                height=180,
            )
            send_reply = st.form_submit_button(
                "Send Reply",
                use_container_width=True,
            )

        if send_reply:
            if not str(reply_message or "").strip():
                st.warning("Enter a reply before sending.")
            else:
                ok, external_id, send_message, attempted = send_inquiry_reply_email(
                    inquiry,
                    reply_message,
                )

                if attempted:
                    record_inquiry_reply(
                        selected_inquiry_id,
                        reply_message,
                        recipient_email,
                        "Sent" if ok else "Failed",
                        external_id,
                    )

                if ok:
                    st.session_state["leadwise_inbox_notice"] = (
                        f"Reply sent to {recipient_email}. Inquiry marked Replied."
                    )
                    st.rerun()
                else:
                    st.error(send_message)

        with st.expander("Update inquiry status", expanded=False):
            status_options = ["New", "In Progress", "Replied", "Closed"]
            current_status = str(inquiry.get("status") or "New")
            default_status_index = (
                status_options.index(current_status)
                if current_status in status_options
                else 0
            )
            new_status = st.selectbox(
                "Status",
                status_options,
                index=default_status_index,
                key=f"inquiry_status_{int(selected_inquiry_id)}",
            )
            if st.button(
                "Update Status",
                key=f"update_inquiry_status_{int(selected_inquiry_id)}",
                use_container_width=True,
            ):
                ok, status_message = update_inquiry_status(
                    selected_inquiry_id,
                    new_status,
                )
                if ok:
                    st.session_state["leadwise_inbox_notice"] = status_message
                    st.rerun()
                else:
                    st.error(status_message)

elif section == "Book Suggestions":
    st.subheader("Book Suggestions")
    suggestions = dataframe(
        """
        SELECT inquiry_id, full_name, email, suggested_title, suggested_author,
               suggested_isbn_or_link, message, status, created_at
        FROM leadwise_inquiries
        WHERE inquiry_type = 'Suggest a Book'
        ORDER BY inquiry_id DESC
        """
    )
    st.dataframe(suggestions, use_container_width=True, hide_index=True)

elif section == "Catalog Management":
    st.subheader("Catalog Management")
    st.caption(
        "Governed catalog administration. Every Add, Edit, Publish, Hide, Archive, "
        "Restore or Retire action is submitted to the Approval Center first. "
        "No catalog mutation is applied until a Super Admin explicitly approves it."
    )

    frozen_catalog, frozen_path = load_frozen_catalog()

    # Catalog Management headline KPIs
    # Published Catalog = original books still effectively Published
    #                     + approved Admin-added books currently Published.
    frozen_removed_count = scalar("""
        SELECT COUNT(*)
        FROM catalog_book_overrides
        WHERE catalog_status IN ('Hidden','Archived')
    """)
    published_admin_added_count = scalar("""
        SELECT COUNT(*)
        FROM live_catalog_books
        WHERE catalog_status='Published'
    """)
    removed_admin_added_count = scalar("""
        SELECT COUNT(*)
        FROM live_catalog_books
        WHERE catalog_status IN ('Hidden','Archived')
    """)
    pending_catalog_requests = scalar(
        "SELECT COUNT(*) FROM catalog_change_requests WHERE status='Pending'"
    )

    published_catalog_count = (
        len(frozen_catalog)
        - frozen_removed_count
        + published_admin_added_count
    )
    removed_catalog_count = (
        frozen_removed_count
        + removed_admin_added_count
    )

    k1,k2,k3 = st.columns(3)
    k1.metric("Published Catalog", f"{published_catalog_count:,}")
    k2.metric("Awaiting Approval", f"{pending_catalog_requests:,}")
    k3.metric("Removed Catalog", f"{removed_catalog_count:,}")

    st.info(
        "Governance rule: submitting a form creates a Pending request only. "
        "The Reader App and live catalog change only after approval."
    )

    catalog_tab, add_tab, lifecycle_tab, processing_tab, approval_center_tab, activity_tab = st.tabs(
        ["Catalog", "Request New Book", "Lifecycle Requests",
         "Recommendation Processing", "Approval Center", "Catalog Activity"]
    )

    # ---------------------------------------------------------
    # CATALOG: edits are requests; nothing is changed directly.
    # ---------------------------------------------------------
    with catalog_tab:
        st.markdown("### Catalog - Published Books")
        st.caption(
            "View, search, copy, and request edits for all currently published LeadWise books, "
            "including approved newly added books."
        )

        if frozen_catalog.empty:
            st.error(f"Base catalog could not be found at {frozen_path}.")
        else:
            # ---------------------------------------------------------
            # Build effective published catalog.
            # ---------------------------------------------------------
            frozen_effective = frozen_catalog.copy()

            def first_catalog_series(frame, candidates):
                result = pd.Series("", index=frame.index, dtype="object")
                for col in candidates:
                    if col in frame.columns:
                        values = frame[col].fillna("").astype(str).str.strip()
                        result = result.where(result.astype(str).str.strip().ne(""), values)
                return result

            if "book_id" not in frozen_effective.columns:
                frozen_effective["book_id"] = ""

            frozen_effective["_catalog_title"] = first_catalog_series(
                frozen_effective, ["display_title","canonical_title","title","Title"]
            )
            frozen_effective["_catalog_authors"] = first_catalog_series(
                frozen_effective, ["display_authors","authors","author","Authors"]
            )
            frozen_effective["_catalog_publisher"] = first_catalog_series(
                frozen_effective, ["display_publisher","publisher"]
            )
            frozen_effective["_catalog_year"] = first_catalog_series(
                frozen_effective, ["publication_year","year"]
            )
            frozen_effective["_isbn10"] = first_catalog_series(
                frozen_effective, ["isbn10","display_isbn10","isbn_10"]
            )
            frozen_effective["_isbn13"] = first_catalog_series(
                frozen_effective, ["isbn13","display_isbn13","isbn_13"]
            )
            frozen_effective["_categories"] = first_catalog_series(
                frozen_effective, ["display_categories","categories","category","subjects"]
            )
            frozen_effective["_language"] = first_catalog_series(
                frozen_effective, ["display_language","language"]
            )
            frozen_effective["_record_type"] = "Frozen"

            # Apply approved frozen-book overrides and exclude frozen books whose
            # approved lifecycle status is not Published.
            overrides = dataframe("""
                SELECT * FROM catalog_book_overrides
            """)
            override_map = (
                {str(row["book_id"]): row.to_dict() for _,row in overrides.iterrows()}
                if not overrides.empty else {}
            )

            frozen_rows = []
            for _,row in frozen_effective.iterrows():
                item = row.to_dict()
                bid = str(item.get("book_id",""))
                ov = override_map.get(bid)
                effective_status = "Published"
                if ov:
                    effective_status = str(ov.get("catalog_status") or "Published")
                    if effective_status == "Published":
                        field_map = {
                            "_catalog_title":"title",
                            "_catalog_authors":"authors",
                            "_catalog_publisher":"publisher",
                            "_catalog_year":"publication_year",
                            "_isbn10":"isbn10",
                            "_isbn13":"isbn13",
                            "_categories":"categories",
                            "_language":"language",
                        }
                        for target,source in field_map.items():
                            value = str(ov.get(source) or "").strip()
                            if value:
                                item[target] = value
                if effective_status == "Published":
                    item["_catalog_status"] = "Published"
                    frozen_rows.append(item)

            effective_frozen = pd.DataFrame(frozen_rows)

            # Approved Admin-added books only enter this Published Catalog once
            # the approval workflow has created/published them.
            published_live = dataframe("""
                SELECT *
                FROM live_catalog_books
                WHERE catalog_status='Published'
                ORDER BY live_book_id DESC
            """)

            live_rows = []
            if not published_live.empty:
                for _,row in published_live.iterrows():
                    item = row.to_dict()
                    live_rows.append({
                        "book_id": str(item.get("book_id","")),
                        "_catalog_title": str(item.get("title","") or ""),
                        "_catalog_authors": str(item.get("authors","") or ""),
                        "_catalog_publisher": str(item.get("publisher","") or ""),
                        "_catalog_year": str(item.get("publication_year","") or ""),
                        "_isbn10": str(item.get("isbn10","") or ""),
                        "_isbn13": str(item.get("isbn13","") or ""),
                        "_categories": str(item.get("categories","") or ""),
                        "_language": str(item.get("language","") or ""),
                        "_record_type": "Admin Added",
                        "_catalog_status": "Published",
                    })
            effective_live = pd.DataFrame(live_rows)

            catalog_parts = []
            if not effective_frozen.empty:
                catalog_parts.append(effective_frozen)
            if not effective_live.empty:
                catalog_parts.append(effective_live)

            published_catalog = (
                pd.concat(catalog_parts,ignore_index=True,sort=False)
                if catalog_parts else pd.DataFrame()
            )

            original_published = len(effective_frozen)
            approved_new_published = len(effective_live)
            total_published = len(published_catalog)

            # Published-catalog operational KPIs.
            # "Removed from Publication" counts catalog records whose approved
            # effective lifecycle status is Hidden or Archived.
            removed_frozen = 0
            if not overrides.empty and "catalog_status" in overrides.columns:
                removed_frozen = int(
                    overrides["catalog_status"]
                    .fillna("")
                    .astype(str)
                    .isin(["Hidden", "Archived"])
                    .sum()
                )

            removed_live_df = dataframe("""
                SELECT COUNT(*) AS removed_count
                FROM live_catalog_books
                WHERE catalog_status IN ('Hidden','Archived')
            """)
            removed_live = (
                int(removed_live_df.iloc[0]["removed_count"])
                if not removed_live_df.empty else 0
            )
            removed_from_publication = removed_frozen + removed_live



            q = st.text_input(
                "Search published catalog",
                placeholder="Enter title, author, Book ID, ISBN or publisher",
                key="published_catalog_search",
            ).strip().lower()

            if published_catalog.empty:
                matches = published_catalog
            else:
                search_blob = (
                    published_catalog["book_id"].fillna("").astype(str) + " " +
                    published_catalog["_catalog_title"].fillna("").astype(str) + " " +
                    published_catalog["_catalog_authors"].fillna("").astype(str) + " " +
                    published_catalog["_catalog_publisher"].fillna("").astype(str) + " " +
                    published_catalog["_isbn10"].fillna("").astype(str) + " " +
                    published_catalog["_isbn13"].fillna("").astype(str)
                )
                matches = published_catalog[
                    search_blob.str.lower().str.contains(q,regex=False,na=False)
                ] if q else published_catalog.copy()

            st.caption(
                f"Showing {len(matches):,} matching published book(s) "
                f"from {total_published:,} currently published records."
            )

            if matches.empty:
                st.info("No published books match the current search.")
            else:
                preview_table = pd.DataFrame({
                    "Book ID": matches["book_id"].fillna("").astype(str),
                    "Title": matches["_catalog_title"].fillna("").astype(str),
                    "Author(s)": matches["_catalog_authors"].fillna("").astype(str),
                    "Publisher": matches["_catalog_publisher"].fillna("").astype(str),
                    "Publication Year": matches["_catalog_year"].fillna("").astype(str),
                    "ISBN-10": matches["_isbn10"].fillna("").astype(str),
                    "ISBN-13": matches["_isbn13"].fillna("").astype(str),
                    "Categories": matches["_categories"].fillna("").astype(str),
                    "Language": matches["_language"].fillna("").astype(str),
                    "Catalog Source": matches["_record_type"].fillna("").astype(str),
                    "Status": "Published",
                }).head(250)

                st.markdown("#### Published Catalog Preview")
                st.caption(
                    "This copy-friendly preview includes both original published books "
                    "and approved new published books."
                )
                st.dataframe(
                    preview_table,
                    use_container_width=True,
                    hide_index=True,
                    height=360,
                )

                selectable = matches.head(250)
                selected_id = st.selectbox(
                    "Select published book to view or edit",
                    selectable["book_id"].astype(str).tolist(),
                    format_func=lambda bid: (
                        f"{bid} · " +
                        str(selectable.loc[
                            selectable["book_id"].astype(str).eq(bid),
                            "_catalog_title"
                        ].iloc[0])
                    ),
                    key="published_catalog_select",
                )
                selected_row = selectable[
                    selectable["book_id"].astype(str).eq(selected_id)
                ].iloc[0]
                selected_type = str(selected_row["_record_type"])

                if selected_type == "Admin Added":
                    defaults = current_live_book(selected_id)
                    record_type = "Admin Added"
                else:
                    source_row = frozen_catalog[
                        frozen_catalog["book_id"].astype(str).eq(selected_id)
                    ].iloc[0]
                    base = frozen_book_to_edit_record(source_row)
                    override = get_catalog_override(selected_id)
                    defaults = dict(base)
                    if override:
                        for k,v in override.items():
                            if k in defaults and v is not None:
                                defaults[k] = v
                    record_type = "Frozen"

                st.markdown("#### Selected Book Preview")
                st.caption(
                    f"Current book metadata is shown "
                    "for reference and copying."
                )
                selected_preview = pd.DataFrame([{
                    "Book ID": selected_id,
                    "Title": defaults.get("title",""),
                    "Author(s)": defaults.get("authors",""),
                    "Publisher": defaults.get("publisher",""),
                    "Publication Date": defaults.get("publication_date",""),
                    "Publication Year": defaults.get("publication_year",""),
                    "ISBN-10": defaults.get("isbn10",""),
                    "ISBN-13": defaults.get("isbn13",""),
                    "Page Count": defaults.get("page_count",""),
                    "Categories": defaults.get("categories",""),
                    "Language": defaults.get("language",""),
                    "Source Type": defaults.get("source_type",""),
                    "Source Rating": defaults.get("source_rating",""),
                    "Rating Count": defaults.get("source_rating_count",""),
                    "Catalog Source": selected_type,
                    "Status": defaults.get("catalog_status","Published"),
                }])
                st.dataframe(
                    selected_preview,use_container_width=True,hide_index=True
                )

                with st.expander("Copy synopsis / description and URLs",expanded=False):
                    st.text_area(
                        "Synopsis / Description — copy reference",
                        value=str(defaults.get("description","") or ""),
                        height=150,
                        key=f"copy_description_{selected_id}_{selected_type}",
                    )
                    st.text_input(
                        "Cover URL — copy reference",
                        value=str(defaults.get("cover_url","") or ""),
                        key=f"copy_cover_{selected_id}_{selected_type}",
                    )
                    st.text_input(
                        "Source URL — copy reference",
                        value=str(defaults.get("source_url","") or ""),
                        key=f"copy_source_{selected_id}_{selected_type}",
                    )

                st.markdown("#### Request an edit")
                edit_reason = st.text_area(
                    "Reason for requested edit *",
                    placeholder="Explain what should be corrected or updated.",
                    key=f"published_edit_reason_{selected_id}_{selected_type}",
                    height=90,
                )
                with st.form(f"published_edit_form_{selected_id}_{selected_type}"):
                    edited = catalog_form(
                        f"published_edit_{selected_id}_{selected_type}",
                        defaults,
                        new_book=(selected_type=="Admin Added"),
                    )
                    submit_edit = st.form_submit_button(
                        "Submit Edit for Approval",
                        use_container_width=True,
                    )

                if submit_edit:
                    edited["book_id"] = selected_id
                    reason = str(edit_reason or "").strip()
                    if not edited["title"].strip():
                        st.error("Title is required.")
                    elif not reason:
                        st.error("A reason is required before submitting an edit request.")
                    else:
                        ok,msg = submit_catalog_change_request(
                            selected_id,record_type,"Edit",
                            defaults,edited,reason
                        )
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()



    # ---------------------------------------------------------
    # ADD: request first. No Draft/live row is created yet.
    # ---------------------------------------------------------
    with add_tab:
        st.markdown("### Request a new book")
        st.caption(
            "A new book does not enter the live catalog at submission time. "
            "It is created only when the request is approved."
        )

        addition_reason = st.text_area(
            "Reason for adding this book *",
            placeholder=(
                "Explain why this book should be included in LeadWise "
                "(for example: catalog gap, reader request, leadership relevance)."
            ),
            key="new_book_reason",
            height=90,
        )

        with st.form("add_new_book_form"):
            new_record = catalog_form(
                "new_book", {"catalog_status":"Published"}, new_book=True
            )
            submit_add = st.form_submit_button(
                "Submit New Book for Approval", use_container_width=True
            )

        if submit_add:
            reason = str(addition_reason or "").strip()
            if not new_record["title"].strip():
                st.error("Title is required.")
            elif not reason:
                st.error("A reason for adding the book is required.")
            else:
                new_id = next_admin_book_id()
                proposed = dict(new_record)
                proposed["catalog_status"] = "Published"
                proposed["intelligence_status"] = "Needs Processing"
                ok,msg = submit_catalog_change_request(
                    new_id,"Admin Added","Add",{},proposed,reason
                )
                (st.success if ok else st.error)(msg)
                if ok:
                    st.info(
                        f"{new_id} is reserved for this request. The book does not yet exist "
                        "in the live Reader catalog. Approval will create it as Published."
                    )
                    st.rerun()

    # ---------------------------------------------------------
    # LIFECYCLE: every state change and retirement is a request.
    # ---------------------------------------------------------
    with lifecycle_tab:
        st.markdown("### Lifecycle Requests")
        st.caption(
            "Request publication, withdrawal, restoration or retirement. "
            "The current live status remains unchanged while the request is Pending."
        )

        lifecycle_books = dataframe("""
            SELECT book_id,title,authors,catalog_status,intelligence_status,
                   'Admin Added' AS record_type,updated_at
            FROM live_catalog_books
            ORDER BY updated_at DESC
        """)

        if lifecycle_books.empty:
            st.info("No approved Admin-added books are available for lifecycle management.")
        else:
            status_filter = st.radio(
                "Current status",
                ["All","Draft","Published","Hidden","Archived"],
                horizontal=True,
                key="catalog_status_filter",
            )
            status_search = st.text_input(
                "Search Book ID, title or author",
                key="catalog_status_search",
            ).strip().lower()

            status_books = lifecycle_books.copy()
            if status_filter != "All":
                status_books = status_books[
                    status_books["catalog_status"].astype(str).eq(status_filter)
                ]
            if status_search and not status_books.empty:
                blob = (
                    status_books["book_id"].fillna("").astype(str) + " " +
                    status_books["title"].fillna("").astype(str) + " " +
                    status_books["authors"].fillna("").astype(str)
                ).str.lower()
                status_books = status_books[
                    blob.str.contains(status_search,regex=False,na=False)
                ]

            if status_books.empty:
                st.info("No books match the current lifecycle filters.")
            else:
                st.dataframe(
                    status_books[
                        ["book_id","title","authors","catalog_status",
                         "intelligence_status","updated_at"]
                    ],
                    use_container_width=True,hide_index=True
                )

                selected_status_book = st.selectbox(
                    "Select book",
                    status_books["book_id"].astype(str).tolist(),
                    format_func=lambda bid: (
                        f"{bid} · " +
                        str(status_books.loc[
                            status_books["book_id"].astype(str).eq(bid),"title"
                        ].iloc[0])
                    ),
                    key="catalog_status_book",
                )
                selected = status_books[
                    status_books["book_id"].astype(str).eq(selected_status_book)
                ].iloc[0]
                current = str(selected["catalog_status"])
                before = current_live_book(selected_status_book)

                c1,c2 = st.columns(2)
                c1.markdown(f"**Current status:** {current}")
                c2.markdown(
                    f"**Intelligence:** {selected['intelligence_status']}"
                )

                lifecycle_reason = st.text_area(
                    "Reason for lifecycle request *",
                    placeholder="Explain why this status change is required.",
                    key="catalog_status_reason",
                    height=80,
                )

                def submit_lifecycle(action_name,target_status):
                    reason = str(lifecycle_reason or "").strip()
                    if not reason:
                        st.error("A reason is required for every lifecycle request.")
                        return
                    proposed = dict(before)
                    proposed["catalog_status"] = target_status
                    ok,msg = submit_catalog_change_request(
                        selected_status_book,"Admin Added",action_name,
                        before,proposed,reason
                    )
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()

                action_cols = st.columns(4)
                if action_cols[0].button(
                    "Request Publish",
                    disabled=(current=="Published"),
                    use_container_width=True,key="catalog_publish"
                ):
                    submit_lifecycle("Publish","Published")
                if action_cols[1].button(
                    "Request Draft",
                    disabled=(current=="Draft"),
                    use_container_width=True,key="catalog_draft"
                ):
                    submit_lifecycle("Draft","Draft")
                if action_cols[2].button(
                    "Request Hide",
                    disabled=(current=="Hidden"),
                    use_container_width=True,key="catalog_hide"
                ):
                    submit_lifecycle("Hide","Hidden")
                if action_cols[3].button(
                    "Request Archive",
                    disabled=(current=="Archived"),
                    use_container_width=True,key="catalog_archive"
                ):
                    submit_lifecycle("Archive","Archived")

                st.divider()
                st.markdown("#### Request retirement / removal")
                st.caption(
                    "LeadWise uses soft retirement rather than physical deletion. "
                    "The record and audit history are preserved, but an approved retirement "
                    "removes the book from the active reader catalog."
                )

                retirement_category = st.selectbox(
                    "Retirement reason *",
                    [
                        "Select a reason",
                        "Duplicate Book",
                        "Incorrect / Invalid Record",
                        "Copyright / Data Concern",
                        "Outdated Record",
                        "Test Record",
                        "Requested Data Correction",
                        "Catalog Quality Issue",
                        "Other",
                    ],
                    key="catalog_retire_reason_category",
                )
                retirement_explanation = st.text_area(
                    "Retirement explanation *",
                    placeholder=(
                        "Explain why this book should be removed. "
                        "This becomes part of the permanent approval and audit record."
                    ),
                    key="catalog_retire_explanation",
                    height=110,
                )

                if st.button(
                    "Submit Retirement for Approval",
                    use_container_width=True,key="catalog_retire"
                ):
                    category = str(retirement_category or "").strip()
                    explanation = str(retirement_explanation or "").strip()
                    if category == "Select a reason":
                        st.error("Select a retirement reason.")
                    elif not explanation:
                        st.error("A retirement explanation is required.")
                    else:
                        reason = f"{category}: {explanation}"
                        proposed = dict(before)
                        proposed["catalog_status"] = "Archived"
                        proposed["retirement_reason_category"] = category
                        proposed["retirement_explanation"] = explanation
                        ok,msg = submit_catalog_change_request(
                            selected_status_book,"Admin Added","Retire",
                            before,proposed,reason
                        )
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()

    # ---------------------------------------------------------
    # RECOMMENDATION PROCESSING HELPERS
    # ---------------------------------------------------------
    def _leadwise_vectorizer_path():
        candidates = [
            PROJECT_ROOT / "models" / "enriched_tfidf_vectorizer_streamlit.joblib",
            Path.cwd() / "models" / "enriched_tfidf_vectorizer_streamlit.joblib",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    FIELD_BOUNDARY = "zzfieldboundaryzz"

    def _ensure_recommendation_vector_table():
        with db_connection() as conn:
            if conn.backend == "postgresql":
                required = {
                    "recommendation_book_vectors": ADMIN_REQUIRED_SCHEMA["recommendation_book_vectors"],
                    "recommendation_processing_history": ADMIN_REQUIRED_SCHEMA["recommendation_processing_history"],
                    "live_catalog_books": ADMIN_REQUIRED_SCHEMA["live_catalog_books"],
                }
                problems = validate_required_schema(conn, required)
                if problems:
                    raise RuntimeError(
                        "LeadWise recommendation schema validation failed: "
                        + " | ".join(problems)
                    )
                return
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recommendation_book_vectors (
                    book_id TEXT PRIMARY KEY,
                    feature_indices_json TEXT NOT NULL,
                    feature_values_json TEXT NOT NULL,
                    feature_count INTEGER NOT NULL,
                    vector_norm REAL NOT NULL,
                    vectorizer_features INTEGER NOT NULL,
                    processed_at TEXT NOT NULL,
                    processing_status TEXT NOT NULL DEFAULT 'Ready',
                    processing_error TEXT,
                    vectorizer_version TEXT
                )
            """)

            vector_columns={r["name"] for r in conn.execute(
                "PRAGMA table_info(recommendation_book_vectors)"
            ).fetchall()}
            if "vectorizer_version" not in vector_columns:
                conn.execute(
                    "ALTER TABLE recommendation_book_vectors "
                    "ADD COLUMN vectorizer_version TEXT"
                )

            conn.execute("""
                CREATE TABLE IF NOT EXISTS recommendation_processing_history (
                    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    feature_count INTEGER,
                    vector_norm REAL,
                    vectorizer_features INTEGER,
                    vectorizer_version TEXT,
                    message TEXT,
                    processed_by INTEGER,
                    processed_at TEXT NOT NULL
                )
            """)
            # Older databases use intelligence_status; keep that as the canonical status field.
            columns={r["name"] for r in conn.execute(
                "PRAGMA table_info(live_catalog_books)"
            ).fetchall()}
            if "intelligence_status" not in columns:
                conn.execute(
                    "ALTER TABLE live_catalog_books "
                    "ADD COLUMN intelligence_status TEXT NOT NULL DEFAULT 'Needs Processing'"
                )
            conn.commit()

    def _book_processing_text(record):
        """Build production-compatible text from metadata actually stored for the book."""
        parts=[]
        for field in ["title","authors","description","categories","publisher"]:
            value=str(record.get(field,"") or "").strip()
            if value:
                parts.append(value)
        return f" {FIELD_BOUNDARY} ".join(parts)

    def _vectorizer_version_label(vectorizer, vectorizer_path):
        """Stable operational label for the production vectorizer artifact."""
        try:
            modified = datetime.fromtimestamp(
                vectorizer_path.stat().st_mtime, tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except Exception:
            modified = "unknown-date"
        features = len(getattr(vectorizer, "vocabulary_", {}) or {})
        return f"{vectorizer_path.name} · {features} features · artifact {modified}"

    def _processing_quality_label(feature_count):
        """
        Descriptive vector richness only — not a recommendation-quality score.
        Thresholds are operational monitoring bands.
        """
        n=int(feature_count or 0)
        if n <= 0:
            return "No usable features"
        if n < 5:
            return "Very sparse"
        if n < 15:
            return "Sparse"
        if n < 40:
            return "Moderate"
        return "Rich"

    def _log_recommendation_processing(
        book_id, action_type, outcome, feature_count=None, vector_norm=None,
        vectorizer_features=None, vectorizer_version=None, message=""
    ):
        actor=admin_user()
        now=datetime.now(timezone.utc).isoformat()
        with db_connection() as conn:
            conn.execute("""
                INSERT INTO recommendation_processing_history
                    (book_id,action_type,outcome,feature_count,vector_norm,
                     vectorizer_features,vectorizer_version,message,
                     processed_by,processed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """,(
                str(book_id),str(action_type),str(outcome),
                feature_count,vector_norm,vectorizer_features,
                vectorizer_version,str(message or ""),
                int(actor["user_id"]) if actor else None,now
            ))
            conn.commit()

    def process_admin_added_book(book_id, action_type="Process"):
        """Persist or regenerate one Published Admin-added book's TF-IDF vector."""
        _ensure_recommendation_vector_table()
        book_df=dataframe("""
            SELECT * FROM live_catalog_books
            WHERE book_id=? LIMIT 1
        """,(book_id,))
        if book_df.empty:
            return False,"Book record was not found."

        record=book_df.iloc[0].to_dict()
        if str(record.get("catalog_status",""))!="Published":
            return False,"Only currently Published books can be processed."

        processing_text=_book_processing_text(record)
        if not processing_text.strip():
            msg="The book has no usable text metadata for recommendation processing."
            _log_recommendation_processing(book_id,action_type,"Failed",message=msg)
            return False,msg

        vectorizer_path=_leadwise_vectorizer_path()
        if not vectorizer_path.exists():
            msg=f"Production TF-IDF vectorizer was not found: {vectorizer_path}"
            _log_recommendation_processing(book_id,action_type,"Failed",message=msg)
            return False,msg

        vectorizer_version=None
        try:
            vectorizer=joblib.load(vectorizer_path)
            vectorizer_version=_vectorizer_version_label(vectorizer,vectorizer_path)
            vector=vectorizer.transform([processing_text]).tocsr()
            nonzero=int(vector.nnz)
            norm=float(np.sqrt(vector.multiply(vector).sum()))
            n_features=int(vector.shape[1])
        except Exception as exc:
            msg=f"Vector processing failed: {exc}"
            with db_connection() as conn:
                conn.execute("""
                    UPDATE live_catalog_books
                    SET intelligence_status='Processing Error',
                        updated_at=CURRENT_TIMESTAMP
                    WHERE book_id=?
                """,(book_id,))
                conn.commit()
            _log_recommendation_processing(
                book_id,action_type,"Failed",
                vectorizer_version=vectorizer_version,message=msg
            )
            return False,msg

        if nonzero<=0 or norm<=0:
            msg=(
                "Processing produced a zero recommendation vector. "
                "Add or correct meaningful title/category/description metadata and retry."
            )
            with db_connection() as conn:
                conn.execute("""
                    UPDATE live_catalog_books
                    SET intelligence_status='Processing Error',
                        updated_at=CURRENT_TIMESTAMP
                    WHERE book_id=?
                """,(book_id,))
                conn.commit()
            _log_recommendation_processing(
                book_id,action_type,"Failed",nonzero,norm,n_features,
                vectorizer_version,msg
            )
            return False,msg

        indices=json.dumps(vector.indices.astype(int).tolist())
        values=json.dumps(vector.data.astype(float).tolist())
        now=datetime.now(timezone.utc).isoformat()

        with db_connection() as conn:
            conn.execute("""
                INSERT INTO recommendation_book_vectors
                    (book_id,feature_indices_json,feature_values_json,feature_count,
                     vector_norm,vectorizer_features,processed_at,processing_status,
                     processing_error,vectorizer_version)
                VALUES (?,?,?,?,?,?,?,'Ready',NULL,?)
                ON CONFLICT(book_id) DO UPDATE SET
                    feature_indices_json=excluded.feature_indices_json,
                    feature_values_json=excluded.feature_values_json,
                    feature_count=excluded.feature_count,
                    vector_norm=excluded.vector_norm,
                    vectorizer_features=excluded.vectorizer_features,
                    processed_at=excluded.processed_at,
                    processing_status='Ready',
                    processing_error=NULL,
                    vectorizer_version=excluded.vectorizer_version
            """,(
                book_id,indices,values,nonzero,norm,n_features,now,
                vectorizer_version
            ))
            conn.execute("""
                UPDATE live_catalog_books
                SET intelligence_status='Ready',updated_at=?
                WHERE book_id=?
            """,(now,book_id))
            conn.commit()

        quality=_processing_quality_label(nonzero)
        msg=(
            f"{book_id} is Recommendation Ready. "
            f"Vector richness: {quality} ({nonzero} non-zero TF-IDF features)."
        )
        _log_recommendation_processing(
            book_id,action_type,"Success",nonzero,norm,n_features,
            vectorizer_version,msg
        )
        log_admin_action(
            "recommendation_book_reprocessed" if action_type=="Reprocess"
            else "recommendation_book_processed",
            "book",str(book_id),
            f"{quality}; features={nonzero}; norm={norm:.6f}; "
            f"vectorizer={vectorizer_version}"
        )
        return True,msg


    def reconcile_recommendation_processing_state():
        """
        Repair legacy status-only Ready records.

        A book is Recommendation Ready only when:
        1) it is Published,
        2) live_catalog_books.intelligence_status == 'Ready', and
        3) a valid persisted Ready vector exists in recommendation_book_vectors.
        """
        _ensure_recommendation_vector_table()
        with db_connection() as conn:
            # Legacy Ready rows from 18.52.x did not persist their vectors.
            stale=conn.execute("""
                SELECT l.book_id
                FROM live_catalog_books l
                LEFT JOIN recommendation_book_vectors v
                  ON v.book_id=l.book_id
                 AND v.processing_status='Ready'
                WHERE l.catalog_status='Published'
                  AND l.intelligence_status='Ready'
                  AND (
                      v.book_id IS NULL
                      OR v.feature_count <= 0
                      OR v.vector_norm <= 0
                  )
            """).fetchall()

            stale_ids=[str(row["book_id"]) for row in stale]
            if stale_ids:
                placeholders=",".join(["?"]*len(stale_ids))
                conn.execute(
                    f"""
                    UPDATE live_catalog_books
                    SET intelligence_status='Needs Processing',
                        updated_at=CURRENT_TIMESTAMP
                    WHERE book_id IN ({placeholders})
                    """,
                    stale_ids,
                )

            # A persisted vector must never make an unpublished book recommendation-active.
            conn.execute("""
                UPDATE live_catalog_books
                SET intelligence_status='Needs Processing',
                    updated_at=CURRENT_TIMESTAMP
                WHERE catalog_status<>'Published'
                  AND intelligence_status='Ready'
            """)
            conn.commit()

        return stale_ids


    reconciled_book_ids=reconcile_recommendation_processing_state()

    # ---------------------------------------------------------
    # RECOMMENDATION PROCESSING
    # ---------------------------------------------------------
    with processing_tab:
        st.markdown("### Recommendation Processing")
        st.caption(
            "Technical ML processing dashboard for published Admin-added books. "
            "This is not an approval stage: catalog approval is handled separately in the Approval Center. "
            "Books remain searchable after publication, while recommendation eligibility depends on successful NLP/vector processing."
        )

        processing_df = dataframe("""
            SELECT *
            FROM live_catalog_books
            ORDER BY live_book_id DESC
        """)

        if processing_df.empty:
            st.info("No Admin-added books are available for recommendation processing yet.")
        else:
            status_col = "intelligence_status"
            if status_col not in processing_df.columns:
                processing_df[status_col] = "Needs Processing"

            processing_df[status_col] = (
                processing_df[status_col].fillna("Needs Processing").astype(str)
            )
            processing_df.loc[
                processing_df[status_col].str.strip().eq(""), status_col
            ] = "Needs Processing"

            published_processing = processing_df[
                processing_df["catalog_status"].fillna("").astype(str).eq("Published")
            ].copy()

            # 18.54.0.2: recommendation readiness is derived from persisted vector evidence,
            # not from a legacy text flag.
            vector_truth = dataframe("""
                SELECT book_id, feature_count, vector_norm, vectorizer_features,
                       processed_at, processing_status, vectorizer_version
                FROM recommendation_book_vectors
            """)
            if not vector_truth.empty:
                vector_truth["Vector Richness"] = vector_truth["feature_count"].apply(
                    _processing_quality_label
                )
                vector_truth["Processed"] = pd.to_datetime(
                    vector_truth["processed_at"], errors="coerce", utc=True
                ).dt.strftime("%Y-%m-%d %H:%M UTC").fillna(
                    vector_truth["processed_at"].astype(str)
                )

            valid_vector_ids = set()
            if not vector_truth.empty:
                valid = vector_truth[
                    vector_truth["processing_status"].fillna("").astype(str).eq("Ready")
                    & (pd.to_numeric(vector_truth["feature_count"], errors="coerce").fillna(0) > 0)
                    & (pd.to_numeric(vector_truth["vector_norm"], errors="coerce").fillna(0) > 0)
                ].copy()
                valid_vector_ids = set(valid["book_id"].astype(str))

            published_processing["vector_ready"] = (
                published_processing["book_id"].astype(str).isin(valid_vector_ids)
            )
            published_processing["Recommendation Status"] = published_processing["vector_ready"].map(
                {True:"Ready", False:"Needs Processing"}
            )

            # Keep the stored status synchronized with vector truth.
            with db_connection() as connection:
                for _, sync_row in published_processing.iterrows():
                    expected = "Ready" if bool(sync_row["vector_ready"]) else "Needs Processing"
                    if str(sync_row.get(status_col) or "") != expected:
                        connection.execute(
                            "UPDATE live_catalog_books SET intelligence_status=?, updated_at=CURRENT_TIMESTAMP WHERE book_id=?",
                            (expected, str(sync_row["book_id"]))
                        )
                connection.commit()

            needs_count = int((~published_processing["vector_ready"]).sum())
            ready_count = int(published_processing["vector_ready"].sum())
            other_count = 0

            r1,r2,r3 = st.columns(3)
            r1.metric("Needs Processing", f"{needs_count:,}")
            r2.metric("Recommendation Ready", f"{ready_count:,}")
            r3.metric("Processing Errors / Review", f"{other_count:,}")

            with st.expander("Recommendation Vector Diagnostics"):
                st.write(f"Published Admin-added books: **{len(published_processing):,}**")
                st.write(f"Valid persisted Ready vectors: **{ready_count:,}**")
                st.write(f"Published books without a valid persisted vector: **{needs_count:,}**")
                if not vector_truth.empty:
                    diagnostics_display=vector_truth[[
                        "book_id","feature_count","Vector Richness","vector_norm",
                        "vectorizer_features","vectorizer_version","Processed",
                        "processing_status"
                    ]].rename(columns={
                        "book_id":"Book ID",
                        "feature_count":"Non-zero Features",
                        "vector_norm":"Vector Norm",
                        "vectorizer_features":"Vectorizer Features",
                        "vectorizer_version":"Vectorizer / Model Version",
                        "processing_status":"Vector Status",
                    })
                    st.dataframe(
                        diagnostics_display,
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(
                        "Vector Richness describes how many production TF-IDF features "
                        "are present in the book representation. It is an operational "
                        "diagnostic, not a quality rating of the book or recommendation."
                    )
                else:
                    st.caption("No persistent recommendation vectors are stored yet.")

            st.markdown("#### Processing Pipeline")
            st.code(
                "Published Book  →  Needs Processing  →  NLP / Vector Validation  →  Recommendation Ready",
                language=None,
            )
            st.caption(
                "Recommendation Ready is a technical system state, not an Approval Center decision."
            )

            st.markdown("#### Published Admin-Added Books")
            cols = [c for c in [
                "book_id","title","authors","catalog_status",
                "Recommendation Status","updated_at"
            ] if c in published_processing.columns]
            display = published_processing[cols].rename(columns={
                "book_id":"Book ID",
                "title":"Title",
                "authors":"Author(s)",
                "catalog_status":"Publication Status",
                "updated_at":"Last Updated",
            })
            st.dataframe(display,use_container_width=True,hide_index=True,height=330)

            needs = published_processing[
                ~published_processing["vector_ready"]
            ].copy()
            if not needs.empty:
                st.markdown("#### Books Waiting for ML Processing")
                st.caption(
                    "These books are published and searchable, but are not yet eligible "
                    "for the production recommendation engine."
                )
                queue_cols=[c for c in ["book_id","title","authors","Recommendation Status"] if c in needs.columns]
                st.dataframe(
                    needs[queue_cols].rename(columns={
                        "book_id":"Book ID",
                        "title":"Title",
                        "authors":"Author(s)",
                        "Recommendation Status":"Recommendation Status",
                    }),
                    use_container_width=True,hide_index=True
                )

            st.info(
                "No Approve/Reject controls are used here. Approval Center governs catalog changes. "
                "The processing controls below only validate recommendation eligibility."
            )

            if not needs.empty:
                st.markdown("#### Process One Book")
                process_ids = needs["book_id"].astype(str).tolist()
                selected_process_id = st.selectbox(
                    "Select a book waiting for ML processing",
                    process_ids,
                    format_func=lambda bid: (
                        f"{bid} · " +
                        str(needs.loc[
                            needs["book_id"].astype(str).eq(bid), "title"
                        ].iloc[0])
                    ),
                    key="recommendation_process_book_select",
                )

                selected_process = needs[
                    needs["book_id"].astype(str).eq(selected_process_id)
                ].iloc[0]
                st.caption(
                    f"Selected: {selected_process_id} · "
                    f"{selected_process.get('title','')} · "
                    f"{selected_process.get('authors','')}"
                )

                if st.button(
                    "Process Book",
                    type="primary",
                    use_container_width=True,
                    key=f"process_recommendation_{selected_process_id}",
                ):
                    with st.spinner("Validating against the production recommendation feature space..."):
                        ok,msg = process_admin_added_book(selected_process_id)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()
            else:
                st.success(
                    "There are no published Admin-added books waiting for recommendation processing."
                )

            st.divider()
            st.markdown("#### Reprocess Recommendation-Ready Book")
            st.caption(
                "Use Reprocess when approved metadata has changed or when you deliberately "
                "want to regenerate a book's vector with the current production vectorizer."
            )

            ready_for_reprocess=published_processing[
                published_processing["vector_ready"]
            ].copy()

            if ready_for_reprocess.empty:
                st.caption("No Recommendation Ready books are available for reprocessing.")
            else:
                reprocess_ids=ready_for_reprocess["book_id"].astype(str).tolist()
                selected_reprocess_id=st.selectbox(
                    "Select a Recommendation Ready book",
                    reprocess_ids,
                    format_func=lambda bid: (
                        f"{bid} · " +
                        str(ready_for_reprocess.loc[
                            ready_for_reprocess["book_id"].astype(str).eq(bid),
                            "title"
                        ].iloc[0])
                    ),
                    key="recommendation_reprocess_book_select",
                )

                current_vector=vector_truth[
                    vector_truth["book_id"].astype(str).eq(selected_reprocess_id)
                ]
                if not current_vector.empty:
                    vr=current_vector.iloc[0]
                    q=_processing_quality_label(vr.get("feature_count"))
                    st.info(
                        f"Current vector: {int(vr.get('feature_count') or 0)} "
                        f"non-zero features · {q} · "
                        f"processed {vr.get('Processed','—')}"
                    )

                confirm_reprocess=st.checkbox(
                    "I understand this will replace the book's current recommendation vector.",
                    key=f"confirm_reprocess_{selected_reprocess_id}",
                )
                if st.button(
                    "Reprocess Book",
                    disabled=not confirm_reprocess,
                    use_container_width=True,
                    key=f"reprocess_recommendation_{selected_reprocess_id}",
                ):
                    with st.spinner("Regenerating the production TF-IDF vector..."):
                        ok,msg=process_admin_added_book(
                            selected_reprocess_id, action_type="Reprocess"
                        )
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()

            st.divider()
            st.markdown("#### Processing History")
            history=dataframe("""
                SELECT h.history_id,h.book_id,h.action_type,h.outcome,
                       h.feature_count,h.vector_norm,h.vectorizer_features,
                       h.vectorizer_version,h.message,
                       u.full_name AS processed_by,h.processed_at
                FROM recommendation_processing_history h
                LEFT JOIN users u ON u.user_id=h.processed_by
                ORDER BY h.history_id DESC
                LIMIT 100
            """)

            if history.empty:
                st.caption(
                    "No processing-history entries have been recorded yet. "
                    "New Process and Reprocess actions will appear here."
                )
            else:
                history["Vector Richness"]=history["feature_count"].apply(
                    _processing_quality_label
                )
                history["Processed"]=pd.to_datetime(
                    history["processed_at"],errors="coerce",utc=True
                ).dt.strftime("%Y-%m-%d %H:%M UTC").fillna(
                    history["processed_at"].astype(str)
                )
                st.dataframe(
                    history[[
                        "history_id","book_id","action_type","outcome",
                        "feature_count","Vector Richness","vectorizer_version",
                        "processed_by","Processed"
                    ]].rename(columns={
                        "history_id":"History ID",
                        "book_id":"Book ID",
                        "action_type":"Action",
                        "outcome":"Outcome",
                        "feature_count":"Non-zero Features",
                        "vectorizer_version":"Vectorizer / Model Version",
                        "processed_by":"Processed By",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

    # ---------------------------------------------------------
    # APPROVAL CENTER: only this stage can mutate the catalog.
    # ---------------------------------------------------------
    with approval_center_tab:
        st.markdown("### Catalog Approval Center")
        st.caption(
            "All catalog changes enter this queue first. "
            "Only a Super Admin can approve or reject a Pending request."
        )

        pending_tab, history_tab = st.tabs(
            ["Pending Approval","Governance History"]
        )

        with pending_tab:
            pending = dataframe("""
                SELECT r.request_id,r.book_id,r.record_type,r.action_type,r.reason,r.status,
                       requester.full_name AS requested_by,r.requested_at,
                       r.before_json,r.proposed_json
                FROM catalog_change_requests r
                LEFT JOIN users requester ON requester.user_id=r.requested_by
                WHERE r.status='Pending'
                ORDER BY r.request_id ASC
            """)

            if pending.empty:
                st.success("No catalog requests are waiting for approval.")
            else:
                st.warning(
                    f"{len(pending):,} catalog request(s) require a decision."
                )
                st.dataframe(
                    pending[
                        ["request_id","book_id","action_type",
                         "requested_by","requested_at","reason"]
                    ],
                    use_container_width=True,hide_index=True
                )

                pending_id = st.selectbox(
                    "Select request to review",
                    pending["request_id"].astype(int).tolist(),
                    format_func=lambda rid: (
                        f"Request #{rid} · " +
                        str(pending.loc[
                            pending["request_id"].astype(int).eq(rid),"action_type"
                        ].iloc[0]) +
                        " · " +
                        str(pending.loc[
                            pending["request_id"].astype(int).eq(rid),"book_id"
                        ].iloc[0])
                    ),
                    key="pending_catalog_approval",
                )
                req = pending[
                    pending["request_id"].astype(int).eq(int(pending_id))
                ].iloc[0]

                st.markdown("#### Request for decision")
                a1,a2,a3 = st.columns(3)
                a1.markdown(f"**Book ID:** {req['book_id']}")
                a2.markdown(f"**Action:** {req['action_type']}")
                a3.markdown(f"**Requested by:** {req['requested_by']}")
                st.markdown(f"**Reason:** {req['reason']}")
                st.caption(f"Submitted: {req['requested_at']}")

                before_json = json.loads(req["before_json"] or "{}")
                proposed_json = json.loads(req["proposed_json"] or "{}")
                fields = sorted(set(before_json) | set(proposed_json))
                changes = []
                for field in fields:
                    old = str(before_json.get(field,"") or "")
                    new = str(proposed_json.get(field,"") or "")
                    if old != new:
                        changes.append({
                            "Field":field,
                            "Current value":old or "—",
                            "Proposed value":new or "—",
                        })
                if changes:
                    st.dataframe(
                        pd.DataFrame(changes),
                        use_container_width=True,hide_index=True
                    )

                if user.get("role") == "super_admin":
                    st.divider()
                    st.markdown("#### Super Admin Decision")
                    review_note = st.text_area(
                        "Decision note",
                        placeholder=(
                            "Optional for approval; mandatory for rejection."
                        ),
                        key="approval_center_review_note",
                        height=90,
                    )
                    approve_col,reject_col = st.columns(2)

                    if approve_col.button(
                        "Approve & Apply",
                        type="primary",
                        use_container_width=True,
                        key="approval_center_approve",
                    ):
                        ok,msg = review_catalog_change_request(
                            int(pending_id),"Approved",review_note
                        )
                        (st.success if ok else st.error)(msg)
                        if ok:
                            st.rerun()

                    if reject_col.button(
                        "Reject Request",
                        use_container_width=True,
                        key="approval_center_reject",
                    ):
                        if not str(review_note or "").strip():
                            st.error("A decision note is required when rejecting a request.")
                        else:
                            ok,msg = review_catalog_change_request(
                                int(pending_id),"Rejected",review_note
                            )
                            (st.success if ok else st.error)(msg)
                            if ok:
                                st.rerun()
                else:
                    st.info(
                        "You submitted/monitor requests here. "
                        "Only a Super Admin can approve or reject them."
                    )

        with history_tab:
            history = dataframe("""
                SELECT r.request_id,r.book_id,r.record_type,r.action_type,r.reason,r.status,
                       requester.full_name AS requested_by,r.requested_at,
                       reviewer.full_name AS reviewed_by,r.reviewed_at,r.review_note
                FROM catalog_change_requests r
                LEFT JOIN users requester ON requester.user_id=r.requested_by
                LEFT JOIN users reviewer ON reviewer.user_id=r.reviewed_by
                WHERE r.status IN ('Approved','Rejected')
                ORDER BY r.request_id DESC
                LIMIT 500
            """)

            if history.empty:
                st.info("No completed catalog governance records yet.")
            else:
                h1,h2 = st.columns(2)
                h1.metric(
                    "Approved",
                    f"{int((history['status'].astype(str)=='Approved').sum()):,}"
                )
                h2.metric(
                    "Rejected",
                    f"{int((history['status'].astype(str)=='Rejected').sum()):,}"
                )
                history_filter = st.radio(
                    "History status",
                    ["All","Approved","Rejected"],
                    horizontal=True,key="catalog_governance_history_filter"
                )
                visible = history.copy()
                if history_filter != "All":
                    visible = visible[
                        visible["status"].astype(str).eq(history_filter)
                    ]
                st.dataframe(
                    visible,
                    use_container_width=True,hide_index=True
                )

    # ---------------------------------------------------------
    # ACTIVITY: immutable operational evidence.
    # ---------------------------------------------------------
    with activity_tab:
        st.markdown("### Catalog Activity")
        st.caption(
            "Audit evidence for requests, approvals, rejections and applied catalog changes."
        )
        activity = dataframe("""
            SELECT a.audit_id,a.created_at,
                   COALESCE(u.full_name,'Former / unavailable administrator') AS administrator,
                   a.action,a.entity_id AS book_id,a.details
            FROM admin_audit_log a
            LEFT JOIN users u ON u.user_id=a.admin_user_id
            WHERE a.entity_type='book'
            ORDER BY a.audit_id DESC
            LIMIT 1000
        """)
        st.dataframe(activity,use_container_width=True,hide_index=True)

    st.info(
        "Recommendation note: Published Admin-added books become eligible for TF-IDF "
        "recommendations after successful Recommendation Processing. Books marked "
        "Recommendation Ready have a validated persisted vector available to the "
        "Reader recommendation engine."
    )

elif section == "Admin Management":
    if user.get("role") != "super_admin":
        st.error("Super Admin access is required.")
        st.stop()

    st.subheader("Admin Management")
    st.caption("Approve administrator requests and manage existing Admin accounts without editing code or the database.")

    pending_count = scalar("SELECT COUNT(*) FROM admin_access_requests WHERE status = 'Pending'")
    active_admins = scalar("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1")
    inactive_admins = scalar("SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 0")

    c1, c2, c3 = st.columns(3)
    c1.metric("Pending Requests", f"{pending_count:,}")
    c2.metric("Active Admins", f"{active_admins:,}")
    c3.metric("Inactive Admins", f"{inactive_admins:,}")

    request_tab, admins_tab, history_tab = st.tabs(
        ["Pending Requests", "Administrators", "Request History"]
    )

    with request_tab:
        pending = dataframe("""
            SELECT request_id, full_name, email, organization_position,
                   reason, requested_role, created_at
            FROM admin_access_requests
            WHERE status = 'Pending'
            ORDER BY request_id DESC
        """)
        if pending.empty:
            st.info("There are no pending administrator access requests.")
        else:
            st.dataframe(pending, use_container_width=True, hide_index=True)
            request_ids = pending["request_id"].astype(int).tolist()
            selected_request = st.selectbox(
                "Select request to review",
                request_ids,
                format_func=lambda rid: (
                    f"#{rid} · " +
                    str(pending.loc[pending['request_id'] == rid, 'full_name'].iloc[0]) +
                    " · " +
                    str(pending.loc[pending['request_id'] == rid, 'email'].iloc[0])
                ),
            )
            selected_row = pending[pending["request_id"] == selected_request].iloc[0]
            st.markdown(f"**Applicant:** {html.escape(str(selected_row['full_name']))}")
            st.markdown(f"**Email:** {html.escape(str(selected_row['email']))}")
            if pd.notna(selected_row["organization_position"]) and str(selected_row["organization_position"]).strip():
                st.markdown(f"**Organization / Position:** {html.escape(str(selected_row['organization_position']))}")
            st.markdown("**Reason for access:**")
            st.write(str(selected_row["reason"]))

            with st.form("review_admin_request_form"):
                admin_note = st.text_area("Internal review note (optional)")
                col1, col2 = st.columns(2)
                approve = col1.form_submit_button("Approve Admin", use_container_width=True)
                decline = col2.form_submit_button("Decline Request", use_container_width=True)

            if approve or decline:
                decision = "Approved" if approve else "Declined"
                ok, message = review_admin_request(selected_request, decision, admin_note)
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    with admins_tab:
        admins = dataframe("""
            SELECT user_id, full_name, email, role, is_active, created_at
            FROM users
            WHERE role IN ('super_admin', 'admin')
            ORDER BY CASE role WHEN 'super_admin' THEN 0 ELSE 1 END, user_id
        """)
        st.dataframe(admins, use_container_width=True, hide_index=True)

        manageable = admins[admins["role"] == "admin"] if not admins.empty else admins
        if not manageable.empty:
            admin_ids = manageable["user_id"].astype(int).tolist()
            selected_admin_id = st.selectbox(
                "Select Admin account",
                admin_ids,
                format_func=lambda uid: (
                    str(manageable.loc[manageable['user_id'] == uid, 'full_name'].iloc[0]) +
                    " · " +
                    str(manageable.loc[manageable['user_id'] == uid, 'email'].iloc[0])
                ),
            )
            selected_admin = manageable[manageable["user_id"] == selected_admin_id].iloc[0]
            currently_active = int(selected_admin["is_active"]) == 1
            action_label = "Deactivate Admin" if currently_active else "Reactivate Admin"
            if st.button(action_label, use_container_width=True):
                ok, message = set_admin_active(selected_admin_id, not currently_active)
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

        st.info("The Super Admin account cannot be deactivated from this screen.")

        st.divider()
        st.markdown("### Administrator lifecycle & succession")
        all_admins = dataframe("""
            SELECT user_id, full_name, email, role, is_active,
                   COALESCE(admin_account_status,'Active') AS account_status
            FROM users
            WHERE role IN ('admin','super_admin')
            ORDER BY CASE role WHEN 'super_admin' THEN 0 ELSE 1 END, full_name
        """)
        if not all_admins.empty:
            gov_id = st.selectbox(
                "Administrator to manage",
                all_admins["user_id"].astype(int).tolist(),
                format_func=lambda uid: (
                    f"{all_admins.loc[all_admins['user_id']==uid,'full_name'].iloc[0]} · "
                    f"{all_admins.loc[all_admins['user_id']==uid,'role'].iloc[0]} · "
                    f"{all_admins.loc[all_admins['user_id']==uid,'account_status'].iloc[0]}"
                ),
                key="governance_admin_select"
            )
            gov_row=all_admins[all_admins["user_id"]==gov_id].iloc[0]
            gov_note=st.text_area("Lifecycle / succession note",key="governance_note")

            g1,g2,g3,g4=st.columns(4)
            freeze=g1.button("Freeze",use_container_width=True)
            deactivate=g2.button("Deactivate",use_container_width=True)
            reactivate=g3.button("Reactivate",use_container_width=True)
            promote=g4.button("Promote to Super Admin",use_container_width=True,
                              disabled=str(gov_row["role"])!="admin")

            if freeze or deactivate or reactivate:
                status="Frozen" if freeze else ("Deactivated" if deactivate else "Active")
                ok,msg=change_admin_lifecycle(gov_id,status,gov_note)
                (st.success if ok else st.error)(msg)
                if ok: st.rerun()

            if promote:
                ok,msg=promote_to_super_admin(gov_id)
                (st.success if ok else st.error)(msg)
                if ok: st.rerun()

            st.markdown("#### Permanently retire login")
            st.caption(
                "Use this when an administrator has permanently left LeadWise. "
                "The account can no longer sign in, while historical audit attribution remains."
            )
            expected=f"RETIRE {gov_row['full_name']}".upper()
            confirmation=st.text_input(
                f"Type {expected} to confirm",
                key="retire_confirmation"
            )
            if st.button("Retire Administrator Login",type="secondary",use_container_width=True):
                ok,msg=retire_admin_login(gov_id,confirmation,gov_note)
                (st.success if ok else st.error)(msg)
                if ok: st.rerun()

    with history_tab:
        history = dataframe("""
            SELECT r.request_id, r.full_name, r.email, r.status,
                   r.created_at, r.reviewed_at,
                   u.full_name AS reviewed_by, r.admin_note
            FROM admin_access_requests r
            LEFT JOIN users u ON u.user_id = r.reviewed_by
            ORDER BY r.request_id DESC
        """)
        st.dataframe(history, use_container_width=True, hide_index=True)

elif section == "Featured Reading":
    st.title("Featured Reading")
    st.caption(
        "Curate books from the currently published LeadWise catalog for the Reader Home page. "
        "Featured Reading is editorial curation and remains separate from personalized ML recommendations."
    )

    # Local SQLite can self-initialize. PostgreSQL uses the validated shared schema.
    with db_connection() as conn:
        if conn.backend == "sqlite":
            conn.execute("""
                CREATE TABLE IF NOT EXISTS featured_reading (
                    feature_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL,
                    feature_message TEXT,
                    display_order INTEGER NOT NULL DEFAULT 1,
                    start_date TEXT,
                    end_date TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        else:
            problems = validate_required_schema(
                conn, {"featured_reading": ADMIN_REQUIRED_SCHEMA["featured_reading"]}
            )
            if problems:
                raise RuntimeError(
                    "LeadWise Featured Reading schema validation failed: "
                    + " | ".join(problems)
                )

    frozen_catalog, _ = load_frozen_catalog()

    def _feature_series(frame,candidates):
        result=pd.Series("",index=frame.index,dtype="object")
        for col in candidates:
            if col in frame.columns:
                vals=frame[col].fillna("").astype(str).str.strip()
                result=result.where(result.astype(str).str.strip().ne(""),vals)
        return result

    feature_rows=[]
    overrides_df=dataframe("SELECT * FROM catalog_book_overrides")
    override_map={str(r["book_id"]):r.to_dict() for _,r in overrides_df.iterrows()} if not overrides_df.empty else {}

    if not frozen_catalog.empty:
        fc=frozen_catalog.copy()
        titles=_feature_series(fc,["display_title","canonical_title","title","Title"])
        authors=_feature_series(fc,["display_authors","authors","author","Authors"])
        cats=_feature_series(fc,["display_categories","categories","subjects"])
        for idx,row in fc.iterrows():
            bid=str(row.get("book_id",""))
            ov=override_map.get(bid,{})
            if str(ov.get("catalog_status") or "Published")!="Published":
                continue
            feature_rows.append({
                "book_id":bid,
                "title":str(ov.get("title") or titles.loc[idx]),
                "authors":str(ov.get("authors") or authors.loc[idx]),
                "categories":str(ov.get("categories") or cats.loc[idx]),
                "catalog_source":"Catalog",
            })

    live_pub=dataframe("""
        SELECT * FROM live_catalog_books
        WHERE catalog_status='Published'
        ORDER BY live_book_id DESC
    """)
    if not live_pub.empty:
        for _,row in live_pub.iterrows():
            feature_rows.append({
                "book_id":str(row.get("book_id","")),
                "title":str(row.get("title","") or ""),
                "authors":str(row.get("authors","") or ""),
                "categories":str(row.get("categories","") or ""),
                "catalog_source":"Admin Added",
            })

    published=pd.DataFrame(feature_rows)
    if not published.empty:
        published=published.drop_duplicates("book_id",keep="last").reset_index(drop=True)

    active_count=scalar("SELECT COUNT(*) FROM featured_reading WHERE is_active=1")
    st.metric("Active Featured Books",f"{active_count:,}")

    current_tab,feature_tab=st.tabs(["Current Features","Feature a Book"])

    with feature_tab:
        st.markdown("### Select from Published Catalog")
        if published.empty:
            st.info("No published books are available.")
        else:
            q=st.text_input(
                "Search published books",
                placeholder="Search title, author, Book ID or category",
                key="feature_search"
            ).strip().lower()
            blob=(published["book_id"]+" "+published["title"]+" "+published["authors"]+" "+published["categories"]).str.lower()
            matches=published[blob.str.contains(q,regex=False,na=False)] if q else published

            st.dataframe(
                matches.rename(columns={
                    "book_id":"Book ID","title":"Title","authors":"Author(s)",
                    "categories":"Categories","catalog_source":"Catalog Source"
                }).head(200),
                use_container_width=True,hide_index=True,height=330
            )

            if not matches.empty:
                choices=matches.head(200)
                bid=st.selectbox(
                    "Select book to feature",
                    choices["book_id"].tolist(),
                    format_func=lambda x:f"{x} · {choices.loc[choices['book_id'].eq(x),'title'].iloc[0]}",
                    key="feature_book_select"
                )
                chosen=choices[choices["book_id"].eq(bid)].iloc[0]
                st.markdown(f"#### {chosen['title']}")
                st.caption(str(chosen["authors"] or ""))

                with st.form("featured_reading_form"):
                    message=st.text_area(
                        "Feature message",
                        placeholder="Why is LeadWise featuring this book?",
                        height=100
                    )
                    order=st.number_input("Display order",1,100,1,1)
                    start_date=st.date_input("Start date",value=None)
                    end_date=st.date_input("End date",value=None)
                    submit=st.form_submit_button("Add to Featured Reading",use_container_width=True)

                if submit:
                    if start_date and end_date and end_date<start_date:
                        st.error("End date cannot be earlier than start date.")
                    else:
                        with db_connection() as conn:
                            exists=conn.execute(
                                "SELECT 1 FROM featured_reading WHERE book_id=? AND is_active=1",(bid,)
                            ).fetchone()
                            if exists:
                                st.error("This book is already active in Featured Reading.")
                            else:
                                conn.execute("""
                                    INSERT INTO featured_reading
                                    (book_id,feature_message,display_order,start_date,end_date,is_active,created_by)
                                    VALUES (?,?,?,?,?,1,?)
                                """,(
                                    bid,str(message or "").strip(),int(order),
                                    start_date.isoformat() if start_date else None,
                                    end_date.isoformat() if end_date else None,
                                    st.session_state.get("admin_user_id")
                                ))
                                conn.commit()
                                st.success("Book added to Featured Reading.")
                                st.rerun()

    with current_tab:
        st.markdown("### Current Featured Reading")
        features=dataframe("""
            SELECT * FROM featured_reading
            ORDER BY is_active DESC,display_order ASC,feature_id DESC
        """)
        if features.empty:
            st.info("No books have been featured yet.")
        else:
            lookup={str(r["book_id"]):r for _,r in published.iterrows()} if not published.empty else {}
            for _,f in features.iterrows():
                bid=str(f["book_id"])
                meta=lookup.get(bid)
                title=str(meta["title"]) if meta is not None else bid
                authors=str(meta["authors"]) if meta is not None else ""
                active=bool(f["is_active"])
                with st.container(border=True):
                    a,b=st.columns([4,1])
                    with a:
                        st.markdown(f"**{title}**")
                        st.caption(f"{authors} · {bid}")
                        if str(f.get("feature_message","") or "").strip():
                            st.write(str(f["feature_message"]))
                        period=[]
                        if f.get("start_date"): period.append(f"Starts {f['start_date']}")
                        if f.get("end_date"): period.append(f"Ends {f['end_date']}")
                        if period: st.caption(" · ".join(period))
                    with b:
                        st.write("Active" if active else "Inactive")
                        label="Remove Feature" if active else "Reactivate"
                        if st.button(label,key=f"feature_toggle_{int(f['feature_id'])}",use_container_width=True):
                            with db_connection() as conn:
                                conn.execute("""
                                    UPDATE featured_reading
                                    SET is_active=?,updated_at=CURRENT_TIMESTAMP
                                    WHERE feature_id=?
                                """,(0 if active else 1,int(f["feature_id"])))
                                conn.commit()
                            st.rerun()

elif section == "System Monitoring":
    st.subheader("System Monitoring")
    if DATABASE_BACKEND == "postgresql":
        with db_connection() as connection:
            connection.execute("SELECT 1 AS ok").fetchone()
        c1, c2, c3 = st.columns(3)
        c1.metric("Database", "Available")
        c2.metric("Backend", "Supabase PostgreSQL")
        c3.metric("Admin Role", "Authorized")
    else:
        db_exists = USER_DB_PATH.exists()
        db_size = USER_DB_PATH.stat().st_size if db_exists else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Database", "Available" if db_exists else "Missing")
        c2.metric("SQLite Size", f"{db_size / 1024:.1f} KB" if db_exists else "—")
        c3.metric("Admin Role", "Authorized")

    st.markdown("**Privacy boundary**")
    st.success(
        "The Admin Control Center does not query private_notes, key_takeaways, "
        "practical_application, or unpublished reader reflections."
    )

    st.markdown("**Recent admin audit events**")
    audit = dataframe(
        """
        SELECT a.audit_id, u.full_name AS administrator, a.action,
               a.entity_type, a.entity_id, a.created_at
        FROM admin_audit_log a
        JOIN users u ON u.user_id = a.admin_user_id
        ORDER BY a.audit_id DESC
        LIMIT 50
        """
    )
    st.dataframe(audit, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("LeadWise Administrator · Role-protected operational interface · 18.56.1")
