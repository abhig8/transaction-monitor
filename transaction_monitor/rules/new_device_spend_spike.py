"""R2: new device plus spend spike.

Account takeover with cash-out: a device the account has never used appears, and
within hours the account buys electronics, jewelry, gift cards or prepaid products
worth many times what it normally spends.
"""
import pandas as pd

from ..flags import make_flags
from ..reason_codes import ReasonCode

WINDOW_AFTER_NEW_DEVICE = pd.Timedelta(hours=24)
SPEND_MULTIPLIER = 3.0


def new_device_spend_spike(transactions: pd.DataFrame, pairings: pd.DataFrame) -> pd.DataFrame:
    """Flag purchases made within 24 hours of a new device first appearing on the account,
    when the amount is more than 3x the account's median purchase from before that device appeared.

    The baseline stops at the device's first use, so a takeover in progress cannot raise
    its own baseline (TDD.md case F3).
    """
    purchases = transactions[transactions["amount"] > 0]  # refunds are not spending
    new_pairings = pairings[pairings["is_new_device"]]
    affected_purchases = purchases[purchases["user_id"].isin(new_pairings["user_id"])]
    purchases_by_user = {user_id: rows for user_id, rows in affected_purchases.groupby("user_id")}

    flagged_ids, reasons = [], []
    for pairing in new_pairings.itertuples():
        account_purchases = purchases_by_user.get(pairing.user_id)
        if account_purchases is None:
            continue

        # Baseline: the account's purchases from before this device appeared.
        earlier = account_purchases[account_purchases["timestamp"] < pairing.first_used_at]
        if earlier.empty:
            continue
        typical_amount = earlier["amount"].median()

        window_end = pairing.first_used_at + WINDOW_AFTER_NEW_DEVICE
        on_new_device = account_purchases[
            (account_purchases["device_id"] == pairing.device_id)
            & (account_purchases["timestamp"] <= window_end)
        ]
        spikes = on_new_device[on_new_device["amount"] > SPEND_MULTIPLIER * typical_amount]
        for purchase in spikes.itertuples():
            flagged_ids.append(purchase.txn_id)
            reasons.append(describe_spike(purchase, pairing.first_used_at, typical_amount, len(earlier)))

    return make_flags(flagged_ids, ReasonCode.LARGE_PURCHASE_ON_NEW_DEVICE, reasons)


def describe_spike(purchase, device_first_used_at: pd.Timestamp, typical_amount: float, earlier_count: int) -> str:
    """Reason text for one flagged purchase."""
    hours_after = (purchase.timestamp - device_first_used_at).total_seconds() / 3600
    if hours_after < 0.05:
        timing = "its first transaction on this account"
    else:
        timing = f"{hours_after:.1f}h after it first appeared on this account"
    return (
        f"${purchase.amount:,.2f} at {purchase.merchant_name} on device {purchase.device_id}, {timing} "
        f"({device_first_used_at:%Y-%m-%d %H:%M} UTC). That is {purchase.amount / typical_amount:.0f}x the "
        f"account's median purchase of ${typical_amount:,.2f} over its {earlier_count} earlier purchases."
    )
