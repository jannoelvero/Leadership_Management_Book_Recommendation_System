"""LeadWise shared database compatibility utilities.

Version 18.58.0

Local development uses SQLite.
Cloud deployment uses PostgreSQL when DATABASE_URL is configured.

This module intentionally contains only database compatibility logic. It does not
create or mutate the PostgreSQL schema. The Supabase schema is managed separately.
"""

from pathlib import Path
import os
import sqlite3


POSTGRES_BACKENDS = {"postgres", "postgresql"}


def _read_setting(name, default=""):
    """Read one database setting from Streamlit secrets, then environment."""
    try:
        import streamlit as st

        value = st.secrets.get(name, default)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    except Exception:
        pass

    value = os.getenv(name, default)
    return str(value or default).strip()


def get_postgres_components():
    """Return PostgreSQL connection components when configured separately.

    Separate settings avoid URL encoding problems in passwords and are the
    preferred Streamlit Community Cloud configuration for LeadWise 18.58.1.
    """
    values = {
        "host": _read_setting("DATABASE_HOST"),
        "port": _read_setting("DATABASE_PORT", "5432"),
        "dbname": _read_setting("DATABASE_NAME", "postgres"),
        "user": _read_setting("DATABASE_USER"),
        "password": _read_setting("DATABASE_PASSWORD"),
        "sslmode": _read_setting("DATABASE_SSLMODE", "require"),
    }

    required = ("host", "dbname", "user", "password")
    if all(values[name] for name in required):
        return values
    return None


def get_database_url(explicit_url=""):
    """Return DATABASE_URL from an explicit value, Streamlit secrets, or env."""
    value = str(explicit_url or "").strip()
    if value:
        return value

    try:
        import streamlit as st

        value = str(st.secrets.get("DATABASE_URL", "") or "").strip()
        if value:
            return value
    except Exception:
        pass

    value = os.getenv("DATABASE_URL", "").strip()
    if value:
        return value

    # A non-secret marker lets existing Reader/Admin code recognize that
    # PostgreSQL is configured through separate connection components.
    if get_postgres_components():
        return "postgresql://configured-from-components"

    return ""


def get_database_backend(database_url=""):
    """Return 'postgresql' when a database URL exists, otherwise 'sqlite'."""
    return "postgresql" if get_database_url(database_url) else "sqlite"


def _translate_qmark_sql(sql):
    """Convert SQLite qmark placeholders to psycopg %s placeholders.

    Question marks inside quoted SQL string literals or quoted identifiers are
    preserved. LeadWise uses qmark placeholders throughout its validated SQLite
    code, so translating them centrally avoids rewriting every query.
    """
    text = str(sql)
    output = []
    i = 0
    in_single_quote = False
    in_double_quote = False

    while i < len(text):
        char = text[i]

        if in_single_quote:
            output.append(char)
            if char == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    output.append(text[i + 1])
                    i += 1
                else:
                    in_single_quote = False
            i += 1
            continue

        if in_double_quote:
            output.append(char)
            if char == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    output.append(text[i + 1])
                    i += 1
                else:
                    in_double_quote = False
            i += 1
            continue

        if char == "'":
            in_single_quote = True
            output.append(char)
        elif char == '"':
            in_double_quote = True
            output.append(char)
        elif char == "?":
            output.append("%s")
        else:
            output.append(char)

        i += 1

    return "".join(output)


def row_to_dict(row):
    """Convert a SQLite Row or PostgreSQL dict row into a regular dictionary."""
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def rows_to_dicts(rows):
    """Convert database rows into a list of regular dictionaries."""
    return [row_to_dict(row) for row in rows]


class LeadWiseConnection:
    """Small compatibility wrapper around SQLite and psycopg connections."""

    def __init__(self, raw_connection, backend):
        self.raw_connection = raw_connection
        self.backend = backend

    def execute(self, sql, params=None):
        params = () if params is None else params
        query = _translate_qmark_sql(sql) if self.backend == "postgresql" else sql
        return self.raw_connection.execute(query, params)

    def commit(self):
        self.raw_connection.commit()

    def rollback(self):
        self.raw_connection.rollback()

    def close(self):
        self.raw_connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.raw_connection.commit()
            else:
                self.raw_connection.rollback()
        finally:
            self.raw_connection.close()
        return False


def connect_database(sqlite_path, database_url=""):
    """Open the current LeadWise database backend.

    SQLite is used when DATABASE_URL is absent.
    PostgreSQL is used when DATABASE_URL is present.
    """
    resolved_url = get_database_url(database_url)
    components = get_postgres_components()

    if resolved_url or components:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL is configured but psycopg is not installed. "
                "Add psycopg[binary] to requirements.txt."
            ) from exc

        if components:
            raw_connection = psycopg.connect(
                host=components["host"],
                port=int(components["port"]),
                dbname=components["dbname"],
                user=components["user"],
                password=components["password"],
                sslmode=components["sslmode"],
                connect_timeout=10,
                row_factory=dict_row,
                autocommit=False,
            )
        else:
            raw_connection = psycopg.connect(
                resolved_url,
                connect_timeout=10,
                row_factory=dict_row,
                autocommit=False,
            )

        return LeadWiseConnection(raw_connection, "postgresql")

    path = Path(sqlite_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    raw_connection = sqlite3.connect(path)
    raw_connection.row_factory = sqlite3.Row
    raw_connection.execute("PRAGMA foreign_keys = ON")
    return LeadWiseConnection(raw_connection, "sqlite")


def fetch_one(connection, sql, params=None):
    """Execute a query and return one row as a regular dictionary."""
    row = connection.execute(sql, params).fetchone()
    return row_to_dict(row)


def fetch_all(connection, sql, params=None):
    """Execute a query and return all rows as regular dictionaries."""
    rows = connection.execute(sql, params).fetchall()
    return rows_to_dicts(rows)


def query_dataframe(connection, sql, params=None):
    """Execute a query and return a pandas DataFrame without SQLAlchemy."""
    import pandas as pd

    rows = fetch_all(connection, sql, params)
    return pd.DataFrame(rows)


def insert_returning_id(connection, sql, params, id_column):
    """Execute an INSERT and return its generated identity value."""
    if connection.backend == "postgresql":
        query = str(sql).strip().rstrip(";")
        if " returning " not in query.lower():
            query = f"{query} RETURNING {id_column}"
        row = connection.execute(query, params).fetchone()
        if row is None:
            raise RuntimeError(f"Insert did not return {id_column}.")
        row_dict = row_to_dict(row)
        return int(row_dict[id_column])

    cursor = connection.execute(sql, params)
    return int(cursor.lastrowid)


def get_table_columns(connection, table_name):
    """Return column names for one table on either supported backend."""
    table_name = str(table_name).strip()

    if connection.backend == "postgresql":
        rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table_name,),
        ).fetchall()
        return [row_to_dict(row)["column_name"] for row in rows]

    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [row["name"] for row in rows]


def validate_required_schema(connection, expected_schema):
    """Validate required tables and columns without mutating the database.

    expected_schema must be a mapping of table name to an iterable of required
    column names. Returns a list of readable validation errors.
    """
    problems = []

    for table_name, required_columns in expected_schema.items():
        actual_columns = set(get_table_columns(connection, table_name))
        if not actual_columns:
            problems.append(f"Missing table: {table_name}")
            continue

        missing_columns = sorted(set(required_columns) - actual_columns)
        if missing_columns:
            problems.append(
                f"{table_name} is missing columns: {', '.join(missing_columns)}"
            )

    return problems


def is_integrity_error(error):
    """Return True for SQLite or PostgreSQL integrity constraint errors."""
    if isinstance(error, sqlite3.IntegrityError):
        return True

    sqlstate = str(getattr(error, "sqlstate", "") or "")
    if sqlstate.startswith("23"):
        return True

    module_name = str(error.__class__.__module__)
    class_name = str(error.__class__.__name__)
    return module_name.startswith("psycopg") and "Integrity" in class_name
