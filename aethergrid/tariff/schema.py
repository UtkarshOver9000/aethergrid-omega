"""Re-exports the Pydantic tariff schema for the tariff/ subpackage so
compiler.py, validator.py and bill.py have a single stable import path."""
from __future__ import annotations

from aethergrid.schemas.tariff import TariffSpec, TOUWindow

CompiledTariff = TariffSpec  # a "compiled" tariff is just a validated TariffSpec

__all__ = ["TariffSpec", "TOUWindow", "CompiledTariff"]
