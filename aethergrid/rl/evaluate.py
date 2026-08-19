"""Wraps a trained PPO model (or the deterministic fallback) as a
core.timestep.PolicyFn, so it can be dropped into simulate_building_series
exactly like any baseline -- same shield, same physics, same BillEngine.
This is what makes 'rl' and 'safe_rl' fair comparisons against 'mean_mpc' /
'quantile_mpc' in the results table."""
from __future__ import annotations

import json
from pathlib import Path

from aethergrid.core.timestep import StepContext
from aethergrid.rl.action import decode_action
from aethergrid.rl.observation import build_observation
from aethergrid.rl.policies import adaptive_fallback_policy

MODEL_DIR = Path("aethergrid/models")


def load_rl_policy(building_type: str, coordination_aware: bool = False):
    """Returns (policy_fn, metadata). Falls back to the deterministic
    adaptive controller if no trained model exists for this building type
    (PART AV) -- never raises, always returns something runnable."""
    model_path = MODEL_DIR / f"ppo_{building_type}.zip"
    meta_path = MODEL_DIR / "run_metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    if not model_path.exists():
        return adaptive_fallback_policy, {**meta, "backend": "deterministic_adaptive_fallback", "fallback": True}

    try:
        from stable_baselines3 import PPO
        model = PPO.load(str(model_path))
    except Exception as e:  # noqa: BLE001
        return adaptive_fallback_policy, {**meta, "backend": "deterministic_adaptive_fallback",
                                           "fallback": True, "load_error": str(e)}

    ev_max_kw_cache = {}

    def policy_fn(ctx: StepContext) -> dict:
        obs = build_observation(ctx)
        action, _ = model.predict(obs, deterministic=True)
        r = ctx.resources
        key = r.building_id
        if key not in ev_max_kw_cache:
            ev_max_kw_cache[key] = r.ev_max_charge_kw * r.ev_count
        return decode_action(action, r, ev_max_kw_cache[key])

    return policy_fn, {**meta, "backend": "stable_baselines3.PPO", "fallback": False}
