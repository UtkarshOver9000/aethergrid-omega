"""Appliance library (PART 4.2 of society_simulation_plan.md). Four
classes determine what the coordinator/curtailment logic is allowed to
do: untouchable (never controlled), deferrable (has a job + deadline),
thermostatic (tied to real indoor-temperature RC dynamics), storage
(SOC-bounded via the reused simulation.storage functions)."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ApplianceClass(str, Enum):
    UNTOUCHABLE = "untouchable"
    DEFERRABLE = "deferrable"
    THERMOSTATIC = "thermostatic"
    STORAGE = "storage"


class ApplianceSpec(BaseModel):
    name: str
    rated_kw: float
    appliance_class: ApplianceClass
    notes: str = ""
    # deferrable-only: a "job" is created stochastically and must complete within deadline_hours
    typical_job_kwh: float | None = None
    typical_runtime_min: int | None = None
    deadline_hours: float | None = None


# Indicative ratings for an Indian flat (PART 4.2 table). Hand-picked and
# labeled as such -- not measured.
HOUSEHOLD_APPLIANCES: dict[str, ApplianceSpec] = {
    "ceiling_fan": ApplianceSpec(name="ceiling_fan", rated_kw=0.07, appliance_class=ApplianceClass.UNTOUCHABLE,
                                  notes="2-4 per flat, one entry represents the flat's total fan draw when occupied"),
    "led_lighting": ApplianceSpec(name="led_lighting", rated_kw=0.15, appliance_class=ApplianceClass.UNTOUCHABLE),
    "refrigerator": ApplianceSpec(name="refrigerator", rated_kw=0.15, appliance_class=ApplianceClass.THERMOSTATIC,
                                   notes="~35% duty cycle, modeled as a small independent thermostatic load"),
    "television_electronics": ApplianceSpec(name="television_electronics", rated_kw=0.15, appliance_class=ApplianceClass.UNTOUCHABLE),
    "cooking": ApplianceSpec(name="cooking", rated_kw=1.8, appliance_class=ApplianceClass.UNTOUCHABLE,
                              notes="induction/mixer/microwave bundled, sharp morning+evening bursts"),
    "ac_1_5_ton": ApplianceSpec(name="ac_1_5_ton", rated_kw=1.65, appliance_class=ApplianceClass.THERMOSTATIC,
                                 notes="inverter unit modulates down to ~0.4kW"),
    "geyser": ApplianceSpec(name="geyser", rated_kw=2.0, appliance_class=ApplianceClass.STORAGE,
                             typical_job_kwh=1.5, notes="15-25L tank, thermal storage via dhw_step"),
    "washing_machine": ApplianceSpec(name="washing_machine", rated_kw=1.0, appliance_class=ApplianceClass.DEFERRABLE,
                                      typical_job_kwh=1.0, typical_runtime_min=60, deadline_hours=18),
    "dishwasher": ApplianceSpec(name="dishwasher", rated_kw=1.2, appliance_class=ApplianceClass.DEFERRABLE,
                                 typical_job_kwh=1.0, typical_runtime_min=90, deadline_hours=10),
    "ev_charger": ApplianceSpec(name="ev_charger", rated_kw=3.3, appliance_class=ApplianceClass.STORAGE),
}

# Society common loads (PART 4.2). The water pump and STP are the best
# curtailment targets: large, fully deferrable, and nobody notices.
COMMON_APPLIANCES: dict[str, ApplianceSpec] = {
    "water_pump": ApplianceSpec(name="water_pump", rated_kw=6.0, appliance_class=ApplianceClass.DEFERRABLE,
                                 typical_job_kwh=6.0, typical_runtime_min=60, deadline_hours=6,
                                 notes="fills the tank; scheduled twice daily, fully deferrable within the day"),
    "lifts": ApplianceSpec(name="lifts", rated_kw=7.5, appliance_class=ApplianceClass.UNTOUCHABLE,
                            notes="occupancy driven, safety-critical, never curtailed"),
    "corridor_streetlights": ApplianceSpec(name="corridor_streetlights", rated_kw=4.0, appliance_class=ApplianceClass.UNTOUCHABLE,
                                            notes="dusk to dawn; classified non-critical for breach shedding despite being 'untouchable' under normal ops"),
    "stp": ApplianceSpec(name="stp", rated_kw=4.0, appliance_class=ApplianceClass.DEFERRABLE,
                          typical_job_kwh=8.0, typical_runtime_min=120, deadline_hours=12),
    "clubhouse_common_hvac": ApplianceSpec(name="clubhouse_common_hvac", rated_kw=3.0, appliance_class=ApplianceClass.THERMOSTATIC),
    "security_fire_systems": ApplianceSpec(name="security_fire_systems", rated_kw=0.5, appliance_class=ApplianceClass.UNTOUCHABLE,
                                            notes="critical, never curtailed even on TRIPPED"),
}
