"""SQLite connector: raw database-file backup via Python's ``sqlite3`` module.

The snapshot stores the full database file (``<alias>.sqlite3``), not a SQL
text dump. Both directions run small ``python -c`` scripts (same interpreter
as Django) through restic's stdin pipeline, using
:meth:`sqlite3.Connection.backup` for a consistent online copy — WAL-safe,
honours SQLite locking, and needs no ``sqlite3`` CLI. Restore copies the
snapshot back *into* the live database, so it works with the file present
and while other connections exist.
"""

from __future__ import annotations

import sys

from .base import BaseConnector

# Online-backup the live DB into a temp file, then stream the temp file's raw
# bytes to stdout for restic. A missing database file is an error — backing
# up a silently-created empty DB must never produce a "successful" snapshot.
_DUMP_SCRIPT = """\
import os, shutil, sqlite3, sys, tempfile
db = sys.argv[1]
if not os.path.exists(db):
    sys.exit("sqlite database not found: " + db)
fd, tmp = tempfile.mkstemp(suffix=".sqlite3")
os.close(fd)
try:
    src = sqlite3.connect(db)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    dst.close()
    src.close()
    with open(tmp, "rb") as fh:
        shutil.copyfileobj(fh, sys.stdout.buffer)
finally:
    os.remove(tmp)
"""

# Reverse: spool restic's raw file bytes from stdin to a temp file, then
# online-backup that temp DB over the live database (created if absent).
_RESTORE_SCRIPT = """\
import os, shutil, sqlite3, sys, tempfile
fd, tmp = tempfile.mkstemp(suffix=".sqlite3")
os.close(fd)
try:
    with open(tmp, "wb") as fh:
        shutil.copyfileobj(sys.stdin.buffer, fh)
    src = sqlite3.connect(tmp)
    dst = sqlite3.connect(sys.argv[1])
    src.backup(dst)
    dst.close()
    src.close()
finally:
    os.remove(tmp)
"""


class SQLite(BaseConnector):
    """Back up / restore a SQLite database as its raw file.

    SQLite needs no credentials or network arguments, so :meth:`extra_env`
    is empty.
    """

    def dump_command(self) -> list[str]:
        return [sys.executable, "-c", _DUMP_SCRIPT, str(self.settings_dict["NAME"])]

    def restore_command(self) -> list[str]:
        return [sys.executable, "-c", _RESTORE_SCRIPT, str(self.settings_dict["NAME"])]

    def extra_env(self) -> dict[str, str]:
        return {}

    @property
    def stdin_filename(self) -> str:
        """Raw file snapshot, so the recorded name is ``<alias>.sqlite3``."""
        return f"{self.alias}.sqlite3"
