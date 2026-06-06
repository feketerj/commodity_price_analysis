from __future__ import annotations

import csv
import io
from typing import Any

from cpa.db import utc_now


def build_case_export(bundle: dict[str, Any], analysis: dict[str, Any], audit_events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "export_schema": "commodity_price_analysis.case_export.v1",
        "generated_at": utc_now(),
        "case": bundle["case"],
        "evidence": bundle["evidence"],
        "adjustments": bundle["adjustments"],
        "analysis": analysis,
        "audit_events": audit_events,
    }


def build_igce_csv(case: dict[str, Any], analysis: dict[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "case_id",
            "case_title",
            "source_name",
            "status",
            "target_unit",
            "normalized_unit_price",
            "adjusted_unit_price",
            "adjustments",
            "critical_issues",
            "warnings",
        ]
    )
    for row in analysis["evidence"]:
        writer.writerow(
            [
                case["id"],
                case["title"],
                row["source_name"],
                row["status"],
                row["target_unit"],
                "" if row["normalized_unit_price"] is None else row["normalized_unit_price"],
                "" if row["adjusted_unit_price"] is None else row["adjusted_unit_price"],
                " | ".join(f"{adj['category']} {adj['amount_per_unit']:+.4f}: {adj['rationale']}" for adj in row["adjustments"]),
                " | ".join(row["critical_issues"]),
                " | ".join(row["warnings"]),
            ]
        )
    return buffer.getvalue()

