"""Input and output file names for runs with and without a dataset suffix. Run: python3 -m unittest"""
import unittest
from pathlib import Path

from transaction_monitor.run_files import resolve_run_files


class ResolveRunFilesTest(unittest.TestCase):
    def test_default_dataset(self):
        files = resolve_run_files()
        self.assertEqual(files.transactions, Path("test_data/transactions.csv"))
        self.assertEqual(files.labels, Path("test_data/confirmed_fraud.csv"))
        self.assertEqual(files.flags, Path("output/flags.csv"))
        self.assertEqual(files.summary, Path("output/summary.json"))

    def test_suffix_applies_to_inputs_and_outputs(self):
        files = resolve_run_files("small")
        self.assertEqual(files.transactions, Path("test_data/transactions_small.csv"))
        self.assertEqual(files.labels, Path("test_data/confirmed_fraud_small.csv"))
        self.assertEqual(files.flags, Path("output/flags_small.csv"))
        self.assertEqual(files.rejects, Path("output/rejects_small.csv"))
        self.assertEqual(files.summary, Path("output/summary_small.json"))

    def test_explicit_paths_override_the_suffix(self):
        files = resolve_run_files("small", "out", transactions="elsewhere/tx.csv")
        self.assertEqual(files.transactions, Path("elsewhere/tx.csv"))
        self.assertEqual(files.flags, Path("out/flags_small.csv"))

    def test_unsafe_suffix_is_rejected(self):
        for bad in ["../x", "a b", "x/y", "x.csv"]:
            with self.assertRaises(ValueError):
                resolve_run_files(bad)


if __name__ == "__main__":
    unittest.main()
