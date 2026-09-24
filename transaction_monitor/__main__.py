"""Command-line entry point.

    python3 -m transaction_monitor                   # the provided dataset in test_data/
    python3 -m transaction_monitor --dataset small   # test_data/transactions_small.csv -> output/flags_small.csv
    python3 -m transaction_monitor --verbose         # also print how long each step and rule takes
"""
import argparse
import sys

from .pipeline import run_pipeline
from .run_files import RunFiles, resolve_run_files


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python3 -m transaction_monitor",
        description="Flag suspicious transactions with rules.",
    )
    parser.add_argument("--dataset", metavar="SUFFIX",
                        help="run on test_data/transactions_SUFFIX.csv; outputs get the same suffix")
    parser.add_argument("--transactions", help="path to a transactions CSV (overrides --dataset)")
    parser.add_argument("--labels", help="path to a confirmed-fraud CSV; optional, used only to evaluate the flags")
    parser.add_argument("--output-dir", default="output", help="where the output files go (default: output)")
    parser.add_argument("-v", "--verbose", action="store_true", help="print how long each step and rule takes")
    args = parser.parse_args(argv)

    try:
        files = resolve_run_files(args.dataset, args.output_dir, args.transactions, args.labels)
    except ValueError as error:
        parser.error(str(error))
    if not files.transactions.exists():
        sys.exit(f"Input not found: {files.transactions}. Download the provided data or add your dataset first (see README.md).")

    summary = run_pipeline(files, args.verbose)
    print_summary(summary, files)


def print_summary(summary: dict, files: RunFiles) -> None:
    flags = summary["flags"]
    usable_rows = summary["ingest"]["usable_rows"]
    total_seconds = summary["timings_seconds"]["pipeline_total"]
    print(f"{usable_rows:,} usable rows -> {flags['transactions_flagged']:,} flagged transactions "
          f"({flags['flag_rate_pct']:.3f}%, review budget ~{flags['review_budget']:,}) in {total_seconds:.1f}s")
    width = max(len(rule) for rule in flags["flags_per_rule"])
    for rule, count in flags["flags_per_rule"].items():
        print(f"  {rule:<{width}}  {count:>5}")
    print(describe_label_coverage(summary.get("evaluation")))
    print(f"Outputs: {files.flags}, {files.rejects}, {files.summary}")


def describe_label_coverage(evaluation: dict | None) -> str:
    """One line on how many labeled transactions fall inside flagged cases, or that there are no labels."""
    if evaluation is None:
        return "Labels: not available (no confirmed-fraud file for this dataset)"
    overall = evaluation["overall"]
    return (f"Labels: {overall['labeled_txns_covered']}/{overall['labeled_txns']} labeled transactions inside "
            f"flagged cases ({overall['labeled_txns_flagged']} flagged directly), "
            f"{overall['labeled_accounts_covered']}/{overall['labeled_accounts']} labeled accounts")


if __name__ == "__main__":
    main()
