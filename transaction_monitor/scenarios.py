"""Budget what-if: what R4, R5 and other options would add on top of the shipped rules.

    python3 -m transaction_monitor.scenarios

R4 and R5 are documented in RULES.md but deliberately not part of the pipeline.
This script measures what adding them, or other uses of the spare review budget,
would do. It prints a table and writes nothing.
"""
import pandas as pd

from .ingest import load_transactions
from .rules import card_testing_burst, find_device_pairings, new_device_spend_spike, shared_device_ring
from .rules.card_testing_burst import MIN_CHARGES, MIN_DISTINCT_MERCHANTS, find_small_charge_bursts
from .run_files import resolve_run_files

REVIEW_BUDGET = 1_000
HEAVY_USER_MIN_TRANSACTIONS = 6_400

# R4: cash-equivalent purchase (documented, not built)
CASH_EQUIVALENT_MERCHANTS = {
    "GIFTCARDS EXPRESS", "PREPAID DEPOT", "JEWELRY WHOLESALE CO", "RESELL MARKET 24", "LUXE ELECTRONICS OUTLET",
}
R4_MIN_AMOUNT = 200.0
R4_MULTIPLIER = 3.0

# R5: velocity (tested and cut)
R5_WINDOW = pd.Timedelta(hours=24)
R5_MULTIPLIER = 5.0
R5_MIN_SPEND = 500.0
R5_MIN_HISTORY = pd.Timedelta(days=7)


def cash_equivalent_purchases(transactions: pd.DataFrame, first_per_account_only: bool) -> set[str]:
    """R4: purchases at a cash-equivalent merchant above $200 and 3x the account's earlier median."""
    purchases = transactions[transactions["amount"] > 0]
    candidates = purchases[
        purchases["merchant_key"].isin(CASH_EQUIVALENT_MERCHANTS) & (purchases["amount"] > R4_MIN_AMOUNT)
    ]
    affected = purchases[purchases["user_id"].isin(candidates["user_id"])]
    purchases_by_user = {user_id: rows for user_id, rows in affected.groupby("user_id")}

    flagged = []
    for purchase in candidates.itertuples():
        history = purchases_by_user[purchase.user_id]
        earlier = history.loc[history["timestamp"] < purchase.timestamp, "amount"]
        if len(earlier) and purchase.amount > R4_MULTIPLIER * earlier.median():
            flagged.append({"user_id": purchase.user_id, "timestamp": purchase.timestamp, "txn_id": purchase.txn_id})
    flagged = pd.DataFrame(flagged, columns=["user_id", "timestamp", "txn_id"])
    if first_per_account_only:
        flagged = flagged.sort_values("timestamp").groupby("user_id").head(1)
    return set(flagged["txn_id"])


def velocity_spikes(transactions: pd.DataFrame) -> set[str]:
    """R5: 24-hour spend above 5x the account's average daily spend so far, and above $500."""
    purchases = transactions[transactions["amount"] > 0].copy()  # sorted by user, then time
    by_user = purchases.groupby("user_id")
    rolling_spend = purchases.set_index("timestamp").groupby("user_id")["amount"].rolling(R5_WINDOW).sum()
    # Rows are sorted by user and time, and the group-by keeps that order, so the
    # rolling result lines up with `purchases` row for row.
    assert (rolling_spend.index.get_level_values("user_id") == purchases["user_id"].to_numpy()).all()
    purchases["spend_24h"] = rolling_spend.to_numpy()

    history = purchases["timestamp"] - by_user["timestamp"].transform("min")
    spend_before = by_user["amount"].cumsum() - purchases["amount"]
    average_daily_spend = spend_before / (history.dt.total_seconds() / 86_400)

    is_spike = (
        (history >= R5_MIN_HISTORY)
        & (purchases["spend_24h"] > R5_MULTIPLIER * average_daily_spend)
        & (purchases["spend_24h"] > R5_MIN_SPEND)
    )
    return set(purchases.loc[is_spike, "txn_id"])


def earlier_ring_device_transactions(transactions: pd.DataFrame, ring_flags: set[str]) -> set[str]:
    """Every transaction on a device R1 flagged, including the ones before the ring was detected."""
    ring_devices = set(transactions.loc[transactions["txn_id"].isin(ring_flags), "device_id"])
    return set(transactions.loc[transactions["device_id"].isin(ring_devices), "txn_id"])


def more_charges_per_burst(transactions: pd.DataFrame, flags_per_burst: int) -> set[str]:
    """R3 variant: flag up to `flags_per_burst` charges per burst, starting at the qualifying charge."""
    charges = find_small_charge_bursts(transactions)
    qualifies = (charges["charges_so_far"] >= MIN_CHARGES) & (charges["merchants_so_far"] >= MIN_DISTINCT_MERCHANTS)
    return set(charges[qualifies].groupby("burst_id").head(flags_per_burst)["txn_id"])


def describe_additions(added: set[str], transactions: pd.DataFrame, labels: set[str],
                       ring_devices: set[str], heavy_users: set[str]) -> dict:
    """Break down flags a scenario adds: labeled, prepaid pattern, ring devices, heavy users."""
    rows = transactions[transactions["txn_id"].isin(added)]
    in_prepaid_band = (rows["merchant_key"] == "PREPAID DEPOT") & rows["amount"].between(470, 500)
    return {
        "added": len(rows),
        "labeled": int(rows["txn_id"].isin(labels).sum()),
        "prepaid pattern": int(in_prepaid_band.sum()),
        "ring devices": int(rows["device_id"].isin(ring_devices).sum()),
        "heavy users": int(rows["user_id"].isin(heavy_users).sum()),
    }


def main() -> None:
    files = resolve_run_files()
    transactions = load_transactions(files.transactions).transactions
    labels = set(pd.read_csv(files.labels, dtype=str)["txn_id"]) if files.labels.exists() else set()
    pairings = find_device_pairings(transactions)

    r1 = set(shared_device_ring(transactions, pairings)["txn_id"])
    r2 = set(new_device_spend_spike(transactions, pairings)["txn_id"])
    r3 = set(card_testing_burst(transactions)["txn_id"])
    shipped = r1 | r2 | r3

    ring_devices = set(transactions.loc[transactions["txn_id"].isin(r1), "device_id"])
    counts = transactions.groupby("user_id").size()
    heavy_users = set(counts[counts > HEAVY_USER_MIN_TRANSACTIONS].index)

    options = {
        "Earlier ring-device transactions": earlier_ring_device_transactions(transactions, r1),
        "R4, first purchase per account": cash_equivalent_purchases(transactions, first_per_account_only=True),
        "R4, every qualifying purchase": cash_equivalent_purchases(transactions, first_per_account_only=False),
        "R3, up to 3 charges per burst": more_charges_per_burst(transactions, flags_per_burst=3),
        "R5 velocity": velocity_spikes(transactions),
    }

    print(f"Shipped (R1-R3): {len(shipped)} flags, budget {REVIEW_BUDGET}\n")
    print("Each option on its own, added on top of R1-R3:")
    rows = []
    for name, flags in options.items():
        breakdown = describe_additions(flags - shipped, transactions, labels, ring_devices, heavy_users)
        rows.append({"option": name, "flags": len(flags), **breakdown, "total": len(shipped | flags)})
    print(pd.DataFrame(rows).to_string(index=False))

    print("\nFilling the budget, highest-value option first:")
    total = set(shipped)
    for name in ["Earlier ring-device transactions", "R4, every qualifying purchase", "R3, up to 3 charges per burst"]:
        added = options[name] - total
        total |= options[name]
        print(f"  + {name:<32} +{len(added):>4}  ->  {len(total):>5} flags ({len(total) / REVIEW_BUDGET:.0%} of budget)")


if __name__ == "__main__":
    main()
