"""Build flag rows for each rule and combine them into the final output."""
from collections.abc import Iterable

import pandas as pd

from .reason_codes import ReasonCode

FLAG_COLUMNS = ["txn_id", "reason_code", "reason", "related_txn_ids"]

OUTPUT_COLUMNS = [
    "txn_id", "rules", "reason",
    "user_id", "timestamp", "amount", "merchant_name", "device_id",
    "related_txn_ids",
]


def make_flags(
    txn_ids: Iterable[str],
    reason_code: ReasonCode,
    reasons: Iterable[str],
    related_txn_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Return one flag row per transaction for a single rule.

    Every reason starts with the code's label, for example
    "Card-testing burst: 10 charges under $5 at 6 different merchants ...".
    """
    txn_ids = list(txn_ids)
    related_txn_ids = [""] * len(txn_ids) if related_txn_ids is None else list(related_txn_ids)
    return pd.DataFrame(
        {
            "txn_id": txn_ids,
            "reason_code": [reason_code.value] * len(txn_ids),
            "reason": [f"{reason_code.label}: {reason}" for reason in reasons],
            "related_txn_ids": related_txn_ids,
        },
        columns=FLAG_COLUMNS,
    )


def combine_flags(flags_per_rule: list[pd.DataFrame], transactions: pd.DataFrame) -> pd.DataFrame:
    """Merge every rule's flags so each flagged transaction appears once, listing all rules that fired."""
    all_flags = pd.concat(flags_per_rule, ignore_index=True)
    if all_flags.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    rows = []
    for txn_id, flags_for_txn in all_flags.groupby("txn_id"):
        related = [ids for ids in flags_for_txn["related_txn_ids"] if ids]
        rows.append({
            "txn_id": txn_id,
            "rules": ";".join(sorted(flags_for_txn["reason_code"])),
            "reason": " | ".join(flags_for_txn["reason"]),
            "related_txn_ids": ";".join(related),
        })
    combined = pd.DataFrame(rows)

    # Add the transaction details an analyst needs next to each flag.
    details = transactions[["txn_id", "user_id", "timestamp", "amount", "merchant_name", "device_id"]]
    combined = combined.merge(details, on="txn_id").sort_values("timestamp")
    combined["timestamp"] = combined["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return combined[OUTPUT_COLUMNS].reset_index(drop=True)
