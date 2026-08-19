"""PPO training script (PART L, Tier A). Trained on a dedicated longer
synthetic world (configs/worlds/rl_train.json) so the policy sees more
variety than the short 2-day demo worlds. If stable-baselines3/PPO is
unavailable or training raises, this records a fallback to the
deterministic adaptive controller (rl/policies.py) per PART AV -- it never
silently substitutes one for the other without saying so.

Given documented evidence (CityLearn 2021-2023) that RL has NOT been
competitive with classical MPC on this problem class, this training run is
intentionally light (a demonstration/comparison policy for testing H3, not
an attempt to out-tune the MPC) -- see docs/METHODOLOGY.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from aethergrid.core.world import World
from aethergrid.forecasting.predict import build_training_building
from aethergrid.forecasting.path_forecast import PathForecaster
from aethergrid.schemas.experiment import ObjectiveWeights

MODEL_DIR = Path("aethergrid/models")


def train_ppo(world_path: str = "aethergrid/configs/worlds/rl_train.json",
              building_id: str = "RL01_office", total_timesteps: int = 20000,
              model_out: str | None = None) -> dict:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    world = World.load(world_path)
    building = world.buildings[building_id]

    _, train_df = build_training_building(building.archetype.type, seed=123, n_days=45, dt_minutes=15)
    load_pf = PathForecaster.fit(train_df["base_load_kw"].values, 96, 32)
    solar_pf = PathForecaster.fit(train_df["solar_kw"].values, 96, 32)

    result = {"backend": None, "fallback": False, "total_timesteps": total_timesteps, "model_path": None}
    try:
        from stable_baselines3 import PPO
        from aethergrid.rl.env import BuildingEnergyEnv

        env = BuildingEnergyEnv(building, world, load_pf, solar_pf, ObjectiveWeights(),
                                 carbon_kg_per_kwh=0.71, horizon_steps=32, risk_level=0.05)
        model = PPO("MlpPolicy", env, verbose=0, n_steps=512, batch_size=64,
                     learning_rate=3e-4, gamma=0.99, seed=123)
        model.learn(total_timesteps=total_timesteps)

        out_path = model_out or str(MODEL_DIR / f"ppo_{building.archetype.type}.zip")
        model.save(out_path)
        result.update({"backend": "stable_baselines3.PPO", "model_path": out_path})
    except Exception as e:  # noqa: BLE001 -- deliberately broad: any training failure triggers the documented fallback
        result.update({"backend": "deterministic_adaptive_fallback", "fallback": True, "error": str(e)})

    (MODEL_DIR / "run_metadata.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    print(json.dumps(train_ppo(), indent=2))
