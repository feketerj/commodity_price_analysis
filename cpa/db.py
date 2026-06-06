from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
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
                """
            )

    def list_cases(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM cases ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def create_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        case_id = payload.get("id") or str(uuid.uuid4())
        now = utc_now()
        record = {
            "id": case_id,
            "title": payload.get("title") or "Untitled pricing case",
            "commodity": payload.get("commodity") or "",
            "form": payload.get("form") or "",
            "pack": payload.get("pack") or "",
            "grade": payload.get("grade") or "",
            "target_unit": payload.get("target_unit") or "lb",
            "target_package_weight_value": payload.get("target_package_weight_value"),
            "target_package_weight_unit": payload.get("target_package_weight_unit"),
            "quantity_value": float(payload.get("quantity_value") or 0),
            "quantity_unit": payload.get("quantity_unit") or "",
            "destination": payload.get("destination") or "",
            "delivery_window": payload.get("delivery_window") or "",
            "acquisition_method": payload.get("acquisition_method") or "",
            "freight_responsibility": payload.get("freight_responsibility") or "delivered",
            "notes": payload.get("notes") or "",
            "created_at": now,
            "updated_at": now,
        }
        if not record["commodity"] or not record["form"] or not record["pack"]:
            raise ValueError("case commodity, form, and pack are required")
        with self.connect() as conn:
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
        now = utc_now()
        record = {
            "id": payload.get("id") or str(uuid.uuid4()),
            "case_id": case_id,
            "source_type": payload.get("source_type") or "analyst_upload",
            "source_name": payload.get("source_name") or "",
            "source_url": payload.get("source_url") or "",
            "citation": payload.get("citation") or "",
            "retrieved_at": payload.get("retrieved_at") or now,
            "raw_description": payload.get("raw_description") or "",
            "commodity": payload.get("commodity") or "",
            "form": payload.get("form") or "",
            "pack": payload.get("pack") or "",
            "grade": payload.get("grade") or "",
            "location": payload.get("location") or "",
            "price_date": payload.get("price_date") or "",
            "quantity_value": _float_or_none(payload.get("quantity_value")),
            "quantity_unit": payload.get("quantity_unit"),
            "unit_price": _float_or_none(payload.get("unit_price")),
            "price_basis_unit": payload.get("price_basis_unit"),
            "package_weight_value": _float_or_none(payload.get("package_weight_value")),
            "package_weight_unit": payload.get("package_weight_unit"),
            "freight_included": 1 if payload.get("freight_included") else 0,
            "delivery_terms": payload.get("delivery_terms") or "",
            "metadata_json": _json(payload.get("metadata") or {}),
            "created_at": now,
        }
        if not record["source_name"]:
            raise ValueError("evidence source_name is required")
        with self.connect() as conn:
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
        now = utc_now()
        record = {
            "id": payload.get("id") or str(uuid.uuid4()),
            "case_id": case_id,
            "evidence_id": payload.get("evidence_id"),
            "category": payload.get("category") or "other",
            "amount_per_unit": float(payload.get("amount_per_unit") or 0),
            "rationale": payload.get("rationale") or "",
            "source_url": payload.get("source_url") or "",
            "created_at": now,
        }
        if not record["rationale"]:
            raise ValueError("adjustment rationale is required")
        with self.connect() as conn:
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
        with self.connect() as conn:
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


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)

