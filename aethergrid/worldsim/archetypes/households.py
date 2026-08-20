"""The 6 household archetypes (PART 4.1 of society_simulation_plan.md),
as data. Shares sum to 1.00: 0.20+0.25+0.15+0.15+0.15+0.10.

`home_prob_by_hour` curves and all numeric parameters are hand-picked to
be *plausible and differentiated*, not measured -- exactly the "hand pick
plausible values and say they are hand picked" standard the parent
project's own planning docs set. This is what engine/occupancy.py reads
to draw per-tick occupancy; it never sees a fixed load curve."""
from __future__ import annotations

from aethergrid.worldsim.schemas.household import HouseholdArchetype, OccupancyPattern

ARCHETYPES: dict[str, HouseholdArchetype] = {
    "dual_income_no_children": HouseholdArchetype(
        name="dual_income_no_children", share=0.20,
        occupancy=OccupancyPattern(
            home_prob_by_hour=[0.95, 0.95, 0.95, 0.95, 0.95, 0.90, 0.85, 0.60, 0.20,
                                0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.15,
                                0.50, 0.85, 0.90, 0.90, 0.95, 0.95],
            weekend_multiplier=1.6, mean_occupant_count=2.0, occupant_count_std=0.5,
        ),
        comfort_t_min_c=22.0, comfort_t_max_c=27.0, comfort_tolerance_c=1.5,
        override_probability=0.15, flexibility=0.7,
        ac_ownership_prob=0.85, ac_count_mean=1.5, geyser_ownership_prob=0.9,
        washing_machine_ownership_prob=0.7, dishwasher_ownership_prob=0.3,
        ev_ownership_prob=0.5, solar_ownership_prob=0.2, battery_ownership_prob=0.1,
        thermal_R_k_per_kw=3.0, thermal_C_kwh_per_k=60, floors_choices=[1, 2],
    ),
    "family_with_children": HouseholdArchetype(
        name="family_with_children", share=0.25,
        occupancy=OccupancyPattern(
            home_prob_by_hour=[0.95, 0.95, 0.95, 0.95, 0.95, 0.90, 0.85, 0.70, 0.50,
                                0.45, 0.45, 0.45, 0.50, 0.50, 0.45, 0.50, 0.60, 0.75,
                                0.90, 0.95, 0.95, 0.95, 0.95, 0.95],
            weekend_multiplier=1.2, mean_occupant_count=4.0, occupant_count_std=1.0,
        ),
        comfort_t_min_c=21.0, comfort_t_max_c=26.0, comfort_tolerance_c=1.0,
        override_probability=0.20, flexibility=0.6,
        ac_ownership_prob=0.9, ac_count_mean=2.0, geyser_ownership_prob=0.95,
        washing_machine_ownership_prob=0.8, dishwasher_ownership_prob=0.3,
        ev_ownership_prob=0.4, solar_ownership_prob=0.25, battery_ownership_prob=0.1,
        thermal_R_k_per_kw=2.8, thermal_C_kwh_per_k=70, floors_choices=[1, 2],
    ),
    "elderly_couple": HouseholdArchetype(
        name="elderly_couple", share=0.15,
        occupancy=OccupancyPattern(
            home_prob_by_hour=[0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.90, 0.90, 0.85,
                                0.80, 0.75, 0.70, 0.70, 0.70, 0.75, 0.80, 0.85, 0.90,
                                0.90, 0.95, 0.95, 0.95, 0.95, 0.95],
            weekend_multiplier=1.0, mean_occupant_count=2.0, occupant_count_std=0.2,
        ),
        comfort_t_min_c=23.0, comfort_t_max_c=26.0, comfort_tolerance_c=0.5,
        override_probability=0.05, flexibility=0.3,
        ac_ownership_prob=0.6, ac_count_mean=1.0, geyser_ownership_prob=0.85,
        washing_machine_ownership_prob=0.5, dishwasher_ownership_prob=0.1,
        ev_ownership_prob=0.1, solar_ownership_prob=0.15, battery_ownership_prob=0.1,
        thermal_R_k_per_kw=3.2, thermal_C_kwh_per_k=55, floors_choices=[1],
    ),
    "work_from_home": HouseholdArchetype(
        name="work_from_home", share=0.15,
        occupancy=OccupancyPattern(
            home_prob_by_hour=[0.90, 0.90, 0.90, 0.90, 0.90, 0.90, 0.85, 0.85, 0.90,
                                0.90, 0.90, 0.90, 0.85, 0.90, 0.90, 0.90, 0.85, 0.85,
                                0.85, 0.85, 0.85, 0.85, 0.90, 0.90],
            weekend_multiplier=1.1, mean_occupant_count=1.0, occupant_count_std=0.3,
        ),
        comfort_t_min_c=22.0, comfort_t_max_c=26.0, comfort_tolerance_c=1.2,
        override_probability=0.30, flexibility=0.6,
        ac_ownership_prob=0.8, ac_count_mean=1.0, geyser_ownership_prob=0.8,
        washing_machine_ownership_prob=0.6, dishwasher_ownership_prob=0.2,
        ev_ownership_prob=0.3, solar_ownership_prob=0.2, battery_ownership_prob=0.1,
        thermal_R_k_per_kw=3.0, thermal_C_kwh_per_k=50, floors_choices=[1],
    ),
    "joint_family": HouseholdArchetype(
        name="joint_family", share=0.15,
        occupancy=OccupancyPattern(
            home_prob_by_hour=[0.98] * 24,
            weekend_multiplier=1.1, mean_occupant_count=6.0, occupant_count_std=1.5,
        ),
        comfort_t_min_c=22.0, comfort_t_max_c=27.0, comfort_tolerance_c=1.0,
        override_probability=0.20, flexibility=0.5,
        ac_ownership_prob=0.95, ac_count_mean=3.0, geyser_ownership_prob=0.95,
        washing_machine_ownership_prob=0.85, dishwasher_ownership_prob=0.2,
        ev_ownership_prob=0.6, solar_ownership_prob=0.3, battery_ownership_prob=0.15,
        thermal_R_k_per_kw=2.5, thermal_C_kwh_per_k=90, floors_choices=[2],
    ),
    "frequently_absent": HouseholdArchetype(
        name="frequently_absent", share=0.10,
        occupancy=OccupancyPattern(
            home_prob_by_hour=[0.15, 0.15, 0.15, 0.15, 0.15, 0.15, 0.10, 0.10, 0.10,
                                0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.15,
                                0.20, 0.20, 0.20, 0.20, 0.20, 0.15],
            weekend_multiplier=1.3, mean_occupant_count=1.5, occupant_count_std=1.5,
        ),
        comfort_t_min_c=22.0, comfort_t_max_c=27.0, comfort_tolerance_c=2.0,
        override_probability=0.40, flexibility=0.3,
        ac_ownership_prob=0.5, ac_count_mean=1.0, geyser_ownership_prob=0.6,
        washing_machine_ownership_prob=0.3, dishwasher_ownership_prob=0.1,
        ev_ownership_prob=0.4, solar_ownership_prob=0.1, battery_ownership_prob=0.05,
        thermal_R_k_per_kw=3.0, thermal_C_kwh_per_k=60, floors_choices=[1, 2],
    ),
}

assert abs(sum(a.share for a in ARCHETYPES.values()) - 1.0) < 1e-9
