"""R1: shared-device ring.

A device that is new to an account, and is then picked up by other accounts it is
also new to, suggests one operator running many accounts: an account-takeover ring
or a mule farm. Household devices do not trigger this rule, because family members
use them from the start of the data, so the device is never new to them.
"""
import pandas as pd

from ..flags import make_flags
from ..reason_codes import ReasonCode

MIN_NEW_ACCOUNTS_ON_DEVICE = 2


def shared_device_ring(transactions: pd.DataFrame, pairings: pd.DataFrame) -> pd.DataFrame:
    """Flag every transaction on a device once 2 or more accounts that are new to it have used it."""
    new_pairings = pairings[pairings["is_new_device"]]

    # For each device, find when it became a ring: the moment its second new account arrived.
    ring_start_by_device = {}
    for device_id, device_pairings in new_pairings.groupby("device_id"):
        arrival_times = device_pairings["first_used_at"].sort_values()
        if len(arrival_times) >= MIN_NEW_ACCOUNTS_ON_DEVICE:
            ring_start_by_device[device_id] = arrival_times.iloc[MIN_NEW_ACCOUNTS_ON_DEVICE - 1]
    if not ring_start_by_device:
        return make_flags([], ReasonCode.DEVICE_NEW_TO_MULTIPLE_ACCOUNTS, [])

    on_ring_device = transactions[transactions["device_id"].isin(list(ring_start_by_device))]
    ring_started_at = on_ring_device["device_id"].map(ring_start_by_device)
    flagged = on_ring_device[on_ring_device["timestamp"] >= ring_started_at]

    reasons = [describe_ring(txn, new_pairings) for txn in flagged.itertuples()]
    return make_flags(flagged["txn_id"], ReasonCode.DEVICE_NEW_TO_MULTIPLE_ACCOUNTS, reasons)


def describe_ring(txn, new_pairings: pd.DataFrame) -> str:
    """Reason text for one flagged transaction, using only what was known at its time."""
    arrivals = new_pairings.loc[new_pairings["device_id"] == txn.device_id, "first_used_at"]
    accounts_so_far = int((arrivals <= txn.timestamp).sum())
    return (
        f"device {txn.device_id} has been used by {accounts_so_far} accounts that had never used it before, "
        f"starting {arrivals.min():%Y-%m-%d}. One device operating several accounts points to an "
        f"account-takeover ring or mule farm. This transaction: ${txn.amount:,.2f} at {txn.merchant_name}."
    )
