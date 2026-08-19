"""Compiles a validated tariff into fast lookup helpers used by BillEngine
and the optimizer's cost objective."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aethergrid.tariff.schema import TariffSpec
from aethergrid.tariff.validator import validate_tariff_dict


def compile_tariff(data: dict) -> TariffSpec:
    return validate_tariff_dict(data)


def rate_array_for_index(tariff: TariffSpec, index: pd.DatetimeIndex) -> np.ndarray:
    """Vectorized per-timestep energy rate (currency/kWh) for a datetime index."""
    hours = index.hour.values + index.minute.values / 60.0
    return np.array([tariff.rate_at(h) for h in hours])
