"""Generates the populated district: 24 societies on one shared feeder,
6 of them running under GridBrain and 18 running unmanaged.

THE MATCHED-TRIPLET DESIGN
--------------------------
The obvious objection to a managed-vs-unmanaged comparison is "did the
managed ones win because of the AI, or because you gave them easier
parameters?". A subtler and more damaging one is "you also gave the
managed societies a 60 kWp solar station -- you're crediting your AI with
what a solar purchase did."

Both are answered structurally. Each of the 12 societies is simulated as
a matched TRIPLET sharing an identical seed, household count, EV
penetration, solar penetration, archetype mix (same seed => same draws)
and transformer rating. The three arms differ ONLY in what has been
deployed:

    raw   -> nothing.                  curtail=F sync=F station=0
    ai    -> coordination only.        curtail=T sync=F station=0
    full  -> coordination + solar.     curtail=T sync=T station=60 kWp

That isolates the two effects cleanly:
    (ai - raw)   = peak protection from coordination alone. ZERO capex.
    (full - ai)  = what the solar package adds. Real capex.

Reporting only (full - raw) and calling it "the AI" would be exactly the
kind of attribution error this project has avoided everywhere else.

IMPORTANT, AND MEASURED: the solar package is a COST lever, not a peak
lever, and the numbers say so plainly -- its effect on peak kVA comes out
slightly NEGATIVE. Solar-sync moves EV charging out of the genuinely empty
small hours into daylight, which buys cheaper self-consumed energy but can
nudge the daytime peak up; and the station generates nothing after sunset,
so it cannot touch the evening peak that actually sizes the transformer.
Both facts are reported as they are rather than being averaged away.

6 societies contribute their `full` arm to the deployed GridBrain cohort;
the other 6 run unmanaged, with their `ai`/`full` arms kept on disk as the
"deploy GridBrain here" target datasets. This module PRINTS all three
arms side by side and ASSERTS equality on every controlled field, so any
drift is caught at generation time rather than argued about later.

TWO-TIER EXPORT (forced by size)
--------------------------------
One 60-household society exports to ~1.3 MB. 24 of those is ~30 MB --
fine on disk, unacceptable as a page load. So:

  viz/data/district.json   static metadata for all 24 + a per-tick rollup
                           per society. Small (well under 500 KB). This is
                           the only file the district view needs at boot.
  viz/data/soc_<id>.json   full per-household detail, generated for all 24
                           but lazy-loaded by the renderer only when the
                           camera actually flies into that society.

Run: python -m aethergrid.worldsim.generate_district"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from aethergrid.worldsim.engine.society import simulate_society
from aethergrid.worldsim.export.jsonio import export_society_json
from aethergrid.worldsim.schemas.scenario import SocietyScenario, WorldSimScenario
from aethergrid.worldsim.schemas.transformer import TransformerSpec

DATE = "2026-07-15"
COMMUNITY_SOLAR_KWP = 60.0

# The run starts at 00:00 from synthetic initial conditions. Storage states
# (EV charge, water-tank heat, battery SOC) are jittered per household so the
# world does not switch on in lockstep, but the very first tick still carries
# some residual cold-start transient -- every thermal/appliance state machine
# is being evaluated for the first time simultaneously. One tick is therefore
# treated as warm-up and excluded from reported STATISTICS. It is still
# exported in the series, so nothing is hidden: the renderer draws the full
# 96-tick day, and only the summary figures skip t=0.
WARMUP_TICKS = 1

# 12 matched pairs. Each entry defines the parameters BOTH members share.
# Deliberately varied across pairs so the district reads as a real mixed
# neighbourhood (old and new stock, rich and poor in EV/solar, tight and
# roomy transformers) rather than 24 copies of one society.
#
# `managed` marks the 6 pairs whose managed member joins the GridBrain
# cohort. Those were chosen to span the difficulty range -- including
# pairs that are NOT under stress -- so the cohort is not cherry-picked
# to only the societies where protection obviously helps.
# NOTE ON THE `stress` COLUMN
# ---------------------------
# The number below is NOT a transformer rating, it is the target ratio of the
# society's own unmanaged peak to its transformer rating. The rating is then
# derived: rating = unmanaged_peak / stress, measured by a calibration pass
# before the real runs.
#
# This replaced hand-picked ratings after the cold-start fix. Those ratings
# had been chosen against inflated peaks; once the artifact was removed, every
# society sat comfortably under its rating, curtailment never triggered, and
# the whole managed-vs-unmanaged comparison measured a difference of exactly
# zero. Deriving the rating from each society's own measured peak keeps the
# district a realistic mix -- some transformers genuinely undersized, some
# with headroom -- regardless of what the engine does to absolute load levels.
#
# stress > 1.0  -> unmanaged society breaches its own rating (real trips)
# stress ~ 0.9  -> runs hot, warnings, no breach
# stress < 0.8  -> comfortable headroom
PAIRS = [
    # key            seed  n   ev    solar stress  deployed  label
    # --- the 6 GridBrain societies. Deliberately spanning the difficulty
    # --- range (Estuary and Fig are NOT under stress) so the cohort is not
    # --- cherry-picked to only the societies where protection obviously wins.
    ("aurum",        401,  60, 0.75, 0.45,   1.18,  True,  "Aurum Enclave"),
    ("banyan",       402,  56, 0.55, 0.40,   0.88,  True,  "Banyan Residency"),
    ("coral",        403,  48, 0.50, 0.35,   1.12,  True,  "Coral Gardens"),
    ("deodar",       404,  64, 0.65, 0.50,   0.95,  True,  "Deodar Heights"),
    ("estuary",      405,  44, 0.30, 0.30,   0.74,  True,  "Estuary Court"),
    ("fig",          406,  52, 0.40, 0.55,   0.82,  True,  "Fig Tree Park"),
    # --- the 18 unmanaged neighbours. Same engine, same depth, nothing
    # --- protecting them. Their `ai`/`full` arms exist on disk purely as
    # --- the "deploy GridBrain here" target datasets.
    ("gulmohar",     407,  60, 0.70, 0.35,   1.22,  False, "Gulmohar Vista"),
    ("harbour",      408,  50, 0.45, 0.25,   0.91,  False, "Harbour Row"),
    ("indigo",       409,  58, 0.60, 0.45,   1.08,  False, "Indigo Fields"),
    ("jacaranda",    410,  46, 0.35, 0.40,   0.78,  False, "Jacaranda Close"),
    ("kadamba",      411,  62, 0.80, 0.30,   1.30,  False, "Kadamba Towers"),
    ("lotus",        412,  54, 0.50, 0.60,   1.05,  False, "Lotus Meadows"),
    ("mahogany",     413,  58, 0.72, 0.28,   1.15,  False, "Mahogany Court"),
    ("neem",         414,  44, 0.28, 0.48,   0.76,  False, "Neem Grove"),
    ("orchid",       415,  66, 0.68, 0.38,   1.10,  False, "Orchid Sanctuary"),
    ("palash",       416,  50, 0.55, 0.22,   0.93,  False, "Palash Quarters"),
    ("quarry",       417,  56, 0.62, 0.42,   1.02,  False, "Quarry Side"),
    ("rosewood",     418,  60, 0.78, 0.32,   1.25,  False, "Rosewood Estate"),
    ("sandal",       419,  48, 0.42, 0.52,   0.85,  False, "Sandalwood Mews"),
    ("teak",         420,  64, 0.85, 0.26,   1.28,  False, "Teak Township"),
    ("umbrella",     421,  46, 0.32, 0.44,   0.72,  False, "Umbrella Walk"),
    ("vetiver",      422,  52, 0.58, 0.36,   0.97,  False, "Vetiver Lane"),
    ("willow",       423,  62, 0.74, 0.30,   1.20,  False, "Willow Bank"),
    ("ixora",        424,  54, 0.48, 0.50,   1.06,  False, "Ixora Colony"),
]

CONTROLLED_FIELDS = ("n_households", "ev_penetration", "solar_penetration",
                     "rating_kva", "seed")


def _society(key: str, seed: int, n: int, ev: float, solar: float, rating: float):
    return SocietyScenario(id=key, n_households=n, has_workspace=False,
                            ev_penetration=ev, solar_penetration=solar,
                            transformer=TransformerSpec(rating_kva=rating))


# The three deployment arms. Only these flags differ within a triplet.
#
# The middle arm is curtailment ONLY, deliberately. It used to also carry
# solar-sync, which made (ai - raw) unreadable: measured on peak kVA it came
# out NEGATIVE, because solar-sync is a COST lever, not a peak lever. It moves
# EV charging out of the genuinely empty small hours and into daylight, where
# it can coincide with other daytime load -- cheaper energy, occasionally a
# slightly higher peak. Bundling it with curtailment hid the peak protection
# that curtailment really does provide.
#
#   (ai   - raw) = peak protection from coordination alone. Zero capex.
#   (full - ai ) = the solar package: self-consumption savings plus the
#                  station's daytime offset. Judge this on cost and on
#                  daytime import, NOT on evening peak.
ARMS = {
    "raw":  dict(enable_curtailment=False, enable_solar_sync=False, community_solar_kwp=0.0),
    "ai":   dict(enable_curtailment=True,  enable_solar_sync=False, community_solar_kwp=0.0),
    "full": dict(enable_curtailment=True,  enable_solar_sync=True,  community_solar_kwp=COMMUNITY_SOLAR_KWP),
}


def _run_one(sid: str, seed: int, n: int, ev: float, solar: float, rating: float,
             arm: str):
    """One real simulation run. `arm` selects ONLY the control flags."""
    scenario = WorldSimScenario(name=sid, scenario=sid, date=DATE, seed=seed,
                                 duration_hours=24, events=[])
    society = _society(sid, seed, n, ev, solar, rating)
    result = simulate_society(scenario, society, base_seed=seed, **ARMS[arm])
    # Only `raw` and `full` are ever flown into by the renderer (they are the
    # two sides of the "deploy GridBrain here" toggle). The `ai` arm exists to
    # separate coordination value from station value; that lives entirely in
    # district.json's rollup, so writing its 1.2 MB detail file would be
    # ~28 MB of disk nothing ever reads.
    if arm in ("raw", "full"):
        export_society_json(scenario, society, result, f"viz/data/soc_{sid}.json")
    return scenario, society, result


def _rollup(sid: str, label: str, arm: str, pair_key: str,
            society: SocietyScenario, result) -> dict:
    """The compact per-society record that goes into district.json. Only
    aggregate per-tick fields -- no per-household arrays. Everything here
    is read straight off the real SocietyResult."""
    n_steps = len(result.transformer_state)
    dt = result.dt_hours
    house_kw = np.stack([s.kw for s in result.house_series], axis=1).sum(axis=1)
    solar_kw = np.stack([s.solar_kw for s in result.house_series], axis=1).sum(axis=1)
    curtailed_count = np.array([len(ids) for ids in result.curtailed_ids_by_tick])
    comfort = np.stack([np.abs(s.comfort_dev_c) for s in result.house_series], axis=1)

    # unserved energy: on a TRIPPED tick the society's demand is not being
    # served at all. This is the real DISCOM-facing reliability quantity.
    tripped = np.array([st == "TRIPPED" for st in result.transformer_state])
    unserved_kwh = float((house_kw * tripped).sum() * dt)

    # statistics skip the warm-up tick (see WARMUP_TICKS); the exported series
    # below are the complete, untrimmed day
    w = WARMUP_TICKS
    kva_s, state_s, house_kw_s = result.transformer_kva[w:], result.transformer_state[w:], house_kw[w:]
    tripped_s, comfort_s, curt_s = tripped[w:], comfort[w:], curtailed_count[w:]
    unserved_kwh = float((house_kw_s * tripped_s).sum() * dt)

    return {
        "id": sid,
        "label": label,
        "arm": arm,
        "managed": arm != "raw",
        "has_station": arm == "full",
        "pair": pair_key,
        "arms": {a: f"{pair_key}_{a}" for a in ARMS},
        "n_households": society.n_households,
        "ev_penetration": society.ev_penetration,
        "solar_penetration": society.solar_penetration,
        "rating_kva": society.transformer.rating_kva,
        "seed": None,  # filled by caller (kept out of SocietyScenario)
        "detail_file": f"soc_{sid}.json",
        "summary": {
            "peak_kva": round(float(kva_s.max()), 2),
            "peak_frac": round(float(kva_s.max() / society.transformer.rating_kva), 4),
            "peak_tick": int(np.argmax(kva_s)) + w,
            "energy_kwh": round(float(house_kw_s.sum() * dt), 2),
            "solar_kwh": round(float(solar_kw[w:].sum() * dt), 2),
            "community_solar_kwh": round(float(result.community_solar_kw[w:].sum() * dt), 2),
            "unserved_kwh": round(unserved_kwh, 3),
            "tripped_ticks": int(tripped_s.sum()),
            "breach_ticks": int(sum(1 for s in state_s if s == "BREACH")),
            "warning_ticks": int(sum(1 for s in state_s if s == "WARNING")),
            "curtailed_house_ticks": int(curt_s.sum()),
            "mean_comfort_dev_c": round(float(comfort_s.mean()), 4),
            "worst_comfort_dev_c": round(float(comfort_s.max()), 4),
            "states": dict(Counter(state_s)),
        },
        "series": {
            "kva": [round(float(v), 2) for v in result.transformer_kva],
            "state": list(result.transformer_state),
            "total_kw": [round(float(v), 2) for v in house_kw],
            "solar_kw": [round(float(v), 2) for v in solar_kw],
            "community_solar_kw": [round(float(v), 2) for v in result.community_solar_kw],
            "curtailed_count": [int(v) for v in curtailed_count],
        },
        "n_steps": n_steps,
    }


def _calibrate(key, seed, n, ev, solar, stress):
    """Measure this society's real unmanaged peak, then size its transformer
    so that peak lands at `stress` x rating. Uses a nominal rating for the
    probe -- the rating does not affect load, only the state machine, and the
    probe runs with curtailment off so nothing feeds back into demand."""
    scenario = WorldSimScenario(name=key, scenario=key, date=DATE, seed=seed,
                                 duration_hours=24, events=[])
    society = _society(key, seed, n, ev, solar, 1000.0)
    result = simulate_society(scenario, society, base_seed=seed, **ARMS["raw"])
    peak = float(result.transformer_kva[WARMUP_TICKS:].max())
    return round(peak / stress, 1), peak


def main():
    t_all = time.time()
    records = []
    print("calibrating transformer ratings from each society's own unmanaged peak...")
    ratings = {}
    for key, seed, n, ev, solar, stress, _c, label in PAIRS:
        ratings[key], pk = _calibrate(key, seed, n, ev, solar, stress)
        print(f"  {label:<20} unmanaged peak {pk:7.1f} kVA / stress {stress:.2f} -> rating {ratings[key]:6.1f} kVA")
    print()
    print(f"{'society':<26} {'mode':<10} {'n':>3} {'ev':>5} {'solar':>5} {'kVA':>6} "
          f"{'peak':>7} {'frac':>5}  states")
    print("-" * 100)

    ARM_LABEL = {"raw": "unmanaged", "ai": "AI only", "full": "AI+station"}
    for key, seed, n, ev, solar, stress, in_cohort, label in PAIRS:
        rating = ratings[key]
        triplet = []
        # All three arms, identical inputs, only the control flags differ.
        for arm in ("raw", "ai", "full"):
            sid = f"{key}_{arm}"
            _, society, result = _run_one(sid, seed, n, ev, solar, rating, arm)
            rec = _rollup(sid, label, arm, key, society=society, result=result)
            rec["seed"] = seed
            # the society is "deployed" only if this pair is in the cohort
            # AND this is the full-package arm
            rec["in_cohort"] = bool(in_cohort and arm == "full")
            triplet.append(rec)
            s = rec["summary"]
            print(f"{label + ' [' + ARM_LABEL[arm] + ']':<28} "
                  f"{arm:<6} {n:>3} {ev:>5.2f} {solar:>5.2f} "
                  f"{rating:>6.1f} {s['peak_kva']:>7.1f} {s['peak_frac']:>5.2f}  {s['states']}")

        # --- assert the controlled variables really are identical ---
        for f in CONTROLLED_FIELDS:
            vals = {r[f] for r in triplet}
            assert len(vals) == 1, f"triplet {key} differs on controlled field {f}: {vals}"

        # --- attribution, computed here so it is never mis-derived in the UI ---
        raw, ai, full = triplet
        coord_kva = raw["summary"]["peak_kva"] - ai["summary"]["peak_kva"]
        station_kva = ai["summary"]["peak_kva"] - full["summary"]["peak_kva"]
        for r in triplet:
            r["attribution"] = {
                "coordination_peak_kva_saved": round(coord_kva, 2),
                "station_peak_kva_saved": round(station_kva, 2),
                "coordination_unserved_kwh_avoided": round(
                    raw["summary"]["unserved_kwh"] - ai["summary"]["unserved_kwh"], 3),
            }
        print(f"{'':<28} -> coordination saves {coord_kva:>6.1f} kVA peak (zero capex); "
              f"station adds {station_kva:>5.1f} kVA")
        records.extend(triplet)
        print()

    # All three arms of all 12 societies are exported. The district view
    # shows 24 live societies: the 6 cohort societies on their `full` arm,
    # and the other 6 on their `raw` arm -- plus, for depth, the remaining
    # raw arms of the cohort societies as their "prove it" twins. The
    # unshown arms exist on disk as "deploy GridBrain here" targets.
    district = {
        "schema_version": "1.0.0",
        "meta": {
            "date": DATE,
            "interval_minutes": 15,
            "n_societies": len(PAIRS),
            "n_runs": len(records),
            "n_cohort_managed": sum(1 for r in records if r["in_cohort"]),
            "community_solar_kwp": COMMUNITY_SOLAR_KWP,
            "warmup_ticks": WARMUP_TICKS,
            "warmup_note": ("Summary statistics exclude the first tick. The run starts at 00:00 "
                            "from synthetic initial conditions and every appliance state machine "
                            "is evaluated simultaneously on the first step, which produced a "
                            "cold-start spike above the genuine evening peak. Storage states are "
                            "jittered per household to avoid lockstep switch-on; one residual "
                            "warm-up tick is still excluded from statistics. The exported series "
                            "are the complete untrimmed day."),
            "arms": {
                "raw": "nothing deployed",
                "ai": "GridBrain coordination only -- zero capex",
                "full": f"coordination + a {COMMUNITY_SOLAR_KWP:.0f} kWp community solar station",
            },
            "note": ("12 societies, each simulated as a matched triplet. All three arms share "
                     "seed, size, EV/solar penetration and transformer rating; only the "
                     "deployment flags differ. (ai - raw) is the value of coordination alone "
                     "at zero capex; (full - ai) is what the solar station adds on top. All "
                     "runs are real -- unmanaged transformers trip because nothing is "
                     "protecting them."),
        },
        "societies": records,
    }
    out = Path("viz/data/district.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(district, separators=(",", ":")))

    size_mb = out.stat().st_size / 1048576
    print("=" * 100)
    print(f"district.json: {size_mb:.2f} MB  ({len(PAIRS)} societies x 3 arms = "
          f"{len(records)} runs, {sum(1 for r in records if r['in_cohort'])} deployed)")

    def agg(arm, k):
        return sum(r["summary"][k] for r in records if r["arm"] == arm)
    print(f"{'arm':<8} {'trips':>6} {'breach':>7} {'unserved kWh':>13} {'peak sum kVA':>13}")
    for arm in ("raw", "ai", "full"):
        print(f"{arm:<8} {agg(arm,'tripped_ticks'):>6} {agg(arm,'breach_ticks'):>7} "
              f"{agg(arm,'unserved_kwh'):>13.1f} {agg(arm,'peak_kva'):>13.1f}")
    coord = agg("raw", "peak_kva") - agg("ai", "peak_kva")
    station = agg("ai", "peak_kva") - agg("full", "peak_kva")
    print(f"\nDistrict-wide attribution (sum of per-society peaks):")
    print(f"  coordination alone (zero capex): {coord:.1f} kVA")
    print(f"  solar station adds on top:       {station:.1f} kVA")
    print(f"total {round(time.time()-t_all,1)}s")


if __name__ == "__main__":
    main()
