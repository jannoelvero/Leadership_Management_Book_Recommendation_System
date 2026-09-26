# =========================================================
# LEADWISE
# Leadership & Management Book Intelligence
# Streamlit Application
# Version 18.58.1 — Shared Cloud Database Backend Verification
# =========================================================

import sys
import os
import re
import json
import uuid
import ast
import html
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import streamlit as st

from scipy.sparse import load_npz, csr_matrix, vstack
from sklearn.metrics.pairwise import cosine_similarity

from db_utils import (
    connect_database,
    get_database_backend,
    get_database_url,
    get_postgres_component_status,
    insert_returning_id,
    is_integrity_error,
    query_dataframe,
    validate_required_schema,
)


# =========================================================
# PROJECT PATHS
# =========================================================

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

DATA_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "models"
ASSETS_DIR = APP_DIR / "assets"

LOGO_PATH = ASSETS_DIR / "logo" / "leadwise_logo.png"
HERO_PATH = ASSETS_DIR / "backgrounds" / "leadwise_hero.png"

# ---------------------------------------------------------
# PORTABLE DEPLOYMENT CONFIGURATION
# ---------------------------------------------------------
# Local development remains the default. A future host can
# override writable application storage without changing the
# Reader's catalog, recommendation, or UI logic.
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

# 18.58.0 keeps SQLite as the local default and activates PostgreSQL
# only when DATABASE_URL is supplied through Streamlit secrets or the
# environment. Reader and Admin can therefore share Supabase in cloud
# while the validated local SQLite workflow remains available.


# =========================================================
# USER ACCOUNT FOUNDATION
# =========================================================

PBKDF2_ITERATIONS = 310_000


READER_REQUIRED_SCHEMA = {
    "users": {
        "user_id", "full_name", "email", "password_hash", "password_salt",
        "created_at", "is_active", "role",
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
        "related_book_id", "created_at", "status",
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
    "recommendation_book_vectors": {
        "book_id", "feature_indices_json", "feature_values_json", "feature_count",
        "vector_norm", "vectorizer_features", "processed_at", "processing_status",
        "processing_error", "vectorizer_version",
    },
}


def get_user_connection():
    """Return the active LeadWise Reader database connection."""
    return connect_database(USER_DB_PATH, DATABASE_URL)


def initialize_user_database():
    """Initialize local SQLite or validate the existing Supabase schema.

    PostgreSQL mode is validation only. The shared Supabase schema is managed
    separately and is never recreated by the Reader application.
    """
    with get_user_connection() as connection:
        if connection.backend == "postgresql":
            problems = validate_required_schema(connection, READER_REQUIRED_SCHEMA)
            if problems:
                raise RuntimeError(
                    "LeadWise PostgreSQL schema validation failed: "
                    + " | ".join(problems)
                )
            return

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
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_leadwise_events_created_at "
            "ON leadwise_events(created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_leadwise_events_event_type "
            "ON leadwise_events(event_type)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_leadwise_events_user_id "
            "ON leadwise_events(user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_leadwise_events_session_id "
            "ON leadwise_events(session_id)"
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_library (
                library_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id TEXT NOT NULL,
                reading_status TEXT NOT NULL DEFAULT 'Want to Read',
                personal_rating REAL,
                private_notes TEXT,
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
                UNIQUE(user_id, book_id),
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )

        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(user_library)").fetchall()
        }
        journal_columns = {
            "key_takeaways": "TEXT",
            "practical_application": "TEXT",
            "date_finished": "TEXT",
        }
        for column_name, column_type in journal_columns.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE user_library ADD COLUMN {column_name} {column_type}"
                )

        review_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(user_reviews)").fetchall()
        }
        community_columns = {
            "is_published": "INTEGER NOT NULL DEFAULT 0",
            "published_at": "TEXT",
        }
        for column_name, column_type in community_columns.items():
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
                FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL
            )
            """
        )



def get_active_featured_reading():
    """Return Admin-curated books that are active for today's Reader Home page."""
    with get_user_connection() as connection:
        today = date.today() if connection.backend == "postgresql" else date.today().isoformat()
        rows = connection.execute(
            """
            SELECT feature_id, book_id, feature_message, display_order,
                   start_date, end_date, created_at
            FROM featured_reading
            WHERE is_active = 1
              AND (start_date IS NULL OR TRIM(CAST(start_date AS TEXT)) = '' OR start_date <= ?)
              AND (end_date IS NULL OR TRIM(CAST(end_date AS TEXT)) = '' OR end_date >= ?)
            ORDER BY display_order ASC, feature_id DESC
            """,
            (today, today),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def normalize_email(value):
    return str(value or "").strip().lower()


def hash_password(password, salt_hex=None):
    if salt_hex is None:
        salt = secrets.token_bytes(16)
        salt_hex = salt.hex()
    else:
        salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return digest.hex(), salt_hex


def create_user(full_name, email, password):
    full_name = str(full_name or "").strip()
    email = normalize_email(email)
    if len(full_name) < 2:
        return False, "Enter your full name."
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Enter a valid email address."
    if len(password) < 8:
        return False, "Password must contain at least 8 characters."
    password_hash, password_salt = hash_password(password)
    try:
        with get_user_connection() as connection:
            created_at = (
                datetime.now(timezone.utc)
                if connection.backend == "postgresql"
                else datetime.now(timezone.utc).isoformat()
            )
            user_id = insert_returning_id(
                connection,
                """
                INSERT INTO users
                    (full_name, email, password_hash, password_salt, created_at, role)
                VALUES (?, ?, ?, ?, ?, 'reader')
                """,
                (full_name, email, password_hash, password_salt, created_at),
                "user_id",
            )
    except Exception as exc:
        if is_integrity_error(exc):
            return False, "An account with this email already exists."
        raise
    return True, {"user_id": user_id, "full_name": full_name, "email": email, "role": "reader"}


def authenticate_user(email, password):
    email = normalize_email(email)
    with get_user_connection() as connection:
        row = connection.execute(
            """
            SELECT user_id, full_name, email, password_hash, password_salt, role
            FROM users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()
    if row is None:
        return None
    candidate_hash, _ = hash_password(password, row["password_salt"])
    if not hmac.compare_digest(candidate_hash, row["password_hash"]):
        return None
    return {
        "user_id": row["user_id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"] if row["role"] in {"reader", "admin"} else "reader",
    }



def _analytics_session_id():
    if "leadwise_analytics_session_id" not in st.session_state:
        st.session_state["leadwise_analytics_session_id"] = uuid.uuid4().hex
    return st.session_state["leadwise_analytics_session_id"]


def track_event(event_type, page=None, book_id=None, related_book_id=None,
                query_id=None, metadata=None, user=None):
    """Record privacy-conscious product usage."""
    if user is None:
        user = st.session_state.get("leadwise_user")
    user_id = int(user["user_id"]) if isinstance(user, dict) and user.get("user_id") else None

    safe_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    for private_key in (
        "private_notes", "key_takeaways", "practical_application",
        "password", "password_hash", "password_salt"
    ):
        safe_metadata.pop(private_key, None)

    with get_user_connection() as connection:
        connection.execute(
            """
            INSERT INTO leadwise_events
                (user_id, session_id, event_type, page, book_id, related_book_id,
                 query_id, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, _analytics_session_id(), str(event_type), page,
                book_id, related_book_id, query_id,
                json.dumps(safe_metadata, ensure_ascii=False, default=str),
                (
                    datetime.now(timezone.utc)
                    if connection.backend == "postgresql"
                    else datetime.now(timezone.utc).isoformat()
                ),
            ),
        )


def track_page_once(page_name):
    marker = f"{_analytics_session_id()}::{page_name}"
    if st.session_state.get("leadwise_last_page_marker") != marker:
        track_event("page_view", page=page_name)
        st.session_state["leadwise_last_page_marker"] = marker


def signed_in_user():
    return st.session_state.get("leadwise_user")


def sign_in_user(user):
    st.session_state["leadwise_user"] = user


def sign_out_user():
    st.session_state.pop("leadwise_user", None)


READING_STATUSES = ["Want to Read", "Currently Reading", "Finished"]


def get_library_entry(user_id, book_id):
    with get_user_connection() as connection:
        row = connection.execute(
            """
            SELECT library_id, user_id, book_id, reading_status, personal_rating, private_notes,
                   key_takeaways, practical_application, date_finished, saved_at, updated_at
            FROM user_library
            WHERE user_id = ? AND book_id = ?
            """,
            (int(user_id), str(book_id)),
        ).fetchone()
    return dict(row) if row else None


def save_library_book(user_id, book_id, reading_status="Want to Read"):
    if reading_status not in READING_STATUSES:
        reading_status = "Want to Read"
    with get_user_connection() as connection:
        now = (
            datetime.now(timezone.utc)
            if connection.backend == "postgresql"
            else datetime.now(timezone.utc).isoformat()
        )
        connection.execute(
            """
            INSERT INTO user_library
                (user_id, book_id, reading_status, saved_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                reading_status = excluded.reading_status,
                updated_at = excluded.updated_at
            """,
            (int(user_id), str(book_id), reading_status, now, now),
        )



def update_library_status(user_id, book_id, reading_status):
    """Update one signed-in user's reading status and return the persisted entry."""
    if reading_status not in READING_STATUSES:
        raise ValueError("Invalid reading status.")
    with get_user_connection() as connection:
        now = (
            datetime.now(timezone.utc)
            if connection.backend == "postgresql"
            else datetime.now(timezone.utc).isoformat()
        )
        existing = connection.execute(
            "SELECT reading_status, date_finished FROM user_library WHERE user_id = ? AND book_id = ?",
            (int(user_id), str(book_id)),
        ).fetchone()
        if existing is None:
            return None
        finished_date = existing["date_finished"]
        if reading_status == "Finished" and not finished_date:
            finished_date = (
                date.today()
                if connection.backend == "postgresql"
                else date.today().isoformat()
            )
        connection.execute(
            """
            UPDATE user_library
            SET reading_status = ?, date_finished = ?, updated_at = ?
            WHERE user_id = ? AND book_id = ?
            """,
            (reading_status, finished_date, now, int(user_id), str(book_id)),
        )
    return get_library_entry(user_id, book_id)

def remove_library_book(user_id, book_id):
    with get_user_connection() as connection:
        connection.execute(
            "DELETE FROM user_library WHERE user_id = ? AND book_id = ?",
            (int(user_id), str(book_id)),
        )


def get_user_library(user_id):
    with get_user_connection() as connection:
        rows = connection.execute(
            """
            SELECT book_id, reading_status, personal_rating, private_notes,
                   key_takeaways, practical_application, date_finished, saved_at, updated_at
            FROM user_library
            WHERE user_id = ?
            ORDER BY updated_at DESC, library_id DESC
            """,
            (int(user_id),),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def save_reading_journal(
    user_id,
    book_id,
    personal_rating=None,
    review_text="",
    key_takeaways="",
    practical_application="",
    private_notes="",
    date_finished=None,
):
    """Persist a signed-in reader's private journal and personal review evidence."""
    rating_value = None if personal_rating in (None, 0, "") else float(personal_rating)
    with get_user_connection() as connection:
        now = (
            datetime.now(timezone.utc)
            if connection.backend == "postgresql"
            else datetime.now(timezone.utc).isoformat()
        )
        if connection.backend == "postgresql" and isinstance(date_finished, str) and date_finished:
            try:
                date_finished = date.fromisoformat(date_finished[:10])
            except ValueError:
                pass
        elif connection.backend == "sqlite" and hasattr(date_finished, "isoformat"):
            date_finished = date_finished.isoformat()
        connection.execute(
            """
            UPDATE user_library
            SET personal_rating = ?, private_notes = ?, key_takeaways = ?,
                practical_application = ?, date_finished = ?, updated_at = ?
            WHERE user_id = ? AND book_id = ?
            """,
            (
                rating_value, str(private_notes or "").strip(),
                str(key_takeaways or "").strip(), str(practical_application or "").strip(),
                date_finished, now, int(user_id), str(book_id),
            ),
        )
        connection.execute(
            """
            INSERT INTO user_reviews (user_id, book_id, rating, review_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, book_id) DO UPDATE SET
                rating = excluded.rating, review_text = excluded.review_text, updated_at = excluded.updated_at
            """,
            (int(user_id), str(book_id), rating_value, str(review_text or "").strip(), now, now),
        )


def get_reading_journal(user_id, book_id):
    with get_user_connection() as connection:
        row = connection.execute(
            """
            SELECT l.personal_rating, l.private_notes, l.key_takeaways,
                   l.practical_application, l.date_finished, r.review_text
            FROM user_library l
            LEFT JOIN user_reviews r
              ON r.user_id = l.user_id AND r.book_id = l.book_id
            WHERE l.user_id = ? AND l.book_id = ?
            """,
            (int(user_id), str(book_id)),
        ).fetchone()
    return dict(row) if row else {}


def get_review_publication(user_id, book_id):
    with get_user_connection() as connection:
        row = connection.execute(
            """
            SELECT is_published, published_at
            FROM user_reviews
            WHERE user_id = ? AND book_id = ?
            """,
            (int(user_id), str(book_id)),
        ).fetchone()
    return dict(row) if row else {"is_published": 0, "published_at": None}


def set_review_publication(user_id, book_id, publish):
    with get_user_connection() as connection:
        now = (
            datetime.now(timezone.utc)
            if connection.backend == "postgresql"
            else datetime.now(timezone.utc).isoformat()
        )
        row = connection.execute(
            "SELECT rating, review_text FROM user_reviews WHERE user_id = ? AND book_id = ?",
            (int(user_id), str(book_id)),
        ).fetchone()
        if row is None:
            return False, "Save your rating or review first."
        has_content = row["rating"] is not None or bool(str(row["review_text"] or "").strip())
        if publish and not has_content:
            return False, "Add a rating or written review before publishing."
        connection.execute(
            """
            UPDATE user_reviews
            SET is_published = ?, published_at = ?, updated_at = ?
            WHERE user_id = ? AND book_id = ?
            """,
            (1 if publish else 0, now if publish else None, now, int(user_id), str(book_id)),
        )
    return True, "Published to Reader Insights." if publish else "Community sharing turned off."


def save_reading_reflection_with_visibility(
    user_id, book_id, personal_rating=None, review_text="", key_takeaways="",
    practical_application="", private_notes="", date_finished=None, publish=False,
):
    """Save the private reading journal and community visibility in one transaction-like workflow."""
    save_reading_journal(
        user_id, book_id, personal_rating, review_text, key_takeaways,
        practical_application, private_notes, date_finished,
    )
    ok, message = set_review_publication(user_id, book_id, bool(publish))
    # Re-read persisted state so the UI and Reader Insights use the same database truth.
    publication = get_review_publication(user_id, book_id)
    return ok, message, publication


def get_community_reviews(book_id=None):
    query = """
        SELECT r.book_id, r.rating, r.review_text, r.published_at, r.updated_at,
               u.full_name
        FROM user_reviews r
        JOIN users u ON u.user_id = r.user_id
        WHERE r.is_published = 1
    """
    params = []
    if book_id is not None:
        query += " AND r.book_id = ?"
        params.append(str(book_id))
    query += " ORDER BY COALESCE(r.published_at, r.updated_at) DESC"
    with get_user_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def get_reader_insight_summary():
    with get_user_connection() as connection:
        rows = connection.execute(
            """
            SELECT book_id, COUNT(*) AS contributor_count,
                   COUNT(rating) AS rating_count, AVG(rating) AS reader_rating,
                   SUM(CASE WHEN TRIM(COALESCE(review_text,'')) <> '' THEN 1 ELSE 0 END) AS written_review_count
            FROM user_reviews
            WHERE is_published = 1
            GROUP BY book_id
            """
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def get_library_activity_summary():
    with get_user_connection() as connection:
        rows = connection.execute(
            """
            SELECT book_id, COUNT(*) AS saved_count,
                   SUM(CASE WHEN reading_status = 'Want to Read' THEN 1 ELSE 0 END) AS want_count,
                   SUM(CASE WHEN reading_status = 'Currently Reading' THEN 1 ELSE 0 END) AS reading_count,
                   SUM(CASE WHEN reading_status = 'Finished' THEN 1 ELSE 0 END) AS finished_count
            FROM user_library
            GROUP BY book_id
            """
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def save_leadwise_feedback(user, feedback_type, subject, message, contact_email):
    message = str(message or "").strip()
    if not message:
        return False
    user_id = int(user["user_id"]) if user else None
    with get_user_connection() as connection:
        now = (
            datetime.now(timezone.utc)
            if connection.backend == "postgresql"
            else datetime.now(timezone.utc).isoformat()
        )
        connection.execute(
            """
            INSERT INTO leadwise_feedback
                (user_id, feedback_type, subject, message, contact_email, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, str(feedback_type), str(subject or "").strip(), message,
             normalize_email(contact_email) if contact_email else None, now),
        )
    return True


# =========================================================
# ASK LEADWISE — ASSISTANT & INQUIRY FOUNDATION
# =========================================================

def classify_ask_leadwise_intent(query):
    """Lightweight deterministic intent routing; no external LLM is required."""
    q = str(query or "").strip().lower()
    if any(term in q for term in ["suggest a book", "add a book", "book suggestion", "missing book"]):
        return "book_suggestion"
    if any(term in q for term in ["wrong information", "incorrect information", "data correction", "correct this book"]):
        return "data_correction"
    if any(term in q for term in ["compare", "difference between", "versus", " vs "]):
        return "comparison"
    if any(term in q for term in ["bug", "feedback", "feature", "website", "app problem"]):
        return "leadwise_feedback"
    if any(term in q for term in ["contact", "inquiry", "email", "support"]):
        return "general_inquiry"
    return "book_discovery"


def log_ask_leadwise_query(user, query_text, intent, results):
    query_text = str(query_text or "").strip()
    if not query_text:
        return
    user_id = int(user["user_id"]) if user else None
    result_count = int(len(results)) if isinstance(results, pd.DataFrame) else 0
    top_book_id = None
    if isinstance(results, pd.DataFrame) and not results.empty and "book_id" in results.columns:
        top_book_id = str(results.iloc[0]["book_id"])
    with get_user_connection() as connection:
        connection.execute(
            """
            INSERT INTO ask_leadwise_queries
                (user_id, query_text, intent, result_count, top_book_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, query_text, str(intent), result_count, top_book_id,
                (
                    datetime.now(timezone.utc)
                    if connection.backend == "postgresql"
                    else datetime.now(timezone.utc).isoformat()
                ),
            ),
        )


def save_leadwise_inquiry(
    user, inquiry_type, full_name, email, subject, message,
    suggested_title="", suggested_author="", suggested_isbn_or_link="",
    related_book_id=None,
):
    message = str(message or "").strip()
    if not message:
        return False, "Please enter a message."
    clean_email = normalize_email(email) if email else ""
    if clean_email and ("@" not in clean_email or "." not in clean_email.split("@")[-1]):
        return False, "Please enter a valid email address or leave it blank."
    user_id = int(user["user_id"]) if user else None
    with get_user_connection() as connection:
        connection.execute(
            """
            INSERT INTO leadwise_inquiries
                (user_id, inquiry_type, full_name, email, subject, message,
                 suggested_title, suggested_author, suggested_isbn_or_link,
                 related_book_id, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'New')
            """,
            (
                user_id, str(inquiry_type), str(full_name or "").strip(),
                clean_email or None, str(subject or "").strip(), message,
                str(suggested_title or "").strip(), str(suggested_author or "").strip(),
                str(suggested_isbn_or_link or "").strip(),
                str(related_book_id) if related_book_id else None,
                (
                    datetime.now(timezone.utc)
                    if connection.backend == "postgresql"
                    else datetime.now(timezone.utc).isoformat()
                ),
            ),
        )
    return True, "Your inquiry has been saved to LeadWise."


def ask_leadwise(query, top_n=5):
    """Grounded assistant response using the production TF-IDF retrieval layer."""
    query = str(query or "").strip()
    if not query:
        return "book_discovery", pd.DataFrame(), "Tell LeadWise what you are looking for."
    intent = classify_ask_leadwise_intent(query)

    # Operational intents are routed to structured forms rather than fabricated answers.
    if intent in {"book_suggestion", "data_correction", "leadwise_feedback", "general_inquiry"}:
        messages = {
            "book_suggestion": "I can help you suggest a book. Use the Suggest a Book form below so the request can be reviewed.",
            "data_correction": "I can help you report book information. Use the Data Correction form below and include the evidence or source when available.",
            "leadwise_feedback": "I can collect feedback about LeadWise. Use the Feedback / Support form below.",
            "general_inquiry": "I can route your inquiry to LeadWise. Use the General Inquiry form below.",
        }
        return intent, pd.DataFrame(), messages[intent]

    results = retrieve_by_query(query, top_n=top_n)
    if results.empty:
        return intent, results, (
            "I could not find a grounded catalog match for that request. "
            "Try different leadership or management terms, or submit a book suggestion if the publication is missing."
        )
    if intent == "comparison":
        message = (
            "I found catalog matches related to your comparison request. "
            "Open the books below, or use Compare Books for the full side-by-side evidence view."
        )
    else:
        message = (
            "These are the strongest content matches I found in the LeadWise catalog. "
            "Similarity reflects textual/content evidence, not book quality or an expert rating."
        )
    return intent, results, message


def _append_leadwise_chat(role, content, **metadata):
    history = st.session_state.setdefault("leadwise_chat_history", [])
    item = {"role": role, "content": str(content)}
    item.update(metadata)
    history.append(item)


def _assistant_book_summary(book):
    """Safely summarize one chatbot result, including stale session-state values."""
    if isinstance(book, pd.Series):
        book = book.to_dict()

    if not isinstance(book, dict):
        return None, None

    title = safe_display_value(book.get("canonical_title"), "Untitled")
    authors = format_list_value(book.get("authors"), "Author unavailable", limit=2)
    year = format_year(book.get("publication_year"))
    topic = safe_display_value(book.get("topic_label"), "")
    parts = [authors]
    if year and year != "Not available":
        parts.append(str(year))
    if topic:
        parts.append(topic)
    return title, " · ".join([p for p in parts if p])


def _set_chat_mode(mode, assistant_message=None):
    st.session_state["leadwise_chat_mode"] = mode
    if assistant_message:
        _append_leadwise_chat("assistant", assistant_message)


def _leadwise_faq_answer(query):
    """Return a grounded FAQ response when a common LeadWise question is detected."""
    q = re.sub(r"\s+", " ", str(query or "").lower()).strip()

    faq_rules = [
        (
            ["what is leadwise", "about leadwise", "what does leadwise do"],
            "LeadWise is a leadership and management book-intelligence application. "
            "It helps readers discover and compare books, manage a personal reading library, "
            "review reader insights, and explore content-based recommendations."
        ),
        (
            ["how does recommendation", "how do recommendations", "recommendation work", "similarity score"],
            "LeadWise recommendations are content-based. The production recommender uses TF-IDF "
            "text features and cosine similarity to identify books with related content. "
            "A similarity score measures textual/content relevance; it is not a quality score, "
            "expert rating, or probability that you will like a book."
        ),
        (
            ["is this ai", "use ai", "artificial intelligence", "machine learning"],
            "LeadWise uses data analytics, NLP and machine-learning components for book intelligence. "
            "The production recommendation layer is grounded in the LeadWise catalog using TF-IDF "
            "and cosine similarity. Experimental dimensionality-reduction, clustering and neural-network "
            "work is documented separately in About the Intelligence."
        ),
        (
            ["how many books", "number of books", "books in leadwise", "catalog size"],
            "The frozen LeadWise capstone catalog contains 2,067 book records. Some records have limited "
            "metadata, so LeadWise does not fabricate missing descriptions, prices, ratings or publication details."
        ),
        (
            ["where does data", "data source", "where are the books from", "source of books"],
            "LeadWise's capstone catalog was assembled from collected book-source data and then cleaned, "
            "integrated and deduplicated. The application preserves source metadata where available and "
            "does not invent missing values."
        ),
        (
            ["rating", "reader rating", "source rating"],
            "LeadWise keeps different rating concepts separate: external/source ratings come from the source data, "
            "personal ratings belong to an individual reader, and LeadWise community ratings come from published "
            "reader reflections. They should not be interpreted as the same metric."
        ),
        (
            ["save a book", "my library", "want to read", "currently reading", "finished"],
            "Sign in and use My Library to save books and track Want to Read, Currently Reading, or Finished status. "
            "You can also keep private notes, takeaways, practical applications and a personal rating."
        ),
        (
            ["reader insights", "community review", "community reviews"],
            "Reader Insights contains published community contributions and book-level reader activity. "
            "Private notes, key takeaways, practical-application notes and unpublished reflections remain separate "
            "from public community content."
        ),
        (
            ["account", "sign in", "register", "create account"],
            "Guests can browse LeadWise and use Ask LeadWise. A registered account is used for persistent reader "
            "features such as My Library, reading status, personal ratings and reflections."
        ),
        (
            ["price", "buy book", "purchase"],
            "LeadWise does not currently provide verified commercial price data for the catalog. "
            "When price data is unavailable, the application reports it as unavailable rather than estimating it."
        ),
        (
            ["contact", "message leadwise", "email leadwise", "support"],
            "You can contact LeadWise directly through **Feedback & Contact** in this chatbot. "
            "Choose General Inquiry, Suggest a Book, Book/Data Correction, or LeadWise Feedback and submit the form."
        ),
        (
            ["suggest a book", "missing book", "add a book"],
            "Book suggestions are handled through **Feedback & Contact**. Choose **Suggest a Book**, provide the title "
            "and any author, ISBN or source information you know, and LeadWise will record it for review."
        ),
        (
            ["correct", "correction", "wrong information", "incorrect information", "data error"],
            "Catalog corrections are handled through **Feedback & Contact**. Choose **Book / Data Correction**, "
            "identify the book, and explain which information should be reviewed."
        ),
        (
            ["privacy", "private notes", "who can see"],
            "Private reading notes, key takeaways, practical-application notes and unpublished reflections are intended "
            "to remain private reader data. Community content is published only through the publication workflow."
        ),
    ]

    for phrases, answer in faq_rules:
        if any(phrase in q for phrase in phrases):
            return answer
    return None


def render_ask_leadwise_panel():
    """LeadWise FAQ, support, feedback and contact assistant."""
    current_user = signed_in_user()

    # Clean older chatbot history safely.
    history = st.session_state.get("leadwise_chat_history", [])
    if isinstance(history, list):
        for item in history:
            if isinstance(item, dict) and "books" in item:
                books = item.get("books")
                if not isinstance(books, list):
                    item["books"] = []
                else:
                    item["books"] = [
                        b.to_dict() if isinstance(b, pd.Series) else b
                        for b in books
                        if isinstance(b, (dict, pd.Series))
                    ]

    if "leadwise_chat_history" not in st.session_state:
        st.session_state["leadwise_chat_history"] = [
            {
                "role": "assistant",
                "content": (
                    "Hello! I'm the LeadWise Assistant. Ask me about LeadWise, recommendations, "
                    "My Library, Reader Insights, ratings, privacy, or how the platform works. "
                    "You can also use **Feedback & Contact** to send LeadWise a message, suggest "
                    "a book, report a catalog correction, or submit feedback."
                ),
            }
        ]

    st.session_state.setdefault("leadwise_contact_open", False)

    st.markdown("### Ask LeadWise")
    st.caption("FAQ · Help · Feedback · Contact")

    # One support/action entry point; book discovery remains in Discover Books.
    if st.button("Feedback & Contact", key="chat_feedback_contact", use_container_width=True):
        st.session_state["leadwise_contact_open"] = not st.session_state.get("leadwise_contact_open", False)
        st.rerun()

    chat_box = st.container(height=350, border=False)
    with chat_box:
        for item in st.session_state.get("leadwise_chat_history", []):
            if not isinstance(item, dict):
                continue
            with st.chat_message(item.get("role", "assistant")):
                st.markdown(str(item.get("content", "")))

    with st.form("leadwise_chat_form", clear_on_submit=True):
        query = st.text_input(
            "Message",
            placeholder="Ask a question about LeadWise...",
            label_visibility="collapsed",
            key="leadwise_chat_message",
        )
        sent = st.form_submit_button("Send", use_container_width=True)

    if sent and str(query or "").strip():
        query = str(query).strip()
        _append_leadwise_chat("user", query)

        faq_answer = _leadwise_faq_answer(query)
        intent = classify_ask_leadwise_intent(query)

        if faq_answer:
            response = faq_answer
            results = pd.DataFrame()
            log_intent = "faq"
        elif intent in {"book_suggestion", "data_correction", "leadwise_feedback", "general_inquiry"}:
            st.session_state["leadwise_contact_open"] = True
            results = pd.DataFrame()
            log_intent = intent
            response = {
                "book_suggestion": (
                    "I can record that for LeadWise. I've opened **Feedback & Contact** below. "
                    "Choose **Suggest a Book** and provide the title plus any author, ISBN or source details you know."
                ),
                "data_correction": (
                    "I've opened **Feedback & Contact** below. Choose **Book / Data Correction**, identify the book, "
                    "and describe the information that should be reviewed."
                ),
                "leadwise_feedback": (
                    "Thank you. I've opened **Feedback & Contact** below. Choose **LeadWise Feedback** and send your comments."
                ),
                "general_inquiry": (
                    "I've opened **Feedback & Contact** below. Choose **General Inquiry** to send LeadWise your message."
                ),
            }[intent]
        else:
            # The chatbot is support/FAQ focused. Discovery remains in the dedicated Discover Books experience.
            results = pd.DataFrame()
            log_intent = "help"
            response = (
                "I can answer questions about LeadWise and help with platform support. "
                "For personalized book searching and recommendations, please use **Discover Books**. "
                "You can also ask me about recommendations, ratings, My Library, Reader Insights, privacy, "
                "book suggestions, corrections, feedback, or contacting LeadWise."
            )

        log_ask_leadwise_query(current_user, query, log_intent, results)
        track_event("ask_leadwise_query", page="Ask LeadWise",
                    metadata={"intent": log_intent}, user=current_user)
        _append_leadwise_chat("assistant", response, intent=log_intent)
        st.rerun()

    if st.button("Clear Chat", key="leadwise_clear_chat", use_container_width=True):
        st.session_state["leadwise_chat_history"] = [
            {
                "role": "assistant",
                "content": "Chat cleared. What would you like to know about LeadWise?",
            }
        ]
        st.session_state["leadwise_contact_open"] = False
        st.rerun()

    # Unified feedback/contact/data collection.
    if st.session_state.get("leadwise_contact_open", False):
        st.markdown("#### Feedback & Contact")

        options = [
            "General Inquiry",
            "LeadWise Feedback",
            "Book / Data Correction",
            "Suggest a Book",
        ]
        inquiry_type = st.selectbox(
            "What would you like to send?",
            options,
            key="assistant_inquiry_type_unified",
        )

        default_name = current_user["full_name"] if current_user else ""
        default_email = current_user["email"] if current_user else ""

        with st.form("leadwise_unified_contact_form", clear_on_submit=True):
            full_name = st.text_input(
                "Full name",
                value=default_name,
                placeholder="Your name",
                key="leadwise_contact_name_unified",
            )
            email = st.text_input(
                "Email",
                value=default_email,
                placeholder="you@example.com",
                key="leadwise_contact_email_unified",
            )
            subject = st.text_input(
                "Subject",
                placeholder="What is this about?",
                key="leadwise_contact_subject_unified",
            )

            suggested_title = ""
            suggested_author = ""
            suggested_isbn_or_link = ""

            if inquiry_type == "Suggest a Book":
                suggested_title = st.text_input(
                    "Book title",
                    placeholder="Required",
                    key="leadwise_suggest_title_unified",
                )
                suggested_author = st.text_input(
                    "Author",
                    placeholder="Author if known",
                    key="leadwise_suggest_author_unified",
                )
                suggested_isbn_or_link = st.text_input(
                    "ISBN or source link",
                    placeholder="Optional",
                    key="leadwise_suggest_source_unified",
                )

            if inquiry_type == "Book / Data Correction":
                st.caption("Please identify the affected book in the subject or message and describe the correction.")

            message = st.text_area(
                "Message",
                placeholder="Write your message to LeadWise...",
                height=120,
                key="leadwise_contact_message_unified",
            )

            consent = st.checkbox(
                "I agree that LeadWise may store this information to review and respond to my submission.",
                key="leadwise_contact_consent_unified",
            )

            submit = st.form_submit_button("Send to LeadWise", use_container_width=True)

        if submit:
            if not consent:
                st.warning("Please confirm that LeadWise may store the submitted information.")
            elif not str(full_name or "").strip():
                st.warning("Please enter your name.")
            elif inquiry_type == "Suggest a Book" and not str(suggested_title or "").strip():
                st.warning("Please enter the book title.")
            elif not str(message or "").strip():
                st.warning("Please enter your message.")
            else:
                ok, msg = save_leadwise_inquiry(
                    current_user,
                    inquiry_type,
                    full_name,
                    email,
                    subject,
                    message,
                    suggested_title,
                    suggested_author,
                    suggested_isbn_or_link,
                )
                if ok:
                    track_event("inquiry_submitted", page="Ask LeadWise",
                                metadata={"inquiry_type": inquiry_type}, user=current_user)
                    _append_leadwise_chat(
                        "assistant",
                        (
                            f"Thank you, {str(full_name).strip()}. Your **{inquiry_type}** "
                            "has been recorded with status **New** for LeadWise review."
                        ),
                    )
                    st.session_state["leadwise_contact_open"] = False
                    st.success("Sent to LeadWise.")
                    st.rerun()
                else:
                    st.warning(msg)


def render_floating_ask_leadwise():
    """
    Stable right-side Ask LeadWise renderer.

    The assistant is placed in a dedicated Streamlit right column instead of
    repositioning a Streamlit container with fixed CSS. This avoids the preview
    failure seen in 18.49.1 while keeping the assistant visible beside the app.
    """
    if "leadwise_chat_open" not in st.session_state:
        st.session_state["leadwise_chat_open"] = False

    st.markdown(
        """
        <style>
        /* LeadWise 18.49.6 — fixed-view assistant */
        /* Permanently anchor Ask LeadWise to the browser viewport. */
        div[data-testid="stColumn"]:has(.st-key-open_leadwise_chat) {
            position: fixed !important;
            right: 24px !important;
            bottom: 24px !important;
            top: auto !important;
            width: 250px !important;
            min-width: 250px !important;
            z-index: 999999 !important;
            background: transparent !important;
        }

        /* Expanded chatbot stays fixed to the same bottom-right corner. */
        div[data-testid="stColumn"]:has(.st-key-close_leadwise_chat) {
            position: fixed !important;
            right: 24px !important;
            bottom: 24px !important;
            top: auto !important;
            width: 390px !important;
            min-width: 390px !important;
            max-width: calc(100vw - 48px) !important;
            max-height: calc(100vh - 48px) !important;
            overflow-y: auto !important;
            z-index: 999999 !important;
            background: #F8F4EC !important;
            border: 1px solid rgba(216, 168, 78, 0.70) !important;
            border-radius: 18px !important;
            padding: 12px !important;
            box-shadow: 0 18px 55px rgba(11, 31, 51, 0.30) !important;
        }

        /* LeadWise 18.49.6 — high-visibility assistant */
        .leadwise-assistant-note {
            font-size: 0.82rem;
            color: #66788A;
            margin-top: 0.20rem;
            text-align: center;
        }

        /* Style the dedicated Ask LeadWise launcher button. */
        .st-key-open_leadwise_chat button {
            background: linear-gradient(135deg, #102A43 0%, #0B1F33 100%) !important;
            color: #FFFFFF !important;
            border: 2px solid #D8A84E !important;
            border-radius: 999px !important;
            min-height: 3.2rem !important;
            font-weight: 800 !important;
            font-size: 1rem !important;
            box-shadow: 0 10px 28px rgba(11, 31, 51, 0.28) !important;
        }

        .st-key-open_leadwise_chat button p,
        .st-key-open_leadwise_chat button span,
        .st-key-open_leadwise_chat button div {
            color: #FFFFFF !important;
        }

        .st-key-open_leadwise_chat button:hover {
            background: #D8A84E !important;
            color: #0B1F33 !important;
            border-color: #F0C96B !important;
            transform: translateY(-1px);
        }

        .st-key-open_leadwise_chat button:hover p,
        .st-key-open_leadwise_chat button:hover span,
        .st-key-open_leadwise_chat button:hover div {
            color: #0B1F33 !important;
        }

        /* Make the assistant column visually distinct when expanded. */
        .leadwise-chat-heading {
            background: #0B1F33;
            color: #F0C96B;
            border: 1px solid #D8A84E;
            border-radius: 12px;
            padding: 0.55rem 0.75rem;
            margin-bottom: 0.5rem;
            font-weight: 800;
        }

        @media (max-width: 900px) {
            div[data-testid="stHorizontalBlock"] {
                gap: 0.75rem;
            }
            div[data-testid="stColumn"]:has(.st-key-open_leadwise_chat) {
                position: fixed !important;
                right: 12px !important;
                bottom: 12px !important;
                width: 210px !important;
                min-width: 210px !important;
            }
            div[data-testid="stColumn"]:has(.st-key-close_leadwise_chat) {
                position: fixed !important;
                right: 12px !important;
                bottom: 12px !important;
                width: calc(100vw - 24px) !important;
                min-width: 0 !important;
                max-width: calc(100vw - 24px) !important;
                max-height: 82vh !important;
                overflow-y: auto !important;
            }
        }
        
/* 18.54.5 — Hero spacing refinement after removal of duplicate hero KPIs */
.leadwise-hero-content {
    padding-right: 42%;
}

.leadwise-hero-quote {
    left: auto !important;
    right: 2.2rem !important;
    top: auto !important;
    bottom: 2rem !important;
    width: min(18rem, 34%) !important;
    max-width: 18rem !important;
    z-index: 3;
}

@media (max-width: 1100px) {
    .leadwise-hero-content {
        padding-right: 38%;
    }

    .leadwise-hero-quote {
        right: 1.5rem !important;
        bottom: 1.5rem !important;
        width: min(16rem, 34%) !important;
    }
}

@media (max-width: 820px) {
    .leadwise-hero-content {
        padding-right: 0;
    }

    .leadwise-hero-quote {
        position: relative !important;
        left: auto !important;
        right: auto !important;
        top: auto !important;
        bottom: auto !important;
        width: 100% !important;
        max-width: none !important;
        margin-top: 1.25rem;
    }
}

</style>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.get("leadwise_chat_open", False):
        if st.button(
            "Ask LeadWise  •  Chat",
            key="open_leadwise_chat",
            use_container_width=True,
            help="Open the LeadWise Assistant",
        ):
            st.session_state["leadwise_chat_open"] = True
            st.rerun()
        st.markdown(
            '<div class="leadwise-assistant-note">Book intelligence &amp; support</div>',
            unsafe_allow_html=True,
        )
    else:
        top_left, top_right = st.columns([5, 1])
        with top_left:
            st.markdown('<div class="leadwise-chat-heading">Ask LeadWise</div>', unsafe_allow_html=True)
        with top_right:
            if st.button("×", key="close_leadwise_chat", help="Minimize"):
                st.session_state["leadwise_chat_open"] = False
                st.rerun()
        render_ask_leadwise_panel()


def queue_library_save(book_id, reading_status="Want to Read"):
    st.session_state["pending_library_save"] = {
        "book_id": str(book_id),
        "reading_status": reading_status if reading_status in READING_STATUSES else "Want to Read",
    }
    st.session_state["open_auth_panel"] = True


def complete_pending_library_save(user):
    pending = st.session_state.get("pending_library_save")
    if not pending or not user:
        return False
    save_library_book(
        user["user_id"], pending["book_id"], pending.get("reading_status", "Want to Read")
    )
    st.session_state.pop("pending_library_save", None)
    st.session_state.pop("open_auth_panel", None)
    st.session_state["library_flash"] = "The book you selected as a guest was saved to My Library."
    return True


initialize_user_database()

# 18.58.1: safe runtime backend verification.
# This exposes only backend/status labels, never credentials.
with get_user_connection() as _backend_check_connection:
    ACTIVE_DATABASE_BACKEND = _backend_check_connection.backend
POSTGRES_COMPONENT_STATUS = get_postgres_component_status()


# =========================================================
# IMPORT PATH
# =========================================================

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))

import nlp_utils


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="LeadWise | Leadership & Management Book Intelligence",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# THEME
# =========================================================

def apply_leadwise_theme():

    st.markdown(
        """
<style>

:root {
    --navy: #0B1F33;
    --midnight: #102A43;
    --gold: #D8A84E;
    --softgold: #F0C96B;
    --cream: #F8F4EC;
    --white: #FFFFFF;
    --slate: #66788A;
    --text: #14213D;
    --green: #19B66A;
}


/* =====================================================
   GLOBAL
   ===================================================== */

.stApp {
    background: #F8F4EC;
    color: #14213D;
}

.block-container {
    max-width: 1500px;
    padding-top: 1.4rem;
    padding-bottom: 3rem;
    padding-left: 2.2rem;
    padding-right: 2.2rem;
}

p {
    color: #334E68;
    line-height: 1.6;
}

h1,
h2,
h3 {
    color: #0B1F33;
}


/* =====================================================
   SIDEBAR
   ===================================================== */

section[data-testid="stSidebar"] {
    background:
        linear-gradient(
            180deg,
            #081A2B 0%,
            #0B1F33 60%,
            #102A43 100%
        );
}

section[data-testid="stSidebar"] * {
    color: #FFFFFF;
}

section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.15);
}

section[data-testid="stSidebar"] label {
    color: #FFFFFF !important;
}


/* =====================================================
   BUTTONS
   ===================================================== */

.stButton > button,
.stFormSubmitButton > button {

    background:
        linear-gradient(
            135deg,
            #D8A84E,
            #F0C96B
        );

    color: #0B1F33;

    border:
        1px solid
        rgba(216,168,78,0.50);

    border-radius: 9px;

    font-weight: 650;

    transition:
        transform 0.15s ease,
        box-shadow 0.15s ease;
}

.stButton > button:hover,
.stFormSubmitButton > button:hover {

    color: #0B1F33;

    border-color: #D8A84E;

    transform: translateY(-1px);

    box-shadow:
        0 6px 18px
        rgba(11,31,51,0.16);
}


/* =====================================================
   INPUTS
   ===================================================== */

div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {

    background: #FFFFFF;
    border-radius: 9px;
}

/* 18.57.2 — Authentication and form input visibility */
div[data-baseweb="input"] input {
    color: #14213D !important;
    -webkit-text-fill-color: #14213D !important;
    caret-color: #14213D !important;
}

div[data-baseweb="input"] input[type="password"] {
    color: #14213D !important;
    -webkit-text-fill-color: #14213D !important;
    caret-color: #14213D !important;
}

div[data-baseweb="input"] input::placeholder {
    color: #66788A !important;
    -webkit-text-fill-color: #66788A !important;
    opacity: 1 !important;
}

div[data-baseweb="textarea"] textarea {
    color: #14213D !important;
    -webkit-text-fill-color: #14213D !important;
    caret-color: #14213D !important;
}

div[data-baseweb="textarea"] textarea::placeholder {
    color: #66788A !important;
    -webkit-text-fill-color: #66788A !important;
    opacity: 1 !important;
}

/* 18.57.3 — Sidebar authentication fields override the global white sidebar text rule.
   Streamlit/BaseWeb may render text inputs through either data-baseweb wrappers or
   stTextInput containers depending on version, so both structures are covered. */
section[data-testid="stSidebar"] div[data-testid="stTextInput"] input,
section[data-testid="stSidebar"] div[data-baseweb="input"] input,
section[data-testid="stSidebar"] input[type="text"],
section[data-testid="stSidebar"] input[type="email"],
section[data-testid="stSidebar"] input[type="password"] {
    color: #14213D !important;
    -webkit-text-fill-color: #14213D !important;
    caret-color: #14213D !important;
}

section[data-testid="stSidebar"] div[data-testid="stTextInput"] div[data-baseweb="input"] > div,
section[data-testid="stSidebar"] div[data-baseweb="input"] > div {
    background-color: #FFFFFF !important;
}

section[data-testid="stSidebar"] div[data-testid="stTextInput"] input::placeholder,
section[data-testid="stSidebar"] div[data-baseweb="input"] input::placeholder,
section[data-testid="stSidebar"] input[type="text"]::placeholder,
section[data-testid="stSidebar"] input[type="email"]::placeholder,
section[data-testid="stSidebar"] input[type="password"]::placeholder {
    color: #66788A !important;
    -webkit-text-fill-color: #66788A !important;
    opacity: 1 !important;
}

/* Chromium/Safari autofill can otherwise replace the LeadWise text/background colors. */
section[data-testid="stSidebar"] input:-webkit-autofill,
section[data-testid="stSidebar"] input:-webkit-autofill:hover,
section[data-testid="stSidebar"] input:-webkit-autofill:focus,
section[data-testid="stSidebar"] input:-webkit-autofill:active {
    -webkit-text-fill-color: #14213D !important;
    caret-color: #14213D !important;
    -webkit-box-shadow: 0 0 0 1000px #FFFFFF inset !important;
    box-shadow: 0 0 0 1000px #FFFFFF inset !important;
    transition: background-color 9999s ease-out 0s;
}

/* Password reveal/visibility control remains visible against the white field. */
section[data-testid="stSidebar"] div[data-testid="stTextInput"] button,
section[data-testid="stSidebar"] div[data-baseweb="input"] button {
    color: #14213D !important;
}


/* =====================================================
   METRICS
   ===================================================== */

div[data-testid="stMetric"] {

    background: rgba(255,255,255,0.97);

    border:
        1px solid
        rgba(216,168,78,0.28);

    border-radius: 12px;

    padding: 1rem;

    box-shadow:
        0 4px 16px
        rgba(11,31,51,0.06);
}


/* =====================================================
   TYPOGRAPHY
   ===================================================== */

.leadwise-eyebrow {

    color: #D8A84E;

    font-size: 0.78rem;
    font-weight: 700;

    letter-spacing: 0.18rem;
    text-transform: uppercase;

    margin-bottom: 0.6rem;
}

.leadwise-page-title {

    color: #0B1F33;

    font-family:
        Georgia,
        "Times New Roman",
        serif;

    font-size: 3rem;
    font-weight: 700;

    line-height: 1.15;

    margin-bottom: 0.5rem;
}

.leadwise-subtitle {

    color: #66788A;

    font-size: 1.05rem;

    line-height: 1.6;

    margin-bottom: 1.4rem;
}

.leadwise-section-title {

    color: #0B1F33;

    font-family:
        Georgia,
        "Times New Roman",
        serif;

    font-size: 1.8rem;
    font-weight: 700;

    line-height: 1.25;

    margin-top: 1.4rem;
    margin-bottom: 0.35rem;
}


/* =====================================================
   HERO
   ===================================================== */

.leadwise-hero {

    position: relative;

    width: 100%;
    min-height: 480px;

    border-radius: 20px;

    overflow: hidden;

    display: flex;
    align-items: center;

    padding:
        3.3rem
        3.4rem;

    margin-bottom: 1.6rem;

    box-shadow:
        0 14px 40px
        rgba(11,31,51,0.18);
}

.leadwise-hero-content {

    position: relative;
    z-index: 2;

    width: 61%;
    max-width: 740px;
}

.leadwise-hero-eyebrow {

    color: #F0C96B;

    font-size: 0.76rem;
    font-weight: 700;

    letter-spacing: 0.17rem;

    margin-bottom: 0.85rem;
}

.leadwise-hero-title {

    color: #FFFFFF;

    font-family:
        Georgia,
        "Times New Roman",
        serif;

    font-size: 4.4rem;
    font-weight: 700;

    line-height: 1;

    margin-bottom: 0.55rem;
}

.leadwise-hero-title span {
    color: #D8A84E;
}

.leadwise-hero-descriptor {

    color: #FFFFFF;

    font-family:
        Georgia,
        "Times New Roman",
        serif;

    font-size: 1.4rem;
    font-weight: 600;

    line-height: 1.35;

    margin-bottom: 1rem;
}

.leadwise-hero-tagline {

    color: #F8F4EC;

    font-size: 1.12rem;
    font-weight: 600;

    line-height: 1.55;

    margin-bottom: 0.55rem;
}

.leadwise-hero-description {

    color: rgba(255,255,255,0.82);

    font-size: 0.93rem;

    line-height: 1.65;

    max-width: 600px;
}

.leadwise-hero-stats {

    display: flex;
    flex-wrap: wrap;

    gap: 1.7rem;

    margin-top: 1.8rem;
}

.leadwise-hero-stat {
    min-width: 90px;
}

.leadwise-hero-stat strong {

    display: block;

    color: #F0C96B;

    font-family:
        Georgia,
        "Times New Roman",
        serif;

    font-size: 1.5rem;

    line-height: 1.15;
}

.leadwise-hero-stat span {

    display: block;

    color: rgba(255,255,255,0.78);

    font-size: 0.72rem;

    margin-top: 0.25rem;
}

.leadwise-hero-quote {

    position: absolute;

    z-index: 2;

    right: 2.2rem;
    bottom: 2.1rem;

    width: 250px;

    padding: 1.2rem 1.3rem;

    background:
        rgba(5,20,34,0.66);

    border:
        1px solid
        rgba(255,255,255,0.16);

    border-radius: 14px;

    color: #FFFFFF;

    font-family:
        Georgia,
        "Times New Roman",
        serif;

    font-size: 0.9rem;

    line-height: 1.55;
}

.leadwise-quote-mark {

    color: #D8A84E;

    font-size: 2.3rem;

    line-height: 0.8;
}

.leadwise-quote-line {

    width: 34px;
    height: 2px;

    background: #D8A84E;

    margin:
        0.8rem
        0
        0.45rem;
}

.leadwise-hero-quote small {
    color: rgba(255,255,255,0.65);
}


/* =====================================================
   TOPIC CARDS
   ===================================================== */

.leadwise-topic-card {

    background: #FFFFFF;

    border:
        1px solid
        rgba(11,31,51,0.08);

    border-radius: 14px;

    padding: 1.15rem;

    min-height: 130px;

    box-shadow:
        0 5px 18px
        rgba(11,31,51,0.06);
}

.leadwise-topic-icon {

    color: #D8A84E;

    font-size: 1.45rem;

    margin-bottom: 0.5rem;
}

.leadwise-topic-name {

    color: #0B1F33;

    font-weight: 700;

    font-size: 0.96rem;
}

.leadwise-topic-description {

    color: #66788A;

    font-size: 0.79rem;

    margin-top: 0.35rem;
}


/* =====================================================
   PIPELINE
   ===================================================== */

.leadwise-pipeline {

    text-align: center;

    padding:
        0.7rem
        0.25rem;
}

.leadwise-pipeline-icon {

    width: 42px;
    height: 42px;

    border-radius: 50%;

    margin:
        0 auto
        0.55rem auto;

    background: #FFF8E7;

    border:
        1px solid
        rgba(216,168,78,0.35);

    display: flex;
    align-items: center;
    justify-content: center;

    color: #D8A84E;

    font-weight: 700;
}

.leadwise-pipeline-title {

    color: #0B1F33;

    font-size: 0.81rem;
    font-weight: 700;
}

.leadwise-pipeline-detail {

    color: #66788A;

    font-size: 0.71rem;

    margin-top: 0.25rem;
}


/* =====================================================
   SIDEBAR STATUS
   ===================================================== */

.leadwise-status-header {

    font-weight: 700;

    margin-bottom: 0.8rem;
}

.leadwise-status-dot {

    display: inline-block;

    width: 9px;
    height: 9px;

    margin-right: 7px;

    border-radius: 50%;

    background: #19B66A;
}

.leadwise-status-label {

    opacity: 0.68;

    font-size: 0.79rem;
}

.leadwise-status-value {

    font-size: 0.88rem;
    font-weight: 700;

    margin-bottom: 0.65rem;
}


/* =====================================================
   PERSONALIZED DISCOVERY PANEL
   ===================================================== */

.leadwise-discovery-panel {

    background:
        linear-gradient(
            135deg,
            rgba(255,255,255,0.98),
            rgba(255,250,239,0.98)
        );

    border:
        1px solid
        rgba(216,168,78,0.25);

    border-radius: 16px;

    padding:
        1.25rem
        1.4rem;

    margin-bottom: 1rem;

    box-shadow:
        0 5px 18px
        rgba(11,31,51,0.05);
}

.leadwise-discovery-panel strong {
    color: #0B1F33;
}


/* =====================================================
   FOOTER
   ===================================================== */

.leadwise-footer {

    color: #66788A;

    font-size: 0.8rem;

    text-align: center;

    margin-top: 3rem;

    padding-top: 1rem;

    border-top:
        1px solid
        rgba(11,31,51,0.10);
}



/* =====================================================
   BOOK INTELLIGENCE CARDS
   ===================================================== */

.leadwise-book-card-title {
    color: #0B1F33;
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1.35rem;
    font-weight: 700;
    line-height: 1.25;
    margin-bottom: 0.25rem;
}

.leadwise-book-meta {
    color: #66788A;
    font-size: 0.82rem;
    line-height: 1.55;
    margin-bottom: 0.45rem;
}

.leadwise-chip {
    display: inline-block;
    background: #FFF8E7;
    color: #805B16;
    border: 1px solid rgba(216,168,78,0.30);
    border-radius: 999px;
    padding: 0.22rem 0.55rem;
    margin: 0 0.25rem 0.25rem 0;
    font-size: 0.72rem;
    font-weight: 650;
}

.leadwise-no-cover {
    min-height: 245px;
    border-radius: 12px;
    border: 1px solid rgba(216,168,78,0.28);
    background:
        linear-gradient(145deg, #102A43 0%, #0B1F33 72%);
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    color: #F8F4EC;
    font-family: Georgia, "Times New Roman", serif;
    padding: 1rem;
}

.leadwise-note {
    background: #FFFFFF;
    border-left: 4px solid #D8A84E;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    margin: 0.5rem 0 1rem 0;
    color: #334E68;
    font-size: 0.85rem;
}

.leadwise-evidence {
    background: rgba(255,255,255,0.92);
    border: 1px solid rgba(11,31,51,0.08);
    border-radius: 12px;
    padding: 1rem;
    height: 100%;
}


/* =====================================================
   RESPONSIVE
   ===================================================== */

@media (max-width: 1100px) {

    .leadwise-hero {

        min-height: 500px;

        padding:
            2.6rem
            2.3rem;
    }

    .leadwise-hero-content {
        width: 72%;
    }

    .leadwise-hero-title {
        font-size: 3.7rem;
    }
}


@media (max-width: 800px) {

    .leadwise-hero {

        min-height: auto;

        padding:
            2.4rem
            1.7rem;
    }

    .leadwise-hero-content {
        width: 100%;
    }

    .leadwise-hero-title {
        font-size: 3rem;
    }

    .leadwise-hero-quote {
        display: none;
    }
}


/* =====================================================
   18.46 MOBILE / TABLET FOUNDATION
   ===================================================== */

@media (max-width: 800px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 1.2rem !important;
    }

    .leadwise-page-title {
        font-size: 2rem !important;
        line-height: 1.12 !important;
    }

    .leadwise-section-title {
        font-size: 1.45rem !important;
    }

    .leadwise-book-card,
    .leadwise-discovery-panel,
    .leadwise-evidence {
        padding: 0.9rem !important;
    }

    div[data-testid="stForm"] button,
    div[data-testid="stButton"] button {
        min-height: 46px;
        font-size: 1rem;
    }

    div[data-testid="stTextArea"] textarea {
        min-height: 150px !important;
        font-size: 16px !important;
    }

    div[data-baseweb="select"] {
        font-size: 16px !important;
    }
}



/* STREAMLIT CHROME */

#MainMenu {
    visibility: hidden;
}

footer {
    visibility: hidden;
}

</style>
        """,
        unsafe_allow_html=True,
    )


apply_leadwise_theme()


# =========================================================
# IMAGE UTILITY
# =========================================================

@st.cache_data
def get_base64_image(image_path_string):

    image_path = Path(image_path_string)

    if not image_path.exists():
        return None

    with open(
        image_path,
        "rb",
    ) as image_file:

        encoded = base64.b64encode(
            image_file.read()
        ).decode("utf-8")

    return encoded


# =========================================================
# PRODUCTION ARTIFACT LOADERS
# =========================================================

@st.cache_resource
def load_model_artifacts():

    matrix = load_npz(
        MODELS_DIR
        / "enriched_tfidf_matrix.npz"
    )

    fitted_vectorizer = joblib.load(
        MODELS_DIR
        / "enriched_tfidf_vectorizer_streamlit.joblib"
    )

    return (
        matrix,
        fitted_vectorizer,
    )


@st.cache_data
def load_grounding_catalog():

    catalog = pd.read_csv(
        DATA_DIR
        / "leadwise_streamlit_catalog.csv"
    )

    catalog = (
        catalog
        .sort_values(
            "matrix_row"
        )
        .reset_index(
            drop=True
        )
    )

    return catalog


# =========================================================
# LOAD ARTIFACTS
# =========================================================

try:

    tfidf_matrix, vectorizer = (
        load_model_artifacts()
    )

    app_catalog = (
        load_grounding_catalog()
    )

except Exception as error:

    st.error(
        "LeadWise could not load its "
        "validated production artifacts."
    )

    st.exception(
        error
    )

    st.stop()


# =========================================================
# RUNTIME VALIDATION
# =========================================================

if (
    tfidf_matrix.shape[0]
    != len(app_catalog)
):

    st.error(
        "Artifact alignment failed: "
        "TF-IDF rows do not match "
        "the catalog."
    )

    st.stop()


if not app_catalog[
    "book_id"
].is_unique:

    st.error(
        "Artifact alignment failed: "
        "book IDs are not unique."
    )

    st.stop()



# =========================================================
# 18.51.3 LIVE CATALOG INTEGRATION
# =========================================================

def _live_safe_text(value):
    if value is None: return ""
    try:
        if pd.isna(value): return ""
    except Exception: pass
    return str(value).strip()

def _ensure_live_catalog_tables(connection):
    if connection.backend == "postgresql":
        required = {
            "live_catalog_books": READER_REQUIRED_SCHEMA["live_catalog_books"],
            "recommendation_book_vectors": READER_REQUIRED_SCHEMA["recommendation_book_vectors"],
            "catalog_book_overrides": READER_REQUIRED_SCHEMA["catalog_book_overrides"],
        }
        problems = validate_required_schema(connection, required)
        if problems:
            raise RuntimeError(
                "LeadWise live catalog schema validation failed: "
                + " | ".join(problems)
            )
        return

    connection.execute("""CREATE TABLE IF NOT EXISTS live_catalog_books (
        live_book_id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL UNIQUE,
        base_book_id TEXT, record_origin TEXT NOT NULL DEFAULT 'admin', title TEXT NOT NULL,
        authors TEXT, description TEXT, publisher TEXT, publication_date TEXT,
        publication_year TEXT, isbn10 TEXT, isbn13 TEXT, page_count TEXT, categories TEXT,
        language TEXT, cover_url TEXT, source_url TEXT, source_type TEXT, source_rating TEXT,
        source_rating_count TEXT, catalog_status TEXT NOT NULL DEFAULT 'Draft',
        intelligence_status TEXT NOT NULL DEFAULT 'Needs Processing', admin_note TEXT,
        created_by INTEGER, updated_by INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS recommendation_book_vectors (
        book_id TEXT PRIMARY KEY, feature_indices_json TEXT NOT NULL,
        feature_values_json TEXT NOT NULL, feature_count INTEGER NOT NULL,
        vector_norm REAL NOT NULL, vectorizer_features INTEGER NOT NULL,
        processed_at TEXT NOT NULL, processing_status TEXT NOT NULL DEFAULT 'Ready',
        processing_error TEXT, vectorizer_version TEXT)""")
    connection.execute("""CREATE TABLE IF NOT EXISTS catalog_book_overrides (
        override_id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL UNIQUE,
        title TEXT, authors TEXT, description TEXT, publisher TEXT, publication_date TEXT,
        publication_year TEXT, isbn10 TEXT, isbn13 TEXT, page_count TEXT, categories TEXT,
        language TEXT, cover_url TEXT, source_url TEXT, source_type TEXT, source_rating TEXT,
        source_rating_count TEXT, catalog_status TEXT NOT NULL DEFAULT 'Published',
        admin_note TEXT, updated_by INTEGER, updated_at TEXT NOT NULL)""")

def build_live_reader_catalog(frozen_catalog):
    base=frozen_catalog.copy()
    with get_user_connection() as connection:
        _ensure_live_catalog_tables(connection)
        overrides=query_dataframe(connection, "SELECT * FROM catalog_book_overrides")
        additions=query_dataframe(
            connection,
            "SELECT * FROM live_catalog_books WHERE catalog_status='Published'",
        )

    if not overrides.empty and "book_id" in base.columns:
        ovmap=overrides.set_index("book_id").to_dict("index")
        drop_indices=[]
        field_map={
            "title":["display_title","title"], "authors":["display_authors","authors"],
            "description":["display_description","description"],
            "publisher":["display_publisher","publisher"],
            "publication_date":["publication_date"],"publication_year":["publication_year"],
            "isbn10":["isbn10"],"isbn13":["isbn13"],
            "page_count":["display_page_count","page_count"],
            "categories":["display_categories","categories"],
            "language":["display_language","language"],
            "cover_url":["display_cover_url","cover_url"],"source_url":["source_url"],
            "source_type":["source_type"],"source_rating":["display_rating","rating","average_rating"],
            "source_rating_count":["rating_count","ratings_count"]}
        for idx,row in base.iterrows():
            bid=_live_safe_text(row.get("book_id")); ov=ovmap.get(bid)
            if not ov: continue
            status=_live_safe_text(ov.get("catalog_status")) or "Published"
            if status != "Published":
                drop_indices.append(idx); continue
            for source,targets in field_map.items():
                value=_live_safe_text(ov.get(source))
                if not value: continue
                for target in targets:
                    if target in base.columns: base.at[idx,target]=value
        if drop_indices: base=base.drop(index=drop_indices)

    if not additions.empty:
        rows=[]
        mapping={"book_id":"book_id","title":"title","canonical_title":"title","display_title":"title",
          "authors":"authors","display_authors":"authors","description":"description",
          "display_description":"description","publisher":"publisher","display_publisher":"publisher",
          "publication_date":"publication_date","publication_year":"publication_year",
          "isbn10":"isbn10","isbn13":"isbn13","page_count":"page_count",
          "display_page_count":"page_count","categories":"categories","subjects":"categories",
          "display_categories":"categories","language":"language","display_language":"language",
          "cover_url":"cover_url","display_cover_url":"cover_url","source_url":"source_url",
          "source_type":"source_type","rating":"source_rating","average_rating":"source_rating",
          "display_rating":"source_rating","rating_count":"source_rating_count",
          "ratings_count":"source_rating_count"}
        for _,r in additions.iterrows():
            rec={col:pd.NA for col in base.columns}
            for target,source in mapping.items():
                if target in rec: rec[target]=r.get(source)
            if "matrix_row" in rec: rec["matrix_row"]=pd.NA
            if "usable_for_recommendation" in rec: rec["usable_for_recommendation"]=False
            if "source_group" in rec: rec["source_group"]="Admin Added"
            if "cluster_label" in rec: rec["cluster_label"]="Not yet classified"
            if "want_to_read_count" in rec: rec["want_to_read_count"]=0
            rows.append(rec)
        if rows: base=pd.concat([base,pd.DataFrame(rows)],ignore_index=True)
    return base.reset_index(drop=True)

# Preserve the frozen production artifacts, then build a runtime recommendation universe
# that can safely include processed Admin-added books without mutating the frozen matrix.
frozen_recommendation_catalog=app_catalog.copy()
app_catalog=build_live_reader_catalog(app_catalog)

def build_runtime_recommendation_universe(base_catalog, base_matrix):
    with get_user_connection() as connection:
        _ensure_live_catalog_tables(connection)

        hidden_rows=connection.execute("""
            SELECT book_id FROM catalog_book_overrides
            WHERE catalog_status IN ('Hidden','Archived','Draft')
        """).fetchall()
        hidden_ids={str(x["book_id"]) for x in hidden_rows}

        ready=query_dataframe(
            connection,
            """
            SELECT l.*,v.feature_indices_json,v.feature_values_json,
                   v.vectorizer_features,v.processed_at
            FROM live_catalog_books l
            JOIN recommendation_book_vectors v ON v.book_id=l.book_id
            WHERE l.catalog_status='Published'
              AND l.intelligence_status='Ready'
              AND v.processing_status='Ready'
            ORDER BY l.live_book_id
            """,
        )

    keep_mask=~base_catalog["book_id"].astype(str).isin(hidden_ids)
    kept_positions=[i for i,keep in enumerate(keep_mask.tolist()) if keep]
    runtime_catalog=base_catalog.loc[keep_mask].copy().reset_index(drop=True)
    runtime_matrix=base_matrix[kept_positions]

    dynamic_rows=[]
    dynamic_vectors=[]
    expected_features=int(base_matrix.shape[1])

    for _,book in ready.iterrows():
        if int(book.get("vectorizer_features") or 0)!=expected_features:
            continue
        try:
            indices=np.asarray(json.loads(book["feature_indices_json"]),dtype=int)
            values=np.asarray(json.loads(book["feature_values_json"]),dtype=float)
            if len(indices)==0 or len(indices)!=len(values):
                continue
            indptr=np.array([0,len(indices)],dtype=int)
            vec=csr_matrix((values,indices,indptr),shape=(1,expected_features))
        except Exception:
            continue

        rec={col:pd.NA for col in runtime_catalog.columns}
        mapping={
            "book_id":"book_id","title":"title","canonical_title":"title","display_title":"title",
            "authors":"authors","display_authors":"authors","description":"description",
            "display_description":"description","publisher":"publisher","display_publisher":"publisher",
            "publication_date":"publication_date","publication_year":"publication_year",
            "isbn10":"isbn10","isbn13":"isbn13","page_count":"page_count",
            "display_page_count":"page_count","categories":"categories","subjects":"categories",
            "display_categories":"categories","language":"language","display_language":"language",
            "cover_url":"cover_url","display_cover_url":"cover_url","source_url":"source_url",
            "source_type":"source_type","rating":"source_rating","average_rating":"source_rating",
            "display_rating":"source_rating","rating_count":"source_rating_count",
            "ratings_count":"source_rating_count"
        }
        for target,source in mapping.items():
            if target in rec:
                rec[target]=book.get(source)
        if "matrix_row" in rec: rec["matrix_row"]=pd.NA
        if "usable_for_recommendation" in rec: rec["usable_for_recommendation"]=True
        if "enriched_zero_vector" in rec: rec["enriched_zero_vector"]=False
        if "source_group" in rec: rec["source_group"]="Admin Added"
        if "cluster_label" in rec: rec["cluster_label"]="Not yet classified"
        if "want_to_read_count" in rec: rec["want_to_read_count"]=0
        dynamic_rows.append(rec)
        dynamic_vectors.append(vec)

    if dynamic_rows:
        runtime_catalog=pd.concat(
            [runtime_catalog,pd.DataFrame(dynamic_rows)],ignore_index=True
        )
        runtime_matrix=vstack([runtime_matrix]+dynamic_vectors,format="csr")

    return runtime_catalog.reset_index(drop=True),runtime_matrix

recommendation_catalog, recommendation_matrix = build_runtime_recommendation_universe(
    frozen_recommendation_catalog,tfidf_matrix
)
# A book is searchable by the recommender only when its runtime TF-IDF row
# contains at least one non-zero feature. Matrix row count alone would also
# include the original zero-vector records.
runtime_nonzero_mask = recommendation_matrix.getnnz(axis=1) > 0
runtime_searchable_vector_count = int(runtime_nonzero_mask.sum())


# Reader synchronization diagnostics. Reader and Admin now read the same
# operational database in cloud, while local development can continue with SQLite.
with get_user_connection() as _catalog_sync_connection:
    _ensure_live_catalog_tables(_catalog_sync_connection)
    _published_row = _catalog_sync_connection.execute(
        "SELECT COUNT(*) AS n FROM live_catalog_books WHERE catalog_status='Published'"
    ).fetchone()
    _draft_row = _catalog_sync_connection.execute(
        "SELECT COUNT(*) AS n FROM live_catalog_books WHERE catalog_status='Draft'"
    ).fetchone()
    READER_PUBLISHED_ADMIN_BOOKS = int(_published_row["n"] or 0)
    READER_DRAFT_ADMIN_BOOKS = int(_draft_row["n"] or 0)

# =========================================================
# CONSTANTS
# =========================================================

CATALOG_BOOKS = len(
    app_catalog
)

USABLE_VECTORS = runtime_searchable_vector_count

CLUSTERED_BOOKS = int(
    app_catalog[
        "topic_cluster"
    ]
    .notna()
    .sum()
)

TOPIC_CLUSTERS = int(
    app_catalog[
        "topic_cluster"
    ]
    .nunique()
)

TFIDF_FEATURES = int(
    tfidf_matrix.shape[1]
)


# =========================================================
# DUPLICATE NORMALIZATION
# =========================================================

def normalize_duplicate_text(
    value,
):

    if pd.isna(value):
        return ""

    value = (
        str(value)
        .lower()
        .strip()
    )

    value = re.sub(
        r"[^\w\s]",
        " ",
        value,
        flags=re.UNICODE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def build_duplicate_key(
    row,
):

    title_key = (
        normalize_duplicate_text(
            row.get(
                "canonical_title",
                "",
            )
        )
    )

    author_key = (
        normalize_duplicate_text(
            row.get(
                "authors",
                "",
            )
        )
    )

    return (
        title_key
        + " || "
        + author_key
    )


if (
    "duplicate_key"
    not in app_catalog.columns
):

    app_catalog[
        "duplicate_key"
    ] = app_catalog.apply(
        build_duplicate_key,
        axis=1,
    )

# 18.51.3.1 — duplicate suppression must also exist on the matrix-aligned catalog.
# Build it independently from the frozen rows so live additions cannot disturb alignment.
if (
    "duplicate_key"
    not in recommendation_catalog.columns
):
    recommendation_catalog[
        "duplicate_key"
    ] = recommendation_catalog.apply(
        build_duplicate_key,
        axis=1,
    )


# =========================================================
# PRODUCTION RETRIEVAL ENGINE
# =========================================================

def retrieve_by_query(
    query,
    top_n=10,
):

    if not isinstance(
        query,
        str,
    ):
        return pd.DataFrame()

    query = query.strip()

    if not query:
        return pd.DataFrame()


    try:

        top_n = int(
            top_n
        )

    except (
        TypeError,
        ValueError,
    ):

        return pd.DataFrame()


    if top_n <= 0:
        return pd.DataFrame()


    query_vector = (
        vectorizer.transform(
            [query]
        )
    )


    if (
        query_vector.nnz
        == 0
    ):

        return pd.DataFrame()


    similarities = (
        cosine_similarity(
            query_vector,
            recommendation_matrix,
        )
        .ravel()
    )


    zero_mask = (
        recommendation_catalog[
            "enriched_zero_vector"
        ]
        .astype(bool)
        .to_numpy()
    )


    similarities[
        zero_mask
    ] = -1.0


    ranked_indices = (
        similarities
        .argsort()[::-1]
    )


    selected_rows = []

    seen_duplicate_keys = set()


    for matrix_index in ranked_indices:

        similarity_score = float(
            similarities[
                matrix_index
            ]
        )


        if similarity_score <= 0:
            break


        catalog_row = (
            recommendation_catalog.iloc[
                matrix_index
            ]
        )


        duplicate_key = (
            catalog_row[
                "duplicate_key"
            ]
        )


        if (
            duplicate_key
            in seen_duplicate_keys
        ):
            continue


        seen_duplicate_keys.add(
            duplicate_key
        )


        result_row = catalog_row.to_dict()

        result_row["rank"] = (
            len(selected_rows) + 1
        )

        result_row["similarity"] = (
            similarity_score
        )

        selected_rows.append(
            result_row
        )


        if (
            len(selected_rows)
            >= top_n
        ):
            break


    return pd.DataFrame(
        selected_rows
    )


# =========================================================
# DISPLAY UTILITIES
# =========================================================

def is_missing(value):

    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass

    text_value = str(value).strip()

    return (
        text_value == ""
        or text_value.lower()
        in {
            "nan",
            "none",
            "null",
            "<na>",
            "[]",
            "{}",
        }
    )


def safe_display_value(
    value,
    fallback="Not available",
):

    if is_missing(value):
        return fallback

    return str(value).strip()


def parse_list_value(value):

    if is_missing(value):
        return []

    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    if isinstance(value, tuple):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]

    text_value = str(value).strip()

    if (
        text_value.startswith("[")
        and text_value.endswith("]")
    ):

        try:
            parsed = ast.literal_eval(
                text_value
            )

            if isinstance(
                parsed,
                (list, tuple),
            ):
                return [
                    str(item).strip()
                    for item in parsed
                    if str(item).strip()
                ]

        except (
            ValueError,
            SyntaxError,
        ):
            pass

    return [text_value]


def format_list_value(
    value,
    fallback="Not available",
    limit=None,
):

    items = parse_list_value(
        value
    )

    if not items:
        return fallback

    if limit is not None:
        items = items[:limit]

    return ", ".join(items)


def format_year(
    book,
):

    year = book.get(
        "publication_year_observed"
    )

    if is_missing(year):
        year = book.get(
            "first_publish_year"
        )

    if is_missing(year):
        return "Year not available"

    try:
        return str(
            int(float(year))
        )

    except (
        TypeError,
        ValueError,
    ):
        return str(year)


def format_rating(
    value,
):

    if is_missing(value):
        return "Rating not available"

    try:
        return f"{float(value):.2f}"

    except (
        TypeError,
        ValueError,
    ):
        return str(value)


def format_integer(
    value,
    fallback="Not available",
):

    if is_missing(value):
        return fallback

    try:
        return f"{int(float(value)):,}"

    except (
        TypeError,
        ValueError,
    ):
        return str(value)


def valid_cover_url(
    value,
):

    if is_missing(value):
        return None

    url = str(value).strip()

    if not url.lower().startswith(
        ("http://", "https://")
    ):
        return None

    return url


def book_label(row):

    title = safe_display_value(
        row.get("canonical_title"),
        "Untitled",
    )

    authors = format_list_value(
        row.get("authors"),
        "Author unavailable",
        limit=2,
    )

    return (
        f"{title} — {authors} "
        f"[{row.get('book_id')}]"
    )


def render_cover(
    book,
    width=None,
):

    cover_url = valid_cover_url(
        book.get("cover_url")
    )

    if cover_url:

        try:
            st.image(
                cover_url,
                width=width,
                use_container_width=(
                    width is None
                ),
            )
            return
        except Exception:
            pass

    title = html.escape(
        safe_display_value(
            book.get("canonical_title"),
            "Book",
        )
    )

    st.markdown(
        (
            '<div class="leadwise-no-cover">'
            '<div>'
            '<div style="font-size:2rem;">◇</div>'
            f'<strong>{title}</strong><br>'
            '<span style="font-size:0.78rem;opacity:0.75;">'
            'No cover available'
            '</span>'
            '</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def render_metadata_chips(
    book,
):

    chip_values = []

    topic = book.get(
        "cluster_label"
    )

    language = book.get(
        "observed_publication_languages"
    )

    country = book.get(
        "earliest_observed_publication_country"
    )

    source = book.get(
        "source_group"
    )

    for value in [
        topic,
        language,
        country,
        source,
    ]:

        if not is_missing(value):
            chip_values.append(
                str(value)
            )

    if not chip_values:
        return

    chips = "".join(
        (
            '<span class="leadwise-chip">'
            f'{html.escape(value)}'
            '</span>'
        )
        for value in chip_values[:4]
    )

    st.markdown(
        chips,
        unsafe_allow_html=True,
    )


def render_book_card(
    book,
    show_similarity=True,
    allow_view_details=False,
    action_context="book",
):

    with st.container(
        border=True
    ):

        cover_col, details_col, score_col = (
            st.columns(
                [1.25, 4.8, 1.25]
            )
        )

        with cover_col:
            render_cover(book)

        with details_col:

            rank = book.get(
                "rank"
            )

            title = safe_display_value(
                book.get(
                    "canonical_title"
                ),
                "Untitled",
            )

            authors = format_list_value(
                book.get(
                    "authors"
                ),
                (
                    "Author information "
                    "not available"
                ),
            )

            title_prefix = ""

            if not is_missing(rank):

                try:
                    title_prefix = (
                        f"{int(rank)}. "
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    pass

            st.markdown(
                (
                    '<div class="leadwise-book-card-title">'
                    f'{html.escape(title_prefix + title)}'
                    '</div>'
                ),
                unsafe_allow_html=True,
            )

            st.markdown(
                f"**Author:** {authors}"
            )

            publisher_value = book.get("publisher")
            if is_missing(publisher_value):
                publisher_value = book.get("publishers")

            publisher_display = format_list_value(
                publisher_value,
                "Not available",
            )

            # Keep cards compact; full evidence remains in Book Details.
            if len(publisher_display) > 90:
                publisher_display = publisher_display[:87].rstrip() + "…"

            st.caption(
                f"Year: {format_year(book)}  •  "
                f"Publisher: {publisher_display}"
            )

            render_metadata_chips(
                book
            )

            description = book.get(
                "description"
            )

            if is_missing(description):

                st.caption(
                    "Synopsis not available "
                    "in the collected dataset."
                )

            else:

                st.write(
                    str(description)
                )

        with score_col:

            if show_similarity:

                similarity = book.get(
                    "similarity"
                )

                if not is_missing(
                    similarity
                ):

                    st.metric(
                        "Content Similarity",
                        f"{float(similarity):.1%}",
                    )

            rating = format_rating(
                book.get(
                    "average_rating"
                )
            )

            if (
                rating
                == "Rating not available"
            ):
                st.caption(rating)
            else:
                st.caption(
                    f"{rating} source rating"
                )

            ratings_count = (
                book.get(
                    "ratings_count"
                )
            )

            if not is_missing(
                ratings_count
            ):
                st.caption(
                    f"{format_integer(ratings_count)} "
                    "source ratings"
                )

            if allow_view_details:
                book_id = str(book.get("book_id"))
                if st.button(
                    "View Details →",
                    key=f"view_details_{action_context}_{book_id}",
                    use_container_width=True,
                ):
                    st.session_state["discover_selected_book_id"] = book_id
                    st.rerun()


# =========================================================
# RESULT RENDERER
# =========================================================

def render_discovery_results(
    results,
    query=None,
):

    if results.empty:

        st.warning(
            "LeadWise could not find books "
            "with positive content similarity "
            "for this request. Try using "
            "different leadership or "
            "management terms."
        )

        return

    st.markdown(
        '<div class="leadwise-section-title">'
        'Recommended Books'
        '</div>',
        unsafe_allow_html=True,
    )

    if query:
        st.caption(
            f'Results for: "{query}"'
        )

    st.caption(
        "Ranked by textual content similarity. "
        "Similarity is not a quality rating, "
        "expert evaluation, or probability."
    )

    for _, book in results.iterrows():
        render_book_card(
            book,
            show_similarity=True,
            allow_view_details=True,
            action_context="recommendation",
        )


# =========================================================
# BOOK-TO-BOOK SIMILARITY
# =========================================================

def recommend_similar_books(
    book_id,
    top_n=6,
):

    matches = recommendation_catalog.index[
        recommendation_catalog["book_id"].astype(str).eq(str(book_id))
    ].tolist()

    if not matches:
        return pd.DataFrame()

    source_index = matches[0]

    if bool(
        recommendation_catalog.iloc[
            source_index
        ].get(
            "enriched_zero_vector",
            False,
        )
    ):
        return pd.DataFrame()

    similarities = (
        cosine_similarity(
            recommendation_matrix[
                source_index
            ],
            recommendation_matrix,
        )
        .ravel()
    )

    similarities[
        source_index
    ] = -1.0

    zero_mask = (
        recommendation_catalog[
            "enriched_zero_vector"
        ]
        .astype(bool)
        .to_numpy()
    )

    similarities[
        zero_mask
    ] = -1.0

    ranked_indices = (
        similarities.argsort()[::-1]
    )

    selected = []
    seen = {
        recommendation_catalog.iloc[
            source_index
        ]["duplicate_key"]
    }

    for matrix_index in ranked_indices:

        score = float(
            similarities[
                matrix_index
            ]
        )

        if score <= 0:
            break

        row = recommendation_catalog.iloc[
            matrix_index
        ]

        duplicate_key = row[
            "duplicate_key"
        ]

        if duplicate_key in seen:
            continue

        seen.add(
            duplicate_key
        )

        result = row.to_dict()
        result["rank"] = (
            len(selected) + 1
        )
        result["similarity"] = score

        selected.append(
            result
        )

        if len(selected) >= top_n:
            break

    return pd.DataFrame(
        selected
    )


def render_page_header(
    eyebrow,
    title,
    subtitle,
):

    st.markdown(
        (
            '<div class="leadwise-eyebrow">'
            f'{html.escape(eyebrow)}'
            '</div>'
            '<div class="leadwise-page-title">'
            f'{html.escape(title)}'
            '</div>'
            '<div class="leadwise-subtitle">'
            f'{html.escape(subtitle)}'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def has_display_value(value):
    """Return False for None/pandas NA/NaN/empty scalar values."""
    if value is None:
        return False
    if isinstance(value,(list,tuple,set,dict)):
        return len(value)>0
    try:
        missing=pd.isna(value)
        if isinstance(missing,(bool,np.bool_)) and missing:
            return False
    except Exception:
        pass
    return str(value).strip() not in {"","<NA>","nan","None","NaT"}


def render_book_details(
    book,
):

    book_id = str(book.get("book_id"))
    current_user = signed_in_user()

    st.markdown(
        '<div class="leadwise-section-title">My Library</div>',
        unsafe_allow_html=True,
    )
    if current_user:
        existing_entry = get_library_entry(current_user["user_id"], book_id)
        default_status = existing_entry["reading_status"] if existing_entry else "Want to Read"
        status_index = READING_STATUSES.index(default_status) if default_status in READING_STATUSES else 0
        lib_status_col, lib_action_col = st.columns([2.2, 1.3])
        with lib_status_col:
            chosen_status = st.selectbox(
                "Reading status", READING_STATUSES, index=status_index,
                key=f"detail_library_status_{book_id}",
            )
        with lib_action_col:
            st.write("")
            st.write("")
            if st.button(
                "Update My Library" if existing_entry else "Save to My Library",
                key=f"detail_library_save_{book_id}", use_container_width=True,
            ):
                save_library_book(current_user["user_id"], book_id, chosen_status)
                st.success(f"Saved as {chosen_status}.")
                st.rerun()
        if existing_entry:
            st.caption(f"Already in My Library · {existing_entry['reading_status']}")
    else:
        st.caption("Save this publication to your personal library by signing in or creating an account.")
        if st.button(
            "Save to My Library", key=f"guest_library_save_{book_id}", use_container_width=True
        ):
            queue_library_save(book_id)
            st.info("Your selected book is remembered. Sign in or create an account in the sidebar to save it.")
            st.rerun()

    cover_col, detail_col = (
        st.columns(
            [1.25, 3.75]
        )
    )

    with cover_col:
        render_cover(book)

    with detail_col:

        st.markdown(
            f"## {safe_display_value(book.get('canonical_title'), 'Untitled')}"
        )

        st.markdown(
            f"**Author:** "
            f"{format_list_value(book.get('authors'), 'Not available')}"
        )

        render_metadata_chips(
            book
        )

        metric_1, metric_2, metric_3 = (
            st.columns(3)
        )

        with metric_1:
            st.metric(
                "Publication Year",
                format_year(book),
            )

        with metric_2:
            st.metric(
                "Source Rating",
                format_rating(
                    book.get(
                        "average_rating"
                    )
                ),
            )

        with metric_3:
            st.metric(
                "Pages",
                format_integer(
                    book.get(
                        "page_count"
                    )
                ),
            )

    st.markdown(
        '<div class="leadwise-section-title">'
        'Synopsis'
        '</div>',
        unsafe_allow_html=True,
    )

    if is_missing(
        book.get(
            "description"
        )
    ):
        st.info(
            "Synopsis not available in the "
            "collected dataset. LeadWise does "
            "not generate or fabricate one."
        )
    else:
        st.write(
            str(
                book.get(
                    "description"
                )
            )
        )

    st.markdown(
        '<div class="leadwise-section-title">'
        'Publication & Evidence'
        '</div>',
        unsafe_allow_html=True,
    )

    evidence_left, evidence_right = (
        st.columns(2)
    )

    with evidence_left:

        st.markdown(
            f"**Publisher:** "
            f"{safe_display_value(book.get('publisher'), safe_display_value(book.get('publishers')))}"
        )

        st.markdown(
            f"**ISBN-10:** "
            f"{format_list_value(book.get('isbn_10'))}"
        )

        st.markdown(
            f"**ISBN-13:** "
            f"{format_list_value(book.get('isbn_13'))}"
        )

        st.markdown(
            f"**Observed publication languages:** "
            f"{safe_display_value(book.get('observed_publication_languages'))}"
        )

    with evidence_right:

        st.markdown(
            f"**Earliest observed publication country:** "
            f"{safe_display_value(book.get('earliest_observed_publication_country'))}"
        )

        st.markdown(
            f"**Topic:** "
            f"{safe_display_value(book.get('cluster_label'))}"
        )

        st.markdown(
            f"**Source:** "
            f"{safe_display_value(book.get('source_group'))}"
        )

        commercial_status = safe_display_value(
            book.get("commercial_metadata_status"),
            "",
        )

        if (
            commercial_status
            == "not_available_from_collected_sources"
            or is_missing(
                book.get(
                    "observed_price"
                )
            )
        ):
            st.markdown(
                "**Price:** Price data not available"
            )
        else:
            st.markdown(
                f"**Observed price:** "
                f"{safe_display_value(book.get('observed_price'))} "
                f"{safe_display_value(book.get('observed_currency'), '')}"
            )

    st.markdown(
        '<div class="leadwise-section-title">'
        'Subjects'
        '</div>',
        unsafe_allow_html=True,
    )

    subjects = parse_list_value(
        book.get(
            "subjects"
        )
    )

    if subjects:
        st.write(
            ", ".join(
                subjects
            )
        )
    else:
        st.caption(
            "Subject metadata not available."
        )

    note = book.get(
        "metadata_quality_note"
    )

    if not is_missing(note):

        st.markdown(
            (
                '<div class="leadwise-note">'
                '<strong>Metadata note:</strong> '
                f'{html.escape(str(note))}'
                '</div>'
            ),
            unsafe_allow_html=True,
        )

# =========================================================
# HERO
# =========================================================

def render_home_hero():

    hero_base64 = (
        get_base64_image(
            str(
                HERO_PATH
            )
        )
    )


    if hero_base64:

        background_style = (
            "background-image:"
            "linear-gradient("
            "90deg,"
            "rgba(5,20,34,0.96) 0%,"
            "rgba(5,20,34,0.84) 36%,"
            "rgba(5,20,34,0.48) 68%,"
            "rgba(5,20,34,0.24) 100%"
            "),"
            f"url('data:image/png;base64,{hero_base64}');"
            "background-size:cover;"
            "background-position:center;"
            "background-repeat:no-repeat;"
        )

    else:

        background_style = (
            "background:"
            "linear-gradient("
            "135deg,"
            "#081A2B 0%,"
            "#0B1F33 55%,"
            "#102A43 100%"
            ");"
        )


    hero_html = (
        f'<div class="leadwise-hero" '
        f'style="{background_style}">'

        '<div class="leadwise-hero-content">'

        '<div class="leadwise-hero-eyebrow">'
        'DISCOVER &nbsp;·&nbsp; '
        'EXPLORE &nbsp;·&nbsp; '
        'LEARN &nbsp;·&nbsp; '
        'GROW'
        '</div>'

        '<div class="leadwise-hero-title">'
        'Lead<span>Wise</span>'
        '</div>'

        '<div class="leadwise-hero-descriptor">'
        'Leadership &amp; Management '
        'Book Intelligence'
        '</div>'

        '<div class="leadwise-hero-tagline">'
        'Discover the right ideas for the '
        'leader you want to become.'
        '</div>'

        '<div class="leadwise-hero-description">'
        f'Explore {CATALOG_BOOKS:,} books '
        'through machine learning, topic '
        'intelligence and personalized '
        'content discovery.'
        '</div>'

        '<div class="leadwise-hero-quote">'

        '<div class="leadwise-quote-mark">'
        '“'
        '</div>'

        '<div>'
        'Leadership development begins '
        'with better questions, better '
        'ideas and continuous learning.'
        '</div>'

        '<div class="leadwise-quote-line">'
        '</div>'

        '<small>'
        'LeadWise'
        '</small>'

        '</div>'
        '</div>'
    )


    st.markdown(
        hero_html,
        unsafe_allow_html=True,
    )


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    if LOGO_PATH.exists():

        st.image(
            str(
                LOGO_PATH
            ),
            use_container_width=True,
        )

    else:

        st.markdown(
            """
<div style="
text-align:center;
padding:0.5rem 0 1rem 0;
">

<div style="
font-family:Georgia,serif;
font-size:2rem;
font-weight:700;
">
Lead<span style="color:#D8A84E;">Wise</span>
</div>

<div style="
font-size:0.75rem;
opacity:0.8;
">
Leadership &amp; Management Book Intelligence
</div>

<div style="
color:#D8A84E;
margin-top:0.3rem;
font-size:0.75rem;
letter-spacing:0.08rem;
">
DR. JAN
</div>

</div>
            """,
            unsafe_allow_html=True,
        )


    st.markdown("---")

    st.markdown(
        "### Navigation"
    )


    page = st.radio(
        "Choose a section",
        [
            "Home",
            "Discover Books",
            "Compare Books",
            "My Library",
            "Reader Insights",
        ],
        label_visibility="collapsed",
        key="leadwise_navigation",
    )


    st.markdown("---")

    current_user = signed_in_user()

    if current_user:
        st.markdown(
            f"**Signed in as**  \n{html.escape(current_user['full_name'])}"
        )
        st.caption(current_user["email"])
        if st.button(
            "Sign Out",
            use_container_width=True,
            key="sidebar_sign_out",
        ):
            sign_out_user()
            st.rerun()
    else:
        st.markdown("**Guest mode**")
        st.caption(
            "Discover, compare, and use Ask LeadWise without an account. "
            "Sign in to use your personal library."
        )
        with st.expander("Sign In / Create Account", expanded=bool(st.session_state.get("open_auth_panel", False))):
            auth_tab_signin, auth_tab_create = st.tabs(
                ["Sign In", "Create Account"]
            )

            with auth_tab_signin:
                with st.form("sidebar_signin_form", clear_on_submit=False):
                    signin_email = st.text_input(
                        "Email",
                        key="signin_email",
                    )
                    signin_password = st.text_input(
                        "Password",
                        type="password",
                        key="signin_password",
                    )
                    signin_submit = st.form_submit_button(
                        "Sign In",
                        use_container_width=True,
                    )
                if signin_submit:
                    user = authenticate_user(signin_email, signin_password)
                    if user:
                        sign_in_user(user)
                        complete_pending_library_save(user)
                        st.success("Signed in successfully.")
                        st.rerun()
                    else:
                        st.error("Email or password is incorrect.")

            with auth_tab_create:
                with st.form("sidebar_create_account_form", clear_on_submit=False):
                    signup_name = st.text_input(
                        "Full name",
                        key="signup_name",
                    )
                    signup_email = st.text_input(
                        "Email",
                        key="signup_email",
                    )
                    signup_password = st.text_input(
                        "Password",
                        type="password",
                        key="signup_password",
                        help="Use at least 8 characters.",
                    )
                    signup_confirm = st.text_input(
                        "Confirm password",
                        type="password",
                        key="signup_confirm",
                    )
                    signup_terms = st.checkbox(
                        "I agree to the LeadWise Terms and Privacy Notice.",
                        key="signup_terms",
                    )
                    signup_submit = st.form_submit_button(
                        "Create Account",
                        use_container_width=True,
                    )
                if signup_submit:
                    if signup_password != signup_confirm:
                        st.error("Passwords do not match.")
                    elif not signup_terms:
                        st.error("Please accept the Terms and Privacy Notice.")
                    else:
                        created, result = create_user(
                            signup_name, signup_email, signup_password
                        )
                        if created:
                            sign_in_user(result)
                            complete_pending_library_save(result)
                            st.success("Account created. You are now signed in.")
                            st.rerun()
                        else:
                            st.error(result)


    st.markdown("---")

    status_html = (
        '<div class="leadwise-status-header">'
        '<span class="leadwise-status-dot">'
        '</span>'
        'System Status'
        '</div>'

        '<div class="leadwise-status-label">'
        'Book Catalog'
        '</div>'

        '<div class="leadwise-status-value">'
        f'{CATALOG_BOOKS:,} books'
        '</div>'

        '<div class="leadwise-status-label">'
        'Usable Vectors'
        '</div>'

        '<div class="leadwise-status-value">'
        f'{USABLE_VECTORS:,}'
        '</div>'

        '<div class="leadwise-status-label">'
        'Topic Clusters'
        '</div>'

        '<div class="leadwise-status-value">'
        f'{TOPIC_CLUSTERS:,}'
        '</div>'

        '<div class="leadwise-status-label">'
        'Clustered Books'
        '</div>'

        '<div class="leadwise-status-value">'
        f'{CLUSTERED_BOOKS:,}'
        '</div>'
    )


    st.markdown(
        status_html,
        unsafe_allow_html=True,
    )


    st.markdown("---")

    st.caption(
        "Developed by Dr. Jan"
    )

    st.caption(
        "Data Analytics Capstone"
    )



# =========================================================
# PAGE ROUTER
# IMPORTANT:
# Every page is isolated inside this router.
# =========================================================

# Main reader experience with a dedicated right-side assistant.
main_col, assistant_col = st.columns([4.7, 1.55], gap="large")

with main_col:
    # =========================================================
    # HOME PAGE
    # =========================================================

    if page == "Home":

        # -----------------------------------------------------
        # HERO
        # -----------------------------------------------------

        render_home_hero()


        # -----------------------------------------------------
        # KPI CARDS
        # -----------------------------------------------------

        metric_1, metric_2, metric_3, metric_4 = (
            st.columns(4)
        )


        with metric_1:

            st.metric(
                "Book Catalog",
                f"{CATALOG_BOOKS:,}",
            )


        with metric_2:

            st.metric(
                "Searchable Vectors",
                f"{USABLE_VECTORS:,}",
            )


        with metric_3:

            st.metric(
                "Topic Clusters",
                f"{TOPIC_CLUSTERS:,}",
            )


        with metric_4:

            st.metric(
                "Clustered Books",
                f"{CLUSTERED_BOOKS:,}",
            )


        # -----------------------------------------------------
        # FEATURED READING — ADMIN CURATION
        # -----------------------------------------------------

        featured_rows = get_active_featured_reading()

        if not featured_rows.empty:
            featured_book_ids = featured_rows["book_id"].astype(str).tolist()
            featured_catalog = app_catalog[
                app_catalog["book_id"].astype(str).isin(featured_book_ids)
            ].copy()

            if not featured_catalog.empty:
                featured_meta = featured_rows.copy()
                featured_meta["book_id"] = featured_meta["book_id"].astype(str)
                featured_catalog["book_id"] = featured_catalog["book_id"].astype(str)
                featured_catalog = featured_meta.merge(
                    featured_catalog,
                    on="book_id",
                    how="inner",
                ).sort_values(
                    ["display_order", "feature_id"],
                    ascending=[True, False],
                )

                st.markdown(
                    '<div class="leadwise-section-title">Featured Reading</div>'
                    '<p>Books selected by the LeadWise editorial team for readers. '
                    'These features are curated by an administrator and are separate '
                    'from personalized machine-learning recommendations.</p>',
                    unsafe_allow_html=True,
                )

                # Show up to three cards per row while retaining every active feature.
                records = [row for _, row in featured_catalog.iterrows()]
                for row_start in range(0, len(records), 3):
                    card_columns = st.columns(3)
                    for card_col, book in zip(
                        card_columns,
                        records[row_start:row_start + 3],
                    ):
                        with card_col:
                            with st.container(border=True):
                                render_cover(book)
                                st.markdown(
                                    f"### {safe_display_value(book.get('canonical_title'), 'Untitled')}"
                                )
                                st.markdown(
                                    f"**{format_list_value(book.get('authors'), 'Author unavailable', limit=2)}**"
                                )

                                feature_message = str(
                                    book.get("feature_message") or ""
                                ).strip()
                                if feature_message:
                                    st.write(feature_message)

                                st.caption(
                                    "Featured by LeadWise · Editorial selection"
                                )

                                featured_book_id = str(book.get("book_id"))
                                if st.button(
                                    "View Book →",
                                    key=f"home_featured_view_{featured_book_id}_{int(book.get('feature_id'))}",
                                    use_container_width=True,
                                ):
                                    st.session_state["home_featured_book_id"] = featured_book_id
                                    track_event(
                                        "featured_book_opened",
                                        page="Home",
                                        book_id=featured_book_id,
                                        metadata={"feature_id": int(book.get("feature_id"))},
                                    )
                                    st.rerun()

                selected_featured_id = st.session_state.get(
                    "home_featured_book_id"
                )
                if selected_featured_id:
                    selected_featured = app_catalog[
                        app_catalog["book_id"].astype(str).eq(
                            str(selected_featured_id)
                        )
                    ]
                    if selected_featured.empty:
                        st.session_state.pop("home_featured_book_id", None)
                    else:
                        st.markdown("---")
                        detail_header_col, detail_close_col = st.columns([5, 1])
                        with detail_header_col:
                            st.markdown(
                                '<div class="leadwise-section-title">'
                                'Featured Book Details'
                                '</div>',
                                unsafe_allow_html=True,
                            )
                        with detail_close_col:
                            if st.button(
                                "Close Details",
                                key="close_home_featured_details",
                                use_container_width=True,
                            ):
                                st.session_state.pop("home_featured_book_id", None)
                                st.rerun()

                        render_book_details(selected_featured.iloc[0])

                st.markdown("---")


        # -----------------------------------------------------
        # HOME QUICK DISCOVERY
        # -----------------------------------------------------

        st.markdown(
            '<div class="leadwise-section-title">'
            'Discover Your Next Book'
            '</div>'

            '<p>'
            'Need a quick recommendation? '
            'Describe one leadership challenge, '
            'management skill or professional goal. '
            'LeadWise will return five content-based '
            'matches.'
            '</p>',
            unsafe_allow_html=True,
        )


        with st.form(
            "home_quick_discovery_form",
            clear_on_submit=False,
        ):

            home_query = (
                st.text_input(
                    "Quick discovery query",
                    placeholder=(
                        "Example: I want to improve "
                        "strategic decision making."
                    ),
                    label_visibility="collapsed",
                )
            )


            home_search_clicked = (
                st.form_submit_button(
                    "Find 5 Books →",
                    use_container_width=True,
                )
            )


        st.caption(
            "Quick Discovery · "
            "Top 5 content matches · "
            "For deeper personalization and catalog "
            "exploration, use Discover Books."
        )


        if home_search_clicked:

            clean_home_query = (
                home_query.strip()
                if isinstance(
                    home_query,
                    str,
                )
                else ""
            )


            if not clean_home_query:

                st.warning(
                    "Describe what you want "
                    "to learn or improve first."
                )

            else:

                with st.spinner(
                    "LeadWise is searching "
                    "the catalog..."
                ):

                    home_results = (
                        retrieve_by_query(
                            clean_home_query,
                            top_n=5,
                        )
                    )


                render_discovery_results(
                    home_results,
                    query=clean_home_query,
                )


        st.markdown("---")


        # -----------------------------------------------------
        # TOPIC PREVIEW
        # -----------------------------------------------------

        st.markdown(
            '<div class="leadwise-section-title">'
            'Explore Leadership Topics'
            '</div>'

            '<p>'
            'Preview areas represented across '
            'the LeadWise leadership and '
            'management catalog.'
            '</p>',
            unsafe_allow_html=True,
        )


        topic_columns = (
            st.columns(4)
        )


        topic_examples = [
            (
                "Team Leadership",
                "Leading and developing teams",
            ),
            (
                "Decision Making",
                "Judgment and managerial choices",
            ),
            (
                "Organizational Behavior",
                "People and organizations",
            ),
            (
                "Strategy & Management",
                "Strategic thinking and execution",
            ),
        ]


        for (
            column,
            (
                topic_name,
                topic_description,
            ),
        ) in zip(
            topic_columns,
            topic_examples,
        ):

            with column:

                st.markdown(
                    (
                        '<div class="leadwise-topic-card">'

                        '<div class="leadwise-topic-icon">'
                        '◈'
                        '</div>'

                        '<div class="leadwise-topic-name">'
                        f'{topic_name}'
                        '</div>'

                        '<div class="leadwise-topic-description">'
                        f'{topic_description}'
                        '</div>'

                        '</div>'
                    ),
                    unsafe_allow_html=True,
                )


        st.markdown("---")


        # -----------------------------------------------------
        # PIPELINE
        # -----------------------------------------------------

        st.markdown(
            '<div class="leadwise-section-title">'
            'How LeadWise Works'
            '</div>'

            '<p>'
            'The discovery system uses the '
            'validated capstone machine-learning '
            'pipeline.'
            '</p>',
            unsafe_allow_html=True,
        )


        pipeline_steps = [
            (
                "Catalog",
                f"{CATALOG_BOOKS:,} books",
            ),
            (
                "Text",
                "Book metadata",
            ),
            (
                "TF-IDF",
                f"{TFIDF_FEATURES:,} features",
            ),
            (
                "Topics",
                f"{TOPIC_CLUSTERS} clusters",
            ),
            (
                "Similarity",
                "Cosine similarity",
            ),
            (
                "Discovery",
                "Ranked matches",
            ),
        ]


        pipeline_columns = (
            st.columns(
                len(
                    pipeline_steps
                )
            )
        )


        for (
            column,
            (
                title,
                detail,
            ),
        ) in zip(
            pipeline_columns,
            pipeline_steps,
        ):

            with column:

                st.markdown(
                    (
                        '<div class="leadwise-pipeline">'

                        '<div class="leadwise-pipeline-icon">'
                        '◇'
                        '</div>'

                        '<div class="leadwise-pipeline-title">'
                        f'{title}'
                        '</div>'

                        '<div class="leadwise-pipeline-detail">'
                        f'{detail}'
                        '</div>'

                        '</div>'
                    ),
                    unsafe_allow_html=True,
                )


    # =========================================================
    # DISCOVER BOOKS
    # Personalized discovery + catalog exploration + details
    # =========================================================

    elif page == "Discover Books":

        render_page_header(
            "Book Discovery",
            "Discover Books",
            (
                "Get personalized recommendations or browse the "
                "catalog, then open detailed book intelligence "
                "without leaving the discovery workspace."
            ),
        )

        # Book Details is contextual rather than a third discovery mode.
        # Selecting a book from either tab opens its detail view here.
        selected_detail_id = st.session_state.get(
            "discover_selected_book_id"
        )

        if selected_detail_id:
            if st.button(
                "← Back to Discover Books",
                key="back_to_discover_books",
            ):
                st.session_state.pop("discover_selected_book_id", None)
                st.rerun()

            selected_matches = app_catalog[
                app_catalog["book_id"].astype(str).eq(
                    str(selected_detail_id)
                )
            ]

            if selected_matches.empty:
                st.warning(
                    "The selected publication could not be found in "
                    "the deployment catalog."
                )
                st.session_state.pop("discover_selected_book_id", None)
            else:
                selected_book = selected_matches.iloc[0]
                render_page_header(
                    "Book Intelligence",
                    safe_display_value(
                        selected_book.get("canonical_title"),
                        "Book Details",
                    ),
                    "Detailed catalog evidence and related books.",
                )
                render_book_details(selected_book)

                similar_books = recommend_similar_books(
                    str(selected_detail_id),
                    top_n=6,
                )

                st.markdown(
                    '<div class="leadwise-section-title">'
                    'Related Books'
                    '</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Related books are ranked by production TF-IDF "
                    "cosine similarity. Similarity is not a quality score."
                )
                if similar_books.empty:
                    st.info(
                        "No positive-similarity related books are "
                        "available for this record."
                    )
                else:
                    for _, related_book in similar_books.iterrows():
                        render_book_card(
                            related_book,
                            show_similarity=True,
                            allow_view_details=True,
                            action_context="related",
                        )

        else:
            discover_tab, explore_tab = st.tabs(
                [
                    "For Me",
                    "Explore Catalog",
                ]
            )

            with discover_tab:
                # IMPORTANT:
                # There is deliberately NO Home quick-search code
                # anywhere inside this page.

                st.markdown(
                    '<div class="leadwise-eyebrow">'
                    'Personalized Discovery'
                    '</div>'

                    '<div class="leadwise-page-title">'
                    'Discover for Me'
                    '</div>'

                    '<div class="leadwise-subtitle">'
                    'Tell LeadWise what you are looking for in your own words, '
                    'then optionally refine the search with leadership area, '
                    'professional goal and experience level.'
                    '</div>',
                    unsafe_allow_html=True,
                )


                st.markdown(
                    """
            <div class="leadwise-discovery-panel">

            <strong>How personalized discovery works</strong><br>

            Your selections are combined with your written request
            to create a richer search query. LeadWise then uses the
            validated production TF-IDF model and cosine similarity
            to retrieve books whose available textual content is most
            closely related to that combined request.

            </div>
                    """,
                    unsafe_allow_html=True,
                )


                # -----------------------------------------------------
                # PERSONALIZATION FORM
                # -----------------------------------------------------

                with st.form(
                    "personalized_discovery_form",
                    clear_on_submit=False,
                ):

                    st.markdown(
                        "#### Tell LeadWise what you're looking for"
                    )

                    st.caption(
                        "Type naturally. You can use this field by itself, "
                        "or combine it with the optional preferences below."
                    )

                    detailed_request = (
                        st.text_area(
                            "What are you looking for?",
                            placeholder=(
                                "Example: I was recently promoted to manager and "
                                "want practical books about motivating an experienced "
                                "team, building trust, improving communication and "
                                "handling conflict."
                            ),
                            height=170,
                            help=(
                                "Describe a challenge, skill you want to develop, "
                                "situation you are facing, or type of leadership or "
                                "management book you want to read."
                            ),
                        )
                    )

                    st.markdown(
                        "#### Optional preferences"
                    )

                    preference_col_1, preference_col_2 = (
                        st.columns(2)
                    )


                    with preference_col_1:

                        leadership_area = (
                            st.selectbox(
                                "Primary area of interest",
                                [
                                    "No specific area",
                                    "Leadership",
                                    "Team Leadership",
                                    "Communication",
                                    "Decision Making",
                                    "Strategic Thinking",
                                    "Management",
                                    "Organizational Behavior",
                                    "Innovation",
                                    "Entrepreneurship",
                                ],
                            )
                        )


                        experience_level = (
                            st.selectbox(
                                "Experience or learning level",
                                [
                                    "No specific level",
                                    "Emerging Leader",
                                    "Middle Manager",
                                    "Senior Leader",
                                    "Executive",
                                    "Entrepreneur",
                                    "Student or Researcher",
                                ],
                            )
                        )


                    with preference_col_2:

                        professional_goal = (
                            st.selectbox(
                                "Professional goal",
                                [
                                    "No specific goal",
                                    "Develop leadership skills",
                                    "Solve a workplace challenge",
                                    "Manage a team effectively",
                                    "Improve decision making",
                                    "Improve communication",
                                    "Develop strategic thinking",
                                    "Prepare for a management role",
                                    "Support academic or professional learning",
                                ],
                            )
                        )


                        result_count = (
                            st.selectbox(
                                "Number of recommendations",
                                [
                                    5,
                                    10,
                                    15,
                                    20,
                                ],
                                index=1,
                            )
                        )


                    personalized_clicked = (
                        st.form_submit_button(
                            "Discover Books for Me →",
                            use_container_width=True,
                        )
                    )


                st.caption(
                    "Your written request can be used on its own. Optional selections "
                    "add context to the same TF-IDF content search; they are not an "
                    "assessment of your ability."
                )


                # -----------------------------------------------------
                # PERSONALIZED RETRIEVAL
                # -----------------------------------------------------

                if personalized_clicked:

                    query_parts = []


                    if (
                        leadership_area
                        != "No specific area"
                    ):

                        query_parts.append(
                            leadership_area
                        )


                    if (
                        professional_goal
                        != "No specific goal"
                    ):

                        query_parts.append(
                            professional_goal
                        )


                    if (
                        experience_level
                        != "No specific level"
                    ):

                        query_parts.append(
                            experience_level
                        )


                    if (
                        isinstance(
                            detailed_request,
                            str,
                        )
                        and detailed_request.strip()
                    ):

                        query_parts.append(
                            detailed_request.strip()
                        )


                    personalized_query = (
                        ". ".join(
                            query_parts
                        )
                    )


                    if not personalized_query:

                        st.warning(
                            "Select at least one preference "
                            "or describe what you want to "
                            "learn, improve or solve."
                        )

                    else:

                        with st.spinner(
                            "LeadWise is building your "
                            "personalized discovery results..."
                        ):

                            personalized_results = (
                                retrieve_by_query(
                                    personalized_query,
                                    top_n=result_count,
                                )
                            )


                        st.session_state["personalized_results"] = (
                            personalized_results
                        )
                        st.session_state["personalized_query"] = (
                            personalized_query
                        )

                saved_personalized_results = st.session_state.get(
                    "personalized_results"
                )
                saved_personalized_query = st.session_state.get(
                    "personalized_query"
                )

                if isinstance(saved_personalized_results, pd.DataFrame):
                    render_discovery_results(
                        saved_personalized_results,
                        query=saved_personalized_query,
                    )



            with explore_tab:
                render_page_header(
                    "Catalog",
                    "Book Explorer",
                    (
                        "Search, filter and browse the "
                        "final LeadWise deployment catalog."
                    ),
                )

                sync_left, sync_right = st.columns([4, 1])
                with sync_left:
                    st.caption(
                        f"Live catalog sync: {READER_PUBLISHED_ADMIN_BOOKS:,} published "
                        f"Admin-added book(s) loaded · {READER_DRAFT_ADMIN_BOOKS:,} Draft."
                    )
                with sync_right:
                    if st.button("Refresh Catalog", use_container_width=True, key="refresh_live_catalog"):
                        st.rerun()

                search_col, topic_col, source_col = (
                    st.columns(
                        [2.2, 1.4, 1.4]
                    )
                )

                with search_col:
                    explorer_query = st.text_input(
                        "Search title, author or subject",
                        placeholder=(
                            "Example: communication, "
                            "Peter Drucker, strategy..."
                        ),
                    )

                topic_options = [
                    "All topics"
                ] + sorted(
                    [
                        str(value)
                        for value in app_catalog[
                            "cluster_label"
                        ].dropna().unique()
                    ]
                )

                with topic_col:
                    explorer_topic = st.selectbox(
                        "Topic",
                        topic_options,
                    )

                source_options = [
                    "All sources"
                ] + sorted(
                    [
                        str(value)
                        for value in app_catalog[
                            "source_group"
                        ].dropna().unique()
                    ]
                )

                with source_col:
                    explorer_source = st.selectbox(
                        "Source",
                        source_options,
                    )

                explorer = app_catalog.copy()

                if explorer_query.strip():

                    needle = explorer_query.strip().lower()

                    searchable = (
                        explorer[
                            "canonical_title"
                        ].fillna("").astype(str)
                        + " "
                        + explorer[
                            "authors"
                        ].fillna("").astype(str)
                        + " "
                        + explorer[
                            "subjects"
                        ].fillna("").astype(str)
                    ).str.lower()

                    explorer = explorer[
                        searchable.str.contains(
                            re.escape(needle),
                            regex=True,
                            na=False,
                        )
                    ]

                if explorer_topic != "All topics":
                    explorer = explorer[
                        explorer[
                            "cluster_label"
                        ].astype(str).eq(
                            explorer_topic
                        )
                    ]

                if explorer_source != "All sources":
                    explorer = explorer[
                        explorer[
                            "source_group"
                        ].astype(str).eq(
                            explorer_source
                        )
                    ]

                st.caption(
                    f"{len(explorer):,} matching books"
                )

                explorer = (
                    explorer
                    .sort_values(
                        [
                            "want_to_read_count",
                            "canonical_title",
                        ],
                        ascending=[
                            False,
                            True,
                        ],
                        na_position="last",
                    )
                    .head(30)
                )

                if explorer.empty:
                    st.info(
                        "No books match the current filters."
                    )
                else:
                    for _, book in explorer.iterrows():
                        render_book_card(
                            book,
                            show_similarity=False,
                            allow_view_details=True,
                            action_context="catalog",
                        )

                    if len(explorer) == 30:
                        st.caption(
                            "Showing the first 30 matching "
                            "records. Refine the filters "
                            "to narrow the catalog."
                        )




    # =========================================================
    # COMPARE BOOKS
    # =========================================================

    elif page == "Compare Books":

        render_page_header(
            "Comparative Intelligence",
            "Compare Books",
            (
                "Compare two publications using bibliographic metadata, "
                "reader evidence and production-model content similarity."
            ),
        )

        compare_catalog = (
            app_catalog
            .sort_values("canonical_title")
            .reset_index(drop=True)
        )

        compare_labels = {
            book_label(row): row["book_id"]
            for _, row in compare_catalog.iterrows()
        }
        labels = list(compare_labels.keys())

        selector_1, selector_2 = st.columns(2)
        with selector_1:
            compare_label_1 = st.selectbox(
                "Book A", labels, index=0, key="compare_book_a"
            )
        with selector_2:
            compare_label_2 = st.selectbox(
                "Book B", labels, index=(1 if len(labels) > 1 else 0),
                key="compare_book_b",
            )

        book_a = app_catalog[
            app_catalog["book_id"].eq(compare_labels[compare_label_1])
        ].iloc[0]
        book_b = app_catalog[
            app_catalog["book_id"].eq(compare_labels[compare_label_2])
        ].iloc[0]

        if book_a["book_id"] == book_b["book_id"]:
            st.warning("Choose two different books for comparison.")
        else:

            def comparison_rating_evidence(book):
                rating = book.get("average_rating")
                count = book.get("ratings_count")
                try:
                    rating_value = float(rating) if not is_missing(rating) else None
                except (TypeError, ValueError):
                    rating_value = None
                try:
                    count_value = int(float(count)) if not is_missing(count) else 0
                except (TypeError, ValueError):
                    count_value = 0

                if rating_value is None:
                    return "Not available", count_value, "No source-rating evidence available"
                if count_value < 5:
                    evidence = "Very limited rating sample"
                elif count_value < 25:
                    evidence = "Limited rating sample"
                elif count_value < 100:
                    evidence = "Moderate rating sample"
                else:
                    evidence = "Larger rating sample"
                return f"{rating_value:.2f} / 5", count_value, evidence

            def comparison_content_evidence(book):
                parts = []
                topic = safe_display_value(book.get("cluster_label"), "")
                subjects = format_list_value(book.get("subjects"))
                description = book.get("description")
                if topic:
                    parts.append(f"Model topic: {topic}.")
                if subjects and subjects != "Not available":
                    parts.append(f"Catalog subjects: {subjects}.")
                if not is_missing(description):
                    parts.append("A source synopsis is available for this publication.")
                else:
                    parts.append("A source synopsis is not available in the deployment catalog.")
                return " ".join(parts)

            def clean_compare_metadata(value, fallback="Not available"):
                """Render list-like CSV fields as reader-friendly text."""
                return format_list_value(value, fallback=fallback)

            def normalized_terms(value):
                return {
                    str(item).strip().casefold(): str(item).strip()
                    for item in parse_list_value(value)
                    if str(item).strip()
                }

            def leadwise_content_comparison(left, right):
                left_subjects = normalized_terms(left.get("subjects"))
                right_subjects = normalized_terms(right.get("subjects"))
                shared_keys = sorted(set(left_subjects) & set(right_subjects))
                shared_subjects = [left_subjects[key] for key in shared_keys]

                topic_a = safe_display_value(left.get("cluster_label"), "")
                topic_b = safe_display_value(right.get("cluster_label"), "")

                statements = []
                if topic_a and topic_b:
                    if topic_a.casefold() == topic_b.casefold():
                        statements.append(
                            f"Both publications are assigned to the model topic “{topic_a}”."
                        )
                    else:
                        statements.append(
                            f"The model places Book A in “{topic_a}” and Book B in “{topic_b}”."
                        )

                if shared_subjects:
                    preview = ", ".join(shared_subjects[:6])
                    statements.append(
                        f"Their catalog metadata shares the following subject evidence: {preview}."
                    )
                else:
                    statements.append(
                        "No exact shared catalog-subject labels were identified between these two records."
                    )

                return " ".join(statements)

            rating_a, rating_count_a, evidence_a = comparison_rating_evidence(book_a)
            rating_b, rating_count_b, evidence_b = comparison_rating_evidence(book_b)

            cover_a, cover_b = st.columns(2)
            with cover_a:
                render_cover(book_a, width=220)
                st.markdown(f"### {book_a['canonical_title']}")
                st.caption(format_list_value(book_a.get("authors")))
            with cover_b:
                render_cover(book_b, width=220)
                st.markdown(f"### {book_b['canonical_title']}")
                st.caption(format_list_value(book_b.get("authors")))

            st.markdown(
                '<div class="leadwise-section-title">Reader Evidence</div>',
                unsafe_allow_html=True,
            )
            rating_col_a, rating_col_b = st.columns(2)
            with rating_col_a:
                st.metric("Book A · Source Rating", rating_a)
                if rating_a == "Not available":
                    st.caption("No source rating is available for this publication.")
                else:
                    st.caption(f"{rating_count_a:,} source ratings · {evidence_a}")
                st.caption(
                    "Want to read: " + format_integer(book_a.get("want_to_read_count"))
                    + "  •  Already read: " + format_integer(book_a.get("already_read_count"))
                )
            with rating_col_b:
                st.metric("Book B · Source Rating", rating_b)
                if rating_b == "Not available":
                    st.caption("No source rating is available for this publication.")
                else:
                    st.caption(f"{rating_count_b:,} source ratings · {evidence_b}")
                st.caption(
                    "Want to read: " + format_integer(book_b.get("want_to_read_count"))
                    + "  •  Already read: " + format_integer(book_b.get("already_read_count"))
                )

            st.info(
                "Reader evidence is shown only when present in the source catalog. "
                "A missing rating is left unavailable rather than estimated. "
                "Source ratings and readership counts are separate from future LeadWise community reviews."
            )

            comparison_rows = [
                ("Authors", clean_compare_metadata(book_a.get("authors")), clean_compare_metadata(book_b.get("authors"))),
                ("Publication year", format_year(book_a), format_year(book_b)),
                ("Publisher", clean_compare_metadata(book_a.get("publisher"), clean_compare_metadata(book_a.get("publishers"))), clean_compare_metadata(book_b.get("publisher"), clean_compare_metadata(book_b.get("publishers")))),
                ("Topic", safe_display_value(book_a.get("cluster_label")), safe_display_value(book_b.get("cluster_label"))),
                ("Source rating", rating_a, rating_b),
                ("Source rating count", f"{rating_count_a:,}" if rating_a != "Not available" else "Not available", f"{rating_count_b:,}" if rating_b != "Not available" else "Not available"),
                ("Rating evidence", evidence_a, evidence_b),
                ("Want to read", format_integer(book_a.get("want_to_read_count")), format_integer(book_b.get("want_to_read_count"))),
                ("Already read", format_integer(book_a.get("already_read_count")), format_integer(book_b.get("already_read_count"))),
                ("Pages", format_integer(book_a.get("page_count")), format_integer(book_b.get("page_count"))),
                ("Observed publication languages", clean_compare_metadata(book_a.get("observed_publication_languages")), clean_compare_metadata(book_b.get("observed_publication_languages"))),
                ("Earliest observed publication country", clean_compare_metadata(book_a.get("earliest_observed_publication_country")), clean_compare_metadata(book_b.get("earliest_observed_publication_country"))),
                ("Source", clean_compare_metadata(book_a.get("source_group")), clean_compare_metadata(book_b.get("source_group"))),
            ]
            comparison_df = pd.DataFrame(comparison_rows, columns=["Dimension", "Book A", "Book B"])
            st.dataframe(comparison_df, use_container_width=True, hide_index=True)

            index_a = int(book_a["matrix_row"])
            index_b = int(book_b["matrix_row"])
            zero_a = str(book_a.get("enriched_zero_vector", False)).strip().lower() in {"true", "1", "yes"}
            zero_b = str(book_b.get("enriched_zero_vector", False)).strip().lower() in {"true", "1", "yes"}

            pair_similarity = None
            if not zero_a and not zero_b:
                pair_similarity = float(
                    cosine_similarity(tfidf_matrix[index_a], tfidf_matrix[index_b])[0, 0]
                )
                st.metric("Textual Content Similarity", f"{pair_similarity:.1%}")
                st.caption(
                    "Similarity is calculated in the production TF-IDF feature space. "
                    "It measures content resemblance; it is not a quality score, reader rating, "
                    "or a verdict on which publication is better."
                )

            st.markdown(
                '<div class="leadwise-section-title">Book Content Evidence</div>',
                unsafe_allow_html=True,
            )
            content_a, content_b = st.columns(2)
            with content_a:
                st.markdown(f"**Book A · {book_a['canonical_title']}**")
                st.write(comparison_content_evidence(book_a))
                if is_missing(book_a.get("description")):
                    st.caption("Source synopsis text is not available.")
                else:
                    with st.expander("Read available synopsis"):
                        st.write(book_a.get("description"))
            with content_b:
                st.markdown(f"**Book B · {book_b['canonical_title']}**")
                st.write(comparison_content_evidence(book_b))
                if is_missing(book_b.get("description")):
                    st.caption("Source synopsis text is not available.")
                else:
                    with st.expander("Read available synopsis"):
                        st.write(book_b.get("description"))

            st.markdown(
                '<div class="leadwise-section-title">LeadWise Content Comparison</div>',
                unsafe_allow_html=True,
            )
            st.write(leadwise_content_comparison(book_a, book_b))
            if pair_similarity is not None:
                st.write(
                    f"In the production TF-IDF representation, the pair has "
                    f"{pair_similarity:.1%} textual content similarity."
                )
            st.caption(
                "System-generated content analysis based only on available catalog metadata "
                "and the production TF-IDF representation. It is not a reader review, "
                "quality judgment or recommendation of one book over the other."
            )


    # =========================================================
    # MY LIBRARY
    # =========================================================

    elif page == "My Library":

        render_page_header(
            "Personal Library",
            "My Library",
            "Your account-specific bookshelf and personal reading journal.",
        )

        current_user = signed_in_user()

        if current_user is None:
            st.info(
                "My Library is an account feature. Continue discovering and comparing as a guest, "
                "then sign in or create an account when you want to save a book or keep reading reflections."
            )
        else:
            flash = st.session_state.pop("library_flash", None)
            if flash:
                st.success(flash)

            detail_id = st.session_state.get("library_detail_id")
            if detail_id:
                detail_matches = app_catalog[app_catalog["book_id"].astype(str).eq(str(detail_id))]
                if detail_matches.empty:
                    st.session_state.pop("library_detail_id", None)
                    st.warning("That saved publication is no longer available in the deployment catalog.")
                else:
                    if st.button("← Back to My Library", key="back_to_library", use_container_width=True):
                        st.session_state.pop("library_detail_id", None)
                        st.rerun()
                    render_page_header(
                        "Saved Book",
                        safe_display_value(detail_matches.iloc[0].get("canonical_title"), "Book Details"),
                        "Catalog evidence for a publication in your personal library.",
                    )
                    render_book_details(detail_matches.iloc[0])
            else:
                library = get_user_library(current_user["user_id"])
                if library.empty:
                    total = want = reading = finished = reviewed = 0
                else:
                    total = len(library)
                    want = int((library["reading_status"] == "Want to Read").sum())
                    reading = int((library["reading_status"] == "Currently Reading").sum())
                    finished = int((library["reading_status"] == "Finished").sum())
                    reviewed = int(library["personal_rating"].notna().sum())

                st.markdown(f"**{html.escape(current_user['full_name'])}'s Library**")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Total Saved", total)
                m2.metric("Want to Read", want)
                m3.metric("Reading", reading)
                m4.metric("Finished", finished)
                m5.metric("Rated", reviewed)

                if library.empty:
                    st.info("Your library is empty. Open a book in Discover Books and choose Save to My Library.")
                else:
                    filter_value = st.selectbox(
                        "Filter by reading status", ["All"] + READING_STATUSES, key="library_status_filter"
                    )
                    visible = library if filter_value == "All" else library[library["reading_status"] == filter_value]

                    for _, lib_row in visible.iterrows():
                        book_id = str(lib_row["book_id"])
                        matches = app_catalog[app_catalog["book_id"].astype(str).eq(book_id)]
                        if matches.empty:
                            continue
                        book = matches.iloc[0]
                        journal = get_reading_journal(current_user["user_id"], book_id)

                        with st.container(border=True):
                            c1, c2 = st.columns([1, 3.2])
                            with c1:
                                render_cover(book)
                            with c2:
                                st.markdown(f"### {safe_display_value(book.get('canonical_title'), 'Untitled')}")
                                st.write(f"**Author:** {format_list_value(book.get('authors'), 'Not available')}")
                                if journal.get("personal_rating"):
                                    st.caption(f"My rating: {'★' * int(round(float(journal['personal_rating'])))} · {float(journal['personal_rating']):.1f}/5")
                                else:
                                    st.caption("My rating: Not rated yet")
                                card_publication = get_review_publication(current_user["user_id"], book_id)
                                if bool(card_publication.get("is_published", 0)):
                                    st.caption("Reader Insights: Published")
                                else:
                                    st.caption("Reader Insights: Private")

                                current_status = lib_row["reading_status"] if lib_row["reading_status"] in READING_STATUSES else "Want to Read"
                                with st.form(f"status_form_{book_id}"):
                                    status = st.selectbox(
                                        "Reading status", READING_STATUSES,
                                        index=READING_STATUSES.index(current_status),
                                        key=f"library_status_{book_id}",
                                    )
                                    update_status = st.form_submit_button("Update Status", use_container_width=True)
                                if update_status:
                                    persisted = update_library_status(current_user["user_id"], book_id, status)
                                    if persisted:
                                        st.session_state["library_flash"] = f"{safe_display_value(book.get('canonical_title'), 'Book')} updated to {persisted['reading_status']}."
                                    else:
                                        st.session_state["library_flash"] = "The library record could not be updated."
                                    st.rerun()

                                a1, a2 = st.columns(2)
                                with a1:
                                    if st.button("View Details", key=f"library_view_{book_id}", use_container_width=True):
                                        st.session_state["library_detail_id"] = book_id
                                        st.rerun()
                                with a2:
                                    if st.button("Remove", key=f"library_remove_{book_id}", use_container_width=True):
                                        remove_library_book(current_user["user_id"], book_id)
                                        st.session_state["library_flash"] = "Book removed from My Library."
                                        st.rerun()

                            # Re-read after any previous persisted change so the journal uses database state.
                            persisted_entry = get_library_entry(current_user["user_id"], book_id) or dict(lib_row)
                            persisted_status = persisted_entry.get("reading_status", current_status)
                            with st.expander("My Reading Reflection", expanded=(persisted_status == "Finished")):
                                st.caption(
                                    "Your own reading record. This is separate from source ratings and LeadWise content analysis."
                                )
                                rating_options = ["Not rated", "1", "2", "3", "4", "5"]
                                current_rating = journal.get("personal_rating")
                                rating_index = 0 if not current_rating else max(1, min(5, int(round(float(current_rating)))))

                                stored_finished = journal.get("date_finished")
                                try:
                                    finished_default = date.fromisoformat(str(stored_finished)) if stored_finished else date.today()
                                except ValueError:
                                    finished_default = date.today()

                                with st.form(f"journal_form_{book_id}"):
                                    rating_choice = st.selectbox(
                                        "My rating", rating_options, index=rating_index, key=f"journal_rating_{book_id}"
                                    )
                                    review_text = st.text_area(
                                        "My Review / Feedback", value=journal.get("review_text") or "",
                                        placeholder="What did you think of the book? What worked well, and what did not?", height=120,
                                    )
                                    key_takeaways = st.text_area(
                                        "Key Takeaways", value=journal.get("key_takeaways") or "",
                                        placeholder="What leadership or management ideas do you want to remember?", height=100,
                                    )
                                    practical_application = st.text_area(
                                        "How I Can Apply It", value=journal.get("practical_application") or "",
                                        placeholder="How could you apply these ideas in your work, team, or leadership practice?", height=100,
                                    )
                                    private_notes = st.text_area(
                                        "Private Notes", value=journal.get("private_notes") or "",
                                        placeholder="Optional notes for yourself.", height=90,
                                    )
                                    publication = get_review_publication(current_user["user_id"], book_id)
                                    is_published = bool(publication.get("is_published", 0))
                                    if is_published:
                                        st.success("Community sharing status: Published in Reader Insights")
                                    else:
                                        st.info("Community sharing status: Private — not included in Reader Insights")
                                    st.caption(
                                        "Publishing shares only My Rating and My Review / Feedback. "
                                        "Key Takeaways, How I Can Apply It, Private Notes, and Date Finished remain private."
                                    )
                                    if persisted_status == "Finished":
                                        date_finished_input = st.date_input(
                                            "Date Finished", value=finished_default,
                                            key=f"journal_finished_{book_id}",
                                        )
                                        st.caption("LeadWise defaults this to today when a book is first marked Finished; you can change it.")
                                    else:
                                        date_finished_input = None
                                        if stored_finished:
                                            st.caption(f"Previous completion date retained: {stored_finished}")
                                        else:
                                            st.caption("Date Finished becomes available when the reading status is Finished.")
                                    b_private, b_publish = st.columns(2)
                                    with b_private:
                                        save_private = st.form_submit_button(
                                            "Save Privately", use_container_width=True
                                        )
                                    with b_publish:
                                        save_publish = st.form_submit_button(
                                            "Save & Publish to Reader Insights", use_container_width=True
                                        )

                                if save_private or save_publish:
                                    rating_value = None if rating_choice == "Not rated" else float(rating_choice)
                                    date_to_save = (
                                        date_finished_input.isoformat() if date_finished_input is not None
                                        else (stored_finished or None)
                                    )
                                    publish_review = bool(save_publish)
                                    published_ok, published_message, persisted_publication = save_reading_reflection_with_visibility(
                                        current_user["user_id"], book_id, rating_value, review_text,
                                        key_takeaways, practical_application, private_notes, date_to_save,
                                        publish=publish_review,
                                    )
                                    if publish_review and not published_ok:
                                        st.session_state["library_flash"] = published_message
                                    elif bool(persisted_publication.get("is_published", 0)):
                                        st.session_state["library_flash"] = (
                                            "Reading reflection saved and published. Your rating/review now contributes "
                                            "to Reader Insights."
                                        )
                                    else:
                                        st.session_state["library_flash"] = (
                                            "Reading reflection saved privately. It is not included in Reader Insights."
                                        )
                                    st.rerun()

    # =========================================================
    # READER INSIGHTS
    # =========================================================

    elif page == "Reader Insights":

        render_page_header(
            "Community Intelligence",
            "Reader Insights",
            "Community reviews, book-level reader evidence, and feedback about LeadWise in one place.",
        )

        reviews_tab, books_tab, feedback_tab = st.tabs(
            ["Community Reviews", "Book Insights", "LeadWise Feedback"]
        )

        with reviews_tab:
            st.markdown("### Community Reviews")
            st.caption(
                "Only ratings and reviews that readers explicitly choose to share appear here. "
                "Private notes, takeaways, application reflections, and completion dates are never displayed."
            )
            community = get_community_reviews()
            summary = get_reader_insight_summary()
            total_ratings = int(summary["rating_count"].sum()) if not summary.empty else 0
            total_reviews = int(summary["written_review_count"].sum()) if not summary.empty else 0
            reviewed_books = int(len(summary)) if not summary.empty else 0
            c1, c2, c3 = st.columns(3)
            c1.metric("Published Ratings", total_ratings)
            c2.metric("Written Reviews", total_reviews)
            c3.metric("Books with Reader Evidence", reviewed_books)

            if community.empty:
                st.info(
                    "No community reviews have been published yet. In My Library → My Reading Reflection, "
                    "use Save & Publish to Reader Insights. Save Privately will intentionally remain excluded."
                )
            else:
                book_options = ["All reviewed books"]
                ids = community["book_id"].astype(str).drop_duplicates().tolist()
                label_map = {}
                for bid in ids:
                    match = app_catalog[app_catalog["book_id"].astype(str).eq(bid)]
                    if not match.empty:
                        label_map[bid] = book_label(match.iloc[0])
                book_options += [label_map[bid] for bid in ids if bid in label_map]
                selected_label = st.selectbox("Filter reviews by book", book_options)
                visible_reviews = community
                if selected_label != "All reviewed books":
                    selected_bid = next((bid for bid, label in label_map.items() if label == selected_label), None)
                    if selected_bid:
                        visible_reviews = community[community["book_id"].astype(str).eq(selected_bid)]

                for _, review in visible_reviews.iterrows():
                    bid = str(review["book_id"])
                    match = app_catalog[app_catalog["book_id"].astype(str).eq(bid)]
                    if match.empty:
                        continue
                    book = match.iloc[0]
                    with st.container(border=True):
                        st.markdown(f"#### {safe_display_value(book.get('canonical_title'), 'Untitled')}")
                        st.caption(format_list_value(book.get("authors"), "Author unavailable"))
                        if not is_missing(review.get("rating")):
                            rating_value = float(review["rating"])
                            st.markdown(f"**LeadWise reader rating:** {'★' * int(round(rating_value))} · {rating_value:.1f}/5")
                        review_text = str(review.get("review_text") or "").strip()
                        if review_text:
                            st.write(review_text)
                        st.caption("Shared by a LeadWise reader · Community contribution")

        with books_tab:
            st.markdown("### Book Insights")
            st.caption(
                "Aggregated LeadWise reader evidence. Ratings are shown with sample sizes and are separate "
                "from external source-platform ratings and TF-IDF content similarity."
            )
            summary = get_reader_insight_summary()
            activity = get_library_activity_summary()
            if summary.empty and activity.empty:
                st.info("Reader insight data will appear as people save, finish, rate, and publish reviews of books.")
            else:
                merged = activity.copy() if not activity.empty else pd.DataFrame(columns=["book_id"])
                if not summary.empty:
                    merged = summary.copy() if merged.empty else merged.merge(summary, on="book_id", how="outer")
                merged = merged.fillna(0)
                catalog_lookup = app_catalog.set_index(app_catalog["book_id"].astype(str))
                rows = []
                for _, item in merged.iterrows():
                    bid = str(item["book_id"])
                    if bid not in catalog_lookup.index:
                        continue
                    book = catalog_lookup.loc[bid]
                    if isinstance(book, pd.DataFrame):
                        book = book.iloc[0]
                    rows.append({
                        "book_id": bid,
                        "title": safe_display_value(book.get("canonical_title"), "Untitled"),
                        "authors": format_list_value(book.get("authors"), "Author unavailable", limit=2),
                        "saved_count": int(item.get("saved_count", 0)),
                        "finished_count": int(item.get("finished_count", 0)),
                        "reader_rating": float(item.get("reader_rating", 0)) if float(item.get("rating_count", 0)) > 0 else None,
                        "rating_count": int(item.get("rating_count", 0)),
                        "written_review_count": int(item.get("written_review_count", 0)),
                    })
                insights = pd.DataFrame(rows)
                if insights.empty:
                    st.info("No usable reader insight records are available yet.")
                else:
                    insights = insights.sort_values(["rating_count", "saved_count"], ascending=[False, False])
                    for _, item in insights.head(20).iterrows():
                        with st.container(border=True):
                            st.markdown(f"#### {html.escape(item['title'])}")
                            st.caption(item["authors"])
                            i1, i2, i3, i4 = st.columns(4)
                            i1.metric("Saved", int(item["saved_count"]))
                            i2.metric("Finished", int(item["finished_count"]))
                            i3.metric(
                                "LeadWise Rating",
                                f"{item['reader_rating']:.2f}/5" if pd.notna(item["reader_rating"]) else "Not rated",
                            )
                            i4.metric("Rating Sample", int(item["rating_count"]))
                            if int(item["rating_count"]) < 3 and int(item["rating_count"]) > 0:
                                st.caption("Very limited reader sample — interpret the rating cautiously.")
                            elif int(item["rating_count"]) >= 3:
                                st.caption(f"{int(item['written_review_count'])} published written review(s).")

        with feedback_tab:
            st.markdown("### LeadWise Feedback")
            st.caption(
                "Use this form for feedback about the LeadWise application. Book reviews belong in My Library "
                "and Community Reviews; private reading reflections remain private."
            )
            current_user = signed_in_user()
            default_email = current_user["email"] if current_user else ""
            with st.form("leadwise_feedback_form", clear_on_submit=True):
                feedback_type = st.selectbox(
                    "Feedback type",
                    ["Feature Suggestion", "Usability Feedback", "Bug Report", "General Feedback"],
                )
                subject = st.text_input("Subject", placeholder="Short description")
                message = st.text_area(
                    "Your feedback",
                    placeholder="Tell us what you noticed or what would make LeadWise more useful.",
                    height=150,
                )
                contact_email = st.text_input(
                    "Email for follow-up (optional)", value=default_email
                )
                submit_feedback = st.form_submit_button("Send Feedback", use_container_width=True)
            if submit_feedback:
                if save_leadwise_feedback(current_user, feedback_type, subject, message, contact_email):
                    st.success("Thank you. Your feedback has been saved to LeadWise.")
                else:
                    st.warning("Please enter feedback before submitting.")

with assistant_col:
    render_floating_ask_leadwise()

# =========================================================
# ABOUT THE INTELLIGENCE — HOME PAGE ONLY
# =========================================================
# Hidden by default and shown only on Home, immediately above the footer.
track_page_once(page)

if page == "Home":
    with st.expander("About the Intelligence", expanded=False):
        st.markdown(
            '<div class="leadwise-eyebrow">'
            'Model Transparency'
            '</div>'

            '<div class="leadwise-page-title">'
            'About the Intelligence'
            '</div>'

            '<div class="leadwise-subtitle">'
            'Understand how LeadWise transforms '
            'book metadata into content-based '
            'discovery and topic intelligence.'
            '</div>',
            unsafe_allow_html=True,
        )


        about_1, about_2, about_3, about_4 = (
            st.columns(4)
        )


        with about_1:

            st.metric(
                "Catalog",
                f"{CATALOG_BOOKS:,}",
            )


        with about_2:

            st.metric(
                "Usable Vectors",
                f"{USABLE_VECTORS:,}",
            )


        with about_3:

            st.metric(
                "Clustered Books",
                f"{CLUSTERED_BOOKS:,}",
            )


        with about_4:

            st.metric(
                "Topic Clusters",
                f"{TOPIC_CLUSTERS:,}",
            )


        st.markdown(
            """
        ### Production recommendation architecture

        LeadWise uses the validated **enriched TF-IDF
        representation with cosine similarity** as its production
        content-based discovery and recommendation architecture.

        The enriched representation uses available:

        - book titles
        - authors
        - subjects
        - descriptions

        The application currently contains **5,130 TF-IDF
        features**.

        ### Topic intelligence

        The **29 K-Means topic clusters** provide an additional
        exploration layer across the catalog.

        The clusters do not replace the production similarity
        ranking.

        ### Dimensionality reduction

        A **200-dimensional Latent Semantic Analysis / Truncated
        SVD representation** supports dimensionality-reduction and
        analytical work.

        ### Experimental neural network

        The autoencoder developed during the project remains an
        **experimental model**. It is not used as the production
        recommendation engine.

        ### Missing metadata

        LeadWise uses the frozen enriched deployment catalog and does not fabricate unavailable metadata.

        If a book does not contain a description, rating, topic
        assignment or other field in the underlying dataset, the
        application reports that information as unavailable.

        ### Similarity scores

        Content-similarity scores measure textual similarity between
        the user's query and the book representation available to
        the TF-IDF model.

        They should **not** be interpreted as:

        - book quality scores
        - expert ratings
        - probabilities
        - measures of leadership effectiveness
        - guarantees that a book will meet a user's needs

        They are retrieval signals used to rank books by content
        similarity.
            """
        )


# =========================================================
# FOOTER
# =========================================================

st.markdown(
    '<div class="leadwise-footer">'
    '<strong>LeadWise</strong> · '
    'Leadership &amp; Management Book Intelligence · '
    'Developed by Dr. Jan'
    '</div>',
    unsafe_allow_html=True,
)
