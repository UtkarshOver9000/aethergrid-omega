# Execution Plan — the 30 Improvements + the Populated Colony

> **Addendum (added after the 30 were approved):** the world grows from 3
> societies to **24**, all simulated at the same depth as Society A. **6 run
> under GridBrain; 18 run unmanaged.** See §7 — this became Phase 0 because
> almost every analytic in Phases 3–5 gets dramatically stronger with a real
> managed-vs-unmanaged population underneath it, and 8 new items (#31–#38)
> fall directly out of it.



Scope: the 30 suggestions issued earlier this session, now approved for
build. This plan covers **all 30**, grouped by what they actually cost,
not by the order they were listed in.

Written against the code as it stands **after** the solar work landed
(`Solar` rail tab, `enable_solar_sync`, `community_solar_kwp`, the 60 kWp
station object, `whatif_ev*_ai_solarsync.json`). Every file and function
named below was verified to exist before this plan was written.

---

## BUILD LOG

### ✅ Phase 0 complete — the populated district (#31–#38)

`aethergrid/worldsim/generate_district.py`, `viz/data/district.json`,
48 lazy-loaded detail files, plus the District camera mode and rail tab in
`viz3d/`.

**Design change made during the build.** The plan called for matched
*pairs* (managed vs unmanaged). Partway through I found that the managed
arm was also receiving the 60 kWp community solar station — so the pair
differed in *physical capex*, not just coordination, and any "our AI saved
X" number would have quietly included a hardware purchase. Rebuilt as
matched **triplets**:

| arm | curtailment | solar-sync | station | meaning |
|---|---|---|---|---|
| `raw` | off | off | 0 | nothing deployed |
| `ai` | on | on | 0 | coordination only — **zero capex** |
| `full` | on | on | 60 kWp | coordination + station |

`(ai − raw)` is coordination's value; `(full − ai)` is the station's. The
generator asserts seed / household count / EV / solar / rating are
identical across all three arms and fails loudly if they ever drift.

**Real generated results** (24 societies × 3 arms = 72 runs, 1,314
households, 7.9 s):

| arm | trips | breach intervals | unserved energy | Σ peak |
|---|---|---|---|---|
| raw | 6 | 24 | 422.6 kWh | 5788.2 kVA |
| ai | **0** | **0** | **0.0 kWh** | 5170.5 kVA |
| full | 0 | 0 | 0.0 kWh | 5047.3 kVA |

**Coordination alone — no hardware — accounts for 617.8 kVA (83%) of the
peak reduction and removes every trip in the district. The solar station
adds 123.2 kVA (17%) and costs money.** That split is now the headline of
the District tab, and it is a stronger and more defensible claim than the
bundled number would have been.

Delivered: district scoreboard (#31), attribution panel (#36 + the
coordination/station split), 24×96 failure heatmap (#38), league table
(#34), live "Deploy GridBrain here" dataset swap (#35 — verified: Kadamba
Towers 121%→99% of rating, 2 trips→0, 144.4 kWh unserved→0), GridBrain
link beams marking the deployed six (#32), district-scale capex (#37).

**Two real rendering bugs found and fixed while verifying this:**
- Camera `far` was **800**, but the district sits ~1,000 units out and
  needs the camera ~550 back — all 24 societies were being clipped by the
  far plane. Now scale-aware (`CAM_RANGE`).
- Raising `far` to 2600 against `near: 0.1` destroyed depth precision
  (everything landed within 0.001 of the buffer's far end). `near` is now
  raised to 5 at district scale too.

Verified: 24/24 societies on screen, 1,314 instanced houses, 6 canopies +
6 beams on the cohort, 24 pickable anchors, `pytest -q` still 26/26.

**Deferred from Phase 0:** #33 (adoption slider 0→24) — the per-society
data supports it, but a *shared upstream feeder* peak needs a real
coincident-aggregate run rather than summing per-society peaks, which
would overstate the benefit. Moving to Phase 5 with the other generator
work rather than shipping a misleading version.

### ✅ Phase 1 complete — the two real defects (#1, #30)

- **#1 night lighting.** The sun had a hard intensity floor of 0.15 and its
  position was clamped to `y >= -5`, so it never set — "night" was dim
  daylight. Sun now reaches true zero and goes below the horizon; the
  `moonLight` that had been declared and left unwired since it was written
  is now a real directional key. Verified across the day: 00:15 → sun 0.0
  (invisible, y=−68), moon 0.42, ambient 0.029; 13:00 → sun 2.5, y=87.
- **#30 the dead ₹0.** The recoverable figure only counted elapsed ticks,
  so it read ₹0 at any time before 6pm. Now shows the exact full-day figure
  alongside what has been incurred so far — exact rather than forecast,
  since the dataset is a complete deterministic 24 h run. Verified at
  00:15: **"₹18 recoverable today · ₹0 of that incurred by 00:15"**.

### ✅ #33 built — and it exposed four engine bugs

#33 was buildable after all: the coincident feeder peak is
`max_t Σ kva_i(t)` over the per-tick series I already had, not a sum of
peaks. Building it surfaced a chain of **synchronization artifacts**, all
the same bug class — *identical initial conditions or shared thresholds
making the whole world switch on at the same instant*:

| # | Artifact | Effect | Fix |
|---|---|---|---|
| 1 | Every EV initialized to exactly `0.4` SOC | whole district charged in lockstep from 00:00 | jittered, and cars home overnight now start charged — they would be |
| 2 | Every geyser initialized to `0.6`, reheating at `0.85` | every element on together for the first 30 min | jittered across the heat/draw cycle |
| 3 | Solar-sync fallback hard-coded to `17:00` | every deferred car switched on at the same instant | jittered 16.5–19.5 h per house |
| 4 | Solar window opened at a shared `ghi > 50` | every deferred car started together at sunrise (**+169 kVA** on one society) | per-house threshold 80–450 W/m² |

The combined effect was a **false midnight coincident peak 39% above the
genuine evening one**. The district's headline had been *6 trips, 24
breaches, 422 kWh unserved* for the unmanaged cohort — **most of that was
the artifact, not the physics.** It would not have survived a judge
plotting the load curve and asking why a residential district peaks at
midnight.

Two consequences had to be fixed downstream:

- **Recalibration.** With peaks corrected, the what-if grid's 280 kVA
  rating left the Coordinator nothing to do (AI-on and AI-off became
  byte-identical). A calibration probe picked **195 kVA**: clean at low EV,
  genuine breach at high EV. Same problem in the district — every society
  now sat under its hand-picked rating and coordination measured *exactly
  zero*. Ratings are now **derived per society** from its own measured
  unmanaged peak against a target stress ratio, so the district keeps a
  realistic mix of undersized and roomy transformers no matter what the
  engine does to absolute load.
- **Arm redefinition.** `ai` had bundled curtailment *and* solar-sync,
  which made `(ai − raw)` measured on peak come out **negative**. That is a
  real result, not a bug: **solar is a cost lever, not a peak lever.**
  Solar-sync moves charging out of the empty small hours into daylight
  (cheaper energy, occasionally a higher peak), and the station generates
  nothing after sunset, so neither can touch the evening peak that sizes
  the transformer. `ai` is now curtailment-only; the solar package is
  judged separately, and its slightly-negative peak effect is **shown in
  the UI rather than averaged away**.

**Corrected district results** (24 societies × 3 arms, warm-up tick
excluded from statistics and disclosed in `district.json` meta):

| arm | trips | breaches | unserved | Σ peak |
|---|---|---|---|---|
| raw | 7 | 73 | 343.9 kWh | 4478.1 kVA |
| ai (coordination, zero capex) | **0** | **0** | **0.0 kWh** | 4072.3 kVA |
| full (+ solar package) | 0 | 0 | 0.0 kWh | 4114.5 kVA |

Coordination: **−406 kVA, zero capex, every trip removed.** Solar package:
**+42 kVA on peak** — disclosed as such. Coincident feeder peak now falls
at **20:45**, which is where a residential district peak belongs.

Adoption curve (real, worst-stressed-first rollout): 4103 → 3842 kVA at 6
societies → 3786 at 12, then flattening — genuine diminishing returns as
the remaining adopters are the unstressed ones.

`pytest -q` 26/26. All datasets regenerated.

### ✅ Phase 2 partial — 5 of 11 (#15, #19, #20, #25, #28)

- **#19 Reset** (topbar button + `R` key). Restores scenario, camera, speed,
  frame, selection, what-if, and — importantly — the **curated 6-society
  GridBrain cohort**, which the adoption slider deliberately overrides.
  Verified: scrambled to 24-deployed / district cam / EV75, reset returned
  6 / orbit / Normal day / frame 40.
- **#20 Topbar day sparkline.** Society A's whole-day loading with the
  rating line and a playhead, always visible. Verified drawing (920 non-empty
  pixels). Hidden under 1100 px so it never crowds the bar.
- **#25 Scenario lighting mood.** Per-scenario grade on fog/sky tint, bloom
  strength and exposure — heatwave warm haze, outage desaturated red, high-EV
  cool. Graded **on top of** the real sun position, never substituted for it.
- **#15 RDSS timeline.** Real public milestones (2021 sanction → FY2025-26
  end-date), stated so they can be checked, with an explicit non-affiliation
  note.
- **#28 Ops counters**, badged **mockup**: 1,314 sub-meters / 6 coordinators,
  derived from the real loaded district but framed honestly as a mockup of a
  console that does not exist.

### ✅ Phase 4 #10 — override audit trail (highest-integrity item)

The engine had always rolled a real override decision (`household.py`
`override_draws`) and thrown it away; `jsonio.py` exported
`"override_events": []` hardcoded. Now recorded per tick as
`HouseholdSeries.overrode`, aggregated in `society.py`, and exported for
real. Verified on `whatif_ev75_ai.json`: **20 curtail-house-ticks, 3 real
override events.** The inspector shows "Resident overrides honoured" per
house — so *"a quota signal, not a command"* is now checkable against
recorded behaviour instead of asserted.

### ✅ Phase 3 — Analysis tab (#5, #9, #11, #14, #16, #17)

New 6th rail tab. All arithmetic over fields already in the scenario JSON
plus two cited constants.

- **#5 Duck curve** — gross vs net-after-solar, belly and ramp annotated.
  Real: belly 0.0 kW at 10:00, steepest evening ramp **46.4 kW/h from
  17:30**.
- **#9 Comfort by archetype** — elderly households broken out (worst
  0.58 °C vs 0.00 for most).
- **#11 Transformer ageing** — IEC 60076-7-style relative rate, badged
  *illustrative model, real input*.
- **#14 + #16 Carbon & reliability** — 1651 kWh drawn / 1182 kg CO₂,
  453 kWh solar / −324 kg, at CEA's cited **0.716 kg/kWh**. Unserved
  energy and outage-minutes as the DISCOM-facing quantity.
- **#17 Five-year headroom** — today's real peak compounded at a *stated*
  6 %/yr assumption; breaches the 195 kVA rating in **year 1**.

### ✅ Phase 2 complete (#18, #22, #23, #24, #26)

- **#18 Trip dispatch banner**, shown only during a real TRIPPED tick,
  labelled *"restoration and crew movement are not simulated"*. Verified
  firing on the outage scenario at 15 min out.
- **#22 Confirm chime**, WebAudio, **default OFF** behind a topbar toggle —
  a sound firing unexpectedly in a live pitch is a liability.
- **#23 Coach marks**, one-shot, `localStorage`-gated, wrapped in try/catch
  for private mode.
- **#24 In-world data-path badge** — "PATH A · OWN SUB-METERS" floating on
  every district society, so the honesty claim sits where the society is.
- **#26 Archetype palettes** — hue biased by archetype (joint family warm
  terracotta → dual-income cool slate), reusing existing variants.

### ▶ Remaining: 5 items

**#21** split-screen compare, **#6** voltage-quality callout, **#13**
multi-state tariff, **#27** flexibility credits, **#29** case-study arc.
**Phase 5 (#2 seasonal, #4 weekday/weekend, #7 ensemble band, #8 rule-based
controller)** needs new generator runs and is deferred.

**33 of 38 delivered.** `pytest -q` 26/26. All datasets regenerated. Local
only, nothing pushed.

---

## 0. Ground truth — what is actually in the code today

Verified, not assumed:

| Thing | State today |
|---|---|
| `viz3d/main.js` night lighting | `sun.intensity = lerp(0.15, 2.5, dayness)` — **floor of 0.15 never reaches zero**. `sun.position.set(sx, Math.max(sy,-5), sz)` clamps the sun above the horizon. `hemi` floor 0.18, `ambient` floor 0.12. |
| `moonLight` | Declared at `main.js:183` with intensity 0, added to scene, **never referenced again**. Inert leftover. |
| Rail tabs | 4: `live`, `brain`, `solar`, `about`. |
| Reset control | **Does not exist.** |
| Topbar day-trend sparkline | **Does not exist.** Sparklines only render inside the inspector. |
| Forecast / uncertainty band | **Does not exist anywhere** in the world sim. |
| `override_events` in JSON | Exported as a **hardcoded empty list** (`jsonio.py:99`). |
| Override logic in engine | **Real and already running** — `household.py:118` `override_draws = rng.random(n) < archetype.override_probability`, consumed at `:147`. Computed, then thrown away. |
| Event types available | `heatwave`, `grid_outage`, `transformer_overload`, `cloud_cover`, `high_ev_arrival`, **`festival`**, **`holiday`**, `workspace_peak`, **`sensor_disturbance`** — the last three already declared but unused by any scenario. |
| Archetypes | 6, with real `share` weights. |
| Data files | 15 JSON files in `viz/data/`. |
| Generators | `generate_scenarios.py`, `generate_colony.py`, `generate_whatif.py`, `generate_solar_sync.py`. |
| Tests | 26 passing (`pytest -q`). |

Two of the 30 (#1, #30) were *diagnosed* earlier but explicitly left
unfixed on your "don't code" instruction. They are still open.

---

## 1. Honest triage — all 30 classified

**T1 = frontend only, existing data.** **T2 = frontend + a client-side
computation over existing data.** **T3 = engine change + data
regeneration.** **T4 = engine + new generator + new data files.**

| # | Item | Tier | Notes / honest caveat |
|---|---|---|---|
| 1 | Night lighting done properly | T1 | Real bug. Sun to true zero, wire up the dead `moonLight`. |
| 2 | Seasonal variation | T4 | `build_environment` already takes `base_temp_c` / `seasonal_amplitude_c`. 3 new runs. |
| 3 | India demand-spike calendar (Diwali, wedding season) | T3 | `festival` event type **already exists** in the schema, unused. Needs an effect implementation. |
| 4 | Weekday vs weekend occupancy | T4 | `generate_occupancy_trace` takes a `DatetimeIndex` — a Sunday date changes behaviour only if the archetype encodes day-type. Needs a real day-type branch, then 1 new run. |
| 5 | Duck-curve visualization | T2 | Pure read of `solar_kw` + `transformer_kva` already in every file. Highest value/cost ratio on this list. |
| 6 | Voltage-quality / harmonic callout at high EV | T2 | **Illustrative only.** The engine models no voltage or harmonics. Must be labelled a domain callout, not a simulated result, or it is a lie. |
| 7 | q05/q95 uncertainty band | T4 | Cannot be faked from one deterministic run. Honest version: a **20-seed ensemble**, band = real quantiles across realizations. |
| 8 | Third state: naive rule-based controller | T4 | The ampcast `₹12.87L / 31 breaches` figures are from the *commercial* benchmark, a different system — **cannot** be pasted onto the world sim. Needs a real rule-based controller in `transformer.py` + 3 runs. |
| 9 | Per-archetype comfort violation | T2 | `comfort_dev_c` + `archetype` already in every frame. Pure aggregation. |
| 10 | Override audit trail | T3 | Engine already computes overrides and discards them. Small, high-integrity fix. |
| 11 | Transformer thermal aging accumulator | T2 | Computable client-side from the `transformer_kva` series. Label the IEC-style curve illustrative. |
| 12 | Comms-dropout resilience | T3 | `sensor_disturbance` event type **already exists**, unused. |
| 13 | Multi-state tariff mode | T2 | Tariffs applied client-side to already-exported kWh. Real published tariff structures, cited. |
| 14 | DISCOM unserved-energy / SAIDI-style ₹ | T2 | `outage.json` + `TRIPPED` ticks already carry this. |
| 15 | RDSS rollout timeline | T1 | Static, public, checkable milestones. |
| 16 | Carbon avoided (CEA grid factor) | T2 | Real computation on already-tracked kWh. |
| 17 | 5-year compounding capex-deferral chart | T2 | Extends the existing `CAPEX_PER_KVA` readout. |
| 18 | Maintenance dispatch on trip | T1 | Dramatization — must be labelled illustrative. |
| 19 | Reset to defaults | T1 | Demo insurance. |
| 20 | Persistent topbar day sparkline | T1 | |
| 21 | Split-screen compare two societies | T1 | Society B/C data already loaded in memory. |
| 22 | Single confirm-chime on Coordinator toggle | T1 | WebAudio oscillator, no asset file. Default **off**. |
| 23 | First-time tooltip layer | T1 | |
| 24 | Per-society data-path badge in-world | T1 | |
| 25 | Per-scenario lighting mood | T1 | |
| 26 | Archetype-correlated house palettes | T1 | Reuses existing material system. |
| 27 | Flexibility-credit balance | T2 | Derived from the real fairness ledger. |
| 28 | Ops dashboard stat (labelled mockup) | T1 | |
| 29 | Year 0 / 1 / 3 case-study arc | T2 | Narrative over real what-if peaks. |
| 30 | Full-day projected ₹ alongside "so far" | T1 | Real bug-adjacent UX fix. |

**Totals: T1 ×12, T2 ×11, T3 ×3, T4 ×4.**

---

## 2. The honesty rules that constrain this build

Non-negotiable, and they shape several items above:

1. **Nothing invented gets presented as simulated.** #6 (voltage/harmonics)
   and #18 (crew dispatch) are *not* modelled by the engine. They ship with
   an explicit "domain callout — not simulated here" label, or they don't
   ship.
2. **No cross-system number laundering.** #8's `₹12.87L / 31 breaches` come
   from the commercial ampcast benchmark on real BDG2 data. Pasting them
   into the world sim would be a fabrication. The world sim gets its **own**
   rule-based controller and its **own** real numbers.
3. **An uncertainty band must come from real variance.** #7 is a 20-seed
   ensemble or it is not built.
4. **Illustrative tariffs stay labelled.** `ILLUSTRATIVE_TARIFF` (₹7.2/kWh)
   and `ILLUSTRATIVE_EXPORT_RATE` (₹3.5) are not filed rates. #13 adds real
   published *structures* and cites them as such; the illustrative default
   stays visibly marked.
5. **Every new engine flag defaults to reproducing today's behaviour**, and
   that is verified by `git status` showing zero diff on existing outputs
   before the new generator runs. This is the pattern already used for
   `enable_curtailment` and `enable_solar_sync`.

---

## 3. Build phases

Ordered so the system is demo-safe at every phase boundary, and so the
cheap high-impact wins land before the expensive ones.

### Phase 1 — Fix the two real defects (#1, #30)

Both were diagnosed and deliberately left open. They go first because one
is an actual rendering bug and the other makes a headline number read as a
dead zero.

- `main.js` `applyFrame()`: replace the lighting floors.
  - `sun.intensity = lerp(0, 2.5, smoothstep(dayness))`, true zero below
    the horizon; drop the `Math.max(sy, -5)` position clamp so the sun
    actually sets.
  - Wire the dead `moonLight` (`main.js:183`): position it opposite the
    sun, intensity ramps in as `dayness → 0`, cool blue, its own soft
    shadow off. Night becomes moonlit, not "dim daylight".
  - Lower `hemi` floor 0.18 → 0.04, `ambient` floor 0.12 → 0.03.
  - Streetlights and window glow become the dominant night light sources —
    which is the whole point of having simulated them.
- `costExposure()`: return `projectedCost` and `projectedShiftSaving`
  computed over **all** frames, not just `0..frameIdx`. Inspector shows
  "₹X so far · ₹Y projected today". Deterministic dataset, so the
  projection is exact, not a guess — label it "full-day, this dataset".

**DoD:** at 00:15 the recoverable figure is non-zero and honest; at 23:45
"so far" and "projected" converge exactly. Night screenshot is visibly
night.

### Phase 2 — Frontend-only batch (#15, #18, #19, #20, #21, #22, #23, #24, #25, #26, #28)

Eleven T1 items, no data dependency, no engine risk.

- **#19 Reset** — topbar button: scenario → `normal`, frame → 40, speed →
  1×, what-if cleared, selection cleared, camera → orbit, rail → `live`.
- **#20 Topbar sparkline** — 96-point `transformer_kva` trend with the
  rating line and a playhead dot, always visible.
- **#25 Scenario lighting mood** — a per-scenario grade applied to fog
  colour + `bloom.strength` + sun tint: heatwave = warm haze, outage =
  desaturated with emergency-red key, normal = neutral, high_ev = neutral
  cool. Data-driven off `data.meta.scenario`.
- **#26 Archetype palettes** — extend `wallVariantFor()` to bias hue by
  archetype (joint_family → warm earth, dual_income → cool modern, etc.).
  No new textures, no new draw calls.
- **#21 Split-screen compare** — a `compare` camera mode rendering Society
  A and Society B side by side with both transformer bars visible. Society
  B/C data is already resident in `colonyData`.
- **#24 In-world data-path badge** — floating label per society: "Path A
  available / Path B not available / Path C fallback", mirroring the About
  tab so the honesty claim is visible in the world, not buried in a tab.
- **#23 First-time tooltips** — one-shot coach marks on the 4 rail tabs +
  what-if panel, dismissible, `localStorage`-gated.
- **#22 Confirm chime** — WebAudio oscillator, ~120 ms, fires **only** on
  the AI Coordinator toggle. Ships **default-off** behind a topbar speaker
  icon; a chime that fires unexpectedly in a live pitch is a liability.
- **#15 RDSS timeline** — static milestone strip in the About tab, real
  public dates, cited.
- **#18 Restoration dramatization** — on `TRIPPED`, a crew marker animates
  from the colony edge to the affected transformer with an ETA readout,
  explicitly badged "illustrative — restoration times not simulated".
- **#28 Ops stat block** — "N sub-meters reporting · M coordinators
  active", badged **mockup**, in the About tab.

**DoD:** zero console errors; every new label that is not simulated
carries its disclaimer; reset restores a known-good state from any
scrambled state.

### Phase 3 — Client-side analytics batch (#5, #9, #11, #13, #14, #16, #17, #27, #29, #6)

A new **`Analysis`** rail tab (5th) holds most of these, so the Live tab
stays clean for the walk-through.

- **#5 Duck curve** — net-load-after-solar curve for the day with the
  midday belly and evening ramp annotated, and the ramp rate in kW/h
  called out. This is the single most recognizable utility chart on the
  list and it is computable today from `solar_kw` + `community_solar_kw` +
  `transformer_kva`.
- **#9 Per-archetype comfort** — mean and worst `comfort_dev_c` grouped by
  archetype, with `elderly_couple` broken out. Answers "who pays the
  comfort cost of your curtailment", which is the sharpest fairness
  question a judge can ask.
- **#11 Transformer aging** — cumulative loss-of-life over the day using a
  simplified IEC 60076-7-style relative-aging curve on the loading series.
  Labelled illustrative model, real loading input.
- **#13 Multi-state tariff** — a selector re-costing the same day under 2–3
  real published state tariff *structures*, each cited by name; the
  illustrative default stays labelled as illustrative.
- **#14 DISCOM unserved-energy** — `TRIPPED` ticks × shed load → unserved
  kWh → an outage-minutes figure, framed as the DISCOM-facing reliability
  angle distinct from the RWA-facing savings angle.
- **#16 Carbon avoided** — energy shifted/curtailed × a stated CEA grid
  emission factor, factor cited inline.
- **#17 5-year capex chart** — compounds the existing per-setting deferred
  kVA under a stated load-growth assumption; assumption shown on the chart.
- **#27 Flexibility credits** — per-house credit balance derived from the
  real fairness ledger, framed as the consumer-facing product surface of a
  metric that already exists.
- **#29 Case-study arc** — Year 0 / Year 1 / Year 3 narrative built on the
  **real** what-if peaks at EV 20/40/75, so the arc is a reading of real
  data rather than a story pasted over it.
- **#6 Voltage-quality callout** — a short, clearly-badged domain note on
  the high-EV scenario. **Not simulated.** Ships as a callout or not at
  all.

**DoD:** every figure traceable to a named field in the JSON or a cited
external constant; nothing labelled "simulated" that isn't.

### Phase 4 — Engine changes, existing data shape (#3, #10, #12)

All three use event types **that already exist in the schema and are
currently unused**, or logic that already runs and is discarded.

- **#10 Override audit trail** — `household.py` already computes
  `override_draws`. Add an `overrides` bool array to `HouseholdSeries`,
  thread it through `society.py`, and replace the hardcoded
  `"override_events": []` in `jsonio.py:99` with the real per-tick list.
  This turns a stubbed field into a true one — the highest integrity-gain
  change in the whole plan.
- **#3 Festival load** — implement the `festival` effect in
  `engine/events.py`: a lighting-load adder plus an occupancy bump, applied
  over the event window. New `festival.json` scenario.
- **#12 Comms dropout** — implement `sensor_disturbance`: a subset of
  houses stop reporting for a window. Export a `reporting: false` flag; the
  renderer greys those houses and the GridBrain ledger says it is holding
  last-known values and coordinating on the rest. Demonstrates graceful
  degradation instead of claiming it.

All three land behind flags/events that default off. `pytest -q` must stay
green; existing outputs must be byte-identical except for the new
`override_events` field (an intentional, disclosed schema addition — same
call already made for `community_solar_kw`).

### Phase 5 — New generators and datasets (#2, #4, #7, #8)

The expensive tier. Each produces real new simulation runs.

- **#8 Rule-based controller** — add `control_mode: "none" | "rule" | "ai"`
  to `decide_transformer_state_and_curtailment`. The `rule` mode is a naive
  fixed-schedule curtailment (shed on a clock, ignore actual loading) — the
  honest strawman a real utility would deploy. `generate_control_modes.py`
  → 3 runs at EV 75. The what-if panel becomes **three** states, and the
  comparison is finally live in the world instead of stranded in a table.
- **#2 Seasonal** — `generate_seasons.py` at three `base_temp_c` /
  `seasonal_amplitude_c` settings (monsoon / peak-summer / mild-winter) →
  3 files. Shows stress migrating seasonally, which is the argument for
  sizing to the worst month.
- **#4 Weekday/weekend** — add a real day-type branch to
  `generate_occupancy_trace` (offices empty, homes fuller), then one
  Sunday run. Guard: if the resulting load shapes are not *visibly*
  distinct, this ships as a documented finding rather than a slider that
  does nothing — the same call already made when the heatwave what-if axis
  was dropped.
- **#7 Uncertainty band** — `generate_ensemble.py`, 20 seeds at fixed
  settings, exporting only the per-tick q05/q50/q95 of `transformer_kva`
  (a small summary file, not 20 full runs). The band is then real variance
  across real realizations — the one visual most on-brand for a
  chance-constrained pitch.

**DoD per generator:** printed peak/state summary reviewed for
plausibility before the file is accepted; determinism re-checked (same
seed → identical output); `viz/data/` growth kept in check by exporting
summaries, not full runs, where only a summary is displayed.

---

## 4. Risk register

| Risk | Mitigation |
|---|---|
| #4 (weekday/weekend) produces no visible difference | Ship as a documented finding, not a dead slider. Precedent: the dropped heatwave what-if axis. |
| #8's rule-based controller accidentally looks *better* than the AI | That would be a real result and gets reported as one. It is also unlikely — a clock-based shedder ignores actual loading by construction. |
| Scope creep across 30 items degrades the core demo | Phases 1–3 are self-contained and demo-safe. If Phase 5 runs long, the sim still ships strictly better than today. |
| `viz/data/` bloat slows first load | Ensemble and season data export as summaries where only summaries are shown. Lazy-load anything not needed at boot. |
| New rail tab crowds the rail on mobile | The rail already scrolls; verify at 375 px before calling Phase 3 done. |
| A disclaimer gets dropped in editing | Phase DoD explicitly re-checks every non-simulated label before sign-off. |

---

## 5. Definition of done — whole plan

- [ ] `pytest -q` green (26+, plus new engine tests for override export,
      festival, sensor dropout, and control modes).
- [ ] Zero console errors on load and after exercising every new control.
- [ ] Every displayed number traceable to a JSON field or a cited constant.
- [ ] Every non-simulated element carries a visible disclaimer.
- [ ] Reset (#19) restores a known-good state from any scrambled state.
- [ ] Determinism re-verified on all regenerated files.
- [ ] Existing outputs byte-identical except the disclosed `override_events`
      schema addition.
- [ ] Verified at 375 px and at presentation zoom.
- [ ] `WORLD_SIM_STATUS.md` updated to describe the delivered state.
- [ ] Everything local. Nothing pushed.

---

## 6. Sequencing summary

```
Phase 0  #31–#38 + 24-society world               8 items   engine + generator  <-- FIRST
Phase 1  #1  #30                                    2 items   real defects
Phase 2  #15 #18 #19 #20 #21 #22 #23 #24 #25 #26 #28  11 items  frontend only
Phase 3  #5  #6  #9  #11 #13 #14 #16 #17 #27 #29     10 items  new Analysis tab
Phase 4  #3  #10 #12                                 3 items   engine, flags off
Phase 5  #2  #4  #7  #8                              4 items   new generators
                                                     ────────
                                                     38 items
```

---

## 7. Phase 0 — The populated colony (24 societies, 6 managed)

### 7.1 What changes

Today: 3 societies (A at full 3D detail, B and C simplified, 156 households).
After: **24 societies, all simulated at Society A's depth**, ~1,300
households. **6 run under GridBrain, 18 run unmanaged** — and the 18 are
not scenery, they are real simulation runs whose transformers genuinely
trip because nothing is protecting them.

This is the difference between "here is our society" and "here is a
district, and you can see which blocks we're in."

### 7.2 The matched-pair design (this is the important part)

The obvious failure mode of a managed-vs-unmanaged comparison is that a
judge asks: *"did the managed ones win because of your AI, or because you
gave them easier parameters?"*

So the population is built in **12 matched pairs**. Each pair shares an
identical seed, household count, EV penetration, solar penetration,
archetype mix, and transformer rating. The **only** difference between the
two members is `enable_curtailment` (+ solar-sync on the managed member).
6 pairs contribute their managed member to the "GridBrain" cohort; the
remaining pairs run unmanaged on both sides to fill out the district.

That makes the comparison a **controlled experiment, not a demo**, and the
UI states it explicitly. The twin dataset is available for every managed
society, so "prove it" is one click, not a promise.

### 7.3 Data architecture (forced by size)

Measured: one 60-household society ≈ **1.3 MB**. 24 of those ≈ 30 MB —
fine on disk, unacceptable as a page load. Two-tier export:

- **`viz/data/district.json`** — static metadata for all 24 societies plus
  a per-tick rollup per society (`kva`, `state`, `total_kw`, `solar_kw`,
  `curtailed_count`, `unserved_kwh`). 24 × 96 × ~8 numbers ≈ **under
  500 KB**. This is the only file the colony view needs, and it loads at
  boot.
- **`viz/data/soc_<id>.json`** — the full per-household detail, generated
  for all 24 but **lazy-loaded only when the camera flies into that
  society**. Boot cost stays flat as the district grows.

### 7.4 3D architecture (forced by draw calls)

1,300 detailed house groups is not renderable. Level-of-detail:

- **District view** — every society is a block: real transformer bar, real
  state colour, and its houses drawn via a single `InstancedMesh` per
  society (or one for the whole district). Managed societies carry a
  GridBrain link beam; unmanaged ones visibly do not.
- **Society view** — flying in swaps that one society to the existing
  full-detail path (`buildHouseGroup`) and loads its detail file.
- Existing detail geometry is reused unchanged; only the selection and
  build path become LOD-aware.

### 7.5 New items falling out of this (#31–#38)

| # | Item | Why it only works now |
|---|---|---|
| 31 | **Managed vs unmanaged scoreboard** | Aggregate ₹, peak kVA, trips, unserved kWh, comfort violations across the two cohorts. Needs a population to average over. |
| 32 | **Shared-feeder coincidence view** | Unmanaged peaks land on top of each other; managed ones stagger. Shows *network* value, which a single society cannot demonstrate. |
| 33 | **Adoption slider (0 → 24 managed)** | Upstream feeder peak as a function of how many societies are covered. The DISCOM-facing argument, and the natural answer to "why should the utility care". Real, from discretely generated adoption levels. |
| 34 | **League table** | All 24 ranked by ₹/household, headroom, trips avoided, comfort violations. Managed cluster at the top — visibly, not rhetorically. |
| 35 | **"Deploy GridBrain here"** | Click an unmanaged society → it swaps to its managed twin dataset live. The single strongest demo interaction available, and it is honest because both datasets are real. |
| 36 | **Matched-pair proof panel** | Shows the two members of a pair share seed/size/EV/solar/rating and differ only in the control flag. Pre-empts "you rigged it". |
| 37 | **District-scale capex + carbon** | Per-society numbers are small; 24 societies makes deferred capex and avoided carbon material enough to matter to a utility. |
| 38 | **Failure heatmap** | 24 × 96 grid, red where a society was BREACH/TRIPPED. Managed rows are visibly clean stripes. One image that carries the entire argument. |

### 7.6 Honesty constraints specific to Phase 0

1. **The 18 unmanaged societies are real runs**, not red rectangles. If an
   unmanaged transformer shows TRIPPED, the engine actually tripped it.
2. **Managed societies must not be given easier parameters.** Enforced
   structurally by the matched-pair design, and the generator prints both
   members' parameters side by side so any drift is visible.
3. **If the managed cohort's advantage is small, that gets reported as the
   result.** Same call already made when the heatwave what-if axis was
   dropped for showing no measurable effect.
4. **Aggregate ₹ figures stay on the illustrative tariff** and keep their
   existing label. Scale makes the number bigger; it does not make it
   filed.

### 7.7 Phase 0 definition of done

- [ ] 24 societies generated, parameters printed as 12 matched pairs.
- [ ] `district.json` under 500 KB and loading at boot.
- [ ] Detail files lazy-load on fly-in; boot time not measurably worse.
- [ ] District view holds interactive framerate with all 24 rendered.
- [ ] Scoreboard, league table, heatmap read only from real rollup fields.
- [ ] "Deploy GridBrain here" swaps to a real twin dataset.
- [ ] Matched-pair panel shows real parameter equality.
- [ ] `pytest -q` still green; existing files unchanged.
