"""CLI entry point: `python -m aethergrid.evaluate --all`.

Runs the results table (baselines + oracle) on the society world, a
robustness suite on one representative building, and a forecast
calibration report -- then writes all three mandatory reports (PART AJ) to
docs/generated/. This is intentionally a REPRESENTATIVE slice, not the
full exhaustive matrix (every controller x every stress scenario x every
world would take hours of wall-clock time re-solving LPs); the same
functions (evaluation/experiments.py, evaluation/robustness.py) can be
called directly for a larger sweep -- see docs/EXPERIMENTS.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from aethergrid.core.world import World
from aethergrid.evaluation.ablation import run_ablation
from aethergrid.evaluation.experiments import get_forecasters, run_experiment
from aethergrid.evaluation.reports import (
    control_report, forecast_report, results_row_from_experiment, robustness_report, write_reports,
)
from aethergrid.evaluation.robustness import run_robustness_suite
from aethergrid.evaluation.baselines import quantile_mpc_policy
from aethergrid.schemas.experiment import ExperimentSpec, ObjectiveWeights

OUT_DIR = "docs/generated"
DEFAULT_CONTROLLERS = ["no_control", "rule_based", "mean_mpc", "quantile_mpc", "oracle"]


def run_all(controllers: list[str], world_path: str = "aethergrid/configs/worlds/society.json",
            run_robustness: bool = True, run_ablation_flag: bool = True) -> None:
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    rows = []
    oracle_bill = None
    print(f"=== CONTROL REPORT: running {controllers} on {world_path} ===")
    for controller in controllers:
        spec = ExperimentSpec(name="control_report", world_config=world_path, controller=controller, seed=42)
        print(f"  running controller={controller} ...")
        result = run_experiment(spec, output_dir="aethergrid/runs")
        result["controller"] = controller
        if controller == "oracle":
            oracle_bill = result["aggregate"]["total_bill_inr"]
        rows.append(result)

    table_rows = [results_row_from_experiment(r, oracle_bill) for r in rows]
    for row in table_rows:
        print(f"  {row}")
    creport = control_report(table_rows, scenario_label="NORMAL")

    if run_robustness or run_ablation_flag:
        world = World.load(world_path)
        building = world.buildings[next(iter(world.buildings))]
        load_pf, solar_pf = get_forecasters(building.archetype.type, seed=42)

    rreport = None
    if run_robustness:
        print(f"\n=== ROBUSTNESS REPORT: stress-testing quantile_mpc on {building.id} ===")
        results = run_robustness_suite(building, world, quantile_mpc_policy, ObjectiveWeights(), 0.71, load_pf, solar_pf)
        for r in results:
            print(f"  {r.scenario:16s} robustness_score={r.robustness_score:.3f}  "
                  f"cost_degradation={r.cost_degradation_frac:+.2%}  critical_failure={r.critical_load_failure_frac:.2%}")
        rreport = robustness_report({r.scenario: r.as_dict() for r in results})

    if run_ablation_flag:
        print(f"\n=== ABLATION: FULL system vs FULL-minus-X on {building.id} ===")
        ablation_results = run_ablation(building, world, load_pf, solar_pf)
        for name, m in ablation_results.items():
            print(f"  {name:32s} bill=Rs.{m['total_bill_inr']:>10,.0f}  "
                  f"delta_vs_full={m['delta_bill_vs_full_pct']:+.2f}%")
        (Path(OUT_DIR) / "ablation_report.json").write_text(json.dumps(ablation_results, indent=2))

    print(f"\n=== FORECAST REPORT: fitting quantile ForecastEngine + calibration for a few building types ===")
    from aethergrid.forecasting.predict import ForecastEngine, build_training_building
    calibration_summaries = {}
    for bt in ["office", "residential", "hospital"]:
        _, train_df = build_training_building(bt, seed=42, n_days=45, dt_minutes=15)
        engine = ForecastEngine("base_load_kw", steps_per_day=96).fit(train_df)
        summary = engine.calibration_summary()
        calibration_summaries[bt] = summary
        overall = {h: r["overall_status"] for h, r in summary["by_horizon"].items()}
        print(f"  {bt:12s} backend={summary['backend']:10s} calibration_by_horizon={overall}")
    freport = forecast_report(calibration_summaries)

    write_reports(OUT_DIR, freport, creport, rreport)
    print(f"\nReports written to {OUT_DIR}/")


def main() -> None:
    parser = argparse.ArgumentParser(description="AETHERGRID Omega evaluation runner")
    parser.add_argument("--all", action="store_true", help="run the representative control+robustness+ablation slice")
    parser.add_argument("--controllers", nargs="*", default=DEFAULT_CONTROLLERS)
    parser.add_argument("--world", default="aethergrid/configs/worlds/society.json")
    parser.add_argument("--no-robustness", action="store_true")
    parser.add_argument("--no-ablation", action="store_true")
    args = parser.parse_args()

    if args.all or args.controllers:
        run_all(args.controllers, args.world, run_robustness=not args.no_robustness, run_ablation_flag=not args.no_ablation)


if __name__ == "__main__":
    main()
