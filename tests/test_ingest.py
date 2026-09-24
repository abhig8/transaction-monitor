"""Ingest: every input row is either used or listed in rejects with a reason. Run: python3 -m unittest"""
import tempfile
import unittest
from pathlib import Path

from transaction_monitor.ingest import load_transactions

CSV = """txn_id,user_id,timestamp,merchant_name,amount,device_id
t1,u1,2026-05-03T10:00:00Z,Shell,10.00,d1
t1,u1,2026-05-03T10:00:00Z,Shell,10.00,d1
t2,u1,not_a_timestamp,Shell,10.00,d1
t3,u1,2026-05-03T11:00:00Z,Shell,,d1
t4,u1,2026-05-03T12:00:00Z,,5.00,d1
t5,u1,2026-05-03T13:00:00Z,Shell,-3.00,d1
"""


class LoadTransactionsTest(unittest.TestCase):
    def test_every_row_is_used_or_rejected_with_a_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "transactions.csv"
            path.write_text(CSV)
            result = load_transactions(path)

        # Blank merchants and refunds are kept; they are usable, just handled carefully by the rules.
        self.assertEqual(list(result.transactions["txn_id"]), ["t1", "t4", "t5"])
        self.assertEqual(list(result.rejects["reject_reason"]),
                         ["exact_duplicate", "unparseable_timestamp", "missing_or_invalid_amount"])
        self.assertEqual(list(result.rejects["file_line"]), [3, 4, 5])
        self.assertEqual(result.counts["rows_read"], len(result.transactions) + len(result.rejects))


if __name__ == "__main__":
    unittest.main()
