"""Tests for the per-engine database connectors.

These tests need no real database: they assert the exact command-line lists
and environment dicts each connector constructs from a ``DATABASES``-style
settings dict. Connectors are constructed directly where possible; the
:func:`get_connector` factory is exercised via ``override_settings``.
"""

import sqlite3
import subprocess
import sys

import pytest
from django.test import override_settings

from django_recovery.connectors import MySQL, Postgres, SQLite, get_connector
from django_recovery.connectors import sqlite as sqlite_mod

# --- Postgres --------------------------------------------------------------

def test_postgres_dump_command():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.dump_command() == [
        "pg_dump", "--clean", "--if-exists", "--no-owner",
        "-h", "localhost", "-p", "5432", "-U", "app", "-d", "appdb",
    ]


def test_postgres_restore_command():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.restore_command() == [
        "psql", "-h", "localhost", "-p", "5432", "-U", "app",
        "-d", "appdb", "-v", "ON_ERROR_STOP=1",
    ]


def test_postgres_extra_env():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.extra_env() == {"PGPASSWORD": "secret"}


def test_postgres_no_password_no_env():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "localhost", "PORT": "5432",
    })
    assert c.extra_env() == {}


def test_postgres_omits_host_and_port_when_empty():
    c = Postgres("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "", "PORT": "",
    })
    assert c.dump_command() == [
        "pg_dump", "--clean", "--if-exists", "--no-owner",
        "-U", "app", "-d", "appdb",
    ]
    assert c.restore_command() == [
        "psql", "-U", "app", "-d", "appdb", "-v", "ON_ERROR_STOP=1",
    ]


# --- MySQL -----------------------------------------------------------------

def test_mysql_dump_command():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "db.internal", "PORT": "3306",
    })
    assert c.dump_command() == [
        "mysqldump", "--single-transaction", "--routines",
        "-h", "db.internal", "-P", "3306", "-u", "app", "appdb",
    ]


def test_mysql_restore_command():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "db.internal", "PORT": "3306",
    })
    assert c.restore_command() == [
        "mysql", "-h", "db.internal", "-P", "3306", "-u", "app", "appdb",
    ]


def test_mysql_extra_env():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
        "HOST": "db.internal", "PORT": "3306",
    })
    assert c.extra_env() == {"MYSQL_PWD": "secret"}


def test_mysql_no_password_no_env():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "", "PORT": "",
    })
    assert c.extra_env() == {}


def test_mysql_omits_host_and_port_when_empty():
    c = MySQL("default", {
        "NAME": "appdb", "USER": "app", "PASSWORD": "",
        "HOST": "", "PORT": "",
    })
    assert c.dump_command() == [
        "mysqldump", "--single-transaction", "--routines", "-u", "app", "appdb",
    ]
    assert c.restore_command() == ["mysql", "-u", "app", "appdb"]


# --- SQLite ----------------------------------------------------------------

def test_sqlite_dump_command_runs_python_backup_script():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.dump_command() == [
        sys.executable, "-c", sqlite_mod._DUMP_SCRIPT, "/path/db.sqlite3",
    ]


def test_sqlite_restore_command_runs_python_backup_script():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.restore_command() == [
        sys.executable, "-c", sqlite_mod._RESTORE_SCRIPT, "/path/db.sqlite3",
    ]


def test_sqlite_extra_env_empty():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.extra_env() == {}


def test_sqlite_dump_restore_roundtrip(tmp_path):
    """Run the real dump/restore scripts: raw file out, overwrite-restore in."""
    src_db = tmp_path / "src.sqlite3"
    conn = sqlite3.connect(str(src_db))
    conn.execute("CREATE TABLE note(id INTEGER PRIMARY KEY, body TEXT)")
    conn.execute("INSERT INTO note(body) VALUES ('hello-file')")
    conn.commit()
    conn.close()

    dumped = subprocess.run(
        SQLite("default", {"NAME": str(src_db)}).dump_command(),
        capture_output=True, check=True,
    ).stdout
    # The stream is the raw database file, not SQL text.
    assert dumped.startswith(b"SQLite format 3\x00")

    # Restore over an EXISTING database with different content.
    dst_db = tmp_path / "dst.sqlite3"
    conn = sqlite3.connect(str(dst_db))
    conn.execute("CREATE TABLE other(x INTEGER)")
    conn.commit()
    conn.close()

    subprocess.run(
        SQLite("default", {"NAME": str(dst_db)}).restore_command(),
        input=dumped, check=True,
    )
    conn = sqlite3.connect(str(dst_db))
    try:
        rows = [r[0] for r in conn.execute("SELECT body FROM note")]
    finally:
        conn.close()
    assert rows == ["hello-file"]


def test_sqlite_dump_fails_on_missing_database(tmp_path):
    missing = tmp_path / "nope.sqlite3"
    proc = subprocess.run(
        SQLite("default", {"NAME": str(missing)}).dump_command(),
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
    assert "sqlite database not found" in proc.stderr


# --- stdin_filename --------------------------------------------------------

def test_stdin_filename_sqlite_is_raw_file():
    c = SQLite("default", {"NAME": "/path/db.sqlite3"})
    assert c.stdin_filename == "default.sqlite3"


def test_stdin_filename_uses_alias():
    c = Postgres("analytics", {"NAME": "appdb", "USER": "", "PASSWORD": "",
                               "HOST": "", "PORT": ""})
    assert c.stdin_filename == "analytics.sql"


# --- get_connector factory -------------------------------------------------

@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": "appdb", "USER": "app", "PASSWORD": "secret",
    "HOST": "localhost", "PORT": "5432",
}})
def test_get_connector_postgresql():
    c = get_connector("default")
    assert isinstance(c, Postgres)
    assert c.alias == "default"


@override_settings(DATABASES={"default": {
    "ENGINE": "django.contrib.gis.db.backends.postgis",
    "NAME": "geodb", "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
}})
def test_get_connector_postgis_maps_to_postgres():
    assert isinstance(get_connector("default"), Postgres)


@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.mysql",
    "NAME": "appdb", "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
}})
def test_get_connector_mysql():
    assert isinstance(get_connector("default"), MySQL)


@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.sqlite3", "NAME": "/path/db.sqlite3",
}})
def test_get_connector_sqlite():
    assert isinstance(get_connector("default"), SQLite)


@override_settings(DATABASES={"default": {
    "ENGINE": "django.db.backends.oracle",
    "NAME": "appdb", "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
}})
def test_get_connector_unknown_engine_raises():
    with pytest.raises(NotImplementedError) as exc:
        get_connector("default")
    assert "django.db.backends.oracle" in str(exc.value)
