from pathlib import Path
from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3
import time
from .schemas import ActionRequest, DriftReport


class ActionCircuitBreaker:
    """Durable fail-closed gate; all downstream dispatchers must consult this gate."""

    def __init__(self, path: Path, property_name: str, max_age_seconds: float = 300):
        if not property_name or not 0 < max_age_seconds < float("inf"):
            raise ValueError("property name and positive finite freshness required")
        self.path = path
        self.property_name = property_name
        self.max_age = max_age_seconds
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS gate(property TEXT PRIMARY KEY, blocked INTEGER NOT NULL, revision INTEGER NOT NULL, checked REAL NOT NULL, report TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, property TEXT NOT NULL, checked REAL NOT NULL, allowed INTEGER NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO gate VALUES (?,1,0,0,'{}')", (property_name,)
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def observe(self, report: DriftReport) -> int:
        if report.property_name != self.property_name:
            raise ValueError("property mismatch")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE gate SET blocked=CASE WHEN ? THEN 1 ELSE blocked END, revision=revision+1, checked=?, report=? WHERE property=?",
                (
                    report.status != "healthy",
                    time.time(),
                    report.model_dump_json(),
                    self.property_name,
                ),
            )
            return int(
                connection.execute(
                    "SELECT revision FROM gate WHERE property=?", (self.property_name,)
                ).fetchone()[0]
            )

    def reset(self, expected_revision: int) -> None:
        """Operator reset requires a fresh healthy observation at the exact revision."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            _, revision, checked, encoded = connection.execute(
                "SELECT blocked,revision,checked,report FROM gate WHERE property=?",
                (self.property_name,),
            ).fetchone()
            age = time.time() - checked
            if (
                revision != expected_revision
                or not 0 <= age <= self.max_age
                or DriftReport.model_validate_json(encoded).status != "healthy"
            ):
                raise RuntimeError(
                    "fresh healthy observation and current revision required"
                )
            connection.execute(
                "UPDATE gate SET blocked=0, revision=revision+1 WHERE property=?",
                (self.property_name,),
            )

    def authorize(self, request: ActionRequest) -> bool:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            blocked, revision, checked = connection.execute(
                "SELECT blocked,revision,checked FROM gate WHERE property=?",
                (self.property_name,),
            ).fetchone()
            now = time.time()
            allowed = (
                not blocked
                and request.expected_revision == revision
                and 0 <= now - checked <= self.max_age
            )
            connection.execute(
                "INSERT INTO decisions(property,checked,allowed,payload) VALUES (?,?,?,?)",
                (self.property_name, now, int(allowed), request.model_dump_json()),
            )
            return bool(allowed)
