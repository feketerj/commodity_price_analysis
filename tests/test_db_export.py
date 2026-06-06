import tempfile
import unittest
from pathlib import Path

from cpa.db import Database
from cpa.exporting import build_case_export, build_igce_csv
from cpa.pricing import analyze_case


class DatabaseExportTests(unittest.TestCase):
    def test_backup_audit_and_exports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db = Database(root / "cpa.sqlite3")
            db.initialize()
            case = db.create_case(
                {
                    "commodity": "pinto beans",
                    "form": "dry edible beans",
                    "pack": "50 kg bag",
                    "target_unit": "lb",
                    "quantity_value": 10,
                    "quantity_unit": "bags",
                }
            )
            db.add_evidence(
                case["id"],
                {
                    "source_type": "analyst_upload",
                    "source_name": "line item",
                    "source_url": "https://example.gov/source",
                    "commodity": "pinto beans",
                    "form": "dry edible beans",
                    "pack": "50 kg bag",
                    "price_date": "2026-06-04",
                    "unit_price": 100,
                    "price_basis_unit": "50kg_bag",
                    "freight_included": True,
                },
            )
            bundle = db.get_case_bundle(case["id"])
            analysis = analyze_case(bundle["case"], bundle["evidence"], bundle["adjustments"])
            audit = db.audit_events(case["id"])
            export = build_case_export(bundle, analysis, audit)
            csv_text = build_igce_csv(bundle["case"], analysis)
            backup = db.backup(root / "backups")
            status = db.status()

            self.assertTrue(backup.exists())
            self.assertGreaterEqual(len(audit), 2)
            self.assertEqual(export["case"]["id"], case["id"])
            self.assertIn("line item", csv_text)
            self.assertEqual(status["counts"]["cases"], 1)


if __name__ == "__main__":
    unittest.main()

