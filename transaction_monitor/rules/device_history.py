"""Which devices are new to which accounts (TDD.md D9).

A "pairing" is one account using one device. We cannot see a device's true age:
a phone someone has owned for years looks "first seen" the first time it is used
inside the 90-day window. So during an account's first 7 days in the data, every
device it uses is treated as one it already had. Only a device that first appears
after that warm-up counts as new to the account.
"""
import pandas as pd

WARMUP_PERIOD = pd.Timedelta(days=7)


def find_device_pairings(transactions: pd.DataFrame) -> pd.DataFrame:
    """Return one row per pairing: user_id, device_id, first_used_at, is_new_device."""
    pairings = (
        transactions.groupby(["user_id", "device_id"], as_index=False)
        .agg(first_used_at=("timestamp", "min"))
    )
    account_first_seen = transactions.groupby("user_id")["timestamp"].min()
    warmup_ends_at = pairings["user_id"].map(account_first_seen) + WARMUP_PERIOD
    pairings["is_new_device"] = pairings["first_used_at"] >= warmup_ends_at
    return pairings
