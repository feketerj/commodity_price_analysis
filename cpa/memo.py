from __future__ import annotations

from datetime import datetime
from typing import Any


def build_memo(case: dict[str, Any], analysis: dict[str, Any]) -> str:
    stats = analysis["statistics"]
    lines: list[str] = []
    lines.append("FAIR AND REASONABLE PRICE ANALYSIS SUPPORT")
    lines.append("Prototype decision-support output; contracting officer review required.")
    lines.append("")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Case: {case['title']}")
    lines.append(f"Commodity: {case['commodity']} | Form: {case['form']} | Pack: {case['pack']} | Grade/Spec: {case.get('grade') or 'not specified'}")
    lines.append(f"Quantity: {case['quantity_value']} {case['quantity_unit']} | Destination: {case.get('destination') or 'not specified'}")
    lines.append(f"Delivery window: {case.get('delivery_window') or 'not specified'} | Pricing unit: {case['target_unit']}")
    lines.append("")

    lines.append("1. Pricing Method")
    lines.append(analysis["method"]["basis"])
    for item in analysis["method"]["techniques"]:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("2. Comparable Unit-Price Evidence")
    if analysis["eligible_count"] == 0:
        lines.append("No evidence passed the comparability gate. Do not use this output as a fair-and-reasonable determination.")
    else:
        for row in analysis["evidence"]:
            if row["status"] != "unit_price_eligible":
                continue
            lines.append(
                f"- {row['source_name']}: normalized ${row['normalized_unit_price']} per {row['target_unit']}; "
                f"adjusted ${row['adjusted_unit_price']} per {row['target_unit']}."
            )
            for adj in row["adjustments"]:
                lines.append(f"  Adjustment: {adj['category']} {adj['amount_per_unit']:+.4f}; {adj['rationale']}")
            for warning in row["warnings"]:
                lines.append(f"  Warning: {warning}")
    lines.append("")

    lines.append("3. Context-Only or Excluded Evidence")
    excluded = [row for row in analysis["evidence"] if row["status"] != "unit_price_eligible"]
    if not excluded:
        lines.append("No evidence was excluded.")
    for row in excluded:
        lines.append(f"- {row['source_name']}")
        for issue in row["critical_issues"]:
            lines.append(f"  Exclusion reason: {issue}")
        for warning in row["warnings"]:
            lines.append(f"  Warning: {warning}")
    lines.append("")

    lines.append("4. Price Range")
    if stats["count"] == 0:
        lines.append("No auditable unit-price range available.")
    else:
        lines.append(
            f"Eligible count: {stats['count']}; median ${stats['median']} per {case['target_unit']}; "
            f"observed range ${stats['min']} to ${stats['max']} per {case['target_unit']}."
        )
        lines.append(
            f"Reasonableness screen: ${stats['reasonableness_low']} to ${stats['reasonableness_high']} per {case['target_unit']}."
        )
    lines.append("")

    lines.append("5. Risk Flags")
    if not analysis["risk_flags"]:
        lines.append("No automated risk flags.")
    for flag in analysis["risk_flags"]:
        lines.append(f"- {flag}")
    lines.append("")

    lines.append("6. Draft CO Language")
    lines.append(
        "Based on the cited market research, eligible comparable unit-price evidence, and documented adjustments, "
        "the contracting officer may use this record as support for an independent fair-and-reasonable price determination. "
        "This prototype does not make the determination; it identifies the evidence used, evidence excluded, calculations performed, "
        "and issues requiring contracting officer judgment."
    )
    lines.append("")
    lines.append("7. Review Checklist")
    lines.append("- Confirm all cited sources are present in the contract file.")
    lines.append("- Confirm commodity specification, pack, grade, quantity, delivery location, and delivery window match the requirement.")
    lines.append("- Confirm any freight, index, location, urgency, or pack adjustments are independently supportable.")
    lines.append("- Confirm USAspending/SAM records were used as discovery/context unless line-level unit data was supplied.")
    lines.append("- Confirm final determination language is edited and signed by the responsible contracting officer.")
    return "\n".join(lines)

