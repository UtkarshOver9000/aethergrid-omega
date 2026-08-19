"""Schema validation gate for tariff JSON. Every tariff -- whether hand
authored or (in a future extension) extracted by an LLM from a document --
MUST pass through here before it can reach BillEngine (PART T: "The LLM is
NEVER the financial authority"). This module has no dependency on any LLM;
it is pure schema + sanity-rule validation."""
from __future__ import annotations

from pydantic import ValidationError

from aethergrid.tariff.schema import TariffSpec


class TariffValidationError(Exception):
    pass


def validate_tariff_dict(data: dict) -> TariffSpec:
    try:
        spec = TariffSpec.model_validate(data)
    except ValidationError as e:
        raise TariffValidationError(f"Tariff JSON failed schema validation: {e}") from e

    if not spec.energy_rates and spec.flat_energy_rate_per_kwh is None:
        raise TariffValidationError(
            "Tariff must define either energy_rates (TOU windows) or flat_energy_rate_per_kwh."
        )
    if spec.contract_demand_kva is not None and spec.contract_demand_kva <= 0:
        raise TariffValidationError("contract_demand_kva must be positive if set.")
    total_hours = sum(
        (w.end_hour - w.start_hour) if w.end_hour >= w.start_hour else (24 - w.start_hour + w.end_hour)
        for w in spec.energy_rates
    )
    if spec.energy_rates and total_hours < 23.9:
        # Not a hard error -- gaps fall back to flat_energy_rate_per_kwh / average,
        # but this is exactly the kind of silent-fallback the system must surface.
        spec_gap_hours = 24 - total_hours
        if spec.flat_energy_rate_per_kwh is None:
            raise TariffValidationError(
                f"TOU windows leave {spec_gap_hours:.2f}h/day uncovered and no "
                "flat_energy_rate_per_kwh fallback is set."
            )
    return spec
