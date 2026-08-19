"""BillEngine -- the deterministic financial ground truth (RULE 2). No ML,
RL or LLM output ever reaches this file except as an input timeseries of
kW flows. Every currency figure shown anywhere in the system must trace
back to `BillEngine.compute`."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from aethergrid.tariff.compiler import rate_array_for_index
from aethergrid.tariff.schema import TariffSpec


@dataclass
class BillBreakdown:
    energy_charge: float
    demand_charge: float
    demand_excess_penalty: float
    power_factor_penalty: float
    fixed_charge: float
    export_credit: float
    total: float
    peak_demand_kw: float
    contract_demand_kva: float | None
    contract_demand_exceeded: bool
    billing_days: float
    assumed_power_factor: float | None = None

    def as_dict(self) -> dict:
        return {
            "energy_charge": round(self.energy_charge, 4),
            "demand_charge": round(self.demand_charge, 4),
            "demand_excess_penalty": round(self.demand_excess_penalty, 4),
            "power_factor_penalty": round(self.power_factor_penalty, 4),
            "fixed_charge": round(self.fixed_charge, 4),
            "export_credit": round(self.export_credit, 4),
            "total": round(self.total, 4),
            "peak_demand_kw": round(self.peak_demand_kw, 4),
            "contract_demand_kva": self.contract_demand_kva,
            "contract_demand_exceeded": self.contract_demand_exceeded,
            "billing_days": round(self.billing_days, 4),
        }


class BillEngine:
    """Deterministic. `compute` is a pure function of (flows, tariff)."""

    @staticmethod
    def compute(
        index: pd.DatetimeIndex,
        import_kw: np.ndarray,
        export_kw: np.ndarray,
        dt_hours: float,
        tariff: TariffSpec,
        assumed_power_factor: float | None = 0.95,
    ) -> BillBreakdown:
        import_kw = np.asarray(import_kw, dtype=float)
        export_kw = np.asarray(export_kw, dtype=float)
        assert len(import_kw) == len(index) == len(export_kw), "flow arrays must match index length"

        rates = rate_array_for_index(tariff, index)
        import_kwh = import_kw * dt_hours
        export_kwh = export_kw * dt_hours

        energy_charge = float(np.sum(import_kwh * rates))
        export_credit = float(np.sum(export_kwh) * tariff.export_compensation_per_kwh)

        peak_demand_kw = float(np.max(import_kw)) if len(import_kw) else 0.0
        # kVA approximation from kW via assumed power factor (no reactive-power model
        # exists in this simulator -- explicitly labeled as an assumption).
        peak_demand_kva = peak_demand_kw / assumed_power_factor if assumed_power_factor else peak_demand_kw
        demand_charge = peak_demand_kva * tariff.demand_charge_per_kva

        demand_excess_penalty = 0.0
        contract_exceeded = False
        if tariff.contract_demand_kva is not None and peak_demand_kva > tariff.contract_demand_kva:
            contract_exceeded = True
            excess_kva = peak_demand_kva - tariff.contract_demand_kva
            demand_excess_penalty = excess_kva * tariff.demand_charge_per_kva * (
                tariff.demand_excess_penalty_multiplier - 1.0
            )

        pf_penalty = 0.0
        if tariff.power_factor_target is not None and assumed_power_factor is not None:
            if assumed_power_factor < tariff.power_factor_target:
                # reactive energy proxy: kWh * tan(acos(pf)) integrated, using assumed constant PF
                phi = np.arccos(np.clip(assumed_power_factor, 1e-3, 1.0))
                kvarh = float(np.sum(import_kwh)) * np.tan(phi)
                pf_penalty = kvarh * tariff.power_factor_penalty_rate_per_kvarh

        billing_days = (index[-1] - index[0]).total_seconds() / 86400.0 + dt_hours / 24.0
        fixed_charge = billing_days * tariff.fixed_charge_per_day

        total = energy_charge + demand_charge + demand_excess_penalty + pf_penalty + fixed_charge - export_credit

        return BillBreakdown(
            energy_charge=energy_charge, demand_charge=demand_charge,
            demand_excess_penalty=demand_excess_penalty, power_factor_penalty=pf_penalty,
            fixed_charge=fixed_charge, export_credit=export_credit, total=total,
            peak_demand_kw=peak_demand_kw, contract_demand_kva=tariff.contract_demand_kva,
            contract_demand_exceeded=contract_exceeded, billing_days=billing_days,
            assumed_power_factor=assumed_power_factor,
        )

    @staticmethod
    def marginal_energy_rate(timestamp: pd.Timestamp, tariff: TariffSpec) -> float:
        hour = timestamp.hour + timestamp.minute / 60.0
        return tariff.rate_at(hour)
