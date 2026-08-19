"""Calibration as a first-class module (PART H). Nothing here is asserted;
every number is computed against held-out realized values."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

UNCALIBRATED_THRESHOLD = 0.10  # |empirical coverage - nominal| beyond this => flagged


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1) * diff)))


def empirical_coverage(y_true: np.ndarray, y_pred_q: np.ndarray) -> float:
    """Fraction of true values at or below the predicted quantile level."""
    return float(np.mean(y_true <= y_pred_q))


@dataclass
class QuantileCalibration:
    quantile: float
    pinball: float
    nominal_coverage: float
    empirical_coverage: float
    calibration_error: float
    status: str  # "CALIBRATED" | "UNCALIBRATED"


@dataclass
class CalibrationReport:
    target: str
    horizon_steps: int
    per_quantile: list[QuantileCalibration]
    mean_interval_width_90: float  # width of [q05, q95]
    overall_status: str

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "horizon_steps": self.horizon_steps,
            "overall_status": self.overall_status,
            "mean_interval_width_90": round(self.mean_interval_width_90, 4),
            "per_quantile": [
                {
                    "quantile": c.quantile, "pinball_loss": round(c.pinball, 4),
                    "nominal_coverage": c.nominal_coverage,
                    "empirical_coverage": round(c.empirical_coverage, 4),
                    "calibration_error": round(c.calibration_error, 4),
                    "status": c.status,
                }
                for c in self.per_quantile
            ],
        }


def build_calibration_report(
    y_true: pd.Series, quantile_preds: pd.DataFrame, target: str, horizon_steps: int,
) -> CalibrationReport:
    y = y_true.values
    per_q = []
    for q in quantile_preds.columns:
        yp = quantile_preds[q].values
        pin = pinball_loss(y, yp, float(q))
        emp = empirical_coverage(y, yp)
        err = abs(emp - float(q))
        status = "UNCALIBRATED" if err > UNCALIBRATED_THRESHOLD else "CALIBRATED"
        per_q.append(QuantileCalibration(float(q), pin, float(q), emp, err, status))

    width = float(np.mean(quantile_preds[0.95].values - quantile_preds[0.05].values)) if (
        0.95 in quantile_preds.columns and 0.05 in quantile_preds.columns
    ) else float("nan")
    overall = "UNCALIBRATED" if any(c.status == "UNCALIBRATED" for c in per_q) else "CALIBRATED"
    return CalibrationReport(target, horizon_steps, per_q, width, overall)


def conformal_correction(y_cal: np.ndarray, pred_cal: np.ndarray, alpha: float) -> float:
    """Split-conformal additive correction for a single quantile level so
    that the corrected quantile achieves (approximately) its nominal
    coverage on held-out calibration data. Returns an additive offset."""
    residuals = y_cal - pred_cal
    if alpha <= 0.5:
        return float(np.quantile(residuals, alpha))
    return float(np.quantile(residuals, alpha))


def apply_conformal(quantile_preds: pd.DataFrame, corrections: dict[float, float]) -> pd.DataFrame:
    out = quantile_preds.copy()
    for q, corr in corrections.items():
        if q in out.columns:
            out[q] = out[q] + corr
    arr = np.sort(out.values, axis=1)
    return pd.DataFrame(arr, index=out.index, columns=out.columns)
