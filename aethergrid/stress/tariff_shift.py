"""TARIFF_CHANGE: swaps in a different (already schema-validated) tariff
JSON from the event's start time onward. Demonstrates PART T's claim --
"the controller must not need to change" -- by feeding a different
TariffSpec into the exact same MPC/BillEngine code path (TEST 8)."""
from __future__ import annotations

import json

from aethergrid.schemas.event import EventSpec
from aethergrid.tariff.compiler import compile_tariff
from aethergrid.tariff.schema import TariffSpec
from aethergrid.stress._window import extra


def load_shifted_tariff(event: EventSpec, base_dir: str = "aethergrid/configs/tariffs") -> TariffSpec:
    assert event.type == "tariff_change"
    tariff_id = extra(event, "new_tariff_id", "tariff_shift")
    with open(f"{base_dir}/{tariff_id}.json", "r", encoding="utf-8") as f:
        return compile_tariff(json.load(f))
