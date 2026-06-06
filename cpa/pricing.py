from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Any


KG_TO_LB = 2.2046226218
CONTEXT_ONLY_SOURCE_TYPES = {"usaspending_award", "sam_opportunity", "sam_award_notice"}


@dataclass
class PriceResult:
    evidence_id: str
    source_name: str
    status: str
    normalized_unit_price: float | None
    adjusted_unit_price: float | None
    target_unit: str
    critical_issues: list[str]
    warnings: list[str]
    adjustments: list[dict[str, Any]]


def analyze_case(case: dict[str, Any], evidence: list[dict[str, Any]], adjustments: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [evaluate_evidence(case, item, adjustments) for item in evidence]
    eligible = [row for row in rows if row.status == "unit_price_eligible" and row.adjusted_unit_price is not None]
    prices = [row.adjusted_unit_price for row in eligible if row.adjusted_unit_price is not None]
    stats = _stats(prices)

    risk_flags = _case_risk_flags(case, rows, stats)
    return {
        "case_id": case["id"],
        "target_unit": case["target_unit"],
        "evidence_count": len(rows),
        "eligible_count": len(eligible),
        "context_count": len(rows) - len(eligible),
        "evidence": [row.__dict__ for row in rows],
        "statistics": stats,
        "risk_flags": risk_flags,
        "method": _method_summary(case, eligible, rows),
        "source_integrity": _source_integrity(rows),
    }


def evaluate_evidence(case: dict[str, Any], item: dict[str, Any], adjustments: list[dict[str, Any]]) -> PriceResult:
    critical: list[str] = []
    warnings: list[str] = []

    source_type = (item.get("source_type") or "").lower()
    if source_type in CONTEXT_ONLY_SOURCE_TYPES:
        critical.append("Discovery source only: does not provide reliable CLIN-level unit price by itself.")

    if not item.get("source_url") and not item.get("citation"):
        critical.append("Missing source URL or citation.")
    if item.get("unit_price") is None or not item.get("price_basis_unit"):
        critical.append("Missing unit price or price basis unit.")
    if not item.get("price_date"):
        critical.append("Missing price date.")

    _compare_text(case, item, "commodity", critical)
    _compare_text(case, item, "form", critical)
    _compare_text(case, item, "pack", critical)

    if case.get("grade") and item.get("grade") and _norm(case["grade"]) != _norm(item["grade"]):
        warnings.append(f"Grade/spec differs: case '{case['grade']}' vs evidence '{item['grade']}'.")
    if case.get("grade") and not item.get("grade"):
        warnings.append("Evidence grade/spec is missing; analyst review required.")
    if case.get("destination") and item.get("location") and _norm(case["destination"]) != _norm(item["location"]):
        warnings.append("Delivery location differs; basis or freight adjustment may be required.")
    if case.get("freight_responsibility") == "delivered" and not item.get("freight_included"):
        warnings.append("Case is delivered pricing, but evidence is not marked freight-included.")

    normalized_price: float | None = None
    if item.get("unit_price") is not None and item.get("price_basis_unit"):
        try:
            normalized_price = normalize_unit_price(item, case)
        except ValueError as exc:
            critical.append(str(exc))

    item_adjustments = _adjustments_for_item(item["id"], adjustments)
    if item.get("freight_included") and any(adj["category"] == "freight" and adj["amount_per_unit"] > 0 for adj in item_adjustments):
        warnings.append("Freight appears included and a positive freight adjustment was also added; check for double counting.")

    adjusted = None
    if normalized_price is not None:
        adjusted = normalized_price + sum(float(adj["amount_per_unit"]) for adj in item_adjustments)

    status = "unit_price_eligible" if not critical else "context_only"
    return PriceResult(
        evidence_id=item["id"],
        source_name=item["source_name"],
        status=status,
        normalized_unit_price=_round_money(normalized_price),
        adjusted_unit_price=_round_money(adjusted),
        target_unit=case["target_unit"],
        critical_issues=critical,
        warnings=warnings,
        adjustments=item_adjustments,
    )


def normalize_unit_price(item: dict[str, Any], case: dict[str, Any]) -> float:
    unit_price = float(item["unit_price"])
    source_unit = _unit(item["price_basis_unit"])
    target_unit = _unit(case["target_unit"])

    if source_unit == target_unit:
        return unit_price

    if source_unit == "kg" and target_unit == "lb":
        return unit_price / KG_TO_LB
    if source_unit == "lb" and target_unit == "kg":
        return unit_price * KG_TO_LB
    if source_unit == "50kg_bag" and target_unit == "lb":
        return unit_price / (50 * KG_TO_LB)
    if source_unit == "50kg_bag" and target_unit == "kg":
        return unit_price / 50
    if source_unit == "lb" and target_unit == "50kg_bag":
        return unit_price * 50 * KG_TO_LB
    if source_unit == "kg" and target_unit == "50kg_bag":
        return unit_price * 50

    if source_unit == "case" and target_unit in {"lb", "kg"}:
        weight_lb = _package_weight_lb(item, "evidence")
        if target_unit == "lb":
            return unit_price / weight_lb
        return unit_price / (weight_lb / KG_TO_LB)

    if source_unit in {"lb", "kg"} and target_unit == "case":
        weight_lb = _case_package_weight_lb(case)
        per_lb = unit_price if source_unit == "lb" else unit_price / KG_TO_LB
        return per_lb * weight_lb

    raise ValueError(f"Unsupported unit conversion: {source_unit} to {target_unit}. Add package weight or compare on same unit.")


def _package_weight_lb(item: dict[str, Any], label: str) -> float:
    value = item.get("package_weight_value")
    unit = _unit(item.get("package_weight_unit"))
    if value is None or not unit:
        raise ValueError(f"Cannot convert {label} case/package to weight without package_weight_value and package_weight_unit.")
    value = float(value)
    if unit == "lb":
        return value
    if unit == "kg":
        return value * KG_TO_LB
    raise ValueError(f"Unsupported package weight unit: {unit}.")


def _case_package_weight_lb(case: dict[str, Any]) -> float:
    value = case.get("target_package_weight_value")
    unit = _unit(case.get("target_package_weight_unit"))
    if value is None or not unit:
        raise ValueError("Cannot convert to case price without case target_package_weight_value and target_package_weight_unit.")
    value = float(value)
    if unit == "lb":
        return value
    if unit == "kg":
        return value * KG_TO_LB
    raise ValueError(f"Unsupported case package weight unit: {unit}.")


def _compare_text(case: dict[str, Any], item: dict[str, Any], field: str, critical: list[str]) -> None:
    case_value = _norm(case.get(field))
    item_value = _norm(item.get(field))
    if not item_value:
        critical.append(f"Missing {field}.")
    elif case_value and case_value != item_value:
        critical.append(f"{field.title()} mismatch: case '{case.get(field)}' vs evidence '{item.get(field)}'.")


def _adjustments_for_item(evidence_id: str, adjustments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scoped: list[dict[str, Any]] = []
    for adj in adjustments:
        if adj.get("evidence_id") in (None, "", evidence_id):
            scoped.append(
                {
                    "category": adj["category"],
                    "amount_per_unit": float(adj["amount_per_unit"]),
                    "rationale": adj["rationale"],
                    "source_url": adj.get("source_url") or "",
                }
            )
    return scoped


def _stats(prices: list[float]) -> dict[str, Any]:
    if not prices:
        return {
            "count": 0,
            "median": None,
            "mean": None,
            "min": None,
            "max": None,
            "iqr": None,
            "mad": None,
            "reasonableness_low": None,
            "reasonableness_high": None,
        }
    ordered = sorted(prices)
    med = median(ordered)
    mean = sum(ordered) / len(ordered)
    mad = median([abs(price - med) for price in ordered])
    q1 = _percentile(ordered, 25)
    q3 = _percentile(ordered, 75)
    iqr = q3 - q1
    if len(ordered) < 3:
        low = ordered[0]
        high = ordered[-1]
    else:
        low = q1 - (1.5 * iqr)
        high = q3 + (1.5 * iqr)
    return {
        "count": len(ordered),
        "median": _round_money(med),
        "mean": _round_money(mean),
        "min": _round_money(min(ordered)),
        "max": _round_money(max(ordered)),
        "iqr": _round_money(iqr),
        "mad": _round_money(mad),
        "reasonableness_low": _round_money(low),
        "reasonableness_high": _round_money(high),
    }


def _percentile(values: list[float], pct: float) -> float:
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * pct / 100
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _case_risk_flags(case: dict[str, Any], rows: list[PriceResult], stats: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if stats["count"] == 0:
        flags.append("No unit-price eligible evidence. Memo must not assert fair and reasonable pricing.")
    elif stats["count"] < 3:
        flags.append("Fewer than three unit-price eligible comparables. Treat range as limited support.")
    if any(row.critical_issues for row in rows):
        flags.append("Some evidence was excluded by the comparability gate.")
    if case.get("freight_responsibility") == "delivered" and any(
        "freight" in " ".join(row.warnings).lower() for row in rows if row.status == "unit_price_eligible"
    ):
        flags.append("Delivered-price case has freight-related warnings.")
    return flags


def _method_summary(case: dict[str, Any], eligible: list[PriceResult], rows: list[PriceResult]) -> dict[str, Any]:
    techniques = [
        "Comparison to prior prices for same or similar items when unit-price evidence is eligible.",
        "Published market prices or indexes as contextual support when current, cited, and comparable.",
        "IGCE comparison using normalized unit prices and documented adjustments.",
    ]
    if any(row.status == "context_only" for row in rows):
        techniques.append("Market research context from discovery sources excluded from unit-price math unless CLIN-level data is present.")
    return {
        "basis": "FAR-style price analysis decision support",
        "techniques": techniques,
        "co_review_required": True,
    }


def _source_integrity(rows: list[PriceResult]) -> dict[str, Any]:
    return {
        "excluded_evidence_ids": [row.evidence_id for row in rows if row.status != "unit_price_eligible"],
        "warnings_count": sum(len(row.warnings) for row in rows),
        "critical_issue_count": sum(len(row.critical_issues) for row in rows),
    }


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def _unit(value: Any) -> str:
    value = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "pound": "lb",
        "pounds": "lb",
        "lbs": "lb",
        "kilogram": "kg",
        "kilograms": "kg",
        "50_kg_bag": "50kg_bag",
        "bag_50_kg": "50kg_bag",
        "bag-50-kg": "50kg_bag",
        "carton": "case",
        "ctn": "case",
    }
    return aliases.get(value, value)


def _round_money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)

