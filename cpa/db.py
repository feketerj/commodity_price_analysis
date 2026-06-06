from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cpa.validation import validate_adjustment_payload, validate_case_payload, validate_evidence_payload


SCHEMA_VERSION = "2026-06-06.operator.1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _parse_json(value: str | None) -> Any:
    if not value:
        return None
    return json.loads(value)


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def session(self):
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.session() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    commodity TEXT NOT NULL,
                    form TEXT NOT NULL,
                    pack TEXT NOT NULL,
                    grade TEXT NOT NULL DEFAULT '',
                    target_unit TEXT NOT NULL,
                    target_package_weight_value REAL,
                    target_package_weight_unit TEXT,
                    quantity_value REAL NOT NULL DEFAULT 0,
                    quantity_unit TEXT NOT NULL DEFAULT '',
                    destination TEXT NOT NULL DEFAULT '',
                    delivery_window TEXT NOT NULL DEFAULT '',
                    acquisition_method TEXT NOT NULL DEFAULT '',
                    freight_responsibility TEXT NOT NULL DEFAULT 'delivered',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    citation TEXT NOT NULL DEFAULT '',
                    retrieved_at TEXT NOT NULL,
                    raw_description TEXT NOT NULL DEFAULT '',
                    commodity TEXT NOT NULL DEFAULT '',
                    form TEXT NOT NULL DEFAULT '',
                    pack TEXT NOT NULL DEFAULT '',
                    grade TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    price_date TEXT NOT NULL DEFAULT '',
                    quantity_value REAL,
                    quantity_unit TEXT,
                    unit_price REAL,
                    price_basis_unit TEXT,
                    package_weight_value REAL,
                    package_weight_unit TEXT,
                    freight_included INTEGER NOT NULL DEFAULT 0,
                    delivery_terms TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS adjustments (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    evidence_id TEXT REFERENCES evidence(id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    amount_per_unit REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    source_url TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY,
                    case_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_evidence_case_created ON evidence(case_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_adjustments_case_created ON adjustments(case_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_audit_case_created ON audit_events(case_id, created_at);
                """
            )
            conn.execute(
                """
                INSERT INTO schema_meta (key, value, updated_at)
                VALUES ('schema_version', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (SCHEMA_VERSION, utc_now()),
            )

    def list_cases(self) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute("SELECT * FROM cases ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = validate_case_payload(payload)
        case_id = payload.get("id") or str(uuid.uuid4())
        now = utc_now()
        record = {
            "id": case_id,
            "title": payload["title"],
            "commodity": payload["commodity"],
            "form": payload["form"],
            "pack": payload["pack"],
            "grade": payload["grade"],
            "target_unit": payload["target_unit"],
            "target_package_weight_value": payload.get("target_package_weight_value"),
            "target_package_weight_unit": payload.get("target_package_weight_unit"),
            "quantity_value": payload["quantity_value"],
            "quantity_unit": payload["quantity_unit"],
            "destination": payload["destination"],
            "delivery_window": payload["delivery_window"],
            "acquisition_method": payload["acquisition_method"],
            "freight_responsibility": payload["freight_responsibility"],
            "notes": payload["notes"],
            "created_at": now,
            "updated_at": now,
        }
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO cases (
                    id, title, commodity, form, pack, grade, target_unit,
                    target_package_weight_value, target_package_weight_unit,
                    quantity_value, quantity_unit, destination, delivery_window,
                    acquisition_method, freight_responsibility, notes, created_at, updated_at
                ) VALUES (
                    :id, :title, :commodity, :form, :pack, :grade, :target_unit,
                    :target_package_weight_value, :target_package_weight_unit,
                    :quantity_value, :quantity_unit, :destination, :delivery_window,
                    :acquisition_method, :freight_responsibility, :notes, :created_at, :updated_at
                )
                """,
                record,
            )
            self._audit(conn, case_id, "case_created", record)
        return record

    def add_evidence(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_case_bundle(case_id):
            raise ValueError(f"case not found: {case_id}")
        payload = validate_evidence_payload(payload)
        now = utc_now()
        record = {
            "id": payload.get("id") or str(uuid.uuid4()),
            "case_id": case_id,
            "source_type": payload["source_type"],
            "source_name": payload["source_name"],
            "source_url": payload["source_url"],
            "citation": payload["citation"],
            "retrieved_at": payload.get("retrieved_at") or now,
            "raw_description": payload["raw_description"],
            "commodity": payload["commodity"],
            "form": payload["form"],
            "pack": payload["pack"],
            "grade": payload["grade"],
            "location": payload["location"],
            "price_date": payload["price_date"],
            "quantity_value": payload.get("quantity_value"),
            "quantity_unit": payload.get("quantity_unit"),
            "unit_price": payload.get("unit_price"),
            "price_basis_unit": payload.get("price_basis_unit"),
            "package_weight_value": payload.get("package_weight_value"),
            "package_weight_unit": payload.get("package_weight_unit"),
            "freight_included": 1 if payload.get("freight_included") else 0,
            "delivery_terms": payload["delivery_terms"],
            "metadata_json": _json(payload.get("metadata") or {}),
            "created_at": now,
        }
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO evidence (
                    id, case_id, source_type, source_name, source_url, citation, retrieved_at,
                    raw_description, commodity, form, pack, grade, location, price_date,
                    quantity_value, quantity_unit, unit_price, price_basis_unit,
                    package_weight_value, package_weight_unit, freight_included,
                    delivery_terms, metadata_json, created_at
                ) VALUES (
                    :id, :case_id, :source_type, :source_name, :source_url, :citation, :retrieved_at,
                    :raw_description, :commodity, :form, :pack, :grade, :location, :price_date,
                    :quantity_value, :quantity_unit, :unit_price, :price_basis_unit,
                    :package_weight_value, :package_weight_unit, :freight_included,
                    :delivery_terms, :metadata_json, :created_at
                )
                """,
                record,
            )
            conn.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now, case_id))
            self._audit(conn, case_id, "evidence_added", record)
        return self._row_to_evidence(record)

    def add_adjustment(self, case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.get_case_bundle(case_id):
            raise ValueError(f"case not found: {case_id}")
        payload = validate_adjustment_payload(payload)
        now = utc_now()
        record = {
            "id": payload.get("id") or str(uuid.uuid4()),
            "case_id": case_id,
            "evidence_id": payload.get("evidence_id"),
            "category": payload["category"],
            "amount_per_unit": payload["amount_per_unit"],
            "rationale": payload["rationale"],
            "source_url": payload["source_url"],
            "created_at": now,
        }
        with self.session() as conn:
            conn.execute(
                """
                INSERT INTO adjustments (
                    id, case_id, evidence_id, category, amount_per_unit, rationale, source_url, created_at
                ) VALUES (
                    :id, :case_id, :evidence_id, :category, :amount_per_unit, :rationale, :source_url, :created_at
                )
                """,
                record,
            )
            conn.execute("UPDATE cases SET updated_at = ? WHERE id = ?", (now, case_id))
            self._audit(conn, case_id, "adjustment_added", record)
        return record

    def get_case_bundle(self, case_id: str) -> dict[str, Any] | None:
        with self.session() as conn:
            case_row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
            if not case_row:
                return None
            evidence_rows = conn.execute("SELECT * FROM evidence WHERE case_id = ? ORDER BY created_at", (case_id,)).fetchall()
            adjustment_rows = conn.execute("SELECT * FROM adjustments WHERE case_id = ? ORDER BY created_at", (case_id,)).fetchall()
        return {
            "case": dict(case_row),
            "evidence": [self._row_to_evidence(dict(row)) for row in evidence_rows],
            "adjustments": [dict(row) for row in adjustment_rows],
        }

    def audit_events(self, case_id: str) -> list[dict[str, Any]]:
        with self.session() as conn:
            rows = conn.execute(
                "SELECT * FROM audit_events WHERE case_id = ? ORDER BY created_at",
                (case_id,),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            event = dict(row)
            event["payload"] = _parse_json(event.pop("payload_json"))
            events.append(event)
        return events

    def backup(self, backup_dir: Path) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = utc_now().replace(":", "").replace("+", "Z")
        backup_path = backup_dir / f"commodity_price_analysis-{stamp}.sqlite3"
        source = self.connect()
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return backup_path

    def status(self) -> dict[str, Any]:
        with self.session() as conn:
            case_count = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            evidence_count = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            adjustment_count = conn.execute("SELECT COUNT(*) FROM adjustments").fetchone()[0]
            audit_count = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            schema_row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            wal_checkpoint = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        return {
            "ok": True,
            "database_path": str(self.path),
            "database_exists": self.path.exists(),
            "database_size_bytes": self.path.stat().st_size if self.path.exists() else 0,
            "schema_version": schema_row[0] if schema_row else "unknown",
            "journal_mode": journal_mode,
            "wal_checkpoint": list(wal_checkpoint) if wal_checkpoint else [],
            "counts": {
                "cases": case_count,
                "evidence": evidence_count,
                "adjustments": adjustment_count,
                "audit_events": audit_count,
            },
        }

    def _audit(self, conn: sqlite3.Connection, case_id: str | None, event_type: str, payload: dict[str, Any]) -> None:
        conn.execute(
            "INSERT INTO audit_events (id, case_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), case_id, event_type, _json(payload), utc_now()),
        )

    def _row_to_evidence(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row["metadata"] = _parse_json(row.pop("metadata_json", "{}")) or {}
        row["freight_included"] = bool(row["freight_included"])
        return row
