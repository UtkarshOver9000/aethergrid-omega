"""Plotly figure builders for the dashboard. Every figure is built directly
from a SimulationSeries / metrics dict that already came out of the real
pipeline -- no chart here invents a data point."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

COLOR_IMPORT = "#e74c3c"
COLOR_SOLAR = "#f2c94c"
COLOR_BATTERY = "#2d9cdb"
COLOR_HVAC = "#9b59b6"
COLOR_CEILING = "#c0392b"
COLOR_COMFORT_BAND = "rgba(39, 174, 96, 0.15)"
COLOR_TEMP = "#27ae60"


def live_grid_figure(df: pd.DataFrame, demand_ceiling_kw: float | None = None, title: str = "Live Grid") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["import_kw"], name="Grid import (kW)",
                              line=dict(color=COLOR_IMPORT, width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=df["solar_kw"], name="Solar (kW)",
                              line=dict(color=COLOR_SOLAR, width=1.5), fill="tozeroy", fillcolor="rgba(242,201,76,0.15)"))
    fig.add_trace(go.Scatter(x=df.index, y=df["hvac_kw"], name="HVAC (kW)",
                              line=dict(color=COLOR_HVAC, width=1.2, dash="dot")))
    fig.add_trace(go.Scatter(x=df.index, y=df["battery_soc_kwh"], name="Battery SOC (kWh)",
                              line=dict(color=COLOR_BATTERY, width=1.2), yaxis="y2"))
    if demand_ceiling_kw:
        fig.add_hline(y=demand_ceiling_kw, line_dash="dash", line_color=COLOR_CEILING,
                       annotation_text="Demand ceiling", annotation_position="top left")
    fig.update_layout(
        title=title, height=380, margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(title=None), yaxis=dict(title="kW"),
        yaxis2=dict(title="Battery SOC (kWh)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        template="plotly_white",
    )
    return fig


def comfort_band_figure(df: pd.DataFrame, t_min: float, t_max: float, hard_min: float, hard_max: float) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=t_min, y1=t_max, fillcolor=COLOR_COMFORT_BAND, line_width=0, annotation_text="comfort band")
    fig.add_hline(y=hard_min, line_dash="dot", line_color="#c0392b", annotation_text="hard min")
    fig.add_hline(y=hard_max, line_dash="dot", line_color="#c0392b", annotation_text="hard max")
    fig.add_trace(go.Scatter(x=df.index, y=df["indoor_temp_c"], name="Indoor temp (C)", line=dict(color=COLOR_TEMP, width=2)))
    violations = df[df["comfort_soft_violation"]]
    if len(violations):
        fig.add_trace(go.Scatter(x=violations.index, y=violations["indoor_temp_c"], mode="markers",
                                  name="Soft violation", marker=dict(color="orange", size=5)))
    hard_violations = df[df["comfort_hard_violation"]]
    if len(hard_violations):
        fig.add_trace(go.Scatter(x=hard_violations.index, y=hard_violations["indoor_temp_c"], mode="markers",
                                  name="HARD violation", marker=dict(color="red", size=8, symbol="x")))
    fig.update_layout(title="Comfort", height=300, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white")
    return fig


def results_bar_figure(rows: list[dict], metric: str, label: str) -> go.Figure:
    controllers = [r.get("controller", "?") for r in rows]
    values = [r.get(metric, 0) for r in rows]
    fig = go.Figure(go.Bar(x=controllers, y=values, marker_color="#2d9cdb"))
    fig.update_layout(title=label, height=320, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white")
    return fig


def robustness_bar_figure(scenarios: dict) -> go.Figure:
    names = list(scenarios.keys())
    scores = [scenarios[n]["robustness_score"] for n in names]
    colors = ["#27ae60" if s >= 0.7 else ("#f2c94c" if s >= 0.4 else "#eb5757") for s in scores]
    fig = go.Figure(go.Bar(x=names, y=scores, marker_color=colors))
    fig.update_layout(title="Robustness score by stress scenario", yaxis_range=[0, 1],
                       height=320, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white")
    return fig


def forecast_calibration_figure(calibration_by_horizon: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="perfect calibration",
                              line=dict(dash="dash", color="gray")))
    for h, rep in calibration_by_horizon.items():
        nominal = [c["nominal_coverage"] for c in rep["per_quantile"]]
        empirical = [c["empirical_coverage"] for c in rep["per_quantile"]]
        fig.add_trace(go.Scatter(x=nominal, y=empirical, mode="markers+lines", name=f"horizon={h} steps"))
    fig.update_layout(title="Forecast reliability diagram (nominal vs empirical coverage)",
                       xaxis_title="Nominal quantile", yaxis_title="Empirical coverage",
                       height=350, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white")
    return fig
