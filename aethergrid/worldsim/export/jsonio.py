"""Serializes a SocietyResult (+ optional colony/connection wrapping) into
the versioned JSON contract. This is the only place that touches JSON --
the renderer never computes, only reads what this module writes."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from aethergrid.worldsim.engine.society import SocietyResult
from aethergrid.worldsim.schemas.frame import SCHEMA_VERSION
from aethergrid.worldsim.schemas.scenario import SocietyScenario, WorldSimScenario


def _house_ev_state(ev_state_list: list) -> list:
    return ev_state_list


def society_to_dict(scenario: WorldSimScenario, society: SocietyScenario, result: SocietyResult) -> dict:
    houses_static = []
    for cfg in result.house_configs:
        houses_static.append({
            "id": cfg.id, "archetype": cfg.archetype_name, "has_ev": cfg.has_ev,
            "has_solar": cfg.has_solar, "has_battery": cfg.has_battery,
            "battery_kwh": round(cfg.battery_kwh, 2), "grid_x": cfg.grid_x, "grid_z": cfg.grid_z,
            "floors": cfg.floors,
        })

    workspace_static = None
    if society.has_workspace:
        workspace_static = {
            "id": "ws0", "archetype": society.workspace_archetype, "has_ev": True, "has_solar": True,
            "battery_kwh": 40.0, "grid_x": -1, "grid_z": society.grid_rows // 2,
        }

    common_infra_static = {
        "water_tank_capacity_l": society.common_infra.water_tank_capacity_l,
        "has_lift": society.common_infra.has_lift, "has_stp": society.common_infra.has_stp,
        "has_clubhouse": society.common_infra.has_clubhouse,
        "streetlight_count": society.common_infra.streetlight_count,
        "critical_ids": society.common_infra.critical_ids, "non_critical_ids": society.common_infra.non_critical_ids,
    }

    events_static = [e.model_dump(mode="json") for e in scenario.events]

    frames = []
    n = len(result.index)
    for t in range(n):
        houses_dyn = []
        for hid, s in enumerate(result.house_series):
            houses_dyn.append({
                "id": hid, "kw": round(float(s.kw[t]), 3), "ac_on": bool(s.ac_on[t]),
                "geyser_on": bool(s.geyser_on[t]), "ev_state": s.ev_state[t],
                "ev_soc": round(float(s.ev_soc_frac[t]), 3), "solar_kw": round(float(s.solar_kw[t]), 3),
                "battery_soc": round(float(s.battery_soc_frac[t]), 3),
                "indoor_temp_c": round(float(s.indoor_temp_c[t]), 2), "comfort_dev_c": round(float(s.comfort_dev_c[t]), 2),
                "occupancy": int(s.occupancy[t]), "curtailed": hid in result.curtailed_ids_by_tick[t],
                "deferrables_active": s.deferrables_active[t],
            })

        workspace_dyn = None
        if result.workspace_series is not None:
            ws = result.workspace_series
            workspace_dyn = {
                "kw": round(float(ws.kw[t]), 3), "occupancy_frac": round(float(ws.occupancy_frac[t]), 3),
                "hvac_kw": round(float(ws.hvac_kw[t]), 3), "lighting_kw": round(float(ws.lighting_kw[t]), 3),
                "computer_kw": round(float(ws.computer_kw[t]), 3), "meeting_room_active": bool(ws.meeting_room_active[t]),
                "solar_kw": round(float(ws.solar_kw[t]), 3), "battery_soc": round(float(ws.battery_soc_frac[t]), 3),
                "ev_count_charging": int(ws.ev_count_charging[t]),
            }

        ci = result.common_infra_series
        env = result.environment
        frame = {
            "t_min": int(round((result.index[t] - result.index[0]).total_seconds() / 60)),
            "environment": {
                "temperature_c": round(float(env.temp_c[t]), 2), "humidity_pct": round(float(env.humidity_pct[t]), 1),
                "irradiance": round(float(env.ghi_wm2[t]), 1), "cloud_factor": round(float(env.cloud_factor[t]), 3),
                "sun_altitude": round(float(env.sun_altitude[t]), 4), "sun_azimuth": round(float(env.sun_azimuth[t]), 4),
            },
            "grid": {
                "available": not bool(result.outage_mask[t]), "transformer_kva": round(float(result.transformer_kva[t]), 2),
                "rating_kva": society.transformer.rating_kva, "state": result.transformer_state[t],
            },
            "society": {
                "common_kw": round(float(result.common_infra_kw[t]), 3),
                "solar_kw": round(float(sum(s.solar_kw[t] for s in result.house_series)), 3),
                "common_infra": {
                    "water_tank_level_pct": round(float(ci.water_tank_level_pct[t]), 1),
                    "pump_on": bool(ci.pump_on[t]), "lift_active": bool(ci.lift_active[t]),
                    "streetlights_on": bool(ci.streetlights_on[t]), "stp_on": bool(ci.stp_on[t]),
                    "clubhouse_hvac_kw": round(float(ci.clubhouse_hvac_kw[t]), 3),
                },
                "fairness": {
                    "curtailed_house_ids": result.curtailed_ids_by_tick[t],
                    "total_curtailed_kwh": round(float(result.total_curtailed_kwh_by_tick[t]), 3),
                    "override_events": [],
                },
            },
            "workspace": workspace_dyn,
            "houses": houses_dyn,
            "events_active": result.active_events_by_tick[t],
        }
        frames.append(frame)

    return {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "scenario": scenario.scenario, "world_type": "society", "n_households": society.n_households,
            "transformer_rating_kva": society.transformer.rating_kva, "interval_minutes": scenario.interval_minutes,
            "date": scenario.date, "seed": scenario.seed, "n_steps": n,
            "ev_penetration": society.ev_penetration, "override_rate": society.override_rate,
            "solar_penetration": society.solar_penetration,
        },
        "houses": houses_static, "workspace": workspace_static, "common_infra": common_infra_static,
        "events": events_static, "frames": frames,
    }


def export_society_json(scenario: WorldSimScenario, society: SocietyScenario, result: SocietyResult,
                         out_path: str | Path) -> dict:
    data = society_to_dict(scenario, society, result)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, separators=(",", ":")))
    return data
