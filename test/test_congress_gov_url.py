#!/usr/bin/env python3
"""Unit tests for Bill.get_congress_gov_url() public congress.gov links."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app  # noqa: F401 — initializes db before models map
from db_models import Bill


class TestCongressGovUrl(unittest.TestCase):
    def _bill(self, congress, bill_type, bill_number):
        return Bill(congress=congress, bill_type=bill_type, bill_number=bill_number)

    def test_house_bill_119(self):
        bill = self._bill(119, 'hr', 7008)
        self.assertEqual(
            bill.get_congress_gov_url(),
            'https://www.congress.gov/bill/119th-congress/house-bill/7008',
        )

    def test_senate_bill(self):
        bill = self._bill(119, 's', 567)
        self.assertEqual(
            bill.get_congress_gov_url(),
            'https://www.congress.gov/bill/119th-congress/senate-bill/567',
        )

    def test_house_joint_resolution(self):
        bill = self._bill(119, 'hjres', 87)
        self.assertEqual(
            bill.get_congress_gov_url(),
            'https://www.congress.gov/bill/119th-congress/house-joint-resolution/87',
        )

    def test_type_case_insensitive(self):
        bill = self._bill(118, 'HR', 1)
        self.assertEqual(
            bill.get_congress_gov_url(),
            'https://www.congress.gov/bill/118th-congress/house-bill/1',
        )

    def test_ordinal_st_nd_rd_th(self):
        self.assertEqual(Bill._congress_ordinal(1), '1st')
        self.assertEqual(Bill._congress_ordinal(2), '2nd')
        self.assertEqual(Bill._congress_ordinal(3), '3rd')
        self.assertEqual(Bill._congress_ordinal(4), '4th')
        self.assertEqual(Bill._congress_ordinal(11), '11th')
        self.assertEqual(Bill._congress_ordinal(12), '12th')
        self.assertEqual(Bill._congress_ordinal(13), '13th')
        self.assertEqual(Bill._congress_ordinal(21), '21st')
        self.assertEqual(Bill._congress_ordinal(119), '119th')
        self.assertEqual(Bill._congress_ordinal(121), '121st')

    def test_unknown_type_returns_none(self):
        bill = self._bill(119, 'xyz', 1)
        self.assertIsNone(bill.get_congress_gov_url())


if __name__ == '__main__':
    unittest.main()
