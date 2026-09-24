"""End-to-end runs of the command line, with and without a labels file. Run: python3 -m unittest"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from transaction_monitor.__main__ import main

TRANSACTIONS = """txn_id,user_id,timestamp,merchant_name,amount,device_id
t1,u1,2026-05-03T10:00:00Z,Shell,10.00,d1
t1,u1,2026-05-03T10:00:00Z,Shell,10.00,d1
t2,u1,not_a_timestamp,Shell,10.00,d1
t3,u1,2026-05-04T11:00:00Z,Target,25.00,d1
t4,u2,2026-05-04T12:00:00Z,,5.00,d2
"""


def run(folder: Path, labels: str | None) -> tuple[str, dict]:
    """Run the command line on the small file above and return what it printed and the summary."""
    (folder / "transactions.csv").write_text(TRANSACTIONS)
    args = ["--transactions", str(folder / "transactions.csv"), "--output-dir", str(folder / "out")]
    labels_path = folder / "confirmed_fraud.csv"
    if labels is not None:
        labels_path.write_text(labels)
    args += ["--labels", str(labels_path)]
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        main(args)
    return printed.getvalue(), json.loads((folder / "out" / "summary.json").read_text())


class CommandLineTest(unittest.TestCase):
    def test_runs_without_a_labels_file(self):
        with tempfile.TemporaryDirectory() as folder:
            printed, summary = run(Path(folder), labels=None)
            self.assertTrue((Path(folder) / "out" / "flags.csv").exists())
        self.assertIn("Labels: not available", printed)
        self.assertNotIn("evaluation", summary)
        self.assertEqual(summary["ingest"]["usable_rows"], 3)

    def test_runs_with_a_labels_file(self):
        with tempfile.TemporaryDirectory() as folder:
            printed, summary = run(Path(folder), labels="txn_id\nt3\n")
        self.assertIn("Labels: 0/1 labeled transactions inside flagged cases", printed)
        self.assertEqual(summary["evaluation"]["labels_found_in_transactions"], 1)


if __name__ == "__main__":
    unittest.main()
