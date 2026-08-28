# Solar execution plan — a dedicated Solar tab, real solar-sync charging, real AI attribution

Written before touching code, as asked. This is the precise design: what
changes in the engine (a real behavior, not a visual trick), what two new
files get generated, the exact formulas, and the exact new tab in the
world sim — plus how it integrates with the existing kVA-shaving
(curtailment) system rather than replacing it.

## What's actually there right now, checked against the real code

`aethergrid/worldsim/engine/household.py` line 188: EV charging is
literally commented `"EV: uncontrolled max-rate charging while present"`
— it charges at full rate the instant `ev_soc < target` (90% of battery
capacity) and the car is home, with zero awareness of time of day or
whether solar is generating. This confirms the gap precisely: there is no
solar-sync behavior today to build on top of — it has to be added.

**One honest nuance worth stating up front, not hidden**: solar-sync
charging only helps houses whose EV is actually *home* during some
daylight hours. `ev_present` is driven by `occupancy_frac[t] > 0.35` —
for a `dual_income_no_children` household away at work all day, the car
isn't home when the sun is up, so solar-sync can't help that house much.
`work_from_home`, `elderly_couple`, and `frequently_absent` archetypes
benefit far more. This is real, and the Solar tab should show it
transparently (some houses save a lot, some save little, and that's
correct, not a bug) rather than pretend every house benefits equally.

---

## 1. The engine change — a real, second real behavior, same pattern as `enable_curtailment`

Add `enable_solar_sync: bool = False` threaded through `simulate_society`
→ `simulate_household` (mirroring exactly how `enable_curtailment` was
added — default `False` so it is provably a no-op on every existing file
until explicitly turned on, verified the same way: regenerate, byte-diff,
confirm zero change).

**The mechanism, precisely** (replaces lines 196-203 in `household.py`
when the flag is on):
- A tick is in the **solar-priority window** when `env.ghi_wm2[t] > 50`
  (meaningful daylight, not just twilight) and `ev_present`.
- Inside that window: charge at full rate if `ev_soc < target`, exactly
  as today.
- Outside that window: charging is held back *unless* either (a)
  `ev_soc` has fallen below a **safety floor** of `0.5 * target` (never
  let the car run dangerously low), or (b) the hour is `>= 17` (approaching
  the real evening peak window already used everywhere else in this
  project, so a car that's still low by then charges anyway rather than
  staying stranded overnight).
- This guarantees the EV always ends up adequately charged — solar-sync
  shifts *when* charging happens, it never leaves someone without a
  usable car, which is the honest, deployable version of this feature.

## 2. Three new real datasets, not twelve — reusing what already exists

The existing `whatif_ev20_ai.json` / `whatif_ev40_ai.json` /
`whatif_ev75_ai.json` (curtailment on, solar-sync off) already *are* the
correct "sync off" baseline — no need to regenerate them. Add exactly
three new paired files via a new
`aethergrid/worldsim/generate_solar_sync.py` (same structure as
`generate_whatif.py`): `whatif_ev20_ai_solarsync.json`,
`whatif_ev40_ai_solarsync.json`, `whatif_ev75_ai_solarsync.json` — same
seed (301), same fixed rating (280 kVA), `enable_curtailment=True,
enable_solar_sync=True`. Three files, not a duplicated grid.

**Verification**: `pytest -q` still 26/26; the three existing what-if
files byte-identical (confirmed via `git status`, same method as before).

## 3. The real savings formulas — two separate streams, both honest

**Self-consumption spread** (per house, per tick, summed over the day):
for every kWh where `enable_solar_sync` moved EV charging into a tick
where that house's own `solar_kw[t] > 0` that wouldn't have been charging
solar-coincident otherwise, value it at
`kwh × (import_rate − export_rate)`. Reuse the existing
`ILLUSTRATIVE_TARIFF.rate_per_kwh` (₹7.2) as the import rate; add one new
labeled constant, `ILLUSTRATIVE_EXPORT_RATE = 3.5` (₹/kWh, roughly half
of import — a realistic shape for Indian net-metering, explicitly labeled
illustrative, not a filed rate, same honesty standard as everything else).

**Demand-charge pro-rata contribution** (per house, once per day): at the
tick of the *society's* real peak kVA, compute each house's share of that
peak (`house_kw_at_peak_tick / total_kw_at_peak_tick`). Multiply that
share by the real reduction in society-wide peak kVA between the sync-off
and sync-on runs, times the **real** ₹608/kVA Tamil Nadu demand charge
already cited in the commercial case (this is the actual tariff that
applies to a bulk HT connection's shared transformer — not the
illustrative residential rate used elsewhere, and the plan should keep
that distinction explicit on screen: *"demand-charge share uses the real
TNERC ₹608/kVA rate; the self-consumption spread uses an illustrative
residential rate — labeled separately, not blended into one misleading
number."*

**The AI-attribution number** — the one that actually answers "how much
is the AI contributing": both formulas above are already computed as a
*delta* between sync-off and sync-on. That delta *is* the AI's
contribution, by construction — not "total solar savings" (which would
include savings from simply owning panels, sync or not), specifically the
incremental value of the coordination. This distinction is the difference
between an honest claim and an inflated one, and it should be the
headline number on the new tab, not a footnote.

## 4. The new "Solar" tab — exact structure

A fourth rail tab, `Live / GridBrain / Solar / Data`, scoped to Society A
(matching the existing what-if panel's scope; Societies B/C don't have
solar-sync data and the tab should say so plainly rather than show blank
fields).

**Top of the tab — the society-level headline**, always visible:
- Total solar generated today (real, sum of `solar_kw` across all hours).
- Total self-consumed vs. exported (real, from the sync-on run).
- **"AI-coordinated saving today: ₹X (₹Y self-consumption + ₹Z demand-charge share)"** — the two formulas above, added but also shown
  separately, sourced from the real sync-off/sync-on delta.
- A one-line honesty note, same tone as the rest of the app: *"This is
  the incremental value of solar-synchronized scheduling specifically —
  not total solar savings, which would happen with or without
  coordination."*

**Below it — a per-house table**, sorted by ₹ saved descending: house id,
archetype, EV present-during-daylight (yes/no, explaining low performers
honestly), kWh self-consumed, ₹ saved. Clicking a row selects that house
and jumps to the existing Live tab's inspector, which gets one new box —
*"Solar-sync contribution"* — alongside the AC/geyser facilities box
already there.

**How this ties to the existing what-if panel, not replaces it**: the
what-if panel's `AI Coordinator ON/OFF` continues to mean curtailment. A
new, separate small toggle inside the Solar tab, `Solar sync: OFF/ON`,
switches between the existing `whatif_ev*_ai.json` and the three new
`*_solarsync.json` files at whatever EV level is currently selected —
same underlying `setScenario` pipeline, no new rendering path, exactly
how the what-if panel itself was built.

## 5. How it integrates with the existing kVA-shaving story, precisely

Solar-sync and curtailment are not competing explanations — they're
sequenced, and the tab should say so: solar-sync runs first, all day,
reducing how much load is even present when evening hits; curtailment
remains the fallback for whatever stress solar-sync couldn't prevent.
The existing decision ledger already logs real curtailment events — with
solar-sync on, there should be genuinely *fewer* of them at the same EV
level, and that reduction is itself a third, freely-derived piece of
evidence (no new computation needed: just count ledger lines in the
sync-on run vs. the sync-off run at the same EV level).

## Risk register

| Risk | Mitigation |
|---|---|
| Solar-sync flag silently changes existing files | Same byte-diff verification as `enable_curtailment`, required before merge |
| Overclaiming "solar saves everyone equally" | Per-house table shows real variance by archetype/presence, stated honestly |
| Blending real TN tariff and illustrative residential rate into one misleading number | Kept explicitly separate on screen, each labeled with its source |
| EV left uncharged overnight for realism's sake | Safety floor (50% of target) + 17:00 fallback guarantee it never happens |

## Definition of done

- [ ] `pytest -q` still 26/26
- [ ] Existing `whatif_ev*_ai.json` files byte-identical (git shows no diff)
- [ ] Three new `*_solarsync.json` files generated, real, paired correctly
- [ ] Solar tab shows a real, non-fabricated AI-attribution ₹ figure, split
      by formula, sourced from the sync-off/sync-on delta
- [ ] Per-house table shows honest variance, not a flat number for every house
- [ ] Ledger shows fewer real curtailment events with sync on, same EV level
- [ ] Solar-sync toggle reuses the existing scenario-load pipeline, no new
      render path

Say "go" to execute in the order above (engine flag → two-file
generation → savings formulas → the new tab).
