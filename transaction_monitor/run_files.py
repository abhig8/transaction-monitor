"""Input and output file names for a run, with an optional dataset suffix.

The default dataset is test_data/transactions.csv with test_data/confirmed_fraud.csv.
Another dataset, such as test_data/transactions_small.csv, is selected with the suffix
"small". Its outputs carry the same suffix (output/flags_small.csv, and so on), so
runs on different datasets never overwrite each other.
"""
import re
from dataclasses import dataclass
from pathlib import Path

TEST_DATA_DIR = Path("test_data")
VALID_SUFFIX = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class RunFiles:
    transactions: Path
    labels: Path
    flags: Path
    rejects: Path
    summary: Path


def resolve_run_files(
    dataset_suffix: str | None = None,
    output_dir: str | Path = "output",
    transactions: str | Path | None = None,
    labels: str | Path | None = None,
) -> RunFiles:
    """Build the file names for a run. Explicit transactions/labels paths override the suffix."""
    if dataset_suffix and not VALID_SUFFIX.fullmatch(dataset_suffix):
        raise ValueError(f"Invalid dataset suffix {dataset_suffix!r}: use letters, digits, '-' or '_'.")
    tag = f"_{dataset_suffix}" if dataset_suffix else ""
    output_dir = Path(output_dir)
    return RunFiles(
        transactions=Path(transactions) if transactions else TEST_DATA_DIR / f"transactions{tag}.csv",
        labels=Path(labels) if labels else TEST_DATA_DIR / f"confirmed_fraud{tag}.csv",
        flags=output_dir / f"flags{tag}.csv",
        rejects=output_dir / f"rejects{tag}.csv",
        summary=output_dir / f"summary{tag}.json",
    )
