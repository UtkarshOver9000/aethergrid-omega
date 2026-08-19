"""Grid interconnection constraints: capacity limit and outage (resilience
mode, PART Z: `grid import = 0` during outage)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GridResult:
    import_kw: float
    export_kw: float
    unserved_kw: float  # load that could not be met because of outage/capacity


def apply_grid_constraints(
    requested_import_kw: float, requested_export_kw: float,
    grid_capacity_kw: float | None, outage: bool,
) -> GridResult:
    if outage:
        # No grid import/export at all; any requested import becomes unserved load.
        return GridResult(0.0, 0.0, requested_import_kw)
    if grid_capacity_kw is not None and requested_import_kw > grid_capacity_kw:
        unserved = requested_import_kw - grid_capacity_kw
        return GridResult(grid_capacity_kw, requested_export_kw, unserved)
    return GridResult(requested_import_kw, requested_export_kw, 0.0)
