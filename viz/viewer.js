// Smart Society Energy Simulation -- pure playback layer.
// This file NEVER computes simulation logic. Every value it draws comes
// directly from a precomputed scenario JSON (see aethergrid/worldsim/).

(function () {
  "use strict";

  // ---------------------------------------------------------------- state
  const state = {
    scenarioKey: "normal",
    data: null,
    frameIdx: 40,
    playing: false,
    speed: 1,
    view: "3d",
    selected: null, // {type:'house', id} | {type:'workspace'} | {type:'transformer'}
    cam: { rotY: Math.PI * 0.25, zoom: 1.0, panX: 0, panY: 0 },
    drag: null,
  };

  const COLORS = {
    load: [ [0.0, "#2b3a67"], [0.35, "#4fd1c5"], [0.6, "#f5b942"], [1.0, "#f0553a"] ],
  };

  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
  function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgbToCss(rgb, a) { return `rgba(${rgb[0]|0},${rgb[1]|0},${rgb[2]|0},${a===undefined?1:a})`; }
  function lerpColorStops(stops, t) {
    t = clamp(t, 0, 1);
    for (let i = 0; i < stops.length - 1; i++) {
      const [t0, c0] = stops[i], [t1, c1] = stops[i + 1];
      if (t >= t0 && t <= t1) {
        const localT = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
        const a = hexToRgb(c0), b = hexToRgb(c1);
        return [lerp(a[0], b[0], localT), lerp(a[1], b[1], localT), lerp(a[2], b[2], localT)];
      }
    }
    return hexToRgb(stops[stops.length - 1][1]);
  }
  function loadColor(kw, maxKw) {
    const t = clamp(kw / Math.max(maxKw, 0.5), 0, 1);
    return lerpColorStops(COLORS.load, t);
  }

  // ------------------------------------------------------------- data api
  function frame() { return state.data.frames[state.frameIdx]; }
  function houseMeta(id) { return state.data.houses[id]; }
  function maxHouseKw() {
    if (state.data._maxKw) return state.data._maxKw;
    let m = 1;
    for (const f of state.data.frames) for (const h of f.houses) m = Math.max(m, h.kw);
    state.data._maxKw = m;
    return m;
  }

  // ---------------------------------------------------------------- canvas
  const canvas = document.getElementById("world");
  const ctx = canvas.getContext("2d");
  let dpr = window.devicePixelRatio || 1;

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    canvas.style.width = rect.width + "px";
    canvas.style.height = rect.height + "px";
  }
  window.addEventListener("resize", resize);

  // -------------------------------------------------------- iso projection
  const TILE_W = 46, TILE_H = 23, HOUSE_H = 34;

  function isoBase() {
    const cols = state.data.meta.n_households > 0 ? Math.max(...state.data.houses.map(h => h.grid_x)) + 1 : 10;
    const rows = Math.max(...state.data.houses.map(h => h.grid_z)) + 1;
    return { cols, rows };
  }

  function project(gx, gz, elevate) {
    elevate = elevate || 0;
    const cx = canvas.width / 2 / dpr + state.cam.panX;
    const cy = canvas.height * 0.32 / dpr + state.cam.panY;
    // simple 4-way rotation snap for an "orbit" feel without full 3D matrix math
    const rot = Math.round(state.cam.rotY / (Math.PI / 2)) % 4;
    let x = gx, z = gz;
    if (rot === 1) { const t = x; x = z; z = -t; }
    else if (rot === 2) { x = -x; z = -z; }
    else if (rot === 3) { const t = x; x = -z; z = t; }
    const zoom = state.cam.zoom;
    const sx = cx + (x - z) * (TILE_W / 2) * zoom;
    const sy = cy + (x + z) * (TILE_H / 2) * zoom - elevate * zoom;
    return [sx, sy];
  }

  function drawIsoBox(gx, gz, w, d, h, topColor, leftColor, rightColor) {
    const zoom = state.cam.zoom;
    const hw = (w * TILE_W / 2) * zoom, hd = (d * TILE_H / 2) * zoom, hh = h * zoom;
    const [cx, cy] = project(gx, gz, 0);
    const top = [cx, cy - hh];
    const left = [cx - hw, cy - hh + hd];
    const right = [cx + hw, cy - hh + hd];
    const bottom = [cx, cy - hh + hd * 2];
    // top face
    ctx.beginPath(); ctx.moveTo(top[0], top[1]); ctx.lineTo(right[0], right[1]);
    ctx.lineTo(bottom[0], bottom[1]); ctx.lineTo(left[0], left[1]); ctx.closePath();
    ctx.fillStyle = topColor; ctx.fill();
    // left face
    ctx.beginPath(); ctx.moveTo(left[0], left[1]); ctx.lineTo(bottom[0], bottom[1]);
    ctx.lineTo(bottom[0], bottom[1] + hh); ctx.lineTo(left[0], left[1] + hh); ctx.closePath();
    ctx.fillStyle = leftColor; ctx.fill();
    // right face
    ctx.beginPath(); ctx.moveTo(right[0], right[1]); ctx.lineTo(bottom[0], bottom[1]);
    ctx.lineTo(bottom[0], bottom[1] + hh); ctx.lineTo(right[0], right[1] + hh); ctx.closePath();
    ctx.fillStyle = rightColor; ctx.fill();
    return { top, left, right, bottom, cx, cy: cy - hh };
  }

  function shade(rgb, f) { return rgbToCss([rgb[0]*f, rgb[1]*f, rgb[2]*f]); }

  // ------------------------------------------------------------- sky/ground
  function skyGradient(env) {
    const alt = env.sun_altitude; // radians, >0 day
    const t = clamp((alt + 0.3) / 0.6, 0, 1); // -0.3..0.3 dawn/dusk transition band
    const night = ["#04070f", "#0a1326"];
    const dusk = ["#2b2140", "#7a4a55"];
    const day = ["#8fc7ea", "#e8f3ff"];
    let top, bot;
    if (alt <= -0.05) { top = night[0]; bot = night[1]; }
    else if (alt < 0.15) {
      const tt = clamp((alt + 0.05) / 0.2, 0, 1);
      top = rgbToCss(lerpColorStops([[0, night[0]], [1, dusk[0]]], tt));
      bot = rgbToCss(lerpColorStops([[0, night[1]], [1, dusk[1]]], tt));
    } else {
      const tt = clamp((alt - 0.15) / 0.4, 0, 1);
      top = rgbToCss(lerpColorStops([[0, dusk[0]], [1, day[0]]], tt));
      bot = rgbToCss(lerpColorStops([[0, dusk[1]], [1, day[1]]], tt));
    }
    const cloud = env.cloud_factor || 0;
    return { top, bot, dim: 1 - cloud * 0.35, alt };
  }

  // -------------------------------------------------------------- 3D scene
  function drawScene3D() {
    const f = frame();
    const env = f.environment;
    const sky = skyGradient(env);
    const w = canvas.width / dpr, h = canvas.height / dpr;

    const grad = ctx.createLinearGradient(0, 0, 0, h * 0.75);
    grad.addColorStop(0, sky.top); grad.addColorStop(1, sky.bot);
    ctx.fillStyle = grad; ctx.fillRect(0, 0, w, h);

    // sun / moon disc
    const sunX = w * (0.5 + 0.35 * Math.cos(env.sun_azimuth));
    const sunY = h * 0.42 - h * 0.32 * Math.max(0, env.sun_altitude) - (env.sun_altitude < 0 ? h * 0.05 : 0);
    if (env.sun_altitude > -0.2) {
      ctx.save();
      ctx.globalAlpha = env.sun_altitude > 0 ? 0.9 : 0.5;
      const sunGrad = ctx.createRadialGradient(sunX, sunY, 2, sunX, sunY, env.sun_altitude > 0 ? 46 : 18);
      sunGrad.addColorStop(0, env.sun_altitude > 0 ? "#fff6dc" : "#dfe6f2");
      sunGrad.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = sunGrad; ctx.beginPath(); ctx.arc(sunX, sunY, env.sun_altitude > 0 ? 46 : 18, 0, 7); ctx.fill();
      ctx.restore();
    }

    const groundY = h * 0.78;
    const groundGrad = ctx.createLinearGradient(0, groundY - 60, 0, h);
    const groundBase = env.sun_altitude > 0 ? [24, 32, 26] : [8, 11, 16];
    groundGrad.addColorStop(0, rgbToCss(groundBase, 1));
    groundGrad.addColorStop(1, rgbToCss(groundBase.map(c => c * 0.7), 1));
    ctx.fillStyle = groundGrad; ctx.fillRect(0, groundY - 200, w, h - groundY + 200);

    const { cols, rows } = isoBase();
    ctx.save();
    ctx.translate(0, groundY - h * 0.5);

    // road grid
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    for (let x = 0; x <= cols; x++) {
      const a = project(x - 0.5, -0.5), b = project(x - 0.5, rows - 0.5);
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    }
    for (let z = 0; z <= rows; z++) {
      const a = project(-0.5, z - 0.5), b = project(cols - 0.5, z - 0.5);
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    }

    // depth-sorted entities
    const entities = [];
    for (const hm of state.data.houses) entities.push({ kind: "house", meta: hm, depth: hm.grid_x + hm.grid_z });
    if (state.data.workspace) entities.push({ kind: "workspace", meta: state.data.workspace, depth: state.data.workspace.grid_x + state.data.workspace.grid_z });
    entities.push({ kind: "transformer", meta: { grid_x: cols, grid_z: rows / 2 }, depth: cols + rows / 2 + 0.5 });
    entities.push({ kind: "watertank", meta: { grid_x: -1.4, grid_z: rows - 1 }, depth: -1.4 + rows - 1 - 0.5 });
    for (let i = 0; i < state.data.common_infra.streetlight_count; i++) {
      const gx = (i % cols) + 0.5, gz = Math.floor(i / cols) % rows;
      entities.push({ kind: "streetlight", meta: { grid_x: gx, grid_z: gz }, depth: gx + gz - 0.4 });
    }
    entities.sort((a, b) => a.depth - b.depth);

    const maxKw = maxHouseKw();
    for (const e of entities) {
      if (e.kind === "house") drawHouse3D(e.meta, f, maxKw, sky.dim);
      else if (e.kind === "workspace") drawWorkspace3D(f, sky.dim);
      else if (e.kind === "transformer") drawTransformer3D(e.meta, f);
      else if (e.kind === "watertank") drawWaterTank3D(e.meta, f);
      else if (e.kind === "streetlight") drawStreetlight3D(e.meta, f);
    }
    ctx.restore();
  }

  const houseHitboxes = [];

  function drawHouse3D(meta, f, maxKw, dim) {
    const hs = f.houses[meta.id];
    const floors = meta.floors || 1;
    const height = HOUSE_H * (0.7 + 0.3 * floors);
    const rgb = loadColor(hs.kw, maxKw);
    const baseTop = shade(rgb, 0.55 * dim);
    const baseLeft = shade(rgb, 0.38 * dim);
    const baseRight = shade(rgb, 0.46 * dim);
    const box = drawIsoBox(meta.grid_x, meta.grid_z, 0.72, 0.72, height,
      "#3a4258", shade([44, 50, 68], 1), shade([54, 61, 82], 1));

    // roof tint by archetype-ish hash for variety
    // window glow
    const glowIntensity = clamp(hs.kw / Math.max(maxKw * 0.6, 0.5), 0.08, 1);
    ctx.save();
    ctx.globalAlpha = 0.55 + glowIntensity * 0.4;
    ctx.fillStyle = rgbToCss(rgb);
    const winW = 6 * state.cam.zoom, winH = 8 * state.cam.zoom;
    ctx.fillRect(box.left[0] + 6, box.left[1] + 6, winW, winH);
    ctx.fillRect(box.right[0] - 12, box.right[1] + 6, winW, winH);
    ctx.restore();

    // solar panel glow on roof
    if (meta.has_solar) {
      const s = clamp(hs.solar_kw / 4, 0, 1);
      ctx.save();
      ctx.globalAlpha = 0.35 + s * 0.55;
      ctx.fillStyle = "#4fd1c5";
      ctx.fillRect(box.top[0] - 6, box.top[1] + 2, 12, 5);
      ctx.restore();
    }

    // EV pulsing ring
    if (meta.has_ev && hs.ev_state === "charging") {
      const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 220);
      ctx.save();
      ctx.strokeStyle = `rgba(52,211,153,${0.4 + pulse * 0.5})`;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.ellipse(box.bottom[0], box.bottom[1] + 4, 12 + pulse * 3, 5 + pulse, 0, 0, 7); ctx.stroke();
      ctx.restore();
    }

    // curtailment ring
    if (hs.curtailed) {
      ctx.save();
      ctx.strokeStyle = "rgba(248,113,113,0.85)"; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.ellipse(box.bottom[0], box.bottom[1] + 2, 14, 6, 0, 0, 7); ctx.stroke();
      ctx.restore();
    }

    houseHitboxes.push({ id: meta.id, x: box.cx, y: box.cy, r: 16 * state.cam.zoom, kind: "house" });
  }

  function drawWorkspace3D(f, dim) {
    if (!state.data.workspace || !f.workspace) return;
    const ws = f.workspace;
    const maxWs = 90;
    const rgb = loadColor(ws.kw, maxWs);
    const box = drawIsoBox(state.data.workspace.grid_x, state.data.workspace.grid_z, 1.5, 1.1, 58,
      "#4a5170", shade([50, 56, 76], 1), shade([60, 67, 90], 1));
    ctx.save();
    ctx.globalAlpha = 0.5 + clamp(ws.kw / maxWs, 0, 1) * 0.45;
    ctx.fillStyle = rgbToCss(rgb);
    for (let i = 0; i < 3; i++) {
      ctx.fillRect(box.left[0] + 4, box.left[1] + 6 + i * 9, 9, 5);
      ctx.fillRect(box.right[0] - 13, box.right[1] + 6 + i * 9, 9, 5);
    }
    ctx.restore();
    houseHitboxes.push({ id: -1, x: box.cx, y: box.cy, r: 22 * state.cam.zoom, kind: "workspace" });
  }

  function transformerColor(stateName) {
    return { NORMAL: "#34d399", WARNING: "#fbbf24", CRITICAL: "#f59e0b", BREACH: "#f87171", TRIPPED: "#ef4444" }[stateName] || "#8b95ab";
  }

  function drawTransformer3D(meta, f) {
    const grid = f.grid;
    const frac = clamp(grid.transformer_kva / grid.rating_kva, 0, 1.3);
    const col = transformerColor(grid.state);
    const flashing = grid.state === "TRIPPED" && Math.sin(performance.now() / 130) > 0;
    drawIsoBox(meta.grid_x, meta.grid_z, 0.55, 0.55, 30, "#565f78", "#3c4258", "#474f68");
    const barH = 46, barW = 8 * state.cam.zoom;
    const [bx, by] = project(meta.grid_x, meta.grid_z, 30);
    ctx.fillStyle = "rgba(20,24,34,0.5)";
    ctx.fillRect(bx - barW / 2, by - barH, barW, barH);
    const fillH = barH * Math.min(1, frac);
    ctx.fillStyle = flashing ? "#ffffff" : col;
    ctx.fillRect(bx - barW / 2, by - fillH, barW, fillH);
    ctx.strokeStyle = "rgba(255,255,255,0.3)"; ctx.strokeRect(bx - barW / 2, by - barH, barW, barH);
    ctx.fillStyle = flashing ? "#fff" : col;
    ctx.font = `${10 * state.cam.zoom}px "IBM Plex Mono", monospace`;
    ctx.textAlign = "center";
    ctx.fillText(grid.state, bx, by - barH - 8);
    houseHitboxes.push({ id: -2, x: bx, y: by - barH / 2, r: 20 * state.cam.zoom, kind: "transformer" });
  }

  function drawWaterTank3D(meta, f) {
    const lvl = f.society.common_infra.water_tank_level_pct / 100;
    const box = drawIsoBox(meta.grid_x, meta.grid_z, 0.4, 0.4, 26, "#4a5568", "#333c4a", "#3d4657");
    const [bx, by] = project(meta.grid_x, meta.grid_z, 26);
    ctx.fillStyle = "rgba(20,24,34,0.5)"; ctx.fillRect(bx - 4, by - 20, 8, 20);
    ctx.fillStyle = "#4fd1c5"; ctx.fillRect(bx - 4, by - 20 * lvl, 8, 20 * lvl);
  }

  function drawStreetlight3D(meta, f) {
    const on = f.society.common_infra.streetlights_on;
    const [x, y] = project(meta.grid_x, meta.grid_z, 0);
    ctx.fillStyle = "rgba(120,130,150,0.5)";
    ctx.fillRect(x - 1, y - 14, 2, 14);
    if (on) {
      ctx.save();
      const g = ctx.createRadialGradient(x, y - 15, 0, x, y - 15, 14);
      g.addColorStop(0, "rgba(255,224,150,0.9)"); g.addColorStop(1, "rgba(255,224,150,0)");
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y - 15, 14, 0, 7); ctx.fill();
      ctx.restore();
    }
  }

  // -------------------------------------------------------------- 2D scene
  function drawScene2D() {
    const f = frame();
    const w = canvas.width / dpr, h = canvas.height / dpr;
    ctx.fillStyle = "#0e1524"; ctx.fillRect(0, 0, w, h);
    const { cols, rows } = isoBase();
    const pad = 40;
    const cell = Math.min((w - pad * 2) / cols, (h - pad * 2 - 60) / rows);
    const ox = (w - cell * cols) / 2, oy = 50;
    const maxKw = maxHouseKw();

    ctx.font = "11px 'IBM Plex Mono', monospace";
    for (const meta of state.data.houses) {
      const hs = f.houses[meta.id];
      const x = ox + meta.grid_x * cell, y = oy + meta.grid_z * cell;
      const rgb = loadColor(hs.kw, maxKw);
      ctx.fillStyle = rgbToCss(rgb, 0.92);
      const r = 6;
      ctx.beginPath();
      ctx.moveTo(x + r, y); ctx.arcTo(x + cell - 4, y, x + cell - 4, y + cell - 4, r);
      ctx.arcTo(x + cell - 4, y + cell - 4, x, y + cell - 4, r);
      ctx.arcTo(x, y + cell - 4, x, y, r); ctx.arcTo(x, y, x + cell - 4, y, r);
      ctx.closePath(); ctx.fill();
      if (hs.curtailed) { ctx.strokeStyle = "#f87171"; ctx.lineWidth = 2; ctx.stroke(); }
      ctx.fillStyle = "rgba(10,14,22,0.85)";
      ctx.fillText(hs.kw.toFixed(1), x + 6, y + cell - 14);
      if (meta.has_ev && hs.ev_state === "charging") { ctx.fillStyle = "#34d399"; ctx.beginPath(); ctx.arc(x + cell - 14, y + 12, 3.5, 0, 7); ctx.fill(); }
      if (meta.has_solar && hs.solar_kw > 0.2) { ctx.fillStyle = "#4fd1c5"; ctx.beginPath(); ctx.arc(x + cell - 14, y + 22, 3.5, 0, 7); ctx.fill(); }
      houseHitboxes.push({ id: meta.id, x: x + cell / 2, y: y + cell / 2, r: cell / 2, kind: "house" });
    }

    // transformer strip
    const grid = f.grid;
    const barX = ox + cols * cell + 24, barW = 26, barH = rows * cell;
    ctx.strokeStyle = "rgba(255,255,255,0.15)"; ctx.strokeRect(barX, oy, barW, barH);
    const frac = clamp(grid.transformer_kva / grid.rating_kva, 0, 1.3);
    const col = transformerColor(grid.state);
    ctx.fillStyle = col; ctx.fillRect(barX, oy + barH * (1 - Math.min(1, frac)), barW, barH * Math.min(1, frac));
    ctx.fillStyle = "#e8ecf4"; ctx.font = "10.5px 'IBM Plex Mono', monospace"; ctx.textAlign = "center";
    ctx.save(); ctx.translate(barX + barW / 2, oy - 8); ctx.fillText(grid.state, 0, 0); ctx.restore();
    houseHitboxes.push({ id: -2, x: barX + barW / 2, y: oy + barH / 2, r: barW, kind: "transformer" });
    ctx.textAlign = "left";
  }

  // --------------------------------------------------------------- render
  function render() {
    houseHitboxes.length = 0;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (state.view === "3d") drawScene3D(); else drawScene2D();
    updateHUD();
  }

  function updateHUD() {
    const f = frame();
    const g = f.grid, env = f.environment;
    document.getElementById("kpiKva").textContent = g.transformer_kva.toFixed(1) + " kVA";
    document.getElementById("kpiKvaPct").textContent = ((g.transformer_kva / g.rating_kva) * 100).toFixed(0) + "% of rating";
    document.getElementById("kpiRating").textContent = "rated " + g.rating_kva + " kVA";
    document.getElementById("kpiState").innerHTML = `<span class="pill ${g.state}">${g.state}</span>`;
    document.getElementById("kpiCurtailed").textContent = f.society.fairness.curtailed_house_ids.length;
    document.getElementById("kpiTemp").textContent = env.temperature_c.toFixed(1) + "°C";
    document.getElementById("kpiHumidity").textContent = env.humidity_pct.toFixed(0) + "% RH";
    document.getElementById("kpiSolar").textContent = f.society.solar_kw.toFixed(1) + " kW";
    document.getElementById("kpiCloud").textContent = "cloud " + (env.cloud_factor * 100).toFixed(0) + "%";

    let peak = 0, peakT = 0;
    for (let i = 0; i < state.data.frames.length; i++) {
      if (state.data.frames[i].grid.transformer_kva > peak) { peak = state.data.frames[i].grid.transformer_kva; peakT = state.data.frames[i].t_min; }
    }
    document.getElementById("kpiPeak").textContent = peak.toFixed(1) + " kVA";
    document.getElementById("kpiPeakTime").textContent = minToClock(peakT);

    const bar = document.getElementById("kvaBar");
    bar.style.width = clamp((g.transformer_kva / g.rating_kva) * 100, 0, 100) + "%";
    bar.style.background = transformerColor(g.state);

    document.getElementById("gridDot").style.background = g.available ? "var(--ok)" : "var(--tripped)";
    document.getElementById("gridLabel").textContent = g.available ? "GRID " + g.state : "GRID OUTAGE";

    document.getElementById("timeLabel").textContent = minToClock(f.t_min);
    document.getElementById("dateLabel").textContent = state.data.meta.date + " · " + state.data.meta.scenario;

    renderInspector();
  }

  function minToClock(tmin) {
    const h = Math.floor(tmin / 60) % 24, m = tmin % 60;
    return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0");
  }

  function renderInspector() {
    const el = document.getElementById("inspector");
    if (!state.selected) { el.innerHTML = '<div class="inspector-empty">Click any house, the workspace, or the transformer in the scene to see its live state here.</div>'; return; }
    const f = frame();
    if (state.selected.kind === "house") {
      const meta = houseMeta(state.selected.id);
      const hs = f.houses[state.selected.id];
      el.innerHTML = `
        <div class="inspector-house">
          <h3>House #${meta.id}</h3>
          <div class="archetype">${meta.archetype.replace(/_/g, " ")} &middot; ${meta.floors} floor${meta.floors > 1 ? "s" : ""}</div>
          <div class="badges">
            ${meta.has_ev ? `<span class="badge ${hs.ev_state === 'charging' ? 'on' : ''}">EV ${hs.ev_state}</span>` : ""}
            ${meta.has_solar ? `<span class="badge on">Solar</span>` : ""}
            ${meta.has_battery ? `<span class="badge">Battery ${(hs.battery_soc*100).toFixed(0)}%</span>` : ""}
            ${hs.curtailed ? `<span class="badge" style="color:var(--crit)">Curtailed</span>` : ""}
          </div>
          <div class="stat-row"><span class="k">Load now</span><span class="v mono">${hs.kw.toFixed(2)} kW</span></div>
          <div class="stat-row"><span class="k">Occupants</span><span class="v mono">${hs.occupancy}</span></div>
          <div class="stat-row"><span class="k">Indoor temp</span><span class="v mono">${hs.indoor_temp_c.toFixed(1)}°C</span></div>
          <div class="stat-row"><span class="k">Comfort deviation</span><span class="v mono">${hs.comfort_dev_c.toFixed(1)}°C</span></div>
          <div class="stat-row"><span class="k">AC</span><span class="v mono">${hs.ac_on ? "on" : "off"}</span></div>
          <div class="stat-row"><span class="k">Geyser</span><span class="v mono">${hs.geyser_on ? "on" : "off"}</span></div>
          ${meta.has_ev ? `<div class="stat-row"><span class="k">EV SOC</span><span class="v mono">${(hs.ev_soc*100).toFixed(0)}%</span></div>` : ""}
          ${meta.has_solar ? `<div class="stat-row"><span class="k">Solar now</span><span class="v mono">${hs.solar_kw.toFixed(2)} kW</span></div>` : ""}
          <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
        </div>`;
      drawSparkline("sparkCanvas", state.data.frames.map(fr => fr.houses[state.selected.id].kw));
    } else if (state.selected.kind === "workspace") {
      const ws = f.workspace;
      el.innerHTML = `
        <div class="inspector-house">
          <h3>Workspace</h3>
          <div class="archetype">${state.data.workspace.archetype.replace(/_/g, " ")}</div>
          <div class="stat-row"><span class="k">Load now</span><span class="v mono">${ws.kw.toFixed(1)} kW</span></div>
          <div class="stat-row"><span class="k">Occupancy</span><span class="v mono">${(ws.occupancy_frac*100).toFixed(0)}%</span></div>
          <div class="stat-row"><span class="k">HVAC</span><span class="v mono">${ws.hvac_kw.toFixed(1)} kW</span></div>
          <div class="stat-row"><span class="k">Computers</span><span class="v mono">${ws.computer_kw.toFixed(1)} kW</span></div>
          <div class="stat-row"><span class="k">Solar now</span><span class="v mono">${ws.solar_kw.toFixed(1)} kW</span></div>
          <div class="stat-row"><span class="k">Battery SOC</span><span class="v mono">${(ws.battery_soc*100).toFixed(0)}%</span></div>
          <div class="stat-row"><span class="k">EVs charging</span><span class="v mono">${ws.ev_count_charging}</span></div>
          <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
        </div>`;
      drawSparkline("sparkCanvas", state.data.frames.map(fr => fr.workspace.kw));
    } else if (state.selected.kind === "transformer") {
      const g = f.grid;
      el.innerHTML = `
        <div class="inspector-house">
          <h3>Transformer</h3>
          <div class="archetype">society connection point</div>
          <div class="stat-row"><span class="k">Loading</span><span class="v mono">${g.transformer_kva.toFixed(1)} kVA</span></div>
          <div class="stat-row"><span class="k">Rating</span><span class="v mono">${g.rating_kva} kVA</span></div>
          <div class="stat-row"><span class="k">State</span><span class="v"><span class="pill ${g.state}">${g.state}</span></span></div>
          <div class="stat-row"><span class="k">Curtailed households</span><span class="v mono">${f.society.fairness.curtailed_house_ids.length}</span></div>
          <div class="stat-row"><span class="k">Curtailed this step</span><span class="v mono">${f.society.fairness.total_curtailed_kwh.toFixed(2)} kWh</span></div>
          <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
        </div>`;
      drawSparkline("sparkCanvas", state.data.frames.map(fr => fr.grid.transformer_kva), state.data.frames[0].grid.rating_kva);
    }
  }

  function drawSparkline(id, values, limitLine) {
    const c = document.getElementById(id); if (!c) return;
    const sctx = c.getContext("2d");
    const w = c.width, h = c.height;
    sctx.clearRect(0, 0, w, h);
    const max = Math.max(...values, limitLine || 0) * 1.1 || 1;
    sctx.strokeStyle = "rgba(139,149,171,0.25)"; sctx.beginPath(); sctx.moveTo(0, h - 1); sctx.lineTo(w, h - 1); sctx.stroke();
    if (limitLine) {
      const ly = h - (limitLine / max) * h;
      sctx.strokeStyle = "rgba(248,113,113,0.5)"; sctx.setLineDash([3, 3]);
      sctx.beginPath(); sctx.moveTo(0, ly); sctx.lineTo(w, ly); sctx.stroke(); sctx.setLineDash([]);
    }
    sctx.beginPath();
    values.forEach((v, i) => {
      const x = (i / (values.length - 1)) * w, y = h - (v / max) * h;
      i === 0 ? sctx.moveTo(x, y) : sctx.lineTo(x, y);
    });
    sctx.strokeStyle = "#f5b942"; sctx.lineWidth = 1.6; sctx.stroke();
    const curX = (state.frameIdx / (values.length - 1)) * w;
    const curY = h - (values[state.frameIdx] / max) * h;
    sctx.fillStyle = "#f5b942"; sctx.beginPath(); sctx.arc(curX, curY, 3, 0, 7); sctx.fill();
  }

  function renderEvents() {
    const el = document.getElementById("eventsList");
    const events = state.data.events || [];
    if (!events.length) { el.innerHTML = '<div class="inspector-empty">No events in this scenario.</div>'; return; }
    el.innerHTML = events.map(e => {
      const active = frame().events_active.includes(e.id);
      return `<div class="event-row" style="${active ? 'border-color:var(--accent-glow)' : ''}">
        <span>${e.type.replace(/_/g, " ")}</span>
        <span class="t mono">${minToClock(e.start_min)} +${(e.duration_min/60).toFixed(1)}h</span>
      </div>`;
    }).join("");
  }

  // ------------------------------------------------------------ interaction
  canvas.addEventListener("mousedown", (e) => { state.drag = { x: e.clientX, y: e.clientY, rot: state.cam.rotY, pan: {...state.cam} }; });
  window.addEventListener("mouseup", () => { state.drag = null; });
  window.addEventListener("mousemove", (e) => {
    if (!state.drag) return;
    const dx = e.clientX - state.drag.x;
    if (Math.abs(dx) > 40) { // snap-rotate every 40px of drag, matches the 4-way projection snap
      state.cam.rotY = state.drag.rot + Math.sign(dx) * Math.PI / 2 * Math.floor(Math.abs(dx) / 40);
      render();
    }
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    state.cam.zoom = clamp(state.cam.zoom * (e.deltaY < 0 ? 1.08 : 0.93), 0.5, 2.2);
    render();
  }, { passive: false });

  canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let best = null, bestD = Infinity;
    for (const hb of houseHitboxes) {
      const d = Math.hypot(mx - hb.x, my - hb.y);
      if (d < hb.r && d < bestD) { best = hb; bestD = d; }
    }
    if (best) {
      state.selected = best.kind === "house" ? { kind: "house", id: best.id }
        : best.kind === "workspace" ? { kind: "workspace" } : { kind: "transformer" };
      render();
    }
  });

  // ------------------------------------------------------------------- ui
  function buildScenarioButtons() {
    const g = document.getElementById("scenarioGroup");
    g.innerHTML = "";
    Object.keys(SCENARIOS).forEach((key) => {
      const b = document.createElement("button");
      b.className = "scenario-btn" + (key === state.scenarioKey ? " active" : "");
      b.textContent = SCENARIO_LABELS[key];
      b.onclick = () => setScenario(key);
      g.appendChild(b);
    });
  }

  function setScenario(key) {
    state.scenarioKey = key;
    state.data = SCENARIOS[key];
    state.frameIdx = Math.min(state.frameIdx, state.data.frames.length - 1);
    state.selected = null;
    document.querySelectorAll(".scenario-btn").forEach(b => b.classList.toggle("active", b.textContent === SCENARIO_LABELS[key]));
    document.getElementById("scrub").max = state.data.frames.length - 1;
    renderEvents();
    render();
  }

  document.getElementById("viewGroup").addEventListener("click", (e) => {
    const btn = e.target.closest(".view-btn"); if (!btn) return;
    state.view = btn.dataset.view;
    document.querySelectorAll(".view-btn").forEach(b => b.classList.toggle("active", b === btn));
    render();
  });

  const SPEEDS = [0.25, 1, 5, 20, 100];
  function buildSpeedButtons() {
    const g = document.getElementById("speedGroup");
    SPEEDS.forEach(sp => {
      const b = document.createElement("button");
      b.className = "speed-btn" + (sp === state.speed ? " active" : "");
      b.textContent = sp + "x";
      b.onclick = () => { state.speed = sp; document.querySelectorAll(".speed-btn").forEach(x => x.classList.toggle("active", x === b)); };
      g.appendChild(b);
    });
  }

  const playBtn = document.getElementById("playBtn");
  playBtn.addEventListener("click", () => {
    state.playing = !state.playing;
    playBtn.innerHTML = state.playing ? "&#10074;&#10074;" : "&#9654;";
  });

  const scrub = document.getElementById("scrub");
  scrub.addEventListener("input", () => { state.frameIdx = +scrub.value; render(); });

  let lastTick = performance.now();
  function loop(now) {
    const dt = now - lastTick;
    if (state.playing && dt > Math.max(30, 220 / state.speed)) {
      lastTick = now;
      state.frameIdx = (state.frameIdx + 1) % state.data.frames.length;
      scrub.value = state.frameIdx;
      render();
    } else if (state.view === "3d") {
      render(); // keep pulsing animations (EV rings, sun) alive even while paused
    }
    requestAnimationFrame(loop);
  }

  // ------------------------------------------------------------------ boot
  function boot() {
    resize();
    buildScenarioButtons();
    buildSpeedButtons();
    setScenario("normal");
    requestAnimationFrame(loop);
  }
  boot();
})();
