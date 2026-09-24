# Transaction Monitoring Subsystem: Technical Design

**Status:** Complete (2026-09-23). All figures were computed from the provided CSVs. The rules themselves are written up for reviewers in [RULES.md](RULES.md).

## Contents

- [Summary](#summary)
- [1. Problem](#1-problem)
- [2. Data](#2-data)
- [3. Fraud patterns in the data](#3-fraud-patterns-in-the-data)
- [4. Decisions](#4-decisions)
- [5. Evaluation](#5-evaluation)
- [6. Results](#6-results)
- [7. Limitations](#7-limitations)
- [8. How AI was used](#8-how-ai-was-used)

## Summary

- **Built:** a batch pipeline (`python3 -m transaction_monitor`) that cleans the 1M-row file and flags transactions with three rules. It runs in about 4 seconds on a laptop.
- **Result:** 714 flags (0.071%) against a budget of about 1,000. 713 fall inside known fraud patterns and 1 is a false positive (a user with a new phone). The flagged cases cover 1,710 of the 1,734 fraud transactions we can identify, including all 190 labeled ones. These figures are measured against the patterns in section 3, which we identified from this same data; the labels are the only independent check.
- **Fraud found:** card testing and account takeover (both labeled), plus two patterns with no labels: a shared-device ring and suspected prepaid cash-out.
- **Key decisions:**
  - The budget is a ceiling, not a target (D1).
  - One flag per transaction, except card-testing bursts (D2).
  - Rules only see the past (D4).
  - A device counts as new only after a 7-day warm-up (D9).

## 1. Problem

Flag suspicious transactions in a 1M-row, 90-day CSV, using rules built only from its six columns. Each flag goes to a fraud-ops analyst, so it must say which rule fired and why.

**Constraints**
- Rules only: no ML, streaming or infrastructure.
- Analysts can review about 1,000 flags per 1M transactions.
- A reviewer must be able to run it in under 10 minutes.
- The fraud labels (`confirmed_fraud.csv`) are incomplete and biased, so an unlabeled transaction is not necessarily legitimate.
- 2–3 hour timebox.

We added two requirements of our own: report each rule's run time, and give every reason code both a machine-readable form and a human-readable form.

## 2. Data

### 2.1 Shape

| | |
|---|---|
| Rows | 1,001,000 (999,965 usable) |
| Period | 2026-05-03 to 2026-07-31 UTC (90 days), about 11,100 rows a day |
| Users / devices | 2,000 / 2,909 |
| Activity per user | Median 256 transactions; 14 heavy users with 6,400+ (up to 19,735) |
| Merchants | 134,586 raw names, 74 after normalization |

The file is shuffled: about half of adjacent rows are out of time order, so the pipeline sorts by account and time before any rule runs. Transactions are spread evenly across all hours of the day, so time-of-day rules would be noise.

### 2.2 Cleaning

| Issue | Rows | Handling |
|---|---:|---|
| Exact duplicate rows | 1,000 | Keep the first copy; list the rest in `rejects.csv` |
| Timestamp is `not_a_timestamp` | 20 | Set aside in `rejects.csv` |
| Blank amount | 15 | Set aside in `rejects.csv` |
| Blank merchant name | 15 | Keep; merchant unknown |
| Negative amount (refund) | 10 | Keep; never flagged, never used in baselines |
| Same user, same second | 398 | Break ties by `txn_id` when sorting |

Every input row is accounted for. The 999,965 usable rows plus the 1,035 rows in `rejects.csv` make 1,001,000, and each rejected row carries its line number in the input file and a reason. None of the 190 labeled transactions is among the rejected rows.

### 2.3 Merchant names

Merchant names differ in format only. The variations are casing, a `SQ *` prefix, store numbers (`#1234`, `Store 615`), and channel or city suffixes (`ONLINE`, `HTTPSWWW`, `SAN JOSE CA`). Stripping these is deterministic and maps every raw name to one of 74 merchants: 57 everyday ones and 17 low-volume ones that appear in the labels. No fuzzy matching is needed.

The tests pin the known pitfalls:
- `7-ELEVEN` and `PG&E` must keep their names.
- Numbers that belong to a name, as in `ONLINE-MKT 8827` and `RESELL MARKET 24`, must survive.

## 3. Fraud patterns in the data

The labels cover 190 transactions across 79 accounts. They describe two patterns with a clean gap between them: 158 labels fall between $0.51 and $4.96, and 32 between $330.63 and $1,753.17. The data also holds two patterns with no labels at all.

| Pattern | Transactions | Accounts | Dollars | Labeled |
|---|---:|---:|---:|---:|
| Card testing | 1,052 | 55 | $2,901.71 | 158 (15%) |
| Account takeover after dormancy | 216 | 45 | $236,549.95 | 32 (15%) |
| Shared-device ring | 466 | 79 | $122,806.44 | 0 |
| Suspected prepaid cash-out | 102 | 35 | $49,427.15 | 0 |

- **Card testing:**
  - 55 bursts of 12–25 charges under $5, each burst within 15–45 minutes, on the account's usual device.
  - They hit 12 low-friction merchants: game credits, app stores, trials and donation pages.
  - Customers dispute the incident, not each charge: 53 of the 55 bursts have a label, but only 15% of the charges do.
- **Account takeover:**
  - After 32–49 days of silence, a device the account never used makes 3–6 purchases within 6 hours.
  - The purchases are at electronics, jewelry, gift-card and prepaid merchants, typically 37x the account's earlier median.
  - 19 of the 45 takeovers were never disputed.
- **Shared-device ring:**
  - 7 devices, each used by 9–14 accounts over 10–41 days.
  - Each account makes about six purchases of $81–$450 at the same cash-out merchants.
  - None of it is labeled. Either the owners never noticed the charges or they rented out their accounts; either way, customer disputes will never surface it.
- **Suspected prepaid cash-out:**
  - 102 PREPAID DEPOT purchases between $470.07 and $499.89, on devices the accounts already used.
  - A tight band just under $500 fits coached scam victims or mule cash-out. This is unconfirmed.

Pattern sizes use hindsight and one artifact of how the data was generated: fraud devices have IDs in a distinct range. We used that only for counting, never as a rule input. We also looked for night-time activity, round-amount structuring and refund abuse, and found none.

**False-positive traps that shaped the rules**
- 52 household devices are shared by 2–6 accounts for the whole period. A rule that only asked "is this device used by several accounts?" would flag families.
- 14 heavy users make 75–220 transactions a day and would trip any fixed velocity threshold.
- About 1,530 purchases of $500 or more have no link to any fraud pattern. An amount-only rule would spend the budget on noise.
- On day one no account has any history, and takeovers target quiet accounts. Any rule that compares against an account's normal behavior needs a warm-up period.

## 4. Decisions

- **D1. The budget is a ceiling, not a target.** The brief gives analyst capacity, not a fraud rate. The fraud here exceeds that capacity: the first three patterns alone hold 1,734 transactions. So the work is choosing what to leave out, not filling slots.
- **D2. One flag per transaction, except card testing, which gets one flag per burst.** A burst is one card and one decision for the analyst: block it. Flagging every charge would cost 1,052 review slots for $2,902 of direct loss. The burst's other charges are listed in `related_txn_ids`.
- **D3. Reason codes live on one enum.** `ReasonCode` holds three things for each code:
  - the code, which is machine-readable and names the observed behavior rather than a conclusion;
  - the label analysts see;
  - a one-line description.

  Every reason starts with the label.
- **D4. Rules only see the past.** A flag must be reproducible with the information available when the transaction happened. Using the full 90 days would:
  - overstate how well the rules work;
  - let fraud hide in its own baseline: u_01282's $1,550 purchase is 2.4x its full-history median but 89x its median before the takeover;
  - leak signals from the future, such as "the account went quiet afterwards".
- **D5. Cleaning as in section 2.**
- **D6. Python 3.11+, pandas and pyarrow at pinned versions, no database.** 1M rows fit in memory, and pandas is familiar to any reviewer.
- **D7. Timings are reported.** Per-step and per-rule times print with `--verbose` and are always written to `summary.json`.
- **D8. Labels evaluate the rules but never feed into them** (section 5).
- **D9. A device counts as new only after a 7-day warm-up.** We can't know a device's true age: a phone someone has owned for years looks "first seen" the first time it appears in the window. The data supports the warm-up:
  - all 2,000 users appear in the first 4 days;
  - 957 devices first appear in a user's first week;
  - after day 7, 124 of the 125 new account–device pairs belong to the ring or a takeover.

  The cost is that a takeover in an account's first week is missed.
- **D10. Test data lives in `test_data/`, downloaded rather than committed.** Setup downloads the provided files from the links in the brief, so the repo stays small and holds none of the company's data. The folder name marks the files as test input, not production data. Other datasets can be added with a suffix and run with `--dataset`; their outputs carry the same suffix (see the README).

## 5. Evaluation

**Why not accuracy or F1.** Accuracy is meaningless here: flagging nothing scores 99.98%. F1 doesn't fit either, because our operating point is set by analyst capacity, not by trading off precision against recall.

**Why the labels only go so far.** Measured against biased labels:
- Precision is only a floor. A perfect ring rule would score 0%, because the ring has no labels.
- Recall only covers fraud that customers report.

**What we report instead:**
- flags and flag rate against the ceiling, per rule and combined;
- the share of flags that are labeled (a floor on precision);
- recall by incident, by transaction and by dollars;
- a time-split check for stability.

`output/summary.json` holds all of these. The results against the labels are in [RULES.md](RULES.md#how-we-used-the-labels).

## 6. Results

Rule definitions, rationale, false-positive trade-offs, prioritization and the use of the spare budget are in [RULES.md](RULES.md). This section covers the overall results, the time-split check, design notes and the case catalog.

### 6.1 Totals

| | Result |
|---|---|
| Flags | 714 (0.071%), with 240 flagged by both R1 and R2 |
| Precision | 713 of 714 fall inside known fraud patterns; 1 new-phone false positive |
| Fraud covered | 1,710 of the 1,734 transactions sit in flagged cases (98.6%): all takeovers, all bursts, and 442 of 466 ring transactions |
| Labels | 190 of 190 are inside flagged cases (37 flagged directly); all 79 accounts; 100% of labeled dollars |
| Runtime | About 4 s (reading and cleaning 3.7 s; each rule under 0.25 s) |

### 6.2 Time-split check

The thresholds were held fixed, and the 90 days were split at 2026-06-17 into two 45-day halves:

| | Days 1–45 | Days 46–90 |
|---|---:|---:|
| Flags | 188 | 526 |
| Flag rate | 0.037% | 0.106% |
| Labeled transactions covered | 73 / 73 | 117 / 117 |
| Labeled accounts covered | 27 / 27 | 52 / 52 |
| Card-testing bursts flagged | 29 | 26 |
| Largest small-charge run that didn't qualify | 9 charges, 8 merchants | 8 charges, 8 merchants |

- **R3:** setting its threshold from the first half alone, one charge above the largest legitimate run, gives the same 10, and it produces no false positives in the second half. The seven legitimate runs of 7–9 charges belong to heavy users (median 3,179 transactions each).
- **R1 and R2:** their thresholds are structural (2 accounts, and 3x a baseline from before the new device appeared) rather than tuned counts.
- **The second half has more flags** because every takeover falls there, so R2 is effectively tested out of sample on takeovers.
- This checks stability, not independence, because the rules were designed after looking at all 90 days.

### 6.3 Design notes

- **R1 threshold.** Counting every account on a device needs a threshold of 8 to stay above households, and catches only 201 of the 466 ring transactions. Counting only accounts that are new to the device lets the threshold drop: 4 or more catches 335, 3 or more catches 380, and 2 or more catches 423. None of these settings flags a transaction on any other device.
- **R2 baseline.** An earlier version compared each purchase with the account's median so far. It missed the last purchase of u_01282's takeover: the takeover's own purchases had raised the median to $351.09, so the $966.64 purchase was only 2.75x. Lowering the multiplier to 2.5x catches it, but that tunes the rule to one labeled case. Stopping the baseline when the new device appears fixes the cause instead: against the $17.39 median from before, the purchase is 56x.

| R2 version | Flags | Takeover transactions | Labeled takeovers | Ring transactions | False positives |
|---|---:|---:|---:|---:|---:|
| 3x, median so far | 475 | 215 / 216 | 31 / 32 | 259 | 1 |
| 2.5x, median so far | 486 | 216 / 216 | 32 / 32 | 269 | 1 |
| 3x, median before the new device (shipped) | 476 | 216 / 216 | 32 / 32 | 259 | 1 |

- **R4 and R5** are measured with `python3 -m transaction_monitor.scenarios`. The results are in [RULES.md](RULES.md#using-the-budget).

### 6.4 Cases

| # | Case | Outcome |
|---|---|---|
| C1 | User gets a new phone (1 account) | R2 flags its first large purchase on the phone. This is the single false positive, and in production it would be R2's main one; an amount floor or a customer confirmation step would handle it. |
| C2 | Device owned before the data window began (957 devices) | Not flagged, thanks to the warm-up (D9) |
| C3 | Household device shared from day one (52 devices) | Not flagged: the device is not new to those accounts |
| C4 | Family buys a new shared tablet | R1 would flag the second account. This is a production false positive; the case doesn't occur in this data. |
| C5 | Heavy user (14 accounts) | Not flagged: there is no velocity rule |
| C6 | Large purchase at an everyday merchant on the usual device (~1,530) | Not flagged, by design |
| C7 | Refund (10 rows) | Excluded |
| F1 | Card-testing burst (55) | All flagged, one flag per burst |
| F2 | Takeover after dormancy (216 transactions) | All flagged |
| F3 | Takeover purchase made after the incident has already inflated the account's median ($966.64, u_01282) | Caught: the baseline stops before the new device appeared, so the purchase is 56x the account's median |
| F4 | Takeover in an account's first 7 days | Missed by design (D9); none occur in the data |
| F5 | Ring victims after the device is shared | 442 of 466 flagged (R1 and R2 together) |
| F6 | Each ring device's first victim, before any sharing (24 transactions) | Missed; catching them means flagging a ring device's earlier transactions once it is detected |
| F7 | Prepaid purchases just under $500 (102) | Not flagged, because R4 is not built |
| F8 | Card-testing charges before and after the flag | Listed in the flag's `related_txn_ids` |

## 7. Limitations

- **Thresholds were chosen on the same data they are evaluated on.** The time split shows the results are stable, but it is not an independent test.
- **Rules need each account's full history.** A dataset sampled by row, rather than by account, makes devices an account has always used look new, and inflates R1 and R2.
- **R1:** the 7-day warm-up only works because every user starts in the first days of the file. Production would use real device history instead. Expected false positives there are new family tablets and shared work phones.
- **R2:**
  - Only 1 of the 2,000 users got a new phone in this data. Production will see many more, so R2 needs an amount floor or a customer confirmation step (step-up authentication).
  - Blind spot: a takeover on an account that already spends a lot, where each purchase stays under 3x its median.
- **R3:** the count threshold sits just above the largest legitimate run, which is 9 charges. Those legitimate runs span 72–124 minutes, while real bursts take 15–45. Real card testers slow down to stay under thresholds, so production should:
  - require the charges to fall within a fixed time window;
  - set the count from what legitimate customers do, not from the fraud we've seen.

What we knowingly let through, and why that is the right trade-off, is in [RULES.md](RULES.md#using-the-budget), along with why R4 and R5 are not shipped. Fuzzy merchant matching and time-of-day rules were not needed (section 2).

## 8. How AI was used

Claude (Claude Code) was used for data exploration, to compute the figures in this document, and to generate rule ideas. Its output was checked against the data before use. For example, it suggested lowering R2's multiplier to 2.5x to catch one labeled transaction; we fixed the underlying cause instead, with a baseline that stops before the new device appeared.
