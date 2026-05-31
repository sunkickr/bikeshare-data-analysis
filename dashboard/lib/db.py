"""Postgres connection layer. Reads credentials from ~/.dbt/profiles.yml.

The engine is created once per Streamlit session via @st.cache_resource and reused
across reruns. Individual query helpers wrap @st.cache_data for result caching.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

PROFILES_PATH = Path.home() / ".dbt" / "profiles.yml"
PROFILE_NAME = "bikeshare"
TARGET_NAME = "dev"


def _read_profile() -> dict:
    """Pull the bikeshare dev target out of ~/.dbt/profiles.yml."""
    with PROFILES_PATH.open() as f:
        profiles = yaml.safe_load(f)
    return profiles[PROFILE_NAME]["outputs"][TARGET_NAME]


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    """Cached SQLAlchemy engine. Single connection pool per Streamlit session."""
    p = _read_profile()
    url = (
        f"postgresql+psycopg2://{p['user']}:{p['password']}"
        f"@{p['host']}:{p['port']}/{p['dbname']}"
    )
    return create_engine(url, pool_pre_ping=True)


def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute SQL and return a DataFrame. Do not cache here; cache at the call site."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})
