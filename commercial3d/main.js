// AETHERGRID commercial pitch — slideshow, not a click-hunt.
// One continuous argument, in the order a judge should hear it. No
// simulation logic here; the world-sim references cite real generated data.
(function () {
  "use strict";
  const rupeeFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  const rupee = (x) => "₹" + rupeeFmt.format(Math.round(x));

  const SLIDES = [
    { id: "hook", dwell: 6000, pitch: true, body: () => `
      <div class="brand-mark"><span class="dot"></span><span>Aethergrid &middot; commercial pitch</span></div>
      <h1>We don't sell a smarter building.<br>We sell whoever already manages the <span class="accent">transformer</span> a way to stop it tripping.</h1>
      <p class="lede">A grid-edge AI coordination layer, validated on real meter data, demonstrated live at three-transformer colony scale, with a buyer ladder and a rupee number ready today.</p>
      <div class="kpi-row">
        <div class="kpi"><div class="label">Real benchmark saving</div><div class="value gold">13%</div><div class="sub">of monthly bill, real meter data</div></div>
        <div class="kpi"><div class="label">Breaches eliminated</div><div class="value ok">11 &rarr; 0</div><div class="sub">same real building, same month</div></div>
        <div class="kpi"><div class="label">Colony proof</div><div class="value">3 transformers</div><div class="sub">independently simulated, one feeder</div></div>
      </div>` },

    { id: "problem", dwell: 8000, pitch: false, body: () => `
      <div class="eyebrow">01 &middot; the problem</div>
      <h1>Every transformer here was sized for a world without EVs in it.</h1>
      <p class="lede">AC, geysers, and EV charging land in the same evening window. Nobody is wasting anything — the coincident peak simply exceeds what the transformer was ever built for. Our own colony simulation shows exactly this: an older, smaller transformer pushed to 94.8% of rating, real curtailment triggered 21 separate times in a single day.</p>
      <div class="kpi-row">
        <div class="kpi"><div class="label">Society B transformer</div><div class="value crit">94.8%</div><div class="sub">peak load vs. 128 kVA rating</div></div>
        <div class="kpi"><div class="label">Curtailment events</div><div class="value">21 / 96</div><div class="sub">ticks in one simulated day</div></div>
        <div class="kpi"><div class="label">A neighbouring society</div><div class="value ok">84.3%</div><div class="sub">real headroom, same feeder</div></div>
      </div>` },

    { id: "map", dwell: 5000, pitch: false, body: () => `
      <div class="eyebrow">02 &middot; the system, in one picture</div>
      <h1>One coordination layer, three real proof points</h1>
      <p class="lede">Method validated on real data. Physics demonstrated at colony scale. Economics computed live for your building. Everything past this slide is one of these three, in detail.</p>
      <svg id="mapSvg" viewBox="0 0 900 420"></svg>` },

    { id: "method", dwell: 9000, pitch: false, body: () => `
      <div class="eyebrow">03 &middot; what the AI actually computes</div>
      <h1>One substitution. That's the whole mechanism.</h1>
      <p class="lede">In the constraint holding grid import under the demand ceiling, use the <b>95th percentile</b> of the base-load forecast and the <b>5th percentile</b> of solar — not the means.</p>
      <div class="formula-box mono">base_q95[t] &nbsp;+&nbsp; controllable[t] &nbsp;&minus;&nbsp; solar_q05[t] &nbsp;&le;&nbsp; D_ceiling</div>
      <div class="step-row">
        <div class="step"><div class="n">SENSE</div><p>Every flat's real sub-meter reading, every 15 minutes — the same granularity a real bulk-HT society already bills on.</p></div>
        <div class="step"><div class="n">DECIDE</div><p>If forecast load breaches the ceiling, the highest-load flexible appliance among households not yet deferred this cycle is queued — deterministic, not a black box.</p></div>
        <div class="step"><div class="n">ACT &amp; LOG</div><p>Every deferral is written to a fairness ledger (Jain's index) and shown in plain English — auditable by the RWA that has to defend it.</p></div>
      </div>
      <div class="callout"><b>Why not reinforcement learning?</b> Across the CityLearn 2021–2023 benchmark, no top-performing team used RL for scheduling. Winners used forecasting plus classical optimisation — we follow that shape and cite the result rather than apologise for it.</div>` },

    { id: "evidence", dwell: 9100, pitch: true, onShow: animateEvidenceBars, body: () => `
      <div class="eyebrow">04 &middot; real meter data, not a projection</div>
      <h1>Validated separately, on a real building</h1>
      <p class="lede">Building Data Genome Project 2 — a real office tower, a real published Tamil Nadu (TNERC) HT-I-A tariff: ₹6.35/kWh energy, ₹608/kVA demand charge.</p>
      <div class="bar-compare">
        <div class="bar-row"><span class="bar-label">No control</span><div class="bar-track"><div class="bar-fill crit" id="barNoControl"></div></div><span class="bar-value mono" id="barNoControlV">—</span></div>
        <div class="bar-row"><span class="bar-label">With Aethergrid</span><div class="bar-track"><div class="bar-fill ok" id="barOurs"></div></div><span class="bar-value mono" id="barOursV">—</span></div>
      </div>
      <div class="bar-delta" id="barDelta"></div>
      <div class="kpi-row" style="margin-top:16px">
        <div class="kpi"><div class="label">Breaches eliminated</div><div class="value ok">11 &rarr; 0</div></div>
        <div class="kpi"><div class="label">Of theoretical maximum</div><div class="value">81.2%</div><div class="sub">perfect-foresight oracle</div></div>
      </div>
      <div class="callout gold"><b>Disclosed, not hidden:</b> the buildings are American (Tempe, Arizona) — the <i>method</i> transfers, not the load shapes. Full detail at aethergrid-vert.vercel.app/method.</div>` },

    { id: "scaleproof", dwell: 9000, pitch: true, onEnter: mountWorldSimProof, body: () => `
      <div class="eyebrow">05 &middot; proof it generalises</div>
      <h1>The same mechanism, running twice, on one feeder</h1>
      <p class="lede">One society reads as a demo of one building. Our world simulation runs the identical logic independently at three transformers, live, clickable — the smallest possible proof this isn't a one-building trick. At EV 75%, flipping its own AI Coordinator toggle turns a real 291.7 kVA breach into a real 240.3 kVA hold, at the same tick.</p>
      <div class="proof-wrap">
        <div class="kpi-row" style="flex:1; min-width:220px;">
          <div class="kpi"><div class="label">Society B</div><div class="value crit">breaches for real</div><div class="sub">128 kVA, 94.8% peak</div></div>
          <div class="kpi"><div class="label">Society C</div><div class="value ok">real headroom</div><div class="sub">210 kVA, 84.3% peak</div></div>
        </div>
        <div class="proof-embed" id="proofEmbed"></div>
      </div>` },

    { id: "buyers", dwell: 9000, pitch: true, body: () => `
      <div class="eyebrow">06 &middot; how we make this commercial</div>
      <h1>Three buyers, in the order they actually close</h1>
      <div class="tier-grid">
        <div class="tier"><div class="n">TIER 1</div><div><h3>Bulk HT societies &middot; close first</h3><p>Facility management already sells an O&amp;M subscription for lifts, pumps, security — this is a new line on an existing invoice, direct rupee savings.</p>
          <div class="tier-stats"><div class="tier-stat">CYCLE<b>Weeks–months</b></div><div class="tier-stat">DEAL<b>₹50k–3L/yr</b></div></div></div></div>
        <div class="tier"><div class="n">TIER 2</div><div><h3>DISCOMs &middot; the venture-scale thesis</h3><p>Pitched as deferred transformer capex, not software. RDSS has already funded DT-level sub-metering nationally, independent of us.</p>
          <div class="tier-stats"><div class="tier-stat">CYCLE<b>12–24 months</b></div><div class="tier-stat">DEAL<b>Feeder/circle scale</b></div></div></div></div>
        <div class="tier"><div class="n">TIER 3</div><div><h3>New-build developers</h3><p>State EV-ready housing mandates make this a launch differentiator; converts to a recurring RWA subscription after handover.</p>
          <div class="tier-stats"><div class="tier-stat">CYCLE<b>Per project</b></div><div class="tier-stat">DEAL<b>Higher LTV</b></div></div></div></div>
      </div>` },

    { id: "calc", dwell: null, pitch: true, body: () => `
      <div class="eyebrow">07 &middot; the number, computed live</div>
      <h1>Not picked for the slide. Put your building in.</h1>
      <div class="calc-wrap">
        <div class="calc-tabs"><button class="calc-tab active" data-mode="ht">Bulk HT</button><button class="calc-tab" data-mode="tf">Transformer capex</button></div>
        <div id="htPanel">
          <div class="field"><label>Flats <span class="fv mono" id="ht_flats_v">60</span></label><input type="range" id="ht_flats" min="20" max="400" value="60" step="10"></div>
          <div class="field"><label>Contract demand (kVA) <span class="fv mono" id="ht_contract_v">500</span></label><input type="range" id="ht_contract" min="100" max="1500" value="500" step="10"></div>
          <div class="field"><label>Peak shave <span class="fv mono" id="ht_shave_v">6.0%</span></label><input type="range" id="ht_shave" min="2" max="10" value="6" step="0.5"></div>
          <div class="field"><label>Demand charge <span class="fv mono" id="ht_rate_v">₹608/kVA</span></label><input type="range" id="ht_rate" min="300" max="900" value="608" step="1"></div>
          <div class="field"><label>Fee model</label><div class="fee-toggle"><button class="active" data-fee="perf">% of saving</button><button data-fee="flat">₹/flat/mo</button></div></div>
          <div class="field" id="ht_perf_field"><label>Fee share <span class="fv mono" id="ht_feepct_v">20%</span></label><input type="range" id="ht_feepct" min="10" max="35" value="20" step="1"></div>
          <div class="field" id="ht_flat_field" style="display:none"><label>Flat fee <span class="fv mono" id="ht_flatfee_v">₹15/flat/mo</span></label><input type="range" id="ht_flatfee" min="5" max="60" value="15" step="1"></div>
        </div>
        <div id="tfPanel" style="display:none">
          <div class="field"><label>Flats <span class="fv mono" id="tf_flats_v">60</span></label><input type="range" id="tf_flats" min="20" max="400" value="60" step="10"></div>
          <div class="field"><label>Transformer rating (kVA) <span class="fv mono" id="tf_rating_v">250</span></label><input type="range" id="tf_rating" min="100" max="1000" value="250" step="10"></div>
          <div class="field"><label>EV penetration <span class="fv mono" id="tf_ev_v">20%</span></label><input type="range" id="tf_ev" min="0" max="60" value="20" step="5"></div>
          <div class="field"><label>Upgrade cost <span class="fv mono" id="tf_cost_v">₹1,200/kVA</span></label><input type="range" id="tf_cost" min="600" max="2500" value="1200" step="50"></div>
        </div>
        <div class="calc-outputs" id="htOut">
          <div class="out-row hero-out"><span class="k">Society keeps / yr<span class="sub">after fee</span></span><span class="v mono" id="ht_net">—</span></div>
          <div class="out-row"><span class="k">Peak reduced</span><span class="v mono" id="ht_kva">—</span></div>
          <div class="out-row"><span class="k">Demand charge saved / yr</span><span class="v mono" id="ht_gross">—</span></div>
          <div class="out-row"><span class="k">Fee / yr</span><span class="v mono" id="ht_fee">—</span></div>
        </div>
        <div class="calc-outputs" id="tfOut" style="display:none">
          <div class="out-row hero-out"><span class="k">Capex deferred</span><span class="v mono" id="tf_capex">—</span></div>
          <div class="out-row"><span class="k">Uncoordinated EV load</span><span class="v mono" id="tf_ev_kw">—</span></div>
          <div class="out-row"><span class="k">Recovered via coordination</span><span class="v mono" id="tf_rec_kw">—</span></div>
          <div class="out-row"><span class="k">New headroom</span><span class="v mono" id="tf_margin">—</span></div>
        </div>
      </div>`, onEnter: wireCalculator },

    { id: "data", dwell: 9000, pitch: false, body: () => `
      <div class="eyebrow">08 &middot; the data, honestly</div>
      <h1>What's real today, what's on the roadmap</h1>
      <p class="lede">Not the discom's smart meter API — it has no public third-party interface yet, and we say that before a judge finds it.</p>
      <div class="datagrid">
        <div class="datacard"><span class="tag now">Real, today</span><h4>Building Data Genome Project 2</h4><p>Four real buildings, two years, held-out test months — the benchmark's forecaster is validated on this, not synthetic data.</p></div>
        <div class="datacard"><span class="tag now">Real, today</span><h4>Society-owned sub-meters (Path A)</h4><p>Every bulk HT society already sub-meters each flat for its own bill. Access is a contract with the RWA, not a regulator.</p></div>
        <div class="datacard"><span class="tag planned">Planned, not yet integrated</span><h4>IRED &middot; IIT Bombay</h4><p>Indian residential load-shape dataset — planned to calibrate archetype behaviour to real Indian households, not yet wired into the model.</p></div>
        <div class="datacard"><span class="tag planned">Planned, not yet integrated</span><h4>Low Carbon London</h4><p>Planned for price-responsiveness calibration. Not currently used — synthetic archetypes stand in today.</p></div>
        <div class="datacard"><span class="tag planned">Planned, not yet integrated</span><h4>Hyderabad AC dataset &middot; iAWE &middot; I-BLEND</h4><p>Planned for thermal and appliance-signature calibration specific to Indian housing stock and climate. On the roadmap, stated as such.</p></div>
        <div class="datacard"><span class="tag now">Real, today</span><h4>Retrofit CT clamp + ESP32 (Path C)</h4><p>For societies without sub-metering — proven, low-cost hardware pattern, not a research problem.</p></div>
      </div>
      <div class="callout"><b>We don't need smart-meter-grade data to run.</b> Aggregate active power per flat at 15-minute resolution plus a few availability flags is enough — high-resolution data trains the model once, offline, and is a design choice, not a gap we're hiding.</div>` },

    { id: "wedge", dwell: 7000, pitch: false, body: () => `
      <div class="eyebrow">09 &middot; why nobody already does this</div>
      <h1>Adjacent categories exist. Naming them is the credible move.</h1>
      <table class="compare"><thead><tr><th>Category</th><th>Does</th><th>Doesn't</th></tr></thead><tbody>
        <tr><td>AMI / smart-meter vendors</td><td>Instruments the meter</td><td>Doesn't coordinate load</td></tr>
        <tr><td>Commercial ESCOs</td><td>Demand-charge cuts for one large HT consumer</td><td>Not built for distributed residential coordination</td></tr>
        <tr><td>Global DERMS</td><td>The validated reference category</td><td>Not localized to Indian tariffs, appliances, societies</td></tr>
        <tr class="us"><td>Aethergrid</td><td>Deterministic dispatch <span class="check">&#10003;</span> fairness ledger <span class="check">&#10003;</span></td><td>&mdash;</td></tr>
      </tbody></table>
      <div class="callout gold"><b>A black box that defers the same six flats every month gets voted out at the next general body meeting.</b> That's a real RWA governance dynamic. Nobody adjacent sells explainability and fairness as the product.</div>` },

    { id: "scaleup", dwell: 8000, pitch: false, body: () => `
      <div class="eyebrow">10 &middot; how this scales further</div>
      <h1>Feeder, then circle, then state — the same mechanism, not a bigger promise</h1>
      <p class="lede">The colony sim already proves the coordination logic runs independently at multiple transformers on one feeder. Scaling up is federation, not reinvention:</p>
      <div class="step-row">
        <div class="step"><div class="n">NOW</div><p>One society, one transformer — the reference build, fully detailed.</p></div>
        <div class="step"><div class="n">PROVEN</div><p>Three transformers, one feeder, cross-society headroom comparison — running today in the world sim.</p></div>
        <div class="step"><div class="n">NEXT</div><p>One DISCOM circle: dozens of feeders, aggregated into a single control-room view, same fairness ledger per transformer.</p></div>
        <div class="step"><div class="n">LATER</div><p>State-level rollout riding RDSS's already-funded DT metering — deployment cost is integration, not new hardware.</p></div>
      </div>
      <div class="callout"><b>Rides a real policy tailwind, not a bet.</b> The sub-metering this depends on is already being installed nationally under RDSS whether or not we exist.</div>` },

    { id: "ask", dwell: 8000, pitch: true, body: () => `
      <div class="eyebrow">11 &middot; the ask</div>
      <h1>Not a bigger model. One real data-sharing agreement.</h1>
      <p class="lede">Six to twelve months of one society's real sub-meter billing data, validated against our forecaster on top of the published research datasets already in use.</p>
      <div class="callout gold"><b>Why this, specifically:</b> it answers "is this real" better than any dataset citation can, because it's our own pilot, not someone else's study — and it's the same proof point an investor asks for first, because it's the leading indicator a real sale is close behind it.</div>
      <div class="kpi-row" style="margin-top:26px">
        <div class="kpi"><div class="label">Method</div><div class="value ok">Validated</div><div class="sub">real meter data, real tariff</div></div>
        <div class="kpi"><div class="label">Scale</div><div class="value ok">Demonstrated</div><div class="sub">three transformers, live</div></div>
        <div class="kpi"><div class="label">Economics</div><div class="value gold">Computed</div><div class="sub">not asserted — try it yourself</div></div>
      </div>` },
  ];

  const deck = document.getElementById("deck");
  SLIDES.forEach((s, i) => {
    const div = document.createElement("div");
    div.className = "slide"; div.id = "slide-" + s.id;
    div.innerHTML = `<div class="slide-inner">${s.body()}</div>`;
    deck.appendChild(div);
  });

  // ---------------------------------------------------- pitch / deep-dive mode
  // Pitch mode restricts navigation to the 6 slides matched to the 60-second
  // script in PITCH_PREP.md. Same slide objects, just a filtered nav set --
  // switching modes never duplicates content, and always lands on the same
  // slide id if it exists in the target mode.
  let mode = "deep"; // "deep" | "pitch"
  let idx = 0;
  function visibleIndices() { return SLIDES.map((s, i) => i).filter(i => mode === "deep" || SLIDES[i].pitch); }
  const dotsEl = document.getElementById("dots");

  function rebuildDots() {
    dotsEl.innerHTML = "";
    visibleIndices().forEach((i) => {
      const b = document.createElement("button");
      b.addEventListener("click", () => goTo(i));
      dotsEl.appendChild(b);
    });
  }
  rebuildDots();

  function setMode(next) {
    const currentId = SLIDES[idx].id;
    mode = next;
    document.getElementById("modeBtn").textContent = mode === "pitch" ? "Pitch mode (6)" : "Deep-dive (12)";
    document.getElementById("modeBtn").classList.toggle("active", mode === "pitch");
    rebuildDots();
    const vis = visibleIndices();
    const sameIdx = vis.find(i => SLIDES[i].id === currentId);
    goTo(sameIdx !== undefined ? sameIdx : vis[0]);
  }
  document.getElementById("modeBtn").addEventListener("click", () => setMode(mode === "deep" ? "pitch" : "deep"));

  function goTo(i) {
    if (!visibleIndices().includes(i)) return;
    idx = i;
    document.querySelectorAll(".slide").forEach((el, j) => el.classList.toggle("active", j === idx));
    const vis = visibleIndices();
    const posInVis = vis.indexOf(idx);
    document.querySelectorAll(".dots button").forEach((b, j) => b.classList.toggle("active", j === posInVis));
    document.getElementById("progressFill").style.width = ((posInVis + 1) / vis.length * 100) + "%";
    document.getElementById("slideCount").textContent = (posInVis + 1) + " / " + vis.length;
    const s = SLIDES[idx];
    if (s.onEnter && !s._entered) { s.onEnter(); s._entered = true; }
    if (s.onShow) s.onShow();
    if (s.id === "map" && !s._mapBuilt) { buildMap(); s._mapBuilt = true; }
    scheduleAutoplay();
  }
  function stepIndex(dir) {
    const vis = visibleIndices();
    const pos = vis.indexOf(idx);
    const nextPos = pos + dir;
    if (nextPos >= 0 && nextPos < vis.length) goTo(vis[nextPos]);
  }
  function next() { stepIndex(1); }
  function prev() { stepIndex(-1); }

  document.getElementById("navLeft").addEventListener("click", prev);
  document.getElementById("navRight").addEventListener("click", next);
  document.getElementById("arrowLeft").addEventListener("click", prev);
  document.getElementById("arrowRight").addEventListener("click", next);
  window.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === " ") next();
    else if (e.key === "ArrowLeft") prev();
  });

  // ---------------------------------------------------------------- autoplay
  // Per-slide dwell time, not a flat interval -- and the calculator slide's
  // dwell is null, meaning autoplay pauses there (not skips) until a manual
  // advance, so nobody's live interaction with it gets yanked away.
  let autoplayOn = false, autoplayTimer = null;
  const autoplayBtn = document.getElementById("autoplayBtn");
  function scheduleAutoplay() {
    if (autoplayTimer) { clearTimeout(autoplayTimer); autoplayTimer = null; }
    if (!autoplayOn) return;
    const dwell = SLIDES[idx].dwell;
    if (dwell == null) return; // paused here until the user moves on manually
    autoplayTimer = setTimeout(() => {
      const vis = visibleIndices();
      if (vis.indexOf(idx) >= vis.length - 1) goTo(vis[0]); else next();
    }, dwell);
  }
  autoplayBtn.addEventListener("click", () => {
    autoplayOn = !autoplayOn;
    autoplayBtn.classList.toggle("on", autoplayOn);
    autoplayBtn.innerHTML = autoplayOn ? "&#10074;&#10074; Autoplay on" : "&#9654; Autoplay";
    scheduleAutoplay();
  });

  goTo(0);

  // ------------------------------------------------------------- map slide
  function buildMap() {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.getElementById("mapSvg");
    const CX = 450, CY = 210, R = 150;
    const nodes = [
      { label: "DATA", sub: "real + planned" }, { label: "METHOD", sub: "q95 constraint" },
      { label: "EVIDENCE", sub: "real benchmark" }, { label: "WORLD SIM", sub: "colony proof" },
      { label: "BUYERS", sub: "3-tier ladder" }, { label: "ROI", sub: "computed live" },
    ];
    const N = nodes.length;
    nodes.forEach((n, i) => {
      const ang = (i / N) * Math.PI * 2 - Math.PI / 2;
      n.x = CX + Math.cos(ang) * R; n.y = CY + Math.sin(ang) * R;
    });
    function el(tag, attrs) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }
    const beams = [];
    for (const n of nodes) {
      svg.appendChild(el("line", { x1: CX, y1: CY, x2: n.x, y2: n.y, stroke: "var(--border-glow)", "stroke-width": 1.2 }));
      const pulse = el("circle", { r: 3, fill: "var(--accent)" });
      pulse.style.filter = "drop-shadow(0 0 4px var(--accent))";
      svg.appendChild(pulse);
      beams.push({ pulse, t: Math.random(), speed: 0.1 + Math.random() * 0.05, x1: CX, y1: CY, x2: n.x, y2: n.y });
    }
    svg.appendChild(el("circle", { cx: CX, cy: CY, r: 44, fill: "var(--panel)", stroke: "var(--gold)", "stroke-width": 2 }));
    const t1 = el("text", { x: CX, y: CY - 3, "text-anchor": "middle", "font-size": 13, fill: "var(--gold)", "font-weight": 700 }); t1.textContent = "AETHER"; svg.appendChild(t1);
    const t2 = el("text", { x: CX, y: CY + 13, "text-anchor": "middle", "font-size": 13, fill: "var(--gold)", "font-weight": 700 }); t2.textContent = "GRID"; svg.appendChild(t2);
    for (const n of nodes) {
      svg.appendChild(el("circle", { class: "node-circle", cx: n.x, cy: n.y, r: 34 }));
      const l1 = el("text", { class: "node-label", x: n.x, y: n.y - 2 }); l1.textContent = n.label; svg.appendChild(l1);
      const l2 = el("text", { x: n.x, y: n.y + 14, "text-anchor": "middle", "font-size": 8.5, fill: "var(--muted)" }); l2.textContent = n.sub; svg.appendChild(l2);
    }
    function lerp(a, b, t) { return a + (b - a) * t; }
    (function anim() {
      for (const b of beams) {
        b.t = (b.t + b.speed * 0.016) % 1;
        const tri = b.t < 0.5 ? b.t * 2 : (1 - b.t) * 2;
        b.pulse.setAttribute("cx", lerp(b.x1, b.x2, tri));
        b.pulse.setAttribute("cy", lerp(b.y1, b.y2, tri));
      }
      requestAnimationFrame(anim);
    })();
  }

  // --------------------------------------------------------------- calc
  // ------------------------------------------------------- evidence bars
  function countUp(el, from, to, dur, fmt) {
    const t0 = performance.now();
    function step(now) {
      const t = Math.min(1, (now - t0) / dur);
      el.textContent = fmt(Math.round(from + (to - from) * t));
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }
  function animateEvidenceBars() {
    const noControl = 1320302, ours = 1148853;
    const barNC = document.getElementById("barNoControl"), barO = document.getElementById("barOurs");
    const vNC = document.getElementById("barNoControlV"), vO = document.getElementById("barOursV");
    const delta = document.getElementById("barDelta");
    if (!barNC) return;
    barNC.style.transition = "none"; barO.style.transition = "none";
    barNC.style.width = "0%"; barO.style.width = "0%";
    vNC.textContent = ""; vO.textContent = ""; delta.textContent = "";
    // force reflow so the transition below actually restarts on re-entry
    void barNC.offsetWidth;
    requestAnimationFrame(() => {
      barNC.style.transition = "width 900ms ease";
      barO.style.transition = "width 900ms ease";
      barNC.style.width = "100%";
      setTimeout(() => { barO.style.width = ((ours / noControl) * 100) + "%"; }, 150);
    });
    countUp(vNC, 0, noControl, 900, rupee);
    setTimeout(() => countUp(vO, 0, ours, 900, rupee), 150);
    setTimeout(() => { delta.innerHTML = `Real monthly saving: <b>${rupee(noControl - ours)}</b> &middot; ~13% of the bill`; }, 1100);
  }

  // -------------------------------------------------- world-sim proof embed
  // Live iframe of the world sim, since both apps share a local origin --
  // measured against a 1200ms load budget; falls back to a text pointer
  // rather than a broken/blank frame if it's ever slow on the presenting
  // machine.
  function mountWorldSimProof() {
    const container = document.getElementById("proofEmbed");
    if (!container) return;
    const t0 = performance.now();
    const iframe = document.createElement("iframe");
    iframe.className = "proof-iframe";
    iframe.loading = "lazy";
    iframe.title = "Aethergrid world simulation, live";
    iframe.addEventListener("load", () => {
      if (performance.now() - t0 > 1200) {
        container.innerHTML = '<div class="proof-fallback">World sim proof runs live at <a href="../viz3d/index.html" target="_blank">../viz3d/index.html</a> — took too long to embed inline on this machine.</div>';
      }
    });
    iframe.src = "../viz3d/index.html";
    container.appendChild(iframe);
  }

  function wireCalculator() {
    const tabs = document.querySelectorAll(".calc-tab");
    tabs.forEach(t => t.addEventListener("click", () => {
      tabs.forEach(x => x.classList.remove("active")); t.classList.add("active");
      const mode = t.dataset.mode;
      document.getElementById("htPanel").style.display = mode === "ht" ? "block" : "none";
      document.getElementById("tfPanel").style.display = mode === "tf" ? "block" : "none";
      document.getElementById("htOut").style.display = mode === "ht" ? "flex" : "none";
      document.getElementById("tfOut").style.display = mode === "tf" ? "flex" : "none";
    }));
    let feeMode = "perf";
    document.querySelectorAll(".fee-toggle button").forEach(b => b.addEventListener("click", () => {
      document.querySelectorAll(".fee-toggle button").forEach(x => x.classList.remove("active"));
      b.classList.add("active"); feeMode = b.dataset.fee;
      document.getElementById("ht_perf_field").style.display = feeMode === "perf" ? "block" : "none";
      document.getElementById("ht_flat_field").style.display = feeMode === "flat" ? "block" : "none";
      calcHT();
    }));
    function calcHT() {
      const flats = +document.getElementById("ht_flats").value;
      const contract = +document.getElementById("ht_contract").value;
      const shave = +document.getElementById("ht_shave").value;
      const rate = +document.getElementById("ht_rate").value;
      const feepct = +document.getElementById("ht_feepct").value;
      const flatfee = +document.getElementById("ht_flatfee").value;
      const kvaShaved = contract * (shave / 100);
      const annualGross = kvaShaved * rate * 12;
      const annualFee = feeMode === "perf" ? annualGross * (feepct / 100) : flats * flatfee * 12;
      document.getElementById("ht_kva").textContent = kvaShaved.toFixed(1) + " kVA";
      document.getElementById("ht_gross").textContent = rupee(annualGross);
      document.getElementById("ht_fee").textContent = rupee(annualFee);
      document.getElementById("ht_net").textContent = rupee(annualGross - annualFee);
    }
    ["ht_flats", "ht_contract", "ht_shave", "ht_rate", "ht_feepct", "ht_flatfee"].forEach(id => {
      document.getElementById(id).addEventListener("input", function () {
        if (id === "ht_flats") document.getElementById("ht_flats_v").textContent = this.value;
        if (id === "ht_contract") document.getElementById("ht_contract_v").textContent = this.value;
        if (id === "ht_shave") document.getElementById("ht_shave_v").textContent = (+this.value).toFixed(1) + "%";
        if (id === "ht_rate") document.getElementById("ht_rate_v").textContent = "₹" + this.value + "/kVA";
        if (id === "ht_feepct") document.getElementById("ht_feepct_v").textContent = this.value + "%";
        if (id === "ht_flatfee") document.getElementById("ht_flatfee_v").textContent = "₹" + this.value + "/flat/mo";
        calcHT();
      });
    });
    function calcTF() {
      const flats = +document.getElementById("tf_flats").value;
      const rating = +document.getElementById("tf_rating").value;
      const ev = +document.getElementById("tf_ev").value;
      const cost = +document.getElementById("tf_cost").value;
      const evKw = flats * (ev / 100) * 3.3 * 0.7;
      const recKw = evKw * 0.6;
      document.getElementById("tf_ev_kw").textContent = evKw.toFixed(1) + " kW";
      document.getElementById("tf_rec_kw").textContent = recKw.toFixed(1) + " kW";
      document.getElementById("tf_capex").textContent = rupee(recKw * cost);
      document.getElementById("tf_margin").textContent = "+" + (rating > 0 ? (recKw / rating * 100) : 0).toFixed(1) + "%";
    }
    ["tf_flats", "tf_rating", "tf_ev", "tf_cost"].forEach(id => {
      document.getElementById(id).addEventListener("input", function () {
        if (id === "tf_flats") document.getElementById("tf_flats_v").textContent = this.value;
        if (id === "tf_rating") document.getElementById("tf_rating_v").textContent = this.value;
        if (id === "tf_ev") document.getElementById("tf_ev_v").textContent = this.value + "%";
        if (id === "tf_cost") document.getElementById("tf_cost_v").textContent = "₹" + this.value + "/kVA";
        calcTF();
      });
    });
    calcHT(); calcTF();
  }
})();
