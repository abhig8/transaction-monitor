"""The monitoring rules, one module per rule (RULES.md).

Every rule decides using only the flagged transaction and what came before it
(TDD.md D4) and returns flag rows built with flags.make_flags.

Performance note: the work over all 1M rows is vectorized (one sort, then
group-bys and cumulative sums). Python loops only run over the few hundred
candidates a rule has already narrowed down, to build readable reason text.
"""
from .card_testing_burst import card_testing_burst
from .device_history import find_device_pairings
from .new_device_spend_spike import new_device_spend_spike
from .shared_device_ring import shared_device_ring

__all__ = ["card_testing_burst", "find_device_pairings", "new_device_spend_spike", "shared_device_ring"]
