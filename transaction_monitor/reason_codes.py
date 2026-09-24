"""Reason codes attached to every flag.

Each code has three forms, all defined here:
- the code itself: a stable, machine-readable value (the enum value);
- a label: the short human-readable name an analyst sees at the start of every reason;
- a description: one sentence explaining what the code means.
"""
from enum import StrEnum


class ReasonCode(StrEnum):
    DEVICE_NEW_TO_MULTIPLE_ACCOUNTS = "DEVICE_NEW_TO_MULTIPLE_ACCOUNTS"
    LARGE_PURCHASE_ON_NEW_DEVICE = "LARGE_PURCHASE_ON_NEW_DEVICE"
    CARD_TESTING_BURST = "CARD_TESTING_BURST"

    @property
    def label(self) -> str:
        return LABELS[self]

    @property
    def description(self) -> str:
        return DESCRIPTIONS[self]


LABELS = {
    ReasonCode.DEVICE_NEW_TO_MULTIPLE_ACCOUNTS: "Device new to multiple accounts",
    ReasonCode.LARGE_PURCHASE_ON_NEW_DEVICE: "Large purchase on new device",
    ReasonCode.CARD_TESTING_BURST: "Card-testing burst",
}

DESCRIPTIONS = {
    ReasonCode.DEVICE_NEW_TO_MULTIPLE_ACCOUNTS:
        "A device that recently appeared on this account is also being used by other accounts "
        "that had never used it before.",
    ReasonCode.LARGE_PURCHASE_ON_NEW_DEVICE:
        "A purchase more than 3x the account's usual amount, made within 24 hours of a new device appearing.",
    ReasonCode.CARD_TESTING_BURST:
        "A rapid run of small charges at many different merchants, the usual way a stolen card is tested.",
}
