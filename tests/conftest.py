"""Tests run against a separate PostgreSQL database (assembly_test), never the dashboard data."""
import os
import re

import psycopg
import pytest

from assembly import db

BASE_URL = db.database_url()
TEST_DB = "assembly_test"


def _with_db(url: str, name: str) -> str:
    return re.sub(r"/[^/?]*(\?|$)", rf"/{name}\1", url, count=1) if "://" in url else url


@pytest.fixture(scope="session", autouse=True)
def test_database():
    with psycopg.connect(BASE_URL, autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        c.execute(f"CREATE DATABASE {TEST_DB}")
    os.environ["DATABASE_URL"] = _with_db(BASE_URL, TEST_DB)
    yield os.environ["DATABASE_URL"]


@pytest.fixture()
def conn(test_database):
    from assembly.pipeline import reset
    with db.connect() as c:
        reset(c)
        yield c
