# AETHERGRID 3D — where this stands, and the plan forward

Written before touching more code, as asked. This is the honest state of things,
the two visual bugs you caught, the plan to actually put "AI" in this view, and
a prioritized list of what's worth building next versus what isn't.

## 1. The two bugs you flagged, diagnosed

**Cars look fake.** Right now each car is an independent point bouncing back
and forth on one fixed lane, snapping its heading between two fixed angles
the instant it changes direction. There's no cornering, no other traffic
awareness, no easing. That reads exactly as "funny," because it is a toy —
a real vehicle doesn't teleport-rotate 180° at a lane's edge. Fix: replace
independent bouncing lanes with a small number of cars (2-3, not 10) driving
one shared rectangular loop route around the perimeter road, with the heading
interpolated smoothly through each corner instead of snapped. Fewer, better,
beats many, wrong.

**Sun and moon aren't real.** There is no moon object at all — at night the
same blurry sprite that represents the sun just dims. That's why it reads as
fake: because it is the same fake blob, day or night. Fix: two distinct
objects — a crisp sun disc with a tight halo (not a soft blurry gradient),
and an actual moon disc using a real public-domain lunar texture (NASA
imagery is public domain, same licensing safety as the ambientCG materials
already in use), swapped in based on `sun_altitude` exactly like the
directional light already is.

Both are small, contained fixes. Worth doing — they're the kind of detail a
judge's eye catches in the first five seconds.

## 2. Where "AI" actually belongs in this, honestly

Repeating the honest point from last time because it's the load-bearing one:
this world simulation is *deliberately* the uncontrolled baseline. There is
no optimizer in it. That was correct for building a believable environment,
and it also means a judge watching it standalone will reasonably ask "where's
the AI." Two ways to close that gap, in order of how much I'd recommend them:

### Recommended: a real, small, toggleable coordinator, live in the viewer

Add an "AI Coordinator: OFF / ON" switch to the topbar. OFF is exactly what
exists today. ON runs a genuinely real — not fabricated, not pre-baked — tiny
greedy controller entirely in the browser, on every tick:

1. Recompute aggregate transformer load with deferrals applied so far.
2. If it's above a target threshold (e.g. 90% of rating), find the
   highest-load deferrable appliance (AC/geyser/EV charging, never a
   critical load) among households *not yet deferred this rotation*.
3. Defer it (zero its contribution for that tick, flag the house), rotate
   the "already deferred" set each cycle so it's never the same six houses
   every time — this is a real, working version of the fairness idea already
   in the write-up.
4. Re-render: the transformer bar visibly stays under the ceiling, deferred
   houses show a distinct badge, and a running counter shows kWh deferred
   and kVA held back this session.

This is not the real q95 chance-constrained LightGBM system — it's a
simplified, transparent, client-side stand-in for it, and the UI should say
exactly that in one line, the same honesty pattern as everything else here.
But it is a *real, running, causal* piece of control logic a judge can watch
flip a graph in real time by clicking a toggle. That is what "the AI part"
looks like in a demo, far more than a static label ever could.

Effort: moderate — a new tick-level pass, a few new UI elements, no new
external dependencies. This is the single highest-value thing left to build.

### Lighter alternative, if time is short

Add a dashed "forecast" line next to the "actual" line on the transformer
sparkline — a simple short-horizon extrapolation (moving average of the last
few ticks), labeled "illustrative forecast signal, not the production
LightGBM model." Shows *a* forecasting concept without a working controller
behind it. Meaningfully less impressive than the toggle above, but a fraction
of the effort.

## 3. Addons, ranked by judge-impression per hour of work

1. **The AI Coordinator toggle** (above). Directly answers the one question
   every judge will ask. Highest priority.
2. **A scripted camera tour** — one "Play tour" button that runs a
   pre-choreographed ~25s camera path: overview → heatwave peak forming →
   zoom into a curtailed house's sub-meter → transformer stress ring → (if
   the coordinator toggle exists) flip it on and watch the bar recover. This
   is as much risk-management as polish: it means you are never relying on
   live clicking under pressure in front of judges, and it *is* your pitch
   choreography, rehearsed into the software itself.
3. **The sun/moon and car fixes** above — cheap, visible, worth doing.
4. **A one-click "presentation mode"** that hides the dev-ish chrome (legend,
   hint text) and enlarges the KPI numbers, for the moments you're not
   narrating over the scrub bar.
5. **Not a code addon — a process one**: record a 30-60s screen capture of
   the tour running well, as an offline backup file on the laptop you present
   from. If the live 3D scene hiccups on the judges' hardware or projector,
   you switch to the video without missing a beat. Cheap insurance against
   the single biggest live-demo risk in this whole conversation.

## 4. What I would *not* spend more time on

More procedural-geometry detail work, more texture variety, more ambient
props. We're past the point where that moves a judge's impression — the
returns have flattened. Everything above is either substance (the AI
toggle) or risk-reduction (the tour + backup video), which is where the
remaining time is worth spending.

## 5. Suggested build order

1. AI Coordinator toggle (core logic + minimal UI)
2. Scripted camera tour
3. Sun/moon + car motion fixes
4. Presentation mode
5. Record the backup video, last, once the tour is final

Tell me which of these to start on, or reorder it — this file is the plan,
not a commitment to build all of it blind.
