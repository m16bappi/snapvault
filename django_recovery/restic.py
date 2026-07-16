"""Thin subprocess wrapper around the restic ``--json`` CLI.

This module never transforms backup data; it only *constructs* argv lists and
runs the restic binary. Passwords are never placed in argv or in exception
text: the configured backend supplies ``RESTIC_PASSWORD`` /
``RESTIC_PASSWORD_FILE`` and cloud credentials via ``extra_env``, which is
merged into the subprocess environment only.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field


class ResticError(RuntimeError):
    """Raised when restic exits with a non-zero return code.

    Carries the process ``returncode`` and ``stderr``. Its string form never
    contains the environment or any password material.
    """

    def __init__(self, returncode: int, stderr: str):
        self.returncode = returncode
        self.stderr = stderr or ""
        super().__init__(f"restic exited with code {returncode}: {self.stderr}")

    def __str__(self) -> str:
        return f"restic exited with code {self.returncode}: {self.stderr}"


@dataclass
class Snapshot:
    """A single restic snapshot as reported by ``restic --json snapshots``."""

    id: str
    short_id: str
    time: str
    tags: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    hostname: str = ""

    @classmethod
    def from_json(cls, d: dict) -> Snapshot:
        """Build a :class:`Snapshot` from a restic snapshot JSON object.

        Missing ``tags``/``paths`` default to ``[]`` (restic omits empty
        lists) and ``short_id``/``hostname`` tolerate absence.
        """
        return cls(
            id=d.get("id", ""),
            short_id=d.get("short_id", ""),
            time=d.get("time", ""),
            tags=list(d.get("tags") or []),
            paths=list(d.get("paths") or []),
            hostname=d.get("hostname", ""),
        )


class Restic:
    """Constructs and runs restic CLI commands against one repository."""

    def __init__(
        self,
        repository: str,
        extra_env: dict[str, str] | None = None,
        binary: str = "restic",
        global_args: list[str] | None = None,
    ):
        self.repository = repository
        self.extra_env = dict(extra_env or {})
        self.binary = binary
        self.global_args = list(global_args or [])

    # -- internals ---------------------------------------------------------

    def _base_argv(self) -> list[str]:
        return [self.binary, "--json", "-r", self.repository, *self.global_args]

    def _env(self) -> dict[str, str]:
        """Build the subprocess environment.

        ``os.environ`` is copied and then overlaid with ``extra_env`` from the
        configured backend (``RESTIC_PASSWORD``/``RESTIC_PASSWORD_FILE`` plus
        cloud credentials). The overlay wins over inherited shell variables so
        behaviour is deterministic regardless of the caller's environment.
        Values in ``extra_env`` never appear in argv or exception text.
        """
        env = os.environ.copy()
        env.update(self.extra_env)
        return env

    def _run(
        self,
        argv: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess:
        env = self._env()
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            argv,
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ResticError(proc.returncode, proc.stderr)
        return proc

    # -- commands ----------------------------------------------------------

    def init(self) -> subprocess.CompletedProcess:
        return self._run(self._base_argv() + ["init"])

    def is_initialized(self) -> bool:
        """Whether the repository already exists.

        Uses ``cat config`` — the canonical restic existence probe. Any
        failure (missing repo, unreachable backend, wrong password) reports
        ``False``; a subsequent ``init`` will surface the real error if the
        repository does exist but cannot be opened.
        """
        try:
            self._run(self._base_argv() + ["cat", "config"])
        except ResticError:
            return False
        return True

    def _backup_flags(
        self,
        tags: list[str] | None,
        host: str | None,
        skip_if_unchanged: bool,
        read_concurrency: int | None,
    ) -> list[str]:
        argv: list[str] = []
        for tag in tags or []:
            argv += ["--tag", tag]
        if host:
            argv += ["--host", host]
        if skip_if_unchanged:
            argv += ["--skip-if-unchanged"]
        if read_concurrency:
            argv += ["--read-concurrency", str(read_concurrency)]
        return argv

    def backup_command(
        self,
        cmd: list[str],
        stdin_filename: str,
        tags: list[str] | None = None,
        extra_env: dict[str, str] | None = None,
        host: str | None = None,
        skip_if_unchanged: bool = False,
        read_concurrency: int | None = None,
    ) -> subprocess.CompletedProcess:
        """Back up the stdout of ``cmd`` as a file named ``stdin_filename``.

        Uses ``restic backup --stdin-from-command`` so a failed dump never
        produces a snapshot. The dump runs inside restic's own process, so any
        credentials the dump needs (e.g. ``PGPASSWORD``) must be present in
        restic's environment: pass them via ``extra_env`` and they are merged
        into the subprocess environment for this call only. ``extra_env`` never
        appears in ``argv``.
        """
        argv = self._base_argv() + ["backup", "--stdin-filename", stdin_filename]
        argv += self._backup_flags(tags, host, skip_if_unchanged, read_concurrency)
        argv += ["--stdin-from-command", "--"] + cmd
        return self._run(argv, extra_env=extra_env)

    def backup_paths(
        self,
        paths: list[str],
        tags: list[str] | None = None,
        host: str | None = None,
        skip_if_unchanged: bool = False,
        read_concurrency: int | None = None,
        exclude: list[str] | None = None,
    ) -> subprocess.CompletedProcess:
        argv = self._base_argv() + ["backup"] + list(paths)
        argv += self._backup_flags(tags, host, skip_if_unchanged, read_concurrency)
        for pattern in exclude or []:
            argv += ["--exclude", pattern]
        return self._run(argv)

    def snapshots(self, tags: list[str] | None = None) -> list[Snapshot]:
        argv = self._base_argv() + ["snapshots"]
        for tag in tags or []:
            argv += ["--tag", tag]
        proc = self._run(argv)
        data = json.loads(proc.stdout or "[]")
        return [Snapshot.from_json(d) for d in data]

    def forget_snapshot(
        self,
        snapshot_id: str,
        prune: bool = True,
    ) -> subprocess.CompletedProcess:
        argv = self._base_argv() + ["forget", snapshot_id]
        if prune:
            argv += ["--prune"]
        return self._run(argv)

    # Deterministic --keep-* flag order for forget_policy.
    _POLICY_FLAGS = (
        ("last", "--keep-last"),
        ("hourly", "--keep-hourly"),
        ("daily", "--keep-daily"),
        ("weekly", "--keep-weekly"),
        ("monthly", "--keep-monthly"),
        ("yearly", "--keep-yearly"),
        ("within", "--keep-within"),
    )

    def forget_policy(
        self,
        retention: dict,
        prune: bool = True,
        group_by: str = "paths,tags",
        dry_run: bool = False,
    ) -> subprocess.CompletedProcess:
        """Apply a retention policy: ``forget --keep-* ... [--prune]``.

        ``group_by`` defaults to ``paths,tags`` (not restic's ``host,paths``)
        so each backup series — ``db:<alias>`` vs ``media`` — is retained
        independently, and changing container hostnames cannot fragment the
        groups.
        """
        argv = self._base_argv() + ["forget", "--group-by", group_by]
        for key, flag in self._POLICY_FLAGS:
            value = retention.get(key)
            if value:
                argv += [flag, str(value)]
        if dry_run:
            argv += ["--dry-run"]
        if prune:
            argv += ["--prune"]
        return self._run(argv)

    def dump_popen(self, snapshot_id: str, path: str) -> subprocess.Popen:
        """Stream the raw content of ``path`` from a snapshot to stdout.

        ``restic dump`` writes raw file bytes to stdout, so ``--json`` is
        deliberately omitted here (it would corrupt the stream). The caller
        pipes ``proc.stdout`` into a restore command and is responsible for
        waiting on the process; we do not wait.
        """
        argv = [self.binary, "-r", self.repository, *self.global_args,
                "dump", snapshot_id, path]
        return subprocess.Popen(argv, stdout=subprocess.PIPE, env=self._env())

    def unlock(self) -> subprocess.CompletedProcess:
        return self._run(self._base_argv() + ["unlock"])

    def version(self) -> str:
        proc = self._run([self.binary, "version"])
        return proc.stdout.strip()
