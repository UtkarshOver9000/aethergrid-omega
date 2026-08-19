"""Gymnasium environment wrapping ONE building's digital twin. Single-agent
by design (PART L: "Do NOT implement multi-agent RL until the single-agent
environment works" -- multi-agent is out of scope for this build, see
docs/LIMITATIONS.md). Every step still passes through the safety shield
(RULE 3) -- the environment cannot be used to bypass it."""
from __future__ import annotations

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
    _HAS_GYM = True
except ImportError:  # pragma: no cover
    _HAS_GYM = False
    gym = object

from aethergrid.core.building import Building
from aethergrid.core.timestep import advance_physics, build_step_context, shield_action
from aethergrid.core.world import World
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.rl.action import ACTION_DIM, decode_action
from aethergrid.rl.observation import OBS_DIM, build_observation
from aethergrid.rl.reward import compute_reward
from aethergrid.schemas.experiment import ObjectiveWeights


class BuildingEnergyEnv(gym.Env if _HAS_GYM else object):
    metadata = {"render_modes": []}

    def __init__(self, building: Building, world: World, load_pf: PathForecaster, solar_pf: PathForecaster,
                 weights: ObjectiveWeights | None = None, carbon_kg_per_kwh: float = 0.71,
                 horizon_steps: int = 32, risk_level: float = 0.05, episode_length: int | None = None):
        if not _HAS_GYM:
            raise ImportError("gymnasium is required for aethergrid.rl.env")
        super().__init__()
        self.building = building
        self.world = world
        self.load_pf = load_pf
        self.solar_pf = solar_pf
        self.weights = weights or ObjectiveWeights()
        self.carbon_kg_per_kwh = carbon_kg_per_kwh
        self.horizon_steps = horizon_steps
        self.risk_level = risk_level
        self.episode_length = episode_length or world.n_steps
        self.peak_reference_kw = float(building.profile.base_load_kw.max())

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(ACTION_DIM,), dtype=np.float32)
        self.observation_space = spaces.Box(low=-10.0, high=10.0, shape=(OBS_DIM,), dtype=np.float32)
        self.t = 0
        self.prev_hvac = 0.0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.building.state = self.building._init_state()
        max_start = max(0, self.world.n_steps - self.episode_length - 1)
        self.t = int(self.np_random.integers(0, max_start + 1)) if max_start > 0 else 0
        self.prev_hvac = 0.0
        ctx, _ = self._build_ctx()
        return build_observation(ctx), {}

    def _build_ctx(self):
        base_fn = lambda t, H: self.load_pf.forecast_path(self.building.profile.base_load_kw, t, H)
        solar_fn = lambda t, H: self.solar_pf.forecast_path(self.building.profile.solar_potential_kw, t, H)
        return build_step_context(
            self.building, self.world, self.t, self.horizon_steps, self.risk_level, self.weights,
            self.carbon_kg_per_kwh, base_fn, solar_fn, import_cap_kw=None,
            coordination_price_per_kwh=None, prev_hvac_kw=self.prev_hvac, outage=False,
        )

    def step(self, action: np.ndarray):
        ctx, internal_gain = self._build_ctx()
        r = self.building.resources
        ev_max_kw = r.ev_max_charge_kw * r.ev_count
        raw_action = decode_action(action, r, ev_max_kw)

        ev_present_now = bool(self.building.profile.ev_present[self.t])
        ig0 = float(internal_gain[0]) if len(internal_gain) else 0.0
        safe = shield_action(raw_action, self.building, self.world, self.t, ig0, ev_present_now, apply_shield=True)
        step_res = advance_physics(self.building, self.world, self.t, safe, ig0, import_cap_kw=None,
                                    outage=False, demand_spike_addon_kw=None, solar_failure_mask=None)
        self.building.state = step_res.next_state
        self.prev_hvac = safe.hvac_kw

        reward = compute_reward(ctx, step_res, self.peak_reference_kw)

        self.t += 1
        terminated = False
        truncated = self.t >= self.world.n_steps - 1
        next_ctx, _ = self._build_ctx()
        obs = build_observation(next_ctx)
        info = {"import_kw": step_res.grid.import_kw, "indoor_temp_c": step_res.next_state.indoor_temp_c}
        return obs, reward, terminated, truncated, info
