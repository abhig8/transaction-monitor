"""Small hand-built cases for the rules. Run: python3 -m unittest"""
import unittest

import pandas as pd

from transaction_monitor.rules import card_testing_burst, find_device_pairings, new_device_spend_spike, shared_device_ring

DAY_ONE = pd.Timestamp("2026-05-03 12:00", tz="UTC")


def make_transactions(rows):
    """rows: (txn_id, user_id, days_after_day_one, amount, merchant, device_id)"""
    frame = pd.DataFrame(rows, columns=["txn_id", "user_id", "days", "amount", "merchant_name", "device_id"])
    frame["timestamp"] = DAY_ONE + pd.to_timedelta(frame["days"], unit="D")
    frame["merchant_key"] = frame["merchant_name"].str.upper()
    return frame.drop(columns="days").sort_values(["user_id", "timestamp", "txn_id"], ignore_index=True)


class DeviceHistoryTest(unittest.TestCase):
    def test_device_first_seen_in_warmup_is_not_new(self):
        txns = make_transactions([
            ("t1", "u1", 0, 10.0, "A", "phone"),
            ("t2", "u1", 3, 10.0, "A", "tablet"),     # inside the 7-day warm-up: existing device
            ("t3", "u1", 20, 10.0, "A", "new_phone"),  # after the warm-up: new device
        ])
        is_new = find_device_pairings(txns).set_index("device_id")["is_new_device"]
        self.assertFalse(is_new["tablet"])
        self.assertTrue(is_new["new_phone"])


class SharedDeviceRingTest(unittest.TestCase):
    def test_flags_start_when_second_new_account_arrives(self):
        txns = make_transactions([
            ("a0", "u1", 0, 10.0, "A", "own1"),
            ("b0", "u2", 0, 10.0, "A", "own2"),
            ("a1", "u1", 20, 300.0, "B", "ring"),  # first new account on the device: not flagged yet
            ("b1", "u2", 21, 300.0, "B", "ring"),  # second new account: the device is now a ring
            ("a2", "u1", 22, 300.0, "B", "ring"),  # everything after is flagged
        ])
        flags = shared_device_ring(txns, find_device_pairings(txns))
        self.assertEqual(sorted(flags["txn_id"]), ["a2", "b1"])

    def test_household_device_used_from_the_start_is_ignored(self):
        txns = make_transactions([
            ("a0", "u1", 0, 10.0, "A", "family_tablet"),
            ("b0", "u2", 1, 10.0, "A", "family_tablet"),
            ("c0", "u3", 2, 10.0, "A", "family_tablet"),
            ("a1", "u1", 30, 10.0, "A", "family_tablet"),
        ])
        self.assertTrue(shared_device_ring(txns, find_device_pairings(txns)).empty)


class NewDeviceSpendSpikeTest(unittest.TestCase):
    def test_baseline_ignores_purchases_made_on_the_new_device(self):
        txns = make_transactions([
            ("h1", "u1", 0, 20.0, "A", "own"),
            ("h2", "u1", 1, 20.0, "A", "own"),
            ("x1", "u1", 30.00, 1500.0, "B", "new"),
            ("x2", "u1", 30.01, 1700.0, "B", "new"),
            # Only 1.2x a median that includes x1 and x2, but 45x the account's real baseline.
            ("x3", "u1", 30.02, 900.0, "B", "new"),
        ])
        flags = new_device_spend_spike(txns, find_device_pairings(txns))
        self.assertEqual(sorted(flags["txn_id"]), ["x1", "x2", "x3"])


class CardTestingBurstTest(unittest.TestCase):
    def test_one_flag_per_burst_on_the_tenth_charge(self):
        minute = 1 / (24 * 60)
        rows = [(f"t{i:02d}", "u1", 10 + i * minute, 1.50, f"M{i % 6}", "own") for i in range(15)]
        flags = card_testing_burst(make_transactions(rows))
        self.assertEqual(list(flags["txn_id"]), ["t09"])  # the 10th charge
        self.assertTrue(flags.iloc[0]["reason"].startswith("Card-testing burst: 10 charges"))
        self.assertEqual(len(flags.iloc[0]["related_txn_ids"].split(";")), 14)

    def test_small_charges_spread_over_hours_are_not_a_burst(self):
        hour = 1 / 24
        rows = [(f"t{i:02d}", "u1", 10 + i * hour, 1.50, f"M{i % 6}", "own") for i in range(15)]
        self.assertTrue(card_testing_burst(make_transactions(rows)).empty)


if __name__ == "__main__":
    unittest.main()
