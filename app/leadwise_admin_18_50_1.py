# LeadWise Administrator Control Center
# Version 18.50.1 — Secure Admin Foundation

from pathlib import Path
import sqlite3
import hashlib
import hmac
import html
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent if APP_DIR.name == "app" else APP_DIR
USER_DB_PATH = PROJECT_ROOT / "data" / "app" / "leadwise_users.db"
PBKDF2_ITERATIONS = 600_000

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


def db_connection():
    USER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(USER_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate_admin_schema():
    with db_connection() as connection:
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


def hash_password(password, salt_hex):
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return digest.hex()


def authenticate_admin(email, password):
    email = str(email or "").strip().lower()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT user_id, full_name, email, password_hash, password_salt, role
            FROM users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()

    if row is None or row["role"] != "admin":
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
    return row[0] if row else 0


def dataframe(query, params=()):
    with db_connection() as connection:
        return pd.read_sql_query(query, connection, params=params)


migrate_admin_schema()

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
    st.info(
        "Sign in with a LeadWise account that has the admin role. "
        "Normal reader accounts cannot access this control center."
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
            st.error("Invalid administrator credentials or this account is not authorized.")
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

    section = st.radio(
        "Administration",
        [
            "Overview",
            "Users",
            "Reader Insights",
            "Ask LeadWise",
            "Inbox",
            "Book Suggestions",
            "Catalog Management",
            "System Monitoring",
        ],
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
    inbox = dataframe(
        """
        SELECT inquiry_id, inquiry_type, full_name, email, subject, message,
               related_book_id, status, created_at
        FROM leadwise_inquiries
        WHERE inquiry_type <> 'Suggest a Book'
        ORDER BY inquiry_id DESC
        """
    )
    st.dataframe(inbox, use_container_width=True, hide_index=True)

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
    st.info(
        "18.50.1 establishes the secure administrator shell. "
        "Dynamic add/edit/hide/archive/publish catalog actions will be implemented next "
        "without modifying the frozen 2,067-book capstone dataset."
    )

elif section == "System Monitoring":
    st.subheader("System Monitoring")
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
st.caption("LeadWise Administrator · Role-protected operational interface · 18.50.1")
