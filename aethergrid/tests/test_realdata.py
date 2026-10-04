"""Tests for the real-data (CEEW smart meter) forecasting benchmark."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aethergrid.realdata import ceew
from aethergrid.realdata.forecast_benchmark import feeder_metrics, pinball, point_metrics

SAMPLE = Path(__file__).parent / "ceew_sample_bareilly_2020-07-01.csv"


def test_hourly_aggregation_of_real_ceew_sample(tmp_path, monkeypatch):
    # Point the loader at a folder holding only the 2-day, 3-household real sample.
    (tmp_path / "sample.csv").write_bytes(SAMPLE.read_bytes())
    monkeypatch.setattr(ceew, "FILES", {0: "sample.csv"})
    hourly = ceew.load_hourly(tmp_path)
    assert set(hourly["meter"]) == {"BR26", "BR28", "BR29"}
    assert len(hourly) == 3 * 48
    assert hourly["complete"].all() and not hourly["outage"].any()
    raw = pd.read_csv(SAMPLE)
    assert hourly["kwh"].sum() == pytest.approx(raw["t_kWh"].sum())
    assert (hourly["city"] == "Bareilly").all()


def test_point_metrics_known_values():
    m = point_metrics(np.array([1.0, 2.0, 3.0]), np.array([1.5, 2.0, 2.0]))
    assert m["mae_kwh"] == pytest.approx(0.5)
    assert m["wape_pct"] == pytest.approx(100 * 1.5 / 6, abs=0.01)
    assert m["bias_kwh"] == pytest.approx(-1 / 6, abs=1e-4)


def test_pinball_loss():
    y = np.array([1.0, 1.0])
    assert pinball(y, np.array([0.0, 0.0]), 0.9) == pytest.approx(0.9)
    assert pinball(y, np.array([2.0, 2.0]), 0.9) == pytest.approx(0.1)


def test_feeder_metrics_sum_households_per_hour():
    hours = pd.date_range("2021-01-01", periods=48, freq="h")
    df = pd.DataFrame({
        "timestamp": np.r_[hours, hours],
        "y": np.r_[np.ones(48), np.ones(48)],
        "pred": np.r_[np.ones(48), np.full(48, 2.0)],
    })
    m = feeder_metrics(df, "pred")
    assert m["mae_kwh"] == pytest.approx(1.0)  # feeder actual 2, forecast 3 every hour
    assert m["abs_error_kwh_per_day"] == pytest.approx(24.0)
    assert m["days_scored"] == 2
