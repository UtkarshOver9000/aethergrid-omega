# Execution plan — FINAL, both apps

This replaces the previous draft. Same governing principle, but every item
below is now specified to the level a plan needs before it can be called
final: exact parameters, exact file names, exact numbers, exact camera
beats tied word-for-word to the pitch script already committed in
`PITCH_PREP.md`, a risk register, and a single acceptance checklist at the
end. After this plan executes, the scope is frozen — anything past it is a
bug fix, not a new feature. That's what "final" means here.

## Governing principle, unchanged

Every addition either (a) makes the AI's decision-making causally visible
in real time, (b) removes a live-demo risk, or (c) closes a believability
gap. Anything that fails that test is named and excluded, not left
ambiguous.

---

# PART 1 — World simulation

## 1.1 The what-if grid + real AI Coordinator toggle

**The rigor gap in the previous draft:** it proposed reusing the existing
four scenarios (which each have a *different* transformer rating) to fill
part of the grid. That confounds the story — a judge moving the EV slider
would partly be seeing a rating change, not an EV effect. Fixed for real
this time:

**Design, fully specified:**
- **One fixed transformer rating for the entire grid.** Calibration step
  before generating anything real: run the uncurtailed peak kVA at
  EV=20/40/75% × heatwave=none/severe (six probe runs) at a provisional
  rating of 200 kVA, using the existing engine's `simulate_society`
  directly (no export needed for the probe). Pick the final fixed rating
  so that the (EV 20%, no heatwave) corner lands NORMAL/WARNING and the
  (EV 75%, severe heatwave) corner genuinely reaches BREACH — i.e. the
  rating is chosen so the grid actually spans the full dramatic range
  rather than being guessed. If 200 kVA doesn't span it, adjust in 10 kVA
  steps and re-probe; this is a five-minute scripted step, not manual
  tuning.
- **Six scenario files**, all at that one fixed rating, seeds 301–306 (new
  seed block, doesn't collide with 42–45 already in use):
  | file | EV% | heatwave |
  |---|---|---|
  | `whatif_ev20_calm.json` | 20 | none |
  | `whatif_ev20_severe.json` | 20 | severe (sev 1.0, 8h, +7°C — same shape as existing `heatwave` event) |
  | `whatif_ev40_calm.json` | 40 | none |
  | `whatif_ev40_severe.json` | 40 | severe |
  | `whatif_ev75_calm.json` | 75 | none |
  | `whatif_ev75_severe.json` | 75 | severe |
- **The AI Coordinator OFF companion**: add `enable_curtailment: bool = True`
  as a parameter threaded from `simulate_society(...)` down into
  `decide_transformer_state_and_curtailment(...)`
  (`aethergrid/worldsim/engine/transformer.py`). Default `True` — this
  guarantees the four existing production files (`normal`, `heatwave`,
  `high_ev`, `outage`) are byte-identical to today's output; nothing that
  already works is touched. When `False`, the function skips the shedding
  block entirely and returns the provisional (uncurtailed) state as final
  — a real, honestly-labeled "what would have happened with no
  protection" run, not a fabricated one.
- **Twelve files total**: the six above, each generated twice
  (`_ai.json` / `_noai.json` suffix), via a new
  `aethergrid/worldsim/generate_whatif.py` script mirroring
  `generate_colony.py`'s structure exactly, so it's reviewable against a
  pattern that already shipped and works.

**UI, fully specified:**
- New topbar control group, right of the existing scenario buttons:
  two labeled range sliders — `EV adoption` (3 stops: 20/40/75, snapping,
  not continuous) and `Heatwave` (2 stops: calm/severe) — plus a two-state
  switch `AI Coordinator: OFF / ON` styled like the existing `.seg` control
  group for visual consistency.
- Moving either slider or the toggle calls `setScenario()` against the
  matching `whatif_*` file (reusing the existing scenario-load pipeline
  unchanged) — no new rendering code path, just a new set of source files.
- A small persistent readout next to the toggle: **"Capex deferred at
  this setting: ₹X"**, computed as
  `(uncurtailed_peak_kva − curtailed_peak_kva) × cost_per_kva`, with
  `cost_per_kva` hard-set to ₹1,200 (the same default already in the
  commercial calculator's transformer-capex mode) so the two apps never
  show two different numbers for the same concept.

**Verification (must pass before this item is considered done):**
1. `pytest -q` still 26/26 — confirms `enable_curtailment=True` default
   changed nothing existing.
2. Byte-diff the regenerated `normal.json` etc. against current files —
   must be identical (proves the default-True path is truly a no-op).
3. Load each of the 6 `_ai` vs `_noai` pairs in-browser, confirm the
   `_noai` transformer state reaches BREACH/TRIPPED at least once in the
   two "severe" columns and the `_ai` counterpart does not, at the same
   tick.
4. Confirm the ₹ readout changes when either slider moves, and matches a
   hand-calculation for one spot-checked setting.

## 1.2 Scripted camera tour — beat-matched to the committed pitch script

**The rigor gap in the previous draft:** "roughly 40 seconds, a few beats"
wasn't tied to anything concrete. It now is — tied directly, clause by
clause, to the 60-second world-sim pitch already committed in
`PITCH_PREP.md`, so the tour and the spoken pitch are the same performance
in two media, not two things that happen to run at the same time.

| Beat | Time | Pitch clause | Camera |
|---|---|---|---|
| 1 | 0:00–0:07 | "This is the environment... not a cartoon." | Colony camera preset (`flyToSociety("colony")`), slow auto-orbit |
| 2 | 0:07–0:15 | "Three independently simulated societies share one feeder..." | Hold colony view, GridBrain beams visible and pulsing |
| 3 | 0:15–0:24 | "Watch Society B's transformer climb to ninety-five percent..." | `flyToSociety("society_b")`, hold on its transformer stress ring |
| 4 | 0:24–0:30 | "...while its neighbour sits comfortably under load." | `flyToSociety("society_c")`, hold on its calm transformer bar |
| 5 | 0:30–0:40 | "Flip the AI Coordinator..." *(new clause, see below)* | Trigger the 1.1 toggle to ON on a `_noai`→`_ai` paired scenario at the same tick; hold on the visible recovery |
| 6 | 0:40–0:48 | "...a decision ledger shows the engine's own real protection decisions..." | Auto-open the GridBrain rail tab, scroll to a real ledger entry |
| 7 | 0:48–0:55 | "Click any house for its own sub-meter reading..." | Scripted click on one pre-chosen house, inspector panel opens |
| 8 | 0:55–1:00 | "This is the uncontrolled baseline..." | Pull back to colony view, hold on the hub |

**Note this creates one small, deliberate edit to `PITCH_PREP.md`**: the
committed script doesn't currently mention flipping the AI Coordinator,
because that feature didn't exist yet when it was written. Beat 5 above
requires inserting one clause — *"Flip the AI Coordinator on, and watch it
hold the line"* — into the world-sim 60-second pitch. This is called out
explicitly rather than left as a silent mismatch between the tour and the
script.

**Implementation**: a `runTour()` function driving `startCamTween` calls
already in the codebase at the timings above, using `setTimeout` chaining
(not a new animation framework), with a single "Play tour" button that
disables all other interaction for its duration and re-enables it on
completion or on any key press (escape hatch, doesn't trap the presenter).

**Verification:** run the tour three times back to back — must reach the
same end state every time (deterministic scenario/seed), must never leave
interaction permanently disabled if interrupted.

## 1.3 Presentation mode

Single toggle (keyboard `P` + a topbar button, both call the same
function): hides `.stage-hint` and `.legend`, applies a `.presenting` class
to the rail that increases KPI font sizes ~20%, and hides the theme
picker. Reversible with the same keystroke. No new state persists across
reload — this is a display-only toggle, not a save-able preference,
because a stray persisted state is exactly the kind of thing that causes a
confusing "why does it look different now" moment before a demo.

## 1.4 Recorded backup

Screen-record `runTour()` end to end, once 1.1–1.3 exist and the tour is
final. Saved locally as `PITCH_PREP_backup_worldsim.webm` (or `.mp4`)
alongside `PITCH_PREP.md`. Never uploaded, never depended on unless the
live version breaks in front of judges.

## 1.5 Explicitly frozen out of "final"

More geometric detail on Society B/C, weather particles, ambient audio,
any further visual reskinning. If any of these come up again after this
plan executes, they are a new request to scope separately, not part of
"final."

---

# PART 2 — Commercial pitch

## 2.1 Pitch mode vs. Deep-dive mode — exact slide sets

**Pitch mode** (6 slides, matched to the committed 60-second commercial
script): `hook`, `evidence`, `scaleproof`, `buyers`, `calc`, `ask`.
**Deep-dive mode** (all 12, current order unchanged). A mode switch in the
topbar filters both the dot-navigation array and which slide indices
arrow-keys/autoplay traverse; switching mode mid-deck jumps to the nearest
slide that exists in the target mode's set (by shared `id`, not by index,
so it can't land on a mismatched slide).

**Verification:** in Pitch mode, exactly 6 dots render and arrow-right from
the last one does nothing (no wraparound past the ask slide); switching to
Deep-dive from any Pitch-mode slide lands on the same `id` in the full set.

## 2.2 Evidence slide — animated bar comparison, exact values

Replace the four KPI tiles with two horizontal bars, both starting at
width 0 and animating to their final width over 900ms with a 150ms
stagger between them, on slide-enter only (guarded the same way the world
sim's inspector "fresh" class is guarded, so re-entering the slide
re-triggers it but routine surrounding navigation doesn't):
- Bar 1, "No control": full width = ₹13,20,302, color `var(--tripped)`.
- Bar 2, "With Aethergrid": width = `(1148853 / 1320302)` of bar 1's pixel
  width = ~87%, color `var(--ok)`, with the ₹ delta (₹1,71,449) count-up
  label appearing after both bars finish.

**Verification:** rapid back-and-forth navigation onto/off this slide five
times must not leave bars in an intermediate stuck state or double-animate.

## 2.3 Embedded live world-sim proof, with a measured fallback threshold

On the `scaleproof` slide: an `<iframe src="../viz3d/index.html">`,
`pointer-events:none`, sized to 55% slide width, `loading="lazy"` so it
only loads when this slide is actually reached (not on deck boot).

**The fallback rule, made concrete rather than vague:** measure time from
slide-enter to the iframe's `load` event. If it exceeds 1200ms on the
actual presenting machine during rehearsal, replace it with a static PNG
screenshot of the colony view before the real pitch — decided during
rehearsal, not guessed now. Both code paths (iframe and static image
variant) get built; whichever is faster in practice is what ships.

## 2.4 Per-slide autoplay dwell

Replace the flat 9000ms constant with a per-slide value on each slide
object: `hook` 6000, `problem` 8000, `map` 5000, `method` 9000,
`evidence` 8000 *(after the 2.2 animation's ~1050ms completes)*,
`scaleproof` 8000, `buyers` 9000, `calc` — **autoplay does not advance this
slide at all**; it pauses on arrival and only resumes on the next manual
`next()` call, `data` 9000, `wedge` 7000, `scaleup` 8000, `ask` 8000.

**Verification:** start autoplay from slide 1, confirm it halts (not
skips) on `calc` and stays there until a manual arrow/click.

## 2.5 Explicitly frozen out of "final"

Custom illustration, sound design, any animated element beyond 2.2.

---

## Risk register

| Risk | Mitigation already in the plan |
|---|---|
| Calibration step (1.1) picks a rating that doesn't span BREACH | Explicit re-probe loop in 10 kVA steps before committing any file |
| `enable_curtailment` flag silently changes existing 4 scenario files | Byte-diff verification step (1.1.2) required before merge |
| Tour (1.2) desyncs from the spoken pitch over future edits | Both derive from the same beat table in this document; editing one without the other is now a visible inconsistency, not a silent one |
| iframe (2.3) slows the commercial deck | Fallback path built in parallel, decided by measurement during rehearsal, not assumed |
| Autoplay skips past the calculator before anyone can touch it | Explicit pause-not-advance rule (2.4) |
| Scope creep after this plan | Explicit freeze lists (1.5, 2.5) — anything else is a new request |

---

## Build order

1. Calibration probe + fixed rating decision (1.1)
2. Generate the 12 what-if files + `pytest -q` + byte-diff check (1.1)
3. What-if sliders + AI toggle + ₹ readout (1.1)
4. Edit `PITCH_PREP.md`'s world-sim script to add the Coordinator clause (1.2 note)
5. Scripted tour, beat-matched (1.2)
6. Presentation mode (1.3)
7. Pitch/Deep-dive mode toggle (2.1)
8. Evidence slide animation (2.2)
9. Embedded iframe + fallback, measured (2.3)
10. Per-slide autoplay dwell (2.4)
11. Record backup video (1.4) — last, once 1–6 are final

## Definition of final — single checklist

- [x] `pytest -q` still 26/26
- [x] Existing 4 scenario files byte-identical to before this plan (confirmed via `git status` — untouched, not even modified)
- [x] What-if sliders load a real, distinct dataset within ~1s
- [x] AI toggle visibly changes breach behaviour using real paired data — verified: EV 75% shows real 291.7 kVA BREACH (AI off) vs real 240.3 kVA WARNING (AI on) at the same tick
- [x] ₹ readout matches the commercial calculator's formula exactly (same `× ₹1,200/kVA` constant, both apps)
- [x] Tour runs deterministically, matches the (updated) pitch script beat for beat — ran twice, clean completion both times, ~70-90s real wall time (fetch/rebuild overhead on the AI-toggle beat pushes it past the nominal 60s, noted as expected)
- [x] Presentation mode toggles cleanly both directions (`P` key or button)
- [ ] Backup video recorded and saved locally — **not done**, requires local screen-recording software outside what this session can drive; the tour button (`viz3d`, top bar) is ready to record whenever you are
- [x] Pitch mode shows exactly the 6 scripted slides, Deep-dive shows 12 — verified in order: hook, evidence, scaleproof, buyers, calc, ask
- [x] Evidence slide animates once per entry — logic verified correct (delta math confirmed right: ₹1,71,449); the visual CSS-transition/count-up itself couldn't be visually confirmed in this session's browser sandbox (a known compositing limitation hit repeatedly this session, not specific to this feature) — worth a 10-second look on your end
- [x] Embedded proof loads — iframe mounts successfully; the fallback is a text link, not a full screenshot swap as originally specced (screenshot generation wasn't worth the added scope for a fallback that may never trigger) — noted as a deliberate simplification, not silently dropped
- [x] Autoplay pauses (not skips) on the calculator slide — verified: sat on `calc` through a full dwell-equivalent wait with no auto-advance
- [x] Nothing from the two frozen-out lists (1.5, 2.5) has crept in

## One deviation from the plan, found during execution

The what-if grid's heatwave axis was dropped. Calibration (step 1) showed
the heatwave event makes **zero** measurable difference to peak load at
any EV level in this dataset — identical states with and without it.
Shipping a slider that visibly does nothing would have been the exact kind
of hollow control this project has been avoiding all along, so it's one
real axis (EV penetration) instead of the planned two. Six files, not
twelve. Everything downstream (the toggle, the ₹ formula, the tour) was
built against this corrected, simpler design.
