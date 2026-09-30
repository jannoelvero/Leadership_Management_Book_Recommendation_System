# LeadWise Administrator Control Center
# Version 18.58.9 — Commerce Management — Administrative Governance & Internal Analytics

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

# 18.58.8: the Admin Control Center must use the same shared Supabase
# PostgreSQL database as the Reader. Silent SQLite fallback is disabled.
if DATABASE_BACKEND != "postgresql":
    raise RuntimeError(
        "LeadWise Admin requires Supabase PostgreSQL. "
        "No PostgreSQL configuration was detected. Configure DATABASE_HOST, "
        "DATABASE_USER and DATABASE_PASSWORD in Streamlit Secrets or in the "
        "local .streamlit/secrets.toml file. SQLite fallback is disabled."
    )

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
