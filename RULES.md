# Rules

This document covers the brief's rule requirements: the five proposed rules and their rationale, the prioritization, the flag format, the review budget and what we knowingly let through, and the note on the labels.

The five rules use only the six columns provided:
- **R1–R3** are built.
- **R4** is documented but not built.
- **R5** was tested and cut.

`python3 -m transaction_monitor` reproduces the results of the built rules, and `python3 -m transaction_monitor.scenarios` reproduces the R4 and R5 measurements. The data behind each pattern is in [TDD.md](TDD.md) §3.

| Rule | Reason code | Status | Flags | What it catches |
|---|---|---|---:|---|
| R1 Shared-device ring | `DEVICE_NEW_TO_MULTIPLE_ACCOUNTS` | Built | 423 | 423 of 466 ring transactions; nothing on any other device |
| R2 New device + spend spike | `LARGE_PURCHASE_ON_NEW_DEVICE` | Built | 476 | All 216 takeover transactions, plus 259 ring transactions (240 also flagged by R1) and 1 false positive |
| R3 Card-testing burst | `CARD_TESTING_BURST` | Built | 55 | All 55 bursts, which contain 1,052 charges |
| R4 Cash-equivalent purchase | – | Not built | +35 to +115 | Suspected prepaid cash-out |
| R5 Velocity | – | Cut | +1,719 | Mostly ordinary purchases |
| **Shipped total** | | | **714 (0.071%)** | 713 inside known fraud patterns; 1 false positive |

## Contents

- [How flags work](#how-flags-work)
- [Prioritization](#prioritization)
- [R1. Shared-device ring](#r1-shared-device-ring)
- [R2. New device and spend spike](#r2-new-device-and-spend-spike)
- [R3. Card-testing burst](#r3-card-testing-burst)
- [R4. Cash-equivalent purchase (not built)](#r4-cash-equivalent-purchase-not-built)
- [R5. Velocity (cut)](#r5-velocity-cut)
- [Using the budget](#using-the-budget)
- [Overfitting check](#overfitting-check)
- [How we used the labels](#how-we-used-the-labels)

## How flags work

- **One row per flagged transaction** in `output/flags.csv`, with its `txn_id`. The `rules` column lists every reason code that fired. Each `reason` starts with the code's label, followed by the specifics of the case.
- **Card testing is the one exception: one flag per burst.** A burst is one card and one decision for the analyst: block it. Flagging every charge would take 1,052 review slots for $2,902 of direct loss, so the burst's other charges go in `related_txn_ids` instead.
- **Rules only see the past.** Each rule uses only the flagged transaction and what came before it, so the flag rate here is the one production would see.
- **A device counts as new only after a warm-up.** It is new to an account only if it first appears after the account's first 7 days in the data, because a device's true age can't be observed.

## Prioritization

1. **R2:** it targets the costliest pattern ($236,550), and every flag it raises except one is fraud.
2. **R1:** the ring has no labels, so without a rule it is never found ($122,806).
3. **R3:** the direct loss is low ($2,902), but this is the earliest point to stop a stolen card. With one flag per burst, it costs only 55 slots.

R4 is deferred: nothing corroborates it, and its merchant list is overfitted. R5 is cut: most of what it adds is ordinary purchases.

**How the thresholds were set.** Each threshold sits in the gap between legitimate behavior and the fraud pattern. None was tuned to fill the budget:
- **R1:** households share devices, but the device is never new to those accounts, so 2 accounts that are new to a device is enough.
- **R2:** 3x the account's pre-device median catches all 216 takeover purchases, 90% of which are 11x or more. The only legitimate purchase above 3x is a new phone.
- **R3:** legitimate runs of small charges top out at 9 charges, while card-testing bursts have 12–25, so the threshold is 10.

Together the thresholds produce 714 flags, under the ~1,000 budget, so none had to be tightened. [Using the budget](#using-the-budget) covers the remaining slots.

## R1. Shared-device ring

`DEVICE_NEW_TO_MULTIPLE_ACCOUNTS` · "Device new to multiple accounts"

- **Pattern:** one device operating many accounts. It is either a takeover ring working through stolen logins or a mule farm. Here: 7 devices, 79 accounts, 466 purchases, $122,806.
- **Why it matters:** per-account controls can't see a ring. Each account gets about six plausible purchases of $81–$450, and only the device ties them together. Nobody disputes these purchases (the ring has no labels), so a rule is the only way to find it.
- **Rule:** once 2 or more accounts that are new to a device have used it, flag every later transaction on that device.
- **Why 2:** the 52 household devices (2–6 accounts each) are used from the first week, so they never count as new to those accounts. The threshold variants tried are in [TDD §6.3](TDD.md#63-design-notes).
- **Results:** 423 flags, all on the 7 ring devices.
- **False positives:** none here. In production, expect a family's new tablet or a shared work phone. The reason text names the device and the account count, so analysts can clear these quickly. Count accounts over a trailing 30-day window so that long-lived or resold devices don't drift over the threshold.
- **Misses:** 43 ring transactions, mostly each device's first victim before any sharing. R2 catches 19 of them. Flagging a ring device's earlier transactions once it is detected would catch the other 24.

## R2. New device and spend spike

`LARGE_PURCHASE_ON_NEW_DEVICE` · "Large purchase on new device"

- **Pattern:** account takeover, then cash-out. After 32–49 days of silence, a device the account has never used makes 3–6 purchases within 6 hours. The purchases are at electronics, jewelry, gift-card and prepaid merchants, typically 37x the account's earlier median.
- **Why it matters:** this is the costliest pattern, at $236,550 across 45 accounts. Fraudsters target dormant accounts because nobody watches them, and 19 of the 45 takeovers were never disputed.
- **Rule:** flag a purchase made within 24 hours of a new device first appearing on the account, if it is more than 3x the account's median purchase from before that device appeared.
- **Baseline:** the median stops when the new device appears, so a takeover in progress can't raise its own baseline. This catches a labeled $966.64 purchase that a running median missed ([TDD §6.3](TDD.md#63-design-notes)).
- **Results:** 476 flags: all 216 takeover transactions (including all 32 labeled), 259 ring transactions (19 of which R1 misses), and 1 false positive.
- **False positives:** the one false positive is a new phone ($109.21 at Steam, 4x the account's median). Production will see many more; add an amount floor, or send these cases to step-up authentication (asking the customer to confirm) instead of an analyst.
- **Blind spots:** a takeover in an account's first 7 days (none occur in the data), and a takeover on a high-spending account whose purchases stay under 3x.

## R3. Card-testing burst

`CARD_TESTING_BURST` · "Card-testing burst"

- **Pattern:** many small charges on a stolen card at low-friction merchants (game credits, app stores, trials, donation pages), to check that it works before it is used or sold. Here: 55 bursts of 12–25 charges, each within 15–45 minutes.
- **Why it matters:** the direct loss is small ($2,902 across 1,052 charges), but the test comes before the cash-out, so this is the cheapest place to stop the card.
- **Rule:** group each account's charges under $5 into bursts, where each charge comes within 30 minutes of the previous one. Flag the charge at which a burst reaches 10 charges at 5 or more merchants, with one flag per burst.
- **Results:** 55 flags, one per burst. All 158 labeled card-testing transactions are inside flagged bursts, and 5 of them are the flagged charge itself.
- **False positives:** none here. The count threshold sits just above the longest legitimate runs (9 charges), but those runs take 72–124 minutes, against 15–45 for real bursts. Hardening for testers who slow down is in [TDD §7](TDD.md#7-limitations).
- **Charges after the flag:** charges 11 and later happen after the flag fires. In batch review they are part of the case; a live system would already have blocked the card.

## R4. Cash-equivalent purchase (not built)

- **Pattern:** 35 accounts made 102 PREPAID DEPOT purchases, all between $470.07 and $499.89 ($49,427 in total), on devices they already used. None are labeled. A tight band just under $500 fits scam victims coached into buying prepaid cards, or mule cash-out.
- **Why it matters:** scams and mule accounts are major sources of loss and regulatory risk for a consumer fintech. Neither leads to a dispute, so the labels never surface them.
- **Rule:** flag a purchase at a cash-equivalent merchant (gift cards, prepaid, jewelry, resale, luxury electronics) that is above both $200 and 3x the account's earlier median.
- **False positives:** legitimate customers buy prepaid and gift cards too, especially around holidays. Without a device or behavior signal, the rule can't tell them apart from scam victims.
- **Measured impact:** flagging only each account's first qualifying purchase adds 35 flags, all in the prepaid pattern. Flagging every qualifying purchase adds 115 (102 in the prepaid pattern, 13 on ring devices).
- **Why it isn't built:**
  - Nothing corroborates it: there are no labels and no device signal.
  - The merchant list was written after seeing these merchant names, which makes it the most overfitted part of the system.
  - Telling a coached victim from a real buyer needs data we don't have, such as payment-to-person history or customer contact records.

## R5. Velocity (cut)

- **Pattern:** rapid draining. After a takeover or a scam, the account's daily spend jumps far above normal.
- **Why it matters:** a drained account is an immediate loss, and speed is the attacker's advantage.
- **Rule tested:** flag a purchase when the account's 24-hour spend exceeds both $500 and 5x its average daily spend so far, after a 7-day warm-up.
- **Measured impact:** 2,149 flags, adding 1,719 to R1–R3:
  - 61 in the prepaid pattern;
  - 12 on ring devices;
  - 1,646 across 331 ordinary accounts, with a median amount of $45, mostly at everyday merchants such as Venmo, Zelle and Chevron.
- **False positives, and why it was cut:** one large legitimate purchase keeps the 24-hour window above the threshold, so every ordinary purchase during the next day is flagged too. That costs nearly two review budgets for coverage R4 gets with 115 flags. A count-based version fails differently: the 14 heavy users, at 75–220 transactions a day, would trip it all day.

## Using the budget

We ship 714 flags, a flag rate of 0.071% on 999,965 usable rows, against about 1,000 review slots. These are the measured options for the other ~286, best value first (`python3 -m transaction_monitor.scenarios`):

| Step | Option | Adds | Running total | What it adds |
|---:|---|---:|---:|---|
| 1 | Earlier transactions on ring devices: when R1 flags a device, also flag what happened on it before | +24 | 738 | The ring's first victims |
| 2 | R4 on every qualifying purchase | +102 | 840 | The prepaid pattern (unverified) |
| 3 | R3 flags up to 3 charges per burst | +110 | 950 | More card-testing charges (12 of them labeled) |
| – | R5 velocity | +1,719 | 2,433 | Mostly ordinary purchases; over budget |

Looking back at earlier transactions only helps R1. R2 already flags every takeover transaction, and R3 already lists the 496 charges before each burst's flag in `related_txn_ids`.

Steps 1–3 would use 95% of the budget. We stop at 714 for four reasons:
- **Flagging earlier ring-device transactions is the right next step.** It is cheap and precise, and was cut only because of the timebox.
- **R4 is unverified and overfitted.**
- **Extra card-testing flags don't change the analyst's decision,** because the card is blocked at the first flag.
- **The headroom has a job.** It absorbs production false positives that this dataset barely has: new phones for R2 and new shared tablets for R1.

**What we knowingly let through:**
- the 24 ring transactions made before a device was shared;
- the prepaid pattern;
- takeovers in an account's first 7 days;
- about 1,530 purchases of $500 or more at everyday merchants on devices the account already uses. An amount-only rule would spend the whole budget on these.

## Overfitting check

We held the thresholds fixed and split the 90 days into two 45-day halves. Both halves behave the same way:
- Every labeled transaction is covered in each half (73 of 73, then 117 of 117).
- The largest run of small charges that didn't qualify is 9 charges in the first half and 8 in the second. So setting R3's threshold on the first half alone would still give 10.

This checks stability, not independence, because the rules were designed after looking at all 90 days. The details are in [TDD §6.2](TDD.md#62-time-split-check).

## How we used the labels

No rule reads the labels. We used them for two things:
- finding the two labeled patterns, card testing and takeover;
- evaluating the flags (`output/summary.json`).

**Assumptions:** a labeled transaction is fraud, but an unlabeled one is not assumed to be legitimate.

Labels mark incidents, not every transaction. Only 15% of card-testing and takeover transactions carry one, even though 53 of the 55 bursts and 26 of the 45 takeovers are labeled somewhere.

| Measure | Result |
|---|---:|
| Labeled transactions inside a flagged case | 190 / 190 |
| Labeled transactions flagged directly | 37 / 190 |
| Labeled accounts covered | 79 / 79 |
| Labeled dollars covered | $32,021.55 / $32,021.55 |
| Flags that are labeled (a floor on precision) | 37 / 714 (5.2%) |

**What the labels tell us:**
- Every fraud type that customers report is caught.
- R2 catches all 32 labeled takeovers without being tuned to them.
- Only 37 labeled transactions are flagged directly because R3 flags one charge per burst. The other labeled card-testing charges are covered through their bursts.

**What they can't tell us:**
- **Precision.** 5.2% is only a floor: of the 677 unlabeled flags, 676 sit inside patterns found in the data, and 1 is the new-phone false positive.
- **Anything about the ring,** which has no labels.
- **Fraud nobody reports,** such as the prepaid pattern.
