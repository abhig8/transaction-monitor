"""Merchant-name normalization (TDD.md section 2.3).

The raw names differ only in format: casing, a card-processor prefix ("SQ *"),
store numbers ("#1234", "Store 615") and channel or location suffixes
("ONLINE", "HTTPSWWW", "SAN JOSE CA"). We turn each name into a matching key.
Anything an analyst reads keeps the raw name.
"""
import pandas as pd

PROCESSOR_PREFIX = r"^SQ\s*\*\s*"

# Numbers are only removed in the "#1234" and "Store 615" forms, so merchants whose
# real name contains a number, like "ONLINE-MKT 8827" or "RESELL MARKET 24", keep it.
TRAILING_SUFFIX = r"(?:\s*#\s*\d+|\s+(?:STORE\s+\d+|ONLINE|HTTPSWWW|SAN JOSE CA|SUNNYVALE CA|CA))$"


def normalize_merchants(merchant_names: pd.Series) -> pd.Series:
    """Return a matching key for each merchant name, or "" for a blank name."""
    # There are far fewer distinct names than rows, so normalize each distinct name once.
    distinct_names = pd.Series(merchant_names.unique())

    keys = distinct_names.str.strip().str.upper()
    keys = keys.str.replace(PROCESSOR_PREFIX, "", regex=True)
    # Run twice because a name can carry two suffixes, e.g. a store number and a city.
    keys = keys.str.replace(TRAILING_SUFFIX, "", regex=True)
    keys = keys.str.replace(TRAILING_SUFFIX, "", regex=True)
    # Drop punctuation last, so "7-ELEVEN" becomes "7ELEVEN" and "PG&E" becomes "PGE".
    keys = keys.str.replace(r"[^A-Z0-9 ]", "", regex=True)
    keys = keys.str.replace(r"\s+", " ", regex=True).str.strip()

    key_for_name = dict(zip(distinct_names, keys))
    return merchant_names.map(key_for_name)
