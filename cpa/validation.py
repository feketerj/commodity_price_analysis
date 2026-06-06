from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any


MAX_TEXT = 2_000
MAX_NOTE = 10_000
ALLOWED_UNITS = {"lb", "kg", "50kg_bag", "case"}
ALLOWED_FREIGHT = {"delivered", "origin", "unknown"}
ALLOWED_SOURCE_TYPES = {
    "analyst_upload",
    "ams_award_line",
    "market_news",
    "quote",
    "usaspending_award",
    "sam_opportunity",
    "sam_award_notice",
    "other",
}
ALLOWED_ADJUSTMENTS = {
    "freight",
    "time_index",
    "regional_basis",
    "pack_grade",
    "quantity",
    "urgency",
    "other",
}
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


class ValidationError(ValueError):
    pass


def validate_case_payload(payload: dict[str, Any]) -> dict[str, Any]:
    record = {
        "id": clean_optional_id(payload.get("id")),
        "title": clean_text(payload.get("title") or "Untitled pricing case", "title"),
        "commodity": required_text(payload.get("commodity"), "commodity"),
        "form": required_text(payload.get("form"), "form"),
        "pack": required_text(payload.get("pack"), "pack"),
        "grade": clean_text(payload.get("grade") or "", "grade"),
        "target_unit": clean_unit(payload.get("target_unit") or "lb", "target_unit"),
        "target_package_weight_value": optional_positive_float(payload.get("target_package_weight_value"), "target_package_weight_value"),
        "target_package_weight_unit": clean_optional_unit(payload.get("target_package_weight_unit"), "target_package_weight_unit"),
        "quantity_value": positive_float(payload.get("quantity_value"), "quantity_value"),
        "quantity_unit": clean_text(payload.get("quantity_unit") or "", "quantity_unit"),
        "destination": clean_text(payload.get("destination") or "", "destination"),
        "delivery_window": clean_text(payload.get("delivery_window") or "", "delivery_window"),
        "acquisition_method": clean_text(payload.get("acquisition_method") or "", "acquisition_method"),
        "freight_responsibility": clean_choice(payload.get("freight_responsibility") or "delivered", ALLOWED_FREIGHT, "freight_responsibility"),
        "notes": clean_text(payload.get("notes") or "", "notes", max_length=MAX_NOTE),
    }
    if record["target_unit"] == "case" and record["target_package_weight_value"] is None:
        raise ValidationError("target_package_weight_value is required when target_unit is case")
    return record


def validate_evidence_payload(payload: dict[str, Any]) -> dict[str, Any]:
    unit_price = optional_positive_float(payload.get("unit_price"), "unit_price")
    basis_unit = clean_optional_unit(payload.get("price_basis_unit"), "price_basis_unit")
    if unit_price is not None and not basis_unit:
        raise ValidationError("price_basis_unit is required when unit_price is provided")
    if basis_unit and unit_price is None:
        raise ValidationError("unit_price is required when price_basis_unit is provided")

    package_weight_value = optional_positive_float(payload.get("package_weight_value"), "package_weight_value")
    package_weight_unit = clean_optional_unit(payload.get("package_weight_unit"), "package_weight_unit")
    if package_weight_value is not None and not package_weight_unit:
        raise ValidationError("package_weight_unit is required when package_weight_value is provided")

    return {
        "id": clean_optional_id(payload.get("id")),
        "source_type": clean_choice(payload.get("source_type") or "analyst_upload", ALLOWED_SOURCE_TYPES, "source_type"),
        "source_name": required_text(payload.get("source_name"), "source_name"),
        "source_url": clean_url(payload.get("source_url") or "", "source_url"),
        "citation": clean_text(payload.get("citation") or "", "citation"),
        "retrieved_at": clean_text(payload.get("retrieved_at") or "", "retrieved_at"),
        "raw_description": clean_text(payload.get("raw_description") or "", "raw_description", max_length=MAX_NOTE),
        "commodity": clean_text(payload.get("commodity") or "", "commodity"),
        "form": clean_text(payload.get("form") or "", "form"),
        "pack": clean_text(payload.get("pack") or "", "pack"),
        "grade": clean_text(payload.get("grade") or "", "grade"),
        "location": clean_text(payload.get("location") or "", "location"),
        "price_date": clean_date(payload.get("price_date") or "", "price_date"),
        "quantity_value": optional_positive_float(payload.get("quantity_value"), "quantity_value"),
        "quantity_unit": clean_text(payload.get("quantity_unit") or "", "quantity_unit"),
        "unit_price": unit_price,
        "price_basis_unit": basis_unit,
        "package_weight_value": package_weight_value,
        "package_weight_unit": package_weight_unit,
        "freight_included": bool(payload.get("freight_included")),
        "delivery_terms": clean_text(payload.get("delivery_terms") or "", "delivery_terms"),
        "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    }


def validate_adjustment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": clean_optional_id(payload.get("id")),
        "evidence_id": clean_optional_id(payload.get("evidence_id")),
        "category": clean_choice(payload.get("category") or "other", ALLOWED_ADJUSTMENTS, "category"),
        "amount_per_unit": finite_float(payload.get("amount_per_unit"), "amount_per_unit"),
        "rationale": required_text(payload.get("rationale"), "rationale", max_length=MAX_NOTE),
        "source_url": clean_url(payload.get("source_url") or "", "source_url"),
    }


def clean_optional_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    value = str(value).strip()
    if not ID_RE.match(value):
        raise ValidationError("id must be 1-96 characters using letters, numbers, underscore, period, or hyphen")
    return value


def required_text(value: Any, field: str, max_length: int = MAX_TEXT) -> str:
    text = clean_text(value, field, max_length=max_length)
    if not text:
        raise ValidationError(f"{field} is required")
    return text


def clean_text(value: Any, field: str, max_length: int = MAX_TEXT) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        raise ValidationError(f"{field} exceeds {max_length} characters")
    if any(ord(char) < 9 for char in text):
        raise ValidationError(f"{field} contains unsupported control characters")
    return text


def clean_choice(value: Any, allowed: set[str], field: str) -> str:
    text = clean_text(value, field).lower()
    if text not in allowed:
        raise ValidationError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return text


def clean_unit(value: Any, field: str) -> str:
    text = normalize_unit(value)
    if text not in ALLOWED_UNITS:
        raise ValidationError(f"{field} must be one of: {', '.join(sorted(ALLOWED_UNITS))}")
    return text


def clean_optional_unit(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    return clean_unit(value, field)


def normalize_unit(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "pound": "lb",
        "pounds": "lb",
        "lbs": "lb",
        "kilogram": "kg",
        "kilograms": "kg",
        "50_kg_bag": "50kg_bag",
        "bag_50_kg": "50kg_bag",
        "bag_50kg": "50kg_bag",
        "carton": "case",
        "ctn": "case",
    }
    return aliases.get(text, text)


def positive_float(value: Any, field: str) -> float:
    number = finite_float(value, field)
    if number <= 0:
        raise ValidationError(f"{field} must be greater than zero")
    return number


def optional_positive_float(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    return positive_float(value, field)


def finite_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a number") from exc
    if not math.isfinite(number):
        raise ValidationError(f"{field} must be finite")
    return number


def clean_url(value: Any, field: str) -> str:
    text = clean_text(value or "", field)
    if not text:
        return ""
    if not (text.startswith("https://") or text.startswith("http://")):
        raise ValidationError(f"{field} must start with http:// or https://")
    return text


def clean_date(value: Any, field: str) -> str:
    text = clean_text(value or "", field, max_length=32)
    if not text:
        return ""
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError(f"{field} must be YYYY-MM-DD") from exc
    return text

