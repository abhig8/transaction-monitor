"""R3: card-testing burst.

Card testers run many small charges on a stolen card at low-friction merchants to
learn whether it works. We group each account's small charges into bursts: a
burst continues while each charge comes within 30 minutes of the previous one.
The flag fires on the charge at which the burst reaches 10 charges at 5 or more
different merchants.

One flag per burst is the deliberate exception to one flag per transaction
(TDD.md D2): a burst is one case for an analyst, and its other charges are listed
in related_txn_ids. Charges after the flag happen after the decision; a live
system would have blocked the card at the flag, so they would not happen at all.
"""
import pandas as pd

from ..flags import make_flags
from ..reason_codes import ReasonCode

SMALL_CHARGE_LIMIT = 5.00
MAX_GAP_BETWEEN_CHARGES = pd.Timedelta(minutes=30)
MIN_CHARGES = 10
MIN_DISTINCT_MERCHANTS = 5


def find_small_charge_bursts(transactions: pd.DataFrame) -> pd.DataFrame:
    """Return every small charge with its burst_id and running totals within its burst."""
    is_small_charge = (transactions["amount"] > 0) & (transactions["amount"] < SMALL_CHARGE_LIMIT)
    charges = transactions[is_small_charge].copy()  # still sorted by user, then time

    time_since_previous = charges.groupby("user_id")["timestamp"].diff()
    starts_new_burst = time_since_previous.isna() | (time_since_previous > MAX_GAP_BETWEEN_CHARGES)
    charges["burst_id"] = starts_new_burst.cumsum()

    by_burst = charges.groupby("burst_id")
    charges["charges_so_far"] = by_burst.cumcount() + 1
    charges["amount_so_far"] = by_burst["amount"].cumsum()
    charges["burst_started_at"] = by_burst["timestamp"].transform("min")

    # A charge is a merchant's first visit in the burst if no earlier charge in the same
    # burst went to that merchant. Counting first visits gives the merchants seen so far.
    is_first_visit = ~charges.duplicated(["burst_id", "merchant_key"]) & (charges["merchant_key"] != "")
    charges["merchants_so_far"] = is_first_visit.groupby(charges["burst_id"]).cumsum()
    return charges


def card_testing_burst(transactions: pd.DataFrame) -> pd.DataFrame:
    """Flag the first charge in each burst that reaches 10 charges at 5 or more merchants."""
    charges = find_small_charge_bursts(transactions)
    meets_threshold = (charges["charges_so_far"] >= MIN_CHARGES) & (charges["merchants_so_far"] >= MIN_DISTINCT_MERCHANTS)
    trigger_charges = charges[meets_threshold].groupby("burst_id").head(1)

    reasons, related_txn_ids = [], []
    for trigger in trigger_charges.itertuples():
        burst = charges[charges["burst_id"] == trigger.burst_id]
        reasons.append(describe_burst(trigger, burst))
        other_charges = burst.loc[burst["txn_id"] != trigger.txn_id, "txn_id"]
        related_txn_ids.append(";".join(other_charges))

    return make_flags(trigger_charges["txn_id"], ReasonCode.CARD_TESTING_BURST, reasons, related_txn_ids)


def describe_burst(trigger, burst: pd.DataFrame) -> str:
    """Reason text for a burst's flag: what was known at the flag, then how the burst ended."""
    minutes = (trigger.timestamp - trigger.burst_started_at).total_seconds() / 60
    return (
        f"{trigger.charges_so_far} charges under ${SMALL_CHARGE_LIMIT:.0f} at {trigger.merchants_so_far} different "
        f"merchants within {minutes:.0f} min (${trigger.amount_so_far:,.2f} so far). "
        f"The burst ran to {len(burst)} charges and ${burst['amount'].sum():,.2f} by {burst['timestamp'].max():%H:%M} UTC; "
        f"its other charges are listed in related_txn_ids."
    )
