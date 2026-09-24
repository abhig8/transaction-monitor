"""Measure the flags against confirmed_fraud.csv (TDD.md section 6).

The rules never read the labels. Labels come from customer disputes, so they only
cover fraud that customers noticed. The share of flags that are labeled is
therefore a floor on precision, and recall only speaks for the reported fraud types.
"""
import pandas as pd

from .rules.card_testing_burst import MIN_CHARGES, MIN_DISTINCT_MERCHANTS, find_small_charge_bursts

TIME_SPLIT_DAYS = 45


def evaluate_against_labels(flags: pd.DataFrame, transactions: pd.DataFrame, labels_path) -> dict:
    labeled_ids = set(pd.read_csv(labels_path, dtype=str)["txn_id"])
    labeled = transactions[transactions["txn_id"].isin(labeled_ids)]

    report = {
        "labels_in_file": len(labeled_ids),
        "labels_found_in_transactions": len(labeled),
        "overall": label_metrics(flags, labeled, len(transactions)),
        "by_rule": {},
    }
    for rule in rule_names(flags):
        rule_flags = flags[flags["rules"].str.contains(rule)]
        report["by_rule"][rule] = label_metrics(rule_flags, labeled, len(transactions))
    report["time_split"] = time_split_check(flags, transactions, labeled)
    return report


def label_metrics(flags: pd.DataFrame, labeled: pd.DataFrame, total_rows: int) -> dict:
    """Coverage of labeled fraud. "Covered" also counts burst charges listed in related_txn_ids."""
    flagged_ids = set(flags["txn_id"])
    covered_ids = flagged_ids | related_ids(flags)
    is_covered = labeled["txn_id"].isin(covered_ids)
    return {
        "flags": len(flags),
        "flag_rate_pct": round(100 * len(flags) / total_rows, 4) if total_rows else None,  # None for an empty period
        "flags_that_are_labeled": int(flags["txn_id"].isin(labeled["txn_id"]).sum()),
        "labeled_txns": len(labeled),
        "labeled_txns_flagged": int(labeled["txn_id"].isin(flagged_ids).sum()),
        "labeled_txns_covered": int(is_covered.sum()),
        "labeled_accounts": int(labeled["user_id"].nunique()),
        "labeled_accounts_covered": int(labeled.loc[is_covered, "user_id"].nunique()),
        "labeled_dollars": round(float(labeled["amount"].sum()), 2),
        "labeled_dollars_covered": round(float(labeled.loc[is_covered, "amount"].sum()), 2),
    }


def related_ids(flags: pd.DataFrame) -> set:
    """Transaction ids listed in related_txn_ids (the other charges of each flagged burst)."""
    ids = set()
    for value in flags["related_txn_ids"]:
        if isinstance(value, str) and value:
            ids.update(value.split(";"))
    return ids


def rule_names(flags: pd.DataFrame) -> list[str]:
    """Every reason code that appears in the flags, sorted."""
    names = set()
    for rules in flags["rules"]:
        names.update(rules.split(";"))
    return sorted(names)


def time_split_check(flags: pd.DataFrame, transactions: pd.DataFrame, labeled: pd.DataFrame) -> dict:
    """Compare the first and second 45 days with thresholds held fixed. Also report how close
    the largest small-charge run that did not qualify came to the card-testing threshold."""
    period_start = transactions["timestamp"].min().normalize()
    split_at = period_start + pd.Timedelta(days=TIME_SPLIT_DAYS)
    period_end = transactions["timestamp"].max() + pd.Timedelta(seconds=1)
    flag_times = pd.to_datetime(flags["timestamp"], utc=True)
    bursts = summarize_bursts(transactions)

    result = {"split_at": f"{split_at:%Y-%m-%d}"}
    for half_name, start, end in [("first_half", period_start, split_at), ("second_half", split_at, period_end)]:
        half_flags = flags[is_between(flag_times, start, end)]
        half_labeled = labeled[is_between(labeled["timestamp"], start, end)]
        half_rows = int(is_between(transactions["timestamp"], start, end).sum())
        half_bursts = bursts[is_between(bursts["started_at"], start, end)]
        near_misses = half_bursts[~half_bursts["qualified"]]

        result[half_name] = label_metrics(half_flags, half_labeled, half_rows)
        result[half_name]["card_testing_bursts_flagged"] = int(half_bursts["qualified"].sum())
        result[half_name]["largest_non_qualifying_run"] = {
            "charges": int(near_misses["charges"].max()) if len(near_misses) else 0,
            "merchants": int(near_misses["merchants"].max()) if len(near_misses) else 0,
        }
    return result


def summarize_bursts(transactions: pd.DataFrame) -> pd.DataFrame:
    """One row per small-charge burst: size, merchants, start time, and whether it met R3's threshold."""
    charges = find_small_charge_bursts(transactions)
    bursts = charges.groupby("burst_id").agg(
        charges=("charges_so_far", "max"),
        merchants=("merchants_so_far", "max"),
        started_at=("burst_started_at", "first"),
    )
    bursts["qualified"] = (bursts["charges"] >= MIN_CHARGES) & (bursts["merchants"] >= MIN_DISTINCT_MERCHANTS)
    return bursts


def is_between(times: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """True where start <= time < end."""
    return (times >= start) & (times < end)
