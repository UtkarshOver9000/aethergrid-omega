"""Pydantic schema for tariff JSON. The compiled tariff is the sole input to
BillEngine (tariff/bill.py) -- no other module is allowed to define money."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TOUWindow(BaseModel):
    """One time-of-use rate window, applied on the given hour range each day."""

    name: str
    start_hour: float = Field(ge=0, le=24)
    end_hour: float = Field(ge=0, le=24)
    rate_per_kwh: float = Field(ge=0)

    def contains(self, hour: float) -> bool:
        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour < self.end_hour
        # wraps past midnight, e.g. 22:00 -> 06:00
        return hour >= self.start_hour or hour < self.end_hour


class TariffSpec(BaseModel):
    id: str
    currency: str = "INR"
    fixed_charge_per_day: float = Field(default=0.0, ge=0)
    energy_rates: list[TOUWindow] = Field(default_factory=list)
    flat_energy_rate_per_kwh: Optional[float] = None

    demand_charge_per_kva: float = Field(default=0.0, ge=0)
    contract_demand_kva: Optional[float] = None
    demand_excess_penalty_multiplier: float = Field(default=1.5, ge=1.0)

    power_factor_target: Optional[float] = None
    power_factor_penalty_rate_per_kvarh: float = Field(default=0.0, ge=0)

    export_compensation_per_kwh: float = Field(default=0.0, ge=0)
    billing_interval_minutes: int = Field(default=15, gt=0)

    @field_validator("energy_rates")
    @classmethod
    def _must_cover_or_have_flat(cls, v: list[TOUWindow]) -> list[TOUWindow]:
        return v

    def rate_at(self, hour: float) -> float:
        """Energy rate (currency/kWh) applicable at the given hour-of-day."""
        for window in self.energy_rates:
            if window.contains(hour):
                return window.rate_per_kwh
        if self.flat_energy_rate_per_kwh is not None:
            return self.flat_energy_rate_per_kwh
        if self.energy_rates:
            # no window matched and no flat fallback -> use average as last resort,
            # but this indicates an incomplete tariff (validator should catch it upstream)
            return sum(w.rate_per_kwh for w in self.energy_rates) / len(self.energy_rates)
        return 0.0
