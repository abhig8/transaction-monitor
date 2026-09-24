"""Merchant normalization cases from TDD.md section 2.3. Run: python3 -m unittest"""
import unittest

import pandas as pd

from transaction_monitor.merchants import normalize_merchants


class NormalizeMerchantsTest(unittest.TestCase):
    def check(self, raw, expected):
        self.assertEqual(normalize_merchants(pd.Series([raw])).iloc[0], expected, raw)

    def test_format_variants_collapse(self):
        for raw in ["Starbucks", "STARBUCKS", "SQ *STARBUCKS", "STARBUCKS #1234",
                    "STARBUCKS ONLINE", "STARBUCKS SAN JOSE CA", "Starbucks CA", " starbucks "]:
            self.check(raw, "STARBUCKS")

    def test_punctuation_is_not_truncation(self):
        self.check("7-ELEVEN", "7ELEVEN")
        self.check("PG&E", "PGE")
        self.check("PG&E HTTPSWWW", "PGE")

    def test_numbers_that_belong_to_the_name_survive(self):
        self.check("ONLINE-MKT 8827", "ONLINEMKT 8827")
        self.check("RESELL MARKET 24", "RESELL MARKET 24")
        self.check("Airbnb Store 615", "AIRBNB")

    def test_blank(self):
        self.check("", "")


if __name__ == "__main__":
    unittest.main()
