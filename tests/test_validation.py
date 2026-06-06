import unittest

from cpa.validation import ValidationError, validate_case_payload, validate_evidence_payload


class ValidationTests(unittest.TestCase):
    def test_case_requires_positive_quantity(self):
        with self.assertRaises(ValidationError):
            validate_case_payload(
                {
                    "commodity": "pinto beans",
                    "form": "dry edible beans",
                    "pack": "50 kg bag",
                    "quantity_value": 0,
                }
            )

    def test_evidence_rejects_bad_url(self):
        with self.assertRaises(ValidationError):
            validate_evidence_payload(
                {
                    "source_name": "bad source",
                    "source_url": "file:///secret",
                }
            )

    def test_evidence_requires_basis_with_unit_price(self):
        with self.assertRaises(ValidationError):
            validate_evidence_payload(
                {
                    "source_name": "missing unit",
                    "unit_price": 10,
                }
            )


if __name__ == "__main__":
    unittest.main()

