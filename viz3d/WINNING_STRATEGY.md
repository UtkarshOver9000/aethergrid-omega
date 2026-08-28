# What actually wins at SIH — the reframe

Not a feature list this time. The addon list in README.md is still correct,
but it's tactics. This is the strategy underneath it, and it changes what
order those tactics matter in.

## The mistake to name plainly

Across this whole build, three genuinely strong things got built as three
separate artifacts:

1. **This world simulation** — a believable, synthetic 60-household society,
   honest about being synthetic.
2. **The real single-building benchmark** (your teammate's, at
   aethergrid-vert.vercel.app) — real BDG2 meter data, a real published Tamil
   Nadu tariff, a calibrated forecaster, honestly reported measurement &
   verification uncertainty.
3. **The Samanvay commercial case** — a real buyer ladder, a real ROI
   calculator, honest data-acquisition paths, grounded in the actual RDSS
   smart-metering rollout already happening nationally.

Each is good on its own. Judges have seen all three *kinds* of thing before,
separately, from other teams: a pretty simulation, a rigorous backtest, a
business slide. None of those three alone wins SIH. What's rare — what
actually wins — is a team that visibly connects all three into one argument,
live, in the room. That connective tissue is the thing not yet built, and
it's worth more than any further polish on any one piece.

## The reframe: stop calling it a simulation

Right now this is pitched as "a world simulation for our hackathon." Reframe
it, honestly, as what it actually is closer to: **a decision-support sandbox
a DISCOM planning department or an RWA facility manager could use today to
stress-test their own transformer against next year's EV and heatwave
numbers, before spending capex.** That is not a stretch — it's a true
description of what the scenario switcher plus the coordinator toggle
already does or is about to do. The difference between "cool simulation" and
"decision-support tool" is entirely in the interaction model and the
framing, not in new rendering work.

Concretely, this means the single most valuable feature to add is not more
visual detail. It's a **live "what-if" control panel**:

- Sliders: EV penetration %, solar penetration %, heatwave severity, override
  rate.
- Moving a slider regenerates the scenario live (the engine already takes
  these as generation parameters — this is wiring, not new physics).
- Two numbers update live, side by side: **transformer breaches this month
  without AI coordination** vs **with it**, and — this is the part that
  connects to Samanvay — **estimated ₹ of transformer-capex deferral this
  represents**, computed with the exact same formula already built and
  validated in the Samanvay ROI calculator (`recKw × cost_per_kva`, the
  transformer-constrained mode).

That one control panel is the whole pitch, interactive, in one screen: this
is what stresses your infrastructure → this is what our method (validated for
real elsewhere, on real data) does about it → this is what that's worth to
you in rupees. Innovation, feasibility, and impact — three separate SIH
judging criteria — answered by one slider, live, instead of three separate
slides.

## The second move: name the real policy tailwind out loud

Ministry-affiliated judges respond to a team that clearly knows the real
ecosystem, not just the algorithm. Say explicitly, in the pitch, that the
metering infrastructure this depends on (smart sub-meters at the flat level)
is already being rolled out nationally under **RDSS** — this system doesn't
need new hardware mandated, it needs to plug into infrastructure procurement
that is already funded and in motion. That single sentence signals
deployability in a way no amount of visual polish can.

## The closing beat: zoom out, don't just zoom in

Every demo of this so far ends by looking *closer* — a house, a sub-meter, a
transformer bar. For the scalability judging criterion specifically, the
strongest possible closing beat is the opposite motion: pull the camera back
and reveal that the same one society sits inside a colony of many, each with
its own transformer, sharing one upstream feeder — even a rough, lower-detail
version of the previously-planned colony scale is enough for this, because
its job is purely rhetorical: *this is one flat, scaled to one society,
scaled to a colony, scaled to a discom feeder, scaled to a state.* One
sentence, one camera pull-back, and the scalability question answers itself
before a judge asks it.

## Revised priority, given this reframe

1. **The what-if control panel with the live ₹-deferral number.** This
   supersedes the plain AI Coordinator toggle from README.md — build the
   toggle *as part of* this panel, not standalone, so the AI's effect is
   always shown in the same rupee terms as the commercial case.
2. **The scripted tour**, but rewritten to actually perform the argument
   above in order: normal → slide EV% up → watch breaches appear → flip AI
   on → watch the ₹ figure and the breach count both move → pull back to
   colony scale → end.
3. Sun/moon/car fixes — still worth doing, still cheap, still visible.
4. Backup recorded video of the tour above, as insurance.

Everything else in the original addon list (presentation mode, further
detail work) drops in priority below this. The what-if panel is the one
piece of work that turns three separately-good artifacts into a single
argument no other team in the room is likely to have made as concretely.

## Why this specifically wins, not just impresses

SIH scoring rewards innovation, feasibility/viability, and impact/scale as
separate axes, plus how well it's presented. Most teams max out one axis and
gesture at the others. A live control panel that (a) is visibly built on a
method already validated against real data elsewhere, (b) produces a rupee
number using the same formula as an actual commercial pitch, and (c) ends by
visually scaling to a feeder — hits all three substantive axes with one
interaction, not three separate arguments a judge has to mentally assemble
themselves. That assembly work is usually left for the judge to do, and most
don't bother. Doing it for them, live, on screen, is the actual differentiator.

Say if you want the what-if panel built next — it's the one thing here worth
prioritizing over the AI toggle exactly as originally scoped.
