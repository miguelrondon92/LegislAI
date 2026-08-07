"""Tests for HiddenProvision persist / heal (sneaky riders DB source of truth)."""
import unittest
from unittest.mock import MagicMock, patch


class TestNormalizeProvisions(unittest.TestCase):
    def test_flat_tier_ab_shape(self):
        from services.hidden_provisions import iter_normalized_provisions

        rows = list(
            iter_normalized_provisions(
                {
                    "detected_provisions": [
                        {
                            "type": "Policy Rider",
                            "text": "Unrelated tax carve-out in a defense bill.",
                            "risk_level": "high",
                            "confidence_score": 0.9,
                            "risk_factors": ["unrelated domain"],
                            "potential_impact": "budget distortion",
                            "recommendation": "strike the rider",
                            "chunk_type": "full_text",
                        }
                    ]
                }
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provision_type"], "Policy Rider")
        self.assertEqual(rows[0]["risk_level"], "high")
        self.assertIn("Unrelated tax", rows[0]["provision_text"])

    def test_legacy_nested_shape(self):
        from services.hidden_provisions import iter_normalized_provisions

        rows = list(
            iter_normalized_provisions(
                {
                    "detected_provisions": [
                        {
                            "chunk_index": 2,
                            "chunk_type": "section",
                            "risk_level": "medium",
                            "confidence_score": 0.7,
                            "overall_assessment": "watch",
                            "suspicious_provisions": [
                                {
                                    "type": "Buried Waiver",
                                    "text": "Notwithstanding any other provision...",
                                    "risk_factors": ["notwithstanding"],
                                }
                            ],
                        }
                    ]
                }
            )
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provision_type"], "Buried Waiver")
        self.assertEqual(rows[0]["risk_level"], "medium")
        self.assertEqual(rows[0]["chunk_index"], 2)


class TestStoreAndHeal(unittest.TestCase):
    def setUp(self):
        from app import app, db
        from db_models import Bill, HiddenProvision

        self.app = app
        self.db = db
        self.Bill = Bill
        self.HiddenProvision = HiddenProvision
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_store_and_heal_roundtrip(self):
        from services.hidden_provisions import (
            heal_hidden_provisions_from_analysis,
            store_hidden_provisions,
        )

        bill = self.Bill.query.filter_by(
            congress=119, bill_type="hr", bill_number="22"
        ).first()
        if not bill:
            self.skipTest("119-HR22 not in local DB")

        # Clear table
        for row in self.HiddenProvision.query.filter_by(bill_id=bill.id).all():
            self.db.session.delete(row)
        self.db.session.commit()
        self.assertEqual(bill.get_hidden_provisions_count()["total"], 0)

        active = bill.get_active_ai_analysis()
        self.assertIsNotNone(active)
        data = active.get_analysis_data() or {}
        hidden = data.get("hidden_provisions")
        self.assertIsInstance(hidden, dict)
        self.assertTrue(hidden.get("detected_provisions"))

        healed = heal_hidden_provisions_from_analysis(bill)
        self.assertGreater(healed, 0)
        counts = bill.get_hidden_provisions_count()
        self.assertEqual(counts["total"], healed)
        self.assertGreater(counts["total"], 0)

        # Second heal is a no-op
        self.assertEqual(heal_hidden_provisions_from_analysis(bill), 0)

        # Replace store still works
        stored = store_hidden_provisions(
            bill, hidden, full_analysis=data, replace=True
        )
        self.assertEqual(stored, counts["total"])


if __name__ == "__main__":
    unittest.main()
