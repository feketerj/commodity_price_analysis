from __future__ import annotations

from cpa.db import Database


DEMO_CASE_ID = "demo-pinto-beans-50kg"


def seed_demo_data(db: Database) -> None:
    if db.get_case_bundle(DEMO_CASE_ID):
        return

    case = db.create_case(
        {
            "id": DEMO_CASE_ID,
            "title": "Demo IGCE - Pinto beans, 50 kg bags",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "USDA commodity specification for dry edible beans, peas, and lentils",
            "target_unit": "lb",
            "quantity_value": 2000,
            "quantity_unit": "50 kg bags",
            "destination": "North Dakota",
            "delivery_window": "August 2026",
            "acquisition_method": "AMS commodity procurement / fair-and-reasonable support",
            "freight_responsibility": "delivered",
            "notes": "Demo case uses sample analyst-entered unit prices plus live-source discovery concepts. Replace sample prices before contract-file use.",
        }
    )

    db.add_evidence(
        case["id"],
        {
            "source_type": "analyst_upload",
            "source_name": "Demo analyst-entered AMS award line A",
            "source_url": "https://www.ams.usda.gov/selling-food/solicitations",
            "citation": "Demo source; replace with actual WBSCM/PCA award line.",
            "raw_description": "BEANS, PINTO BAG-50 KG",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "USDA commodity specification for dry edible beans, peas, and lentils",
            "location": "North Dakota",
            "price_date": "2026-06-04",
            "unit_price": 78.50,
            "price_basis_unit": "50kg_bag",
            "freight_included": True,
            "delivery_terms": "delivered",
            "metadata": {"demo_only": True},
        },
    )
    db.add_evidence(
        case["id"],
        {
            "source_type": "analyst_upload",
            "source_name": "Demo analyst-entered AMS award line B",
            "source_url": "https://www.ams.usda.gov/selling-food/solicitations",
            "citation": "Demo source; replace with actual WBSCM/PCA award line.",
            "raw_description": "BEANS, PINTO BAG-50 KG",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "USDA commodity specification for dry edible beans, peas, and lentils",
            "location": "North Dakota",
            "price_date": "2026-06-04",
            "unit_price": 82.25,
            "price_basis_unit": "50kg_bag",
            "freight_included": True,
            "delivery_terms": "delivered",
            "metadata": {"demo_only": True},
        },
    )
    db.add_evidence(
        case["id"],
        {
            "source_type": "analyst_upload",
            "source_name": "Demo analyst-entered quote, adjusted for delivery",
            "source_url": "https://www.ams.usda.gov/selling-food/product-specs",
            "citation": "Demo quote source; replace with quote or market-research file.",
            "raw_description": "Pinto beans 50 kg bags, USDA spec, delivered ND",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "USDA commodity specification for dry edible beans, peas, and lentils",
            "location": "North Dakota",
            "price_date": "2026-05-20",
            "unit_price": 0.76,
            "price_basis_unit": "lb",
            "freight_included": True,
            "delivery_terms": "delivered",
            "metadata": {"demo_only": True},
        },
    )
    db.add_evidence(
        case["id"],
        {
            "source_type": "usaspending_award",
            "source_name": "USAspending context - AMS pinto bean award",
            "source_url": "https://api.usaspending.gov/",
            "citation": "USAspending discovery record; award amount is not unit-price evidence.",
            "raw_description": "COMMODITIES FOR USG FOOD DONATIONS: BEANS, PINTO BAG-50 KG",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "",
            "location": "North Dakota",
            "price_date": "2026-06-04",
            "unit_price": None,
            "price_basis_unit": None,
            "freight_included": False,
            "delivery_terms": "unknown",
            "metadata": {"demo_only": True, "award_amount": 153180.0},
        },
    )

