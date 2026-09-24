# Transaction Monitoring Subsystem

This project uses rules to flag suspicious consumer card transactions for a fraud-ops review queue. It was built as a 2–3 hour take-home.

- [RULES.md](RULES.md) covers the five rules, their trade-offs, what we let through, and how the labels were used.
- [TDD.md](TDD.md) covers the data review, design decisions and results.
- [output/flags.csv](output/flags.csv) is the list of flagged transactions.

Contents: [Results](#results) · [Setup](#setup) · [Run](#run) · [Running other datasets](#running-other-datasets) · [Outputs](#outputs) · [Code layout](#code-layout) · [What we cut](#what-we-cut)

## Results

| | |
|---|---|
| Usable rows | 999,965 of 1,001,000. The other 1,035 rows (1,000 exact duplicates and 35 that can't be parsed) are listed in `output/rejects.csv` |
| Flagged transactions | 714 (0.071%), against a review budget of about 1,000 |
| Flags per rule | R1: 423, R2: 476, R3: 55 (240 transactions are flagged by both R1 and R2) |
| Fraud coverage | The flagged cases contain 1,710 of the 1,734 fraud transactions identified in the data (98.6%), and all 190 labeled ones |
| Runtime | About 4 seconds for 1M rows on a laptop |

## Setup

```bash
git clone https://github.com/abhig8/transaction-monitor.git
cd transaction-monitor
```

Requires Python 3.11 or newer. Check your version with `python3 --version`. If it is older, name a newer Python explicitly, as the first line below does.

```bash
python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
```

On Windows, use `python` wherever these instructions say `python3`.

Download the provided data into `test_data/`. These are the two files linked in the brief, and they are not committed:

```bash
mkdir -p test_data
curl -L -o test_data/transactions.csv "https://drive.usercontent.google.com/download?id=1aRY6Yf0vQFqoSEg77npv92iJsl16snYP&export=download&confirm=t"
curl -L -o test_data/confirmed_fraud.csv "https://drive.usercontent.google.com/download?id=1MS6ZKhhx6v8BYQYWGysBsULiI-nsJLzo&export=download&confirm=t"
```

You can also download them in a browser ([transactions.csv](https://drive.google.com/file/d/1aRY6Yf0vQFqoSEg77npv92iJsl16snYP/view), [confirmed_fraud.csv](https://drive.google.com/file/d/1MS6ZKhhx6v8BYQYWGysBsULiI-nsJLzo/view)) and save them under those names in `test_data/`.

## Run

```bash
python3 -m transaction_monitor
```

Expected output:

```
999,965 usable rows -> 714 flagged transactions (0.071%, review budget ~1,000) in 4.1s
  DEVICE_NEW_TO_MULTIPLE_ACCOUNTS    423
  LARGE_PURCHASE_ON_NEW_DEVICE       476
  CARD_TESTING_BURST                  55
Labels: 190/190 labeled transactions inside flagged cases (37 flagged directly), 79/79 labeled accounts
Outputs: output/flags.csv, output/rejects.csv, output/summary.json
```

Add `--verbose` to print how long each step and each rule takes. To run the unit tests:

```bash
python3 -m unittest
```

To measure what R4, R5 and the other budget options in RULES.md would add:

```bash
python3 -m transaction_monitor.scenarios
```

## Running other datasets

Add the files to `test_data/`, each with the same short suffix (letters, digits, `-` or `_`):

```
test_data/transactions_<suffix>.csv
test_data/confirmed_fraud_<suffix>.csv     optional; only used to evaluate the flags
```

Then run:

```bash
python3 -m transaction_monitor --dataset <suffix>
```

The outputs carry the same suffix (`output/flags_<suffix>.csv`, `output/rejects_<suffix>.csv` and `output/summary_<suffix>.json`), so runs never overwrite each other. Without a labels file, the run prints `Labels: not available` and skips the evaluation. For files stored elsewhere, pass `--transactions`, and optionally `--labels`, instead. `--output-dir` changes where the outputs go.

A new dataset needs the same six columns as the provided one. It must also hold each account's full history, so sample by account, not by row. If you sample rows, devices an account has always used start to look new, and R1 and R2 fill up with false positives.

## Outputs

| File | Contents |
|---|---|
| `output/flags.csv` | One row per flagged transaction with these columns: `txn_id`; `rules` (reason codes separated by `;`); `reason`; `user_id`; `timestamp`; `amount`; `merchant_name`; `device_id`; and `related_txn_ids` (for a card-testing burst, the burst's other charges) |
| `output/rejects.csv` | Every input row that was not used, with its line number in the input file (`file_line`) and a `reject_reason`: `exact_duplicate`, `unparseable_timestamp` or `missing_or_invalid_amount`. Usable rows plus these rows equal the rows read. |
| `output/summary.json` | Cleaning counts, flags per rule, the flag rate, the label evaluation including the time split, and how long each step took |

Each reason code and its label are defined once, in `transaction_monitor/reason_codes.py`, and every `reason` starts with the label:

| Reason code | Label |
|---|---|
| `DEVICE_NEW_TO_MULTIPLE_ACCOUNTS` | Device new to multiple accounts |
| `LARGE_PURCHASE_ON_NEW_DEVICE` | Large purchase on new device |
| `CARD_TESTING_BURST` | Card-testing burst |

Example:

> Large purchase on new device: $1,550.06 at Best Buy on device d_864334, its first transaction on this account (2026-06-20 21:54 UTC). That is 89x the account's median purchase of $17.39 over its 5 earlier purchases.

## Code layout

```
transaction_monitor/
  __main__.py                  command line: python3 -m transaction_monitor
  run_files.py                 input and output file names, including dataset suffixes
  pipeline.py                  runs the steps in order, times them, writes the outputs
  ingest.py                    loads the CSV, drops duplicates, sets aside bad rows, sorts
  merchants.py                 merchant-name normalization
  reason_codes.py              reason codes, labels and descriptions
  flags.py                     builds flag rows and combines them into one row per transaction
  evaluate.py                  label-based evaluation and the time-split check
  scenarios.py                 budget what-if for R4, R5 and other options (not part of the pipeline)
  rules/
    device_history.py          which devices are new to which accounts (7-day warm-up)
    shared_device_ring.py      R1
    new_device_spend_spike.py  R2
    card_testing_burst.py      R3
tests/                         unit tests
test_data/                     the provided dataset, downloaded during setup (not committed)
output/                        flags, rejects and run summary
```

The pipeline sorts the data once, then uses vectorized group-bys and cumulative sums over all rows. Python loops only run over the few hundred candidates a rule has already narrowed down, to write the reason text.

## What we cut

- **R4, cash-equivalent purchases:** documented but not built. It would add 35–115 flags, it is unverified, and its merchant list was written after seeing the data.
- **R5, velocity:** cut. It would add 1,719 flags, mostly ordinary purchases made the day after a large one.
- **Earlier transactions on ring devices:** once R1 flags a device, also flagging what happened on it before would catch 24 more ring transactions. Deferred.
- **ML, streaming, UI:** out of scope per the brief.

How AI was used is described in [TDD §8](TDD.md#8-how-ai-was-used).
