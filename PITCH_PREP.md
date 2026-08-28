# AETHERGRID — pitch prep

One file: where things stand, how the whole thing works in brief, a 60
second pitch for the world simulation, a separate 60 second pitch for the
commercial case, and every counter-question a judge is likely to fire back.
Nothing here is pushed anywhere — both apps run off a local static server
only, per your instruction.

## Progress at a glance

- **World simulation** (`viz3d/`): a real Three.js 3D colony — Society A
  (60 households, fully detailed) plus two more independently generated
  neighbour societies, Society B and C, on a shared feeder. Real photographed
  CC0 materials (brick/stucco/roof/grass/asphalt), real sun and moon
  objects, cars and a bus driving an actual road loop, per-house AC and
  geyser fixtures wired to real state, four playable scenarios (normal,
  heatwave, high EV, outage).
- **GridBrain** (inside the world sim, "GridBrain" tab): a visible
  coordination hub connected to all three transformers by animated
  data-flow beams, plus a live decision ledger sourced directly from each
  society's own real, already-simulated curtailment output — not a
  separate fabricated "AI layer."
- **What-if panel + AI Coordinator toggle**: three real EV-penetration
  levels (20/40/75%), each pre-simulated twice by the actual engine — once
  with real transformer-protection curtailment on, once off. Flipping the
  toggle at EV 75% swaps a real 291.7 kVA BREACH for a real 240.3 kVA
  WARNING at the same tick, with a live ₹ capex-deferral readout using the
  same formula as the commercial calculator.
- **Scripted tour + presentation mode**: a "Play tour" button runs a fixed
  ~70s choreography beat-matched to the 60-second world-sim pitch below
  (colony → Society B stress → AI Coordinator flip → GridBrain ledger →
  house inspector → pull back), with all manual interaction disabled for
  its duration and cleanly restored after. "Present" (or key `P`) hides
  dev chrome and enlarges KPI text for narrated moments.
- **Commercial pitch** (`commercial3d/`): a 12-slide, arrow-key-driven
  slideshow (not a click-hunt) covering the problem, the method, real
  benchmark evidence, the world-sim proof, the buyer ladder, a live ROI
  calculator, an honest data roadmap, the competitive wedge, how it scales
  further, and the ask.
- Both apps link to each other from their top bars.
- Local URLs: `http://localhost:8020/viz3d/index.html` and
  `http://localhost:8020/commercial3d/index.html`.

## How the whole thing works, in brief

Three separate pieces of evidence, kept honestly separate rather than
blurred into one claim:

1. **The world simulation** is a fully synthetic, hand-authored 60(+48+48)
   household colony. Every 15 minutes it runs occupancy, appliances
   (AC/geyser/EV/battery/solar), a real RC thermal model, and real
   sun-position astronomy per house, then aggregates to a transformer and
   runs the transformer's own protection logic: past a rating threshold it
   sheds the highest-load flexible appliance among households not already
   curtailed this rotation, logs it, and keeps critical loads (security,
   lifts) untouched. Nothing here is claimed as real-time or measured data.
2. **GridBrain** is the presentation layer that makes that mechanism
   visible instead of implied: a pulse of light from every transformer to a
   central hub, a plain-English ledger of the engine's real curtailment
   decisions as they happen, and a live cross-society headroom comparison
   (framed as a recommendation — automated cross-feeder transfer is not
   actually simulated, and we say so).
3. **The commercial case** is the separate, real evidence layer: a
   forecasting method validated on Building Data Genome Project 2 (real
   meter data, real Tamil Nadu tariff, published elsewhere), a buyer ladder,
   and a live ROI calculator using the same formulas a real sales
   conversation would use. It explicitly does not claim the world sim's
   synthetic households are real measured data, and explicitly names which
   Indian datasets (IRED, Low Carbon London, the Hyderabad AC dataset,
   iAWE, I-BLEND) are **planned but not yet integrated**, rather than
   implying they already are.

The honesty boundary matters more than any single number: *what's real*
(BDG2, the tariff, the bill engine, the sub-meter data path) is kept
strictly separate from *what's illustrative* (the synthetic households, the
flat residential tariff used for cost-exposure readouts) and from *what's
planned* (the Indian datasets, cross-feeder automation). Every panel in
both apps says which of the three it is.

---

## 60 second pitch — the world simulation

> This is the environment an AI coordination layer has to prove itself
> against, not a cartoon. Three independently simulated societies share
> one feeder — real occupancy, real appliances, real thermal physics, no
> fixed load curves. Watch Society B's older transformer actually climb to
> ninety-five percent, while its neighbour sits comfortably under load.
> Flip the AI Coordinator on — real pre-simulated data, not a fudge-factor
> slider — and watch the same transformer hold the line instead of
> breaching. Then open the GridBrain tab: a live hub connects all three
> transformers, and a decision ledger shows the engine's own real
> protection decisions in plain English as they happen — not a scripted
> demo, the actual simulation output. Click any house for its own
> sub-meter reading and what that resident's bill exposure looks like
> today. This is the uncontrolled baseline an optimizer is built to
> improve on, built to survive being clicked on by a judge.

*(~155 words, ~60 seconds at a measured pace — matches `runTour()` in
`viz3d/main.js` beat for beat)*

## 60 second pitch — the commercial case

> We don't sell to a resident, we sell to whoever already manages the
> transformer. The method is validated separately on real meter data —
> Building Data Genome Project 2, a real published Tamil Nadu tariff — and
> it turned an eleven-breach month into zero, at thirteen percent of the
> bill, eighty-one percent of the theoretical best case. Three buyers, in
> the order they close: bulk HT societies first, weeks to close, direct
> rupee savings on an existing facility-management invoice; DISCOMs next,
> pitched as deferred transformer capex riding infrastructure India is
> already installing under RDSS; new-build developers third, as an
> EV-ready launch differentiator. Put your own building's numbers into the
> calculator right now — that's not a projection for the slide, it's the
> same arithmetic the coordinator runs. And we say plainly what's real
> today versus what's still a roadmap, because a judge who catches an
> overclaim stops listening to everything after it.

*(~145 words, ~60 seconds at a measured pace)*

---

## Counter-questions judges will ask

### On the world simulation

1. **Is any of this real data?**
   No, and we say so unprompted. It's fully synthetic — hand-authored
   archetype behaviour, not fitted to a named dataset. The physics (RC
   thermal model, EV/battery curves, sun-position astronomy) are standard
   equations, not measured recordings.

2. **Then what is it proving?**
   That the coordination *mechanism* — sense every sub-meter, forecast,
   protect the transformer, log the decision fairly — works correctly and
   consistently across more than one location, under real engine logic,
   not that any specific number is a real-world measurement.

3. **Where's the actual AI? I just see a 3D neighbourhood.**
   The world runs deliberately uncontrolled — it's the baseline an
   optimizer improves on. The real decision-making shown live is the
   transformer's own protection logic (curtailment), surfaced in the
   GridBrain ledger in plain English as it happens. The forecasting/q95
   optimizer itself is validated separately, on real data, in the
   commercial case.

4. **Why three societies instead of one bigger one?**
   To prove the mechanism generalizes rather than only working once. Same
   logic, independently run, at three different transformers with
   different ratings and EV penetration — one genuinely breaches, one has
   real headroom.

5. **What's the "GridBrain recommendation" — is that automated?**
   No, and we label it as a recommendation specifically because it isn't.
   It's a real, live computed comparison (which society is stressed, which
   has headroom) — automated cross-feeder power transfer is not simulated,
   and claiming otherwise would be the overclaim we're trying to avoid.

6. **How do you know the households aren't unrealistically synchronized?**
   Measured directly as a coincidence factor (peak of combined load ÷ sum
   of individual peaks). It should land 0.4–0.6 for a realistic
   population; checked early, not assumed.

7. **What happens on a real device that isn't your dev machine?**
   The scene degrades gracefully — fog and camera framing adapt per view
   mode, and interaction uses generous screen-space hit-targets rather
   than pixel-perfect 3D raycasting, specifically because demo hardware is
   unpredictable.

### On the commercial case

8. **Is the ROI calculator using real numbers or picked-for-the-slide ones?**
   The formulas are real and stated (kVA shaved × demand charge × 12,
   fee models, EV coincidence assumptions) — the *inputs* are yours to
   change live. It's arithmetic, not a black box.

9. **Will you use the DISCOM smart meter API?**
   Not yet — there is no standard third-party access API today, and we
   say so before a judge finds it. We don't build the product around a
   dependency we don't control.

10. **Then how do you get real operational data?**
    Two real paths today: a bulk HT society's own sub-meters (a commercial
    conversation with the RWA, not a regulatory filing), or a low-cost
    retrofit CT clamp + microcontroller for societies without sub-metering.

11. **What about IRED, Low Carbon London, the Hyderabad AC dataset, iAWE,
    I-BLEND — are those in the model?**
    Not yet, and we label them explicitly as planned, not current. Today's
    real data is Building Data Genome Project 2, used in the separate
    single-building benchmark. Those Indian datasets are the named next
    step for calibrating archetype behaviour to Indian households
    specifically — an honest roadmap item, not a current claim.

12. **Why should a resident trust an algorithm deciding whose appliance
    waits?**
    It's a quota signal, not a command — a resident can override anytime.
    Deferral decisions are deterministic and logged with a reason in plain
    English, and a fairness ledger (Jain's index) prevents the same
    households being chosen every time — the exact failure mode that gets
    a vendor voted out at a society's general body meeting.

13. **Who is the actual first paying customer?**
    A bulk HT society's facility management company — a new line on an
    O&M invoice they already send, not a new vendor relationship built
    from nothing.

14. **Is this a big venture outcome or a small services business?**
    Told plainly: the bulk-HT segment alone is a real, bootstrappable
    subscription business but modest per-customer revenue. The DISCOM
    segment is where a venture-scale outcome lives, and it depends
    entirely on landing one credible, published pilot first.

15. **What already exists in this market — why hasn't someone done this?**
    AMI vendors instrument the meter but don't coordinate load; commercial
    ESCOs serve single large HT consumers, not distributed residential
    coordination; global DERMS platforms are the validated reference
    category but aren't localized to Indian tariffs or society governance.
    A specific, named wedge — not an empty-market claim.

16. **What's the single next step that matters most?**
    Not a bigger model — one real society's or FM company's data-sharing
    agreement, validating the forecaster against real flat-wise billing
    data on top of the published research datasets already used. That's
    the same proof point an early investor asks for first.

17. **What would you fix first with more time?**
    Real operational data replacing the research-dataset training
    entirely, and finishing the Indian-dataset calibration roadmap named
    honestly in the data slide rather than left as a citation.
