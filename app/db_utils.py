"""LeadWise shared database compatibility utilities.

Version 18.58.3

Local development uses SQLite.
Cloud deployment uses PostgreSQL when either:
1. Separate PostgreSQL component settings are configured, or
2. DATABASE_URL is configured.

Component settings are preferred because they avoid URL encoding problems.
This module never creates or mutates the PostgreSQL schema.
"""

from pathlib import Path
import os
import sqlite3


POSTGRES_BACKENDS = {"postgres", "postgresql"}


def _streamlit_secret(name, default=""):
    """Read a top-level Streamlit secret without exposing its value."""
    try:
        import streamlit as st

        value = st.secrets.get(name, default)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    except Exception:
        pass
    return ""


def _nested_streamlit_secret(section_name, key_name, default=""):
    """Read a nested Streamlit secret such as [database] host = '...'."""
    try:
        import streamlit as st

        section = st.secrets.get(section_name, {})
        if section:
            value = section.get(key_name, default)
            if value is not None and str(value).strip() != "":
                return str(value).strip()
    except Exception:
        pass
    return ""


def _read_setting(name, default="", nested_keys=()):
    """Read one setting from top-level secrets, nested secrets, then env."""
    value = _streamlit_secret(name)
    if value:
        return value

    for section_name, key_name in nested_keys:
        value = _nested_streamlit_secret(section_name, key_name)
        if value:
            return value

    value = os.getenv(name, "")
    if value is not None and str(value).strip() != "":
        return str(value).strip()

    return str(default or "").strip()


def _component_values():
    """Return PostgreSQL component values with safe defaults."""
    return {
        "host": _read_setting(
            "DATABASE_HOST",
            nested_keys=(("database", "host"), ("postgres", "host")),
        ),
        "port": _read_setting(
            "DATABASE_PORT",
            "5432",
            nested_keys=(("database", "port"), ("postgres", "port")),
        ),
        "dbname": _read_setting(
            "DATABASE_NAME",
            "postgres",
            nested_keys=(
                ("database", "name"),
                ("database", "dbname"),
                ("postgres", "name"),
                ("postgres", "dbname"),
            ),
        ),
        "user": _read_setting(
            "DATABASE_USER",
            nested_keys=(("database", "user"), ("postgres", "user")),
        ),
        "password": _read_setting(
            "DATABASE_PASSWORD",
            nested_keys=(("database", "password"), ("postgres", "password")),
        ),
        "sslmode": _read_setting(
            "DATABASE_SSLMODE",
            "require",
            nested_keys=(("database", "sslmode"), ("postgres", "sslmode")),
        ),
    }


def get_postgres_component_status():
    """Return safe component presence information without secret values."""
    values = _component_values()
    required = {
        "DATABASE_HOST": values["host"],
        "DATABASE_USER": values["user"],
        "DATABASE_PASSWORD": values["password"],
    }
    present = [name for name, value in required.items() if value]
    missing = [name for name, value in required.items() if not value]
    return {
        "any_present": bool(present),
        "complete": not missing,
        "present": present,
        "missing": missing,
    }


def get_postgres_components():
    """Return PostgreSQL components only when the required values are complete."""
    values = _component_values()
    if values["host"] and values["user"] and values["password"]:
        return values
    return None


def get_database_url(explicit_url=""):
    """Return DATABASE_URL only. Component configuration is handled separately."""
    value = str(explicit_url or "").strip()
    if value and value != "postgresql://configured-from-components":
        return value

    value = _streamlit_secret("DATABASE_URL")
    if value:
        return value

    value = os.getenv("DATABASE_URL", "").strip()
    if value:
        return value

    return ""


def get_database_backend(database_url=""):
    """Return the active database backend name."""
    status = get_postgres_component_status()
    if status["any_present"] or get_database_url(database_url):
        return "postgresql"
    return "sqlite"


def _translate_qmark_sql(sql):
    """Convert SQLite qmark placeholders to psycopg %s placeholders."""
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
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def rows_to_dicts(rows):
    return [row_to_dict(row) for row in rows]


class LeadWiseConnection:
    """Small compatibility wrapper around SQLite and psycopg connections."""

    def __init__(self, raw_connection, backend):
        self.raw_connection = raw_connection
        self.backend = backend

    def execute(self, sql, params=None):
        query = _translate_qmark_sql(sql) if self.backend == "postgresql" else sql

        # Important for psycopg:
        # When a query has no parameters, do not pass an empty tuple.
        # Psycopg treats percent signs in SQL text as parameter markers whenever
        # a params object is supplied. This breaks valid SQL such as:
        # LIKE 'administrator_%'
        if params is None:
            return self.raw_connection.execute(query)

        try:
            has_params = len(params) > 0
        except TypeError:
            has_params = True

        if not has_params:
            return self.raw_connection.execute(query)

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
    """Open SQLite locally or PostgreSQL in cloud.

    Separate PostgreSQL components are always preferred over DATABASE_URL.
    If component configuration is partial, fail with the exact missing secret
    names instead of silently falling back to a stale DATABASE_URL.
    """
    component_status = get_postgres_component_status()
    components = get_postgres_components()
    resolved_url = get_database_url(database_url)

    if component_status["any_present"] and not component_status["complete"]:
        missing = ", ".join(component_status["missing"])
        raise RuntimeError(
            "LeadWise PostgreSQL component configuration is incomplete. "
            f"Missing Streamlit secret(s): {missing}. "
            "Use DATABASE_HOST, DATABASE_USER, and DATABASE_PASSWORD at the top "
            "level of Streamlit Secrets. DATABASE_PORT, DATABASE_NAME, and "
            "DATABASE_SSLMODE are optional because LeadWise supplies safe defaults."
        )

    if components or resolved_url:
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
    row = connection.execute(sql, params).fetchone()
    return row_to_dict(row)


def fetch_all(connection, sql, params=None):
    rows = connection.execute(sql, params).fetchall()
    return rows_to_dicts(rows)


def query_dataframe(connection, sql, params=None):
    import pandas as pd

    rows = fetch_all(connection, sql, params)
    return pd.DataFrame(rows)


def insert_returning_id(connection, sql, params, id_column):
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
    if isinstance(error, sqlite3.IntegrityError):
        return True

    sqlstate = str(getattr(error, "sqlstate", "") or "")
    if sqlstate.startswith("23"):
        return True

    module_name = str(error.__class__.__module__)
    class_name = str(error.__class__.__name__)
    return module_name.startswith("psycopg") and "Integrity" in class_name
