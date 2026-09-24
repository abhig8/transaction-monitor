"""Output format: one row per flagged transaction, listing every rule that fired. Run: python3 -m unittest"""
import unittest

import pandas as pd

from transaction_monitor.flags import OUTPUT_COLUMNS, combine_flags, make_flags
from transaction_monitor.reason_codes import ReasonCode

TRANSACTIONS = pd.DataFrame({
    "txn_id": ["a1"],
    "user_id": ["u1"],
    "timestamp": [pd.Timestamp("2026-06-01 12:00", tz="UTC")],
    "amount": [300.0],
    "merchant_name": ["PREPAID DEPOT"],
    "device_id": ["d1"],
})


class CombineFlagsTest(unittest.TestCase):
    def test_one_row_per_transaction_listing_every_rule_and_reason(self):
        flags = combine_flags([
            make_flags(["a1"], ReasonCode.DEVICE_NEW_TO_MULTIPLE_ACCOUNTS, ["shared device"]),
            make_flags(["a1"], ReasonCode.LARGE_PURCHASE_ON_NEW_DEVICE, ["big purchase"]),
        ], TRANSACTIONS)

        self.assertEqual(list(flags.columns), OUTPUT_COLUMNS)
        self.assertEqual(len(flags), 1)
        row = flags.iloc[0]
        self.assertEqual(row["txn_id"], "a1")
        self.assertEqual(row["rules"], "DEVICE_NEW_TO_MULTIPLE_ACCOUNTS;LARGE_PURCHASE_ON_NEW_DEVICE")
        self.assertEqual(row["reason"],
                         "Device new to multiple accounts: shared device | Large purchase on new device: big purchase")


if __name__ == "__main__":
    unittest.main()
