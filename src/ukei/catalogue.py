"""Versioned SQLite persistence for sources and validation history."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ukei.models import SourceRecord, SourceStatus, ValidationResult, parse_datetime, utc_now

SCHEMA_VERSION = 1

_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    source_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    publisher TEXT NOT NULL,
    description TEXT NOT NULL,
    licence TEXT NOT NULL,
    geographic_scope TEXT NOT NULL,
    update_frequency TEXT NOT NULL,
    formats_json TEXT NOT NULL,
    themes_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('candidate', 'verified', 'degraded', 'retired')),
    discovered_at TEXT NOT NULL,
    last_verified_at TEXT,
    provenance_url TEXT,
    connector TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_url ON sources(url);
CREATE INDEX IF NOT EXISTS idx_sources_publisher ON sources(publisher);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);
CREATE TABLE IF NOT EXISTS validation_events (
    validation_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    message TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_validation_source_time
    ON validation_events(source_id, checked_at DESC);
"""


class CatalogueError(RuntimeError):
    """The catalogue could not complete a requested operation."""


class Catalogue:
    """Transactional repository for catalogue domain records."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> int:
        """Apply all known idempotent migrations and return the schema version."""
        with self.connect() as connection:
            connection.executescript(_MIGRATION_1)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, utc_now().isoformat()),
            )
        return SCHEMA_VERSION

    def schema_version(self) -> int:
        if not self.path.exists():
            return 0
        try:
            with self.connect() as connection:
                row = connection.execute(
                    "SELECT MAX(version) AS version FROM schema_migrations"
                ).fetchone()
        except sqlite3.OperationalError:
            return 0
        return int(row["version"] or 0) if row else 0

    def upsert_source(self, source: SourceRecord) -> SourceRecord:
        """Insert or update a source while preserving its original creation timestamp."""
        self.initialize()
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT created_at FROM sources WHERE source_id = ?", (source.source_id,)
            ).fetchone()
            created_at = parse_datetime(existing["created_at"]) if existing else source.created_at
            updated_at = now if existing else source.updated_at
            stored = replace(
                source, created_at=created_at or now, updated_at=updated_at
            ).with_current_hash()
            values = self._source_values(stored)
            try:
                connection.execute(
                    """
                    INSERT INTO sources (
                        source_id, title, url, publisher, description, licence, geographic_scope,
                        update_frequency, formats_json, themes_json, status, discovered_at,
                        last_verified_at, provenance_url, connector, content_hash,
                        created_at, updated_at
                    ) VALUES (
                        :source_id, :title, :url, :publisher, :description, :licence,
                        :geographic_scope, :update_frequency, :formats_json, :themes_json, :status,
                        :discovered_at, :last_verified_at, :provenance_url, :connector,
                        :content_hash,
                        :created_at, :updated_at
                    )
                    ON CONFLICT(source_id) DO UPDATE SET
                        title=excluded.title, url=excluded.url, publisher=excluded.publisher,
                        description=excluded.description, licence=excluded.licence,
                        geographic_scope=excluded.geographic_scope,
                        update_frequency=excluded.update_frequency,
                        formats_json=excluded.formats_json, themes_json=excluded.themes_json,
                        status=excluded.status, discovered_at=excluded.discovered_at,
                        last_verified_at=excluded.last_verified_at,
                        provenance_url=excluded.provenance_url, connector=excluded.connector,
                        content_hash=excluded.content_hash, updated_at=excluded.updated_at
                    """,
                    values,
                )
            except sqlite3.IntegrityError as exc:
                message = f"source URL already belongs to another record: {source.url}"
                raise CatalogueError(message) from exc
        return stored

    def get_source(self, source_id: str) -> SourceRecord | None:
        self.initialize()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE source_id = ?", (source_id,)
            ).fetchone()
        return self._row_to_source(row) if row else None

    def list_sources(self, *, status: SourceStatus | None = None) -> list[SourceRecord]:
        self.initialize()
        query = "SELECT * FROM sources"
        parameters: tuple[str, ...] = ()
        if status:
            query += " WHERE status = ?"
            parameters = (status.value,)
        query += " ORDER BY publisher COLLATE NOCASE, title COLLATE NOCASE"
        with self.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_source(row) for row in rows]

    def record_validations(self, results: Sequence[ValidationResult]) -> None:
        if not results:
            return
        self.initialize()
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO validation_events (
                    validation_id, source_id, check_name, passed, message, checked_at, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        result.validation_id,
                        result.source_id,
                        result.check_name,
                        int(result.passed),
                        result.message,
                        result.checked_at.astimezone(UTC).isoformat(),
                        json.dumps(result.details, sort_keys=True),
                    )
                    for result in results
                ],
            )

    def validation_history(self, source_id: str) -> list[ValidationResult]:
        self.initialize()
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM validation_events WHERE source_id = ? ORDER BY checked_at DESC",
                (source_id,),
            ).fetchall()
        return [
            ValidationResult(
                validation_id=row["validation_id"],
                source_id=row["source_id"],
                check_name=row["check_name"],
                passed=bool(row["passed"]),
                message=row["message"],
                checked_at=parse_datetime(row["checked_at"]) or utc_now(),
                details=json.loads(row["details_json"]),
            )
            for row in rows
        ]

    def counts(self) -> dict[str, int]:
        self.initialize()
        counts = {status.value: 0 for status in SourceStatus}
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM sources GROUP BY status"
            ).fetchall()
            validation_count = connection.execute(
                "SELECT COUNT(*) AS count FROM validation_events"
            ).fetchone()["count"]
        for row in rows:
            counts[row["status"]] = int(row["count"])
        counts["total"] = sum(counts.values())
        counts["validation_events"] = int(validation_count)
        return counts

    def integrity_errors(self) -> list[str]:
        """Return record-level hash mismatches and SQLite integrity failures."""
        errors: list[str] = []
        self.initialize()
        with self.connect() as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            errors.append(f"sqlite: {result}")
        for source in self.list_sources():
            if source.content_hash != source.calculate_hash():
                errors.append(f"hash mismatch: {source.source_id}")
        return errors

    def export_records(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": utc_now().isoformat(),
            "record_count": self.counts()["total"],
            "records": [source.to_dict() for source in self.list_sources()],
        }

    def import_records(self, records: Sequence[dict[str, Any]]) -> int:
        imported = 0
        for payload in records:
            source = SourceRecord.from_dict(payload)
            claimed_hash = source.content_hash
            if claimed_hash and claimed_hash != source.calculate_hash():
                raise CatalogueError(f"content hash mismatch for {source.source_id}")
            self.upsert_source(source)
            imported += 1
        return imported

    @staticmethod
    def _source_values(source: SourceRecord) -> dict[str, Any]:
        return {
            "source_id": source.source_id,
            "title": source.title,
            "url": source.url,
            "publisher": source.publisher,
            "description": source.description,
            "licence": source.licence,
            "geographic_scope": source.geographic_scope,
            "update_frequency": source.update_frequency,
            "formats_json": json.dumps(sorted(set(source.formats))),
            "themes_json": json.dumps(sorted(set(source.themes))),
            "status": source.status.value,
            "discovered_at": source.discovered_at.astimezone(UTC).isoformat(),
            "last_verified_at": (
                source.last_verified_at.astimezone(UTC).isoformat()
                if source.last_verified_at
                else None
            ),
            "provenance_url": source.provenance_url,
            "connector": source.connector,
            "content_hash": source.content_hash,
            "created_at": source.created_at.astimezone(UTC).isoformat(),
            "updated_at": source.updated_at.astimezone(UTC).isoformat(),
        }

    @staticmethod
    def _row_to_source(row: sqlite3.Row) -> SourceRecord:
        return SourceRecord(
            source_id=row["source_id"],
            title=row["title"],
            url=row["url"],
            publisher=row["publisher"],
            description=row["description"],
            licence=row["licence"],
            geographic_scope=row["geographic_scope"],
            update_frequency=row["update_frequency"],
            formats=tuple(json.loads(row["formats_json"])),
            themes=tuple(json.loads(row["themes_json"])),
            status=SourceStatus(row["status"]),
            discovered_at=parse_datetime(row["discovered_at"]) or datetime.now(UTC),
            last_verified_at=parse_datetime(row["last_verified_at"]),
            provenance_url=row["provenance_url"],
            connector=row["connector"],
            content_hash=row["content_hash"],
            created_at=parse_datetime(row["created_at"]) or datetime.now(UTC),
            updated_at=parse_datetime(row["updated_at"]) or datetime.now(UTC),
        )
