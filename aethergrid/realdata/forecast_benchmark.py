"""
Day-ahead household load forecasting on real smart-meter data.

    python -m aethergrid.realdata.forecast_benchmark --ceew-dir data/ceew

For every CEEW household and every hour, forecast the hour's electricity use
24 hours ahead (every input is at least 24 hours old, except weather, where
observed weather stands in for a day-ahead weather forecast). This uses the
same LightGBM quantile approach as AETHERGRID's forecaster (q10/q50/q90).

Time split (by calendar date, all households together):
  train  < 2020-07-01  |  validation 2020-07-01 .. 2020-09-30  |  test >= 2020-10-01
Hours without grid supply (outages) or with too few readings are excluded from
training targets and from scoring, and reported separately.
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .ceew import load_hourly
from .weather import VARIABLES, load_weather

QUANTILES = (0.1, 0.5, 0.9)
VAL_START, TEST_START = pd.Timestamp("2020-07-01"), pd.Timestamp("2020-10-01")
FEATURES = [
    "lag_24", "lag_48", "lag_168", "same_hour_mean_7d", "mean_24h_ending_24h_ago", "max_24h_ending_24h_ago",
    "hour", "weekday", "month", "is_weekend", "household_train_mean", "is_bareilly", *VARIABLES,
]


def build_panel(ceew_dir: Path, cache_dir: Path) -> tuple[pd.DataFrame, dict]:
    hourly = load_hourly(ceew_dir)
    stats = {
        "households": int(hourly["meter"].nunique()),
        "bareilly_households": int(hourly.loc[hourly.city == "Bareilly", "meter"].nunique()),
        "mathura_households": int(hourly.loc[hourly.city == "Mathura", "meter"].nunique()),
        "household_hours": int(len(hourly)),
        "complete_hours": int(hourly["complete"].sum()),
        "outage_hours": int(hourly["outage"].sum()),
        "first_hour": str(hourly["hour"].min()),
        "last_hour": str(hourly["hour"].max()),
    }
    # Regular hourly grid per meter so lags are true calendar lags.
    frames = []
    for meter, g in hourly.groupby("meter"):
        g = g.set_index("hour").asfreq("h")
        g["meter"], g["city"] = meter, g["city"].ffill().bfill()
        valid = g["complete"].fillna(False).astype(bool) & ~g["outage"].fillna(False).astype(bool)
        y = g["kwh"].where(valid)
        g["y"] = y
        g["lag_24"], g["lag_48"], g["lag_168"] = y.shift(24), y.shift(48), y.shift(168)
        g["same_hour_mean_7d"] = pd.concat([y.shift(24 * d) for d in range(1, 8)], axis=1).mean(axis=1)
        g["mean_24h_ending_24h_ago"] = y.shift(24).rolling(24, min_periods=12).mean()
        g["max_24h_ending_24h_ago"] = y.shift(24).rolling(24, min_periods=12).max()
        frames.append(g.reset_index())
    panel = pd.concat(frames, ignore_index=True)

    weather = load_weather(str(panel["hour"].min().date()), str(panel["hour"].max().date()), cache_dir)
    panel = panel.merge(weather, on=["hour", "city"], how="left")
    panel["hour_of_day"] = panel["hour"].dt.hour
    panel["weekday"] = panel["hour"].dt.dayofweek
    panel["month"] = panel["hour"].dt.month
    panel["is_weekend"] = (panel["weekday"] >= 5).astype(int)
    panel["is_bareilly"] = (panel["city"] == "Bareilly").astype(int)
    train_mean = panel[panel["hour"] < VAL_START].groupby("meter")["y"].mean()
    panel["household_train_mean"] = panel["meter"].map(train_mean)
    panel = panel.rename(columns={"hour": "timestamp", "hour_of_day": "hour"})
    panel = panel.dropna(subset=["y", "lag_168", "household_train_mean", *VARIABLES])
    return panel.reset_index(drop=True), stats


def pinball(y, q_pred, q) -> float:
    diff = y - q_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def point_metrics(y, pred) -> dict:
    err = pred - y
    return {
        "mae_kwh": round(float(np.mean(np.abs(err))), 4),
        "rmse_kwh": round(float(np.sqrt(np.mean(err**2))), 4),
        "wape_pct": round(float(100 * np.sum(np.abs(err)) / np.sum(np.abs(y))), 2),
        "bias_kwh": round(float(np.mean(err)), 4),
    }


def feeder_metrics(test: pd.DataFrame, pred_col: str) -> dict:
    """All households summed per hour: the load a distribution company schedules day-ahead."""
    agg = test.groupby("timestamp")[["y", pred_col]].sum()
    out = point_metrics(agg["y"].to_numpy(), agg[pred_col].to_numpy())
    daily = agg.groupby(agg.index.date)
    hits = [abs(int(d["y"].idxmax().hour) - int(d[pred_col].idxmax().hour)) <= 1 for _, d in daily if len(d) == 24]
    out["daily_peak_hour_within_1h_pct"] = round(100 * float(np.mean(hits)), 1)
    out["days_scored"] = len(hits)
    out["abs_error_kwh_per_day"] = round(float(np.abs(agg[pred_col] - agg["y"]).groupby(agg.index.date).sum().mean()), 2)
    return out


def _fit(train: pd.DataFrame, val: pd.DataFrame, objective: str, metric: str, alpha: float | None = None):
    evals: dict = {}
    params = dict(objective=objective, n_estimators=3000, learning_rate=0.05, num_leaves=63, min_child_samples=200,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbosity=-1, random_state=7)
    if alpha is not None:
        params["alpha"] = alpha
    model = lgb.LGBMRegressor(**params)
    model.fit(
        train[FEATURES], train["y"], eval_set=[(train[FEATURES], train["y"]), (val[FEATURES], val["y"])],
        eval_names=["train", "validation"], eval_metric=metric,
        callbacks=[lgb.early_stopping(100, verbose=False), lgb.record_evaluation(evals)],
    )
    curve = {
        "best_round": int(model.best_iteration_),
        "rounds_run": len(evals["validation"][metric]),
        "train_loss": [round(v, 6) for v in evals["train"][metric]],
        "val_loss": [round(v, 6) for v in evals["validation"][metric]],
        "loss": metric,
    }
    return model, curve


def train_quantiles(train: pd.DataFrame, val: pd.DataFrame) -> tuple[dict, dict]:
    """q10/q50/q90 quantile models plus a mean (L2) model; the mean model is what sums correctly to a feeder total."""
    models, curves = {}, {}
    for q in QUANTILES:
        models[q], curves[q] = _fit(train, val, "quantile", "quantile", alpha=q)
    models["mean"], curves["mean"] = _fit(train, val, "regression", "l2")
    return models, curves


def save_figures(curves: dict, test: pd.DataFrame, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 4, figsize=(20, 4))
    for ax, key in zip(axes, [*QUANTILES, "mean"]):
        c = curves[key]
        ax.plot(c["train_loss"], label="train")
        ax.plot(c["val_loss"], label="validation")
        ax.axvline(c["best_round"] - 1, color="grey", ls="--", label=f"kept: round {c['best_round']}")
        name = "mean model: squared error" if key == "mean" else f"q{int(key * 100)} model: pinball loss"
        ax.set(title=f"{name} per round", xlabel="boosting round", ylabel=c["loss"])
        ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "ceew_training_curves.png", dpi=130)
    plt.close(fig)

    agg = test.groupby("timestamp")[["y", "q10", "mean", "q90", "naive_7d_mean"]].sum()
    week = agg.loc[agg.index >= agg.index.min() + pd.Timedelta(days=14)].iloc[: 24 * 7]
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(week.index, week["q10"], week["q90"], alpha=0.25, label="q10-q90 band")
    ax.plot(week.index, week["y"], color="black", lw=1.2, label="actual (all households)")
    ax.plot(week.index, week["mean"], lw=1.2, label="LightGBM forecast (24 h ahead)")
    ax.plot(week.index, week["naive_7d_mean"], lw=1, ls=":", label="mean of same hour, last 7 days")
    ax.set(title="Feeder-level load, one test week", ylabel="kWh per hour")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_dir / "ceew_test_week.png", dpi=130)
    plt.close(fig)


def run(ceew_dir: Path, cache_dir: Path, reports_dir: Path) -> dict:
    t0 = time.time()
    panel, stats = build_panel(ceew_dir, cache_dir)
    train = panel[panel["timestamp"] < VAL_START]
    val = panel[(panel["timestamp"] >= VAL_START) & (panel["timestamp"] < TEST_START)]
    test = panel[panel["timestamp"] >= TEST_START].copy()
    # Score every method on the same rows: those where all naive baselines are defined.
    n_test_all = len(test)
    test = test.dropna(subset=["lag_24", "lag_168", "same_hour_mean_7d"]).copy()

    models, curves = train_quantiles(train, val)
    for q in QUANTILES:
        test[f"q{int(q * 100)}"] = models[q].predict(test[FEATURES], num_iteration=models[q].best_iteration_)
    test["mean"] = np.clip(models["mean"].predict(test[FEATURES], num_iteration=models["mean"].best_iteration_), 0, None)
    q = np.sort(test[["q10", "q50", "q90"]].to_numpy(), axis=1)  # no quantile crossing
    test["q10"], test["q50"], test["q90"] = q[:, 0], q[:, 1], q[:, 2]
    test["naive_24"], test["naive_168"], test["naive_7d_mean"] = test["lag_24"], test["lag_168"], test["same_hour_mean_7d"]

    y = test["y"].to_numpy()
    methods = [("lightgbm_mean", "mean"), ("lightgbm_q50", "q50"), ("same_hour_yesterday", "naive_24"),
               ("same_hour_last_week", "naive_168"), ("mean_of_same_hour_last_7_days", "naive_7d_mean")]
    household = {name: point_metrics(y, test[col].to_numpy()) for name, col in methods}
    household["lightgbm_q50"]["pinball"] = {f"q{int(qq * 100)}": round(pinball(y, test[f'q{int(qq * 100)}'], qq), 5)
                                            for qq in QUANTILES}
    inside = (y >= test["q10"]) & (y <= test["q90"])
    household["lightgbm_q50"]["q10_q90_coverage_pct"] = round(100 * float(inside.mean()), 2)
    household["lightgbm_q50"]["q10_q90_mean_width_kwh"] = round(float((test["q90"] - test["q10"]).mean()), 4)

    feeder = {name: feeder_metrics(test, col) for name, col in methods}
    best_naive = min(("same_hour_yesterday", "same_hour_last_week", "mean_of_same_hour_last_7_days"),
                     key=lambda k: feeder[k]["abs_error_kwh_per_day"])
    reduction = 1 - feeder["lightgbm_mean"]["abs_error_kwh_per_day"] / feeder[best_naive]["abs_error_kwh_per_day"]
    naive_names = ("same_hour_yesterday", "same_hour_last_week", "mean_of_same_hour_last_7_days")
    hh_reduction = 1 - household["lightgbm_mean"]["mae_kwh"] / min(household[k]["mae_kwh"] for k in naive_names)

    report = {
        "data": {
            "dataset": "CEEW high-frequency smart meter data, Mathura and Bareilly (doi:10.7910/DVN/GOCHJH, CC0)",
            "weather": "Open-Meteo historical archive (CC BY 4.0), hourly, Asia/Kolkata",
            **stats,
            "rows_used": int(len(panel)),
            "test_rows_with_all_baselines": int(len(test)),
            "test_rows_before_baseline_filter": int(n_test_all),
            "split": {k: {"rows": int(len(v)), "from": str(v["timestamp"].min()), "to": str(v["timestamp"].max())}
                      for k, v in {"train": train, "validation": val, "test": test}.items()},
        },
        "features": FEATURES,
        "training": {str(k): {kk: vv for kk, vv in c.items() if not kk.endswith("_loss")} for k, c in curves.items()},
        "test_household_hourly": household,
        "test_feeder_hourly": feeder,
        "business": {
            "best_naive_method": best_naive,
            "day_ahead_scheduling_error_kwh_per_day": feeder["lightgbm_mean"]["abs_error_kwh_per_day"],
            "naive_scheduling_error_kwh_per_day": feeder[best_naive]["abs_error_kwh_per_day"],
            "scheduling_error_reduction_pct": round(100 * reduction, 1),
            "household_mae_reduction_vs_best_naive_pct": round(100 * hh_reduction, 1),
            "peak_hour_identified_within_1h_pct": feeder["lightgbm_mean"]["daily_peak_hour_within_1h_pct"],
        },
        "environment": {"python": platform.python_version(), "lightgbm": lgb.__version__},
    }
    save_figures(curves, test, reports_dir / "figures")
    report["runtime_seconds"] = round(time.time() - t0, 1)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "ceew_forecast_metrics.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Day-ahead load forecasting on CEEW smart-meter data")
    parser.add_argument("--ceew-dir", type=Path, default=Path("data/ceew"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/weather"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()
    report = run(args.ceew_dir, args.cache_dir, args.reports_dir)
    print(json.dumps({k: report[k] for k in ("data", "test_household_hourly", "test_feeder_hourly", "business")},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
