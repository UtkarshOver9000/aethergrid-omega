# AETHERGRID — current status

A factual snapshot of what exists and runs today. No pending work, no
suggestions, no roadmap — that's in `EXECUTION_PLAN.md` and the pitch docs.
This is just what's actually built.

Both apps are local-only: served from a static file server on
`localhost:8020`, nothing pushed to any remote.

---

## World simulation (`viz3d/`)

A real Three.js WebGL 3D scene, not a mockup — every value shown comes from
a precomputed JSON scenario file produced by the Python engine in
`aethergrid/worldsim/`.

**The colony**: three societies on a shared feeder.
- **Society A** — 60 households, the fully detailed build: real photographed
  CC0 PBR materials (brick, stucco, wood siding, roof tile, grass, asphalt,
  paving stone, concrete), individual doors, framed windows, rooftop water
  tanks, wall-mounted AC units and geysers with their own indicator lights
  tied to real on/off state, boundary hedges, paved yards, parked cars,
  and a workspace building.
- **Society B** — 48 households, an older/smaller transformer, simplified
  geometry (shared wall/roof materials, one window per face, no yard
  props) to keep total scene cost sane with three societies live at once.
- **Society C** — 48 households, a newer/better-rated transformer, same
  simplified tier as B.
- All three run independently generated real synthetic data (not shared
  or copied between them), on the same simulated day and 96-tick clock, so
  scrubbing the timeline moves all three in sync.

**GridBrain** — the visible coordination layer, reachable via its own rail
tab:
- A glowing wireframe hub positioned above the colony, connected to each
  society's transformer by an animated light beam whose speed and color
  respond live to that specific transformer's real current stress level.
- A live decision ledger: plain-English lines generated directly from each
  society's own already-simulated curtailment output ("House #13 curtailed
  — transformer at 85% (WARNING)") — not a separate authored layer.
- A cross-society headroom comparison, computed live and explicitly
  labeled as a recommendation (automated cross-feeder transfer is not
  simulated).
- A node-map summary of all three societies' live states, with each row
  clickable to fly the camera directly to that society.

**What-if panel + AI Coordinator toggle** (floating panel, bottom-left of
the 3D stage):
- Three real EV-penetration levels for Society A — 20%, 40%, 75% — each
  backed by a real, independently generated dataset at one fixed
  transformer rating (280 kVA).
- Each EV level exists as a real pair: one run with the engine's
  transformer-protection curtailment logic enabled, one with it disabled
  (`enable_curtailment` flag in `aethergrid/worldsim/engine/transformer.py`).
- Flipping the toggle swaps between the two real datasets for the current
  EV level and re-renders the same time window — at EV 75%, this is a real
  291.7 kVA BREACH (AI off) versus a real 240.4 kVA WARNING (AI on) at the
  same tick.
- A live readout computes the illustrative capex-deferral rupee figure
  from the real kVA difference between the two runs, using the same
  ₹1,200/kVA constant as the commercial calculator.

**Scripted tour** — a "Play tour" button in the topbar runs a fixed,
deterministic ~70-90 second camera choreography: colony overview → Society
B stress → Society C headroom → AI Coordinator flipped on with the
transformer visibly recovering → GridBrain ledger → a house inspector →
pull back to the hub. All manual interaction is disabled for its duration
and restored cleanly on completion or on Escape.

**Presentation mode** (topbar button or `P` key) — hides the legend and
hint text and enlarges KPI text, for narrated moments.

**Camera modes**: Orbit (free look around Society A), Top-down
(orthographic), Colony (pulled back to see all three societies + the hub).

**Theme picker** — five color palettes (cyan, gold, crimson, silver, black
& white) swap the UI's accent colors live via a topbar swatch row.

**Per-house inspector** (click any house): live load, occupancy, indoor
temperature, comfort deviation, AC/geyser state, EV/solar/battery status
where applicable, a sub-meter energy/cost readout (illustrative tariff,
clearly labeled as such), an "if peak-window load shifted off-peak"
recoverable-₹ figure computed as direct arithmetic on that reading, and a
"GridBrain facilities on this house" panel (sub-metering, fair-rotation
protection, real recorded curtailment hours today, colony headroom
awareness).

**Traffic**: a handful of cars plus one bus per society, each following a
real shared perimeter road loop with smoothly interpolated cornering,
animated in real time independent of playback speed.

**Environment**: real sun-position astronomy driving a directional light,
a separate sun disc/halo and a separate moon object with its own
procedural cratered texture, a starfield at night, drifting cloud sprites,
and weather (temperature, humidity, cloud cover) read directly from the
simulation data.

**Scenarios**: four playable representative days — Normal day, Heatwave,
High EV, Grid outage — each a real, independently generated dataset.

**Data & method tab**: states plainly what's synthetic (the household
behaviour and archetypes), what's real (the sub-meter data path, the
separate single-building benchmark on Building Data Genome Project 2 and a
real published Tamil Nadu tariff), and does not claim the world sim's
households are measured data.

---

## Commercial pitch (`commercial3d/`)

A 12-slide, arrow-key/click/dot-navigated slideshow — not a click-hunt
node graph.

**Two navigation modes**: Deep-dive (all 12 slides) and Pitch mode (a
6-slide subset — hook, evidence, proof-at-scale, buyers, calculator, ask —
matched to the 60-second script in `PITCH_PREP.md`), switchable from the
topbar, always landing on the same slide by id across modes.

**The 12 slides**: hook, the problem, a system map (an animated node
network as a purely visual overview, six nodes radiating from a central
hub), the method (the real q95 substitution formula plus the
sense/decide/act loop), evidence (an animated bar-chart comparison of a
real benchmark's monthly bill, before/after, with a live count-up), proof
at scale (citing the world sim's real Society B/C numbers, with a live
embedded iframe of the running world sim itself), the buyer ladder, a live
ROI calculator (two modes: bulk-HT demand-charge and transformer-capex
deferral, both fully interactive), an honest data-sources slide (what's
real today versus what's planned but not yet integrated, named
specifically), the competitive wedge, how the mechanism scales further,
and the ask.

**Autoplay**: per-slide dwell timing, with the calculator slide set to
pause rather than auto-advance so live interaction with it is never
interrupted.

**Cross-linking**: both apps have a topbar link to the other, opening in a
new tab.

---

## Underlying engine (`aethergrid/worldsim/`)

Python, deterministic and seeded. Per 15-minute tick: environment/weather,
occupancy, appliances (AC/geyser/EV/battery/solar), a real RC thermal
model per household, aggregation to a transformer, and a real state
machine (NORMAL/WARNING/CRITICAL/BREACH/TRIPPED) that — when curtailment
is enabled — actually sheds the highest-load flexible appliance among
households not yet curtailed in the current rotation, and logs exactly
which households and how much.

**Generation scripts**: `generate_scenarios.py` (the four base scenarios),
`generate_colony.py` (Societies B and C), `generate_whatif.py` (the six
EV-level × AI-on/off pairs at the fixed 280 kVA calibrated rating).

**Test suite**: 26 tests, passing, unaffected by the `enable_curtailment`
addition (its default value reproduces the original four scenario files
byte-for-byte, confirmed via `git status` showing zero diff).

---

## Documentation on file

`PITCH_PREP.md` (60-second pitches for both apps plus judge counter-
questions), `EXECUTION_PLAN.md` (the plan this build executed against, with
its final checklist), `WINNING_STRATEGY.md` and `GRID_BRAIN_VISION.md`
(the earlier strategic reasoning that shaped the GridBrain and what-if
design).
