"""Transformer hierarchy config (house -> society -> transformer kVA ->
colony -> grid). State thresholds are configurable fractions of rated
capacity; defaults follow common utility practice (headroom warning well
before an actual breach)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

TransformerState = Literal["NORMAL", "WARNING", "CRITICAL", "BREACH", "TRIPPED"]


class TransformerSpec(BaseModel):
    rating_kva: float = 250.0
    assumed_power_factor: float = 0.9
    warning_frac: float = 0.70
    critical_frac: float = 0.90
    breach_frac: float = 1.00
    tripped_frac: float = 1.15

    def state_for(self, kva: float) -> TransformerState:
        frac = kva / self.rating_kva if self.rating_kva > 0 else 0.0
        if frac >= self.tripped_frac:
            return "TRIPPED"
        if frac >= self.breach_frac:
            return "BREACH"
        if frac >= self.critical_frac:
            return "CRITICAL"
        if frac >= self.warning_frac:
            return "WARNING"
        return "NORMAL"
