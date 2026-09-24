"""Run the monitoring steps in order and write the output files."""
import json
import time
from collections.abc import Callable

import pandas as pd

from .evaluate import evaluate_against_labels
from .flags import combine_flags
from .ingest import load_transactions
from .reason_codes import ReasonCode
from .rules import card_testing_burst, find_device_pairings, new_device_spend_spike, shared_device_ring
from .run_files import RunFiles

REVIEW_BUDGET_PER_MILLION = 1_000  # analyst capacity from the brief


class StepTimer:
    """Records how long each named step takes, and prints it in verbose mode."""

    def __init__(self, verbose: bool):
        self.verbose = verbose
        self.seconds: dict[str, float] = {}

    def run(self, step_name: str, function: Callable, *args):
        start = time.perf_counter()
        result = function(*args)
        self.seconds[step_name] = round(time.perf_counter() - start, 3)
        if self.verbose:
            print(f"  {step_name:<38}{self.seconds[step_name]:>7.2f}s")
        return result


def run_pipeline(files: RunFiles, verbose: bool = False) -> dict:
    """Load, clean, apply every rule, write the outputs, and return the run summary."""
    timer = StepTimer(verbose)
    started = time.perf_counter()

    ingested = timer.run("ingest", load_transactions, files.transactions)
    transactions = ingested.transactions
    pairings = timer.run("device_pairings", find_device_pairings, transactions)

    rules = [
        (ReasonCode.DEVICE_NEW_TO_MULTIPLE_ACCOUNTS, shared_device_ring, (transactions, pairings)),
        (ReasonCode.LARGE_PURCHASE_ON_NEW_DEVICE, new_device_spend_spike, (transactions, pairings)),
        (ReasonCode.CARD_TESTING_BURST, card_testing_burst, (transactions,)),
    ]
    flags_by_rule = {}
    for reason_code, rule, rule_inputs in rules:
        flags_by_rule[reason_code] = timer.run(f"rule {reason_code}", rule, *rule_inputs)
    flags = timer.run("combine_flags", combine_flags, list(flags_by_rule.values()), transactions)

    timer.run("write_outputs", write_outputs, files, flags, ingested.rejects)
    timer.seconds["pipeline_total"] = round(time.perf_counter() - started, 3)

    summary = build_summary(files, ingested.counts, flags, flags_by_rule)
    if files.labels.exists():
        summary["evaluation"] = timer.run("evaluate", evaluate_against_labels, flags, transactions, files.labels)
    summary["timings_seconds"] = timer.seconds
    files.summary.write_text(json.dumps(summary, indent=2))
    return summary


def write_outputs(files: RunFiles, flags: pd.DataFrame, rejects: pd.DataFrame) -> None:
    files.flags.parent.mkdir(parents=True, exist_ok=True)
    flags.to_csv(files.flags, index=False)
    rejects.to_csv(files.rejects, index=False)


def build_summary(files: RunFiles, ingest_counts: dict, flags: pd.DataFrame,
                  flags_by_rule: dict[ReasonCode, pd.DataFrame]) -> dict:
    """Counts for the summary file: inputs, cleaning, flags per rule, flag rate against the budget."""
    usable_rows = ingest_counts["usable_rows"]
    return {
        "inputs": {
            "transactions": str(files.transactions),
            "labels": str(files.labels) if files.labels.exists() else None,
        },
        "ingest": ingest_counts,
        "flags": {
            "transactions_flagged": len(flags),
            "flag_rate_pct": round(100 * len(flags) / usable_rows, 4),
            "review_budget": round(usable_rows * REVIEW_BUDGET_PER_MILLION / 1_000_000),
            "flags_per_rule": {code.value: len(rule_flags) for code, rule_flags in flags_by_rule.items()},
            "flagged_by_more_than_one_rule": int(flags["rules"].str.contains(";").sum()),
        },
        "reason_codes": {code.value: {"label": code.label, "description": code.description} for code in ReasonCode},
    }
