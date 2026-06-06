import unittest

from cpa.pricing import analyze_case, evaluate_evidence, normalize_unit_price


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "id": "case-1",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "USDA spec",
            "target_unit": "lb",
            "target_package_weight_value": None,
            "target_package_weight_unit": None,
            "destination": "North Dakota",
            "freight_responsibility": "delivered",
        }

    def test_50kg_bag_normalizes_to_lb(self):
        evidence = {
            "unit_price": 110.23113109,
            "price_basis_unit": "50kg_bag",
        }
        self.assertAlmostEqual(normalize_unit_price(evidence, self.case), 1.0, places=5)

    def test_usaspending_is_context_only(self):
        evidence = {
            "id": "ev-1",
            "source_type": "usaspending_award",
            "source_name": "USAspending award",
            "source_url": "https://api.usaspending.gov/",
            "citation": "",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "USDA spec",
            "price_date": "2026-06-04",
            "unit_price": 100,
            "price_basis_unit": "50kg_bag",
            "freight_included": True,
        }
        result = evaluate_evidence(self.case, evidence, [])
        self.assertEqual(result.status, "context_only")
        self.assertIn("Discovery source only", result.critical_issues[0])

    def test_analysis_stats_from_eligible_evidence(self):
        evidence = []
        for index, price in enumerate([100, 110, 120]):
            evidence.append(
                {
                    "id": f"ev-{index}",
                    "source_type": "analyst_upload",
                    "source_name": f"Line {index}",
                    "source_url": "https://example.gov/source",
                    "citation": "source",
                    "commodity": "pinto beans",
                    "form": "dry edible beans",
                    "pack": "50 kg bag",
                    "grade": "USDA spec",
                    "location": "North Dakota",
                    "price_date": "2026-06-04",
                    "unit_price": price,
                    "price_basis_unit": "50kg_bag",
                    "freight_included": True,
                }
            )
        analysis = analyze_case(self.case, evidence, [])
        self.assertEqual(analysis["eligible_count"], 3)
        self.assertAlmostEqual(analysis["statistics"]["median"], 110 / (50 * 2.2046226218), places=4)

    def test_pack_mismatch_excludes_evidence(self):
        evidence = {
            "id": "ev-1",
            "source_type": "analyst_upload",
            "source_name": "Wrong pack",
            "source_url": "https://example.gov/source",
            "citation": "source",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "25 kg bag",
            "grade": "USDA spec",
            "price_date": "2026-06-04",
            "unit_price": 60,
            "price_basis_unit": "kg",
            "freight_included": True,
        }
        result = evaluate_evidence(self.case, evidence, [])
        self.assertEqual(result.status, "context_only")
        self.assertTrue(any("Pack mismatch" in issue for issue in result.critical_issues))

    def test_negative_adjusted_price_excludes_evidence(self):
        evidence = {
            "id": "ev-1",
            "source_type": "analyst_upload",
            "source_name": "bad adjustment",
            "source_url": "https://example.gov/source",
            "citation": "source",
            "commodity": "pinto beans",
            "form": "dry edible beans",
            "pack": "50 kg bag",
            "grade": "USDA spec",
            "price_date": "2026-06-04",
            "unit_price": 1,
            "price_basis_unit": "lb",
            "freight_included": True,
        }
        adjustments = [
            {
                "evidence_id": "ev-1",
                "category": "other",
                "amount_per_unit": -2,
                "rationale": "test",
            }
        ]
        result = evaluate_evidence(self.case, evidence, adjustments)
        self.assertEqual(result.status, "context_only")
        self.assertTrue(any("zero or negative" in issue for issue in result.critical_issues))


if __name__ == "__main__":
    unittest.main()
