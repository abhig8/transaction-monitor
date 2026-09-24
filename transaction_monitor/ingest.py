"""Load the transaction CSV and clean it (TDD.md section 2.2)."""
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .merchants import normalize_merchants


@dataclass
class IngestResult:
    transactions: pd.DataFrame  # clean rows, sorted by user_id, then timestamp, then txn_id
    rejects: pd.DataFrame       # rows we could not use, with a reject_reason column
    counts: dict                # row counts for the run summary


def load_transactions(path: str | Path) -> IngestResult:
    """Read the CSV, drop exact duplicates, set aside unusable rows, and sort the rest."""
    # Read everything as text first so that bad values can be inspected, not lost.
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    counts = {"rows_read": len(raw)}

    # Record each row's line number in the file (line 1 is the header), so any
    # rejected row can be found in the input.
    raw.insert(0, "file_line", raw.index + 2)

    # Step 1: exact duplicate rows are replays of the same record. Keep the first
    # copy and set the others aside, so every input row is accounted for.
    is_exact_duplicate = raw.drop(columns="file_line").duplicated()
    duplicates = raw[is_exact_duplicate].assign(reject_reason="exact_duplicate")
    raw = raw[~is_exact_duplicate]
    counts["exact_duplicates_dropped"] = int(is_exact_duplicate.sum())

    # Step 2: parse timestamps and amounts. Values that do not parse become NaT / NaN.
    parsed_timestamp = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce", format="ISO8601")
    parsed_amount = pd.to_numeric(raw["amount"], errors="coerce")

    # Step 3: set aside rows we cannot evaluate, recording why.
    reject_reason = find_reject_reasons(raw, parsed_timestamp, parsed_amount)
    is_rejected = reject_reason != ""
    unusable = raw[is_rejected].assign(reject_reason=reject_reason[is_rejected])
    for reason, count in reject_reason[is_rejected].value_counts().items():
        counts[f"rejected_{reason}"] = int(count)
    rejects = pd.concat([duplicates, unusable]).sort_values("file_line")
    counts["rows_in_rejects_file"] = len(rejects)

    # Step 4: keep the rest, with parsed values and a normalized merchant key.
    transactions = raw[~is_rejected].drop(columns="file_line")
    transactions["timestamp"] = parsed_timestamp[~is_rejected]
    transactions["amount"] = parsed_amount[~is_rejected]
    transactions["merchant_key"] = normalize_merchants(transactions["merchant_name"])

    # Step 5: sort so each account's history reads in time order. txn_id breaks ties
    # between transactions in the same second, which keeps runs reproducible.
    transactions = transactions.sort_values(["user_id", "timestamp", "txn_id"], ignore_index=True)

    has_merchant = transactions["merchant_key"] != ""
    counts["usable_rows"] = len(transactions)
    counts["blank_merchant_kept"] = int((~has_merchant).sum())
    counts["refunds_kept"] = int((transactions["amount"] < 0).sum())
    counts["distinct_merchant_names"] = int(transactions.loc[has_merchant, "merchant_name"].nunique())
    counts["distinct_merchants_after_normalizing"] = int(transactions.loc[has_merchant, "merchant_key"].nunique())
    return IngestResult(transactions, rejects, counts)


def find_reject_reasons(raw: pd.DataFrame, parsed_timestamp: pd.Series, parsed_amount: pd.Series) -> pd.Series:
    """Return why each row cannot be used, or "" if it is fine. The first matching reason wins."""
    reason = pd.Series("", index=raw.index)
    # Exact duplicates are already gone, so a repeated txn_id now means two different
    # versions of one transaction. We cannot tell which is right, so both are set aside.
    reason[raw["txn_id"].duplicated(keep=False)] = "conflicting_duplicate_txn_id"
    reason[(reason == "") & parsed_timestamp.isna()] = "unparseable_timestamp"
    reason[(reason == "") & parsed_amount.isna()] = "missing_or_invalid_amount"
    return reason
