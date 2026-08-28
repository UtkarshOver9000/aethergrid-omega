// AETHERGRID 3D — real WebGL world simulation viewer.
// Pure playback + presentation layer: every value drawn comes from the
// precomputed scenario JSON in ../viz/data/. No simulation logic lives here.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

// ------------------------------------------------------------------ config
const TILE = 3.6;               // world units per grid cell
const SCENARIO_FILES = { normal: "../viz/data/normal.json", heatwave: "../viz/data/heatwave.json", high_ev: "../viz/data/high_ev.json", outage: "../viz/data/outage.json" };
const SCENARIO_LABELS = { normal: "Normal day", heatwave: "Heatwave", high_ev: "High EV", outage: "Grid outage" };
const SPEEDS = [0.25, 1, 5, 20, 100];

// What-if grid: one fixed transformer rating (280 kVA, chosen by
// calibration so the grid genuinely spans NORMAL through BREACH), three
// real EV-penetration levels, each with a real AI-Coordinator-on and
// AI-Coordinator-off run from the same engine. Six real files, not a
// live re-simulation and not a fudge-factor slider.
const WHATIF_EV_LEVELS = [20, 40, 75];
const WHATIF_RATING_KVA = 195;
function whatifKey(ev, ai) { return `whatif_ev${ev}_${ai ? "ai" : "noai"}`; }
for (const ev of WHATIF_EV_LEVELS) {
  SCENARIO_FILES[whatifKey(ev, true)] = `../viz/data/${whatifKey(ev, true)}.json`;
  SCENARIO_FILES[whatifKey(ev, false)] = `../viz/data/${whatifKey(ev, false)}.json`;
  SCENARIO_FILES[`whatif_ev${ev}_ai_solarsync`] = `../viz/data/whatif_ev${ev}_ai_solarsync.json`;
}
const CAPEX_PER_KVA = 1200; // same default as the commercial calculator's transformer-capex mode

// Illustrative-only residential tariff used purely for the per-house "cost
// exposure" readout. NOT a real DISCOM tariff filing — labelled as such in
// the UI. Loosely shaped like common Indian domestic ToD structures.
const ILLUSTRATIVE_TARIFF = { rate_per_kwh: 7.2, peak_multiplier: 1.35, peak_start_min: 18 * 60, peak_end_min: 22 * 60 };
// Export rate used only for the solar self-consumption spread calculation
// (import rate minus export rate) -- roughly half of import, a realistic
// shape for Indian net-metering, explicitly illustrative, not a filed rate.
const ILLUSTRATIVE_EXPORT_RATE = 3.5;

const CAR_COLORS = [0xcfd6e0, 0x8b95ab, 0x3a4a63, 0x6b2f2f, 0x2f4a3a, 0xb8791f];

// Neighbouring societies on the same feeder — real, independently generated
// synthetic worlds (aethergrid/worldsim/generate_colony.py), not decoration.
// Society B runs an older/smaller transformer and genuinely breaches;
// Society C has real headroom. Positions are hand-placed offsets in world
// units, forming a triangle around the GridBrain hub.
const COLONY = {
  society_b: { file: "../viz/data/society_b.json", label: "Society B", offset: { x: -128, z: 70 } },
  society_c: { file: "../viz/data/society_c.json", label: "Society C", offset: { x: 128, z: 70 } },
};

function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }
function lerp(a, b, t) { return a + (b - a) * t; }
function hash01(n) { const x = Math.sin(n * 12.9898) * 43758.5453; return x - Math.floor(x); }
function minToClock(tmin) {
  const h = Math.floor(tmin / 60) % 24, m = Math.floor(tmin) % 60;
  return String(h).padStart(2, "0") + ":" + String(m).padStart(2, "0");
}

// heat colour ramp used for window/load emissive tint
const LOAD_STOPS = [[0.0, 0x2b3a67], [0.35, 0x4fd1c5], [0.6, 0xf5b942], [1.0, 0xf0553a]];
function loadColor(kw, maxKw) {
  const t = clamp(kw / Math.max(maxKw, 0.5), 0, 1);
  for (let i = 0; i < LOAD_STOPS.length - 1; i++) {
    const [t0, c0] = LOAD_STOPS[i], [t1, c1] = LOAD_STOPS[i + 1];
    if (t >= t0 && t <= t1) {
      const lt = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
      return new THREE.Color(c0).lerp(new THREE.Color(c1), lt);
    }
  }
  return new THREE.Color(LOAD_STOPS[LOAD_STOPS.length - 1][1]);
}

// ---------------------------------------------------------- shared textures
function makeRadialTexture(inner, outer, size = 128) {
  const c = document.createElement("canvas"); c.width = c.height = size;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, inner); grad.addColorStop(1, outer);
  g.fillStyle = grad; g.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(c);
}
const SHADOW_TEX = makeRadialTexture("rgba(0,0,0,0.5)", "rgba(0,0,0,0)");
const CLOUD_TEX = makeRadialTexture("rgba(255,255,255,0.85)", "rgba(255,255,255,0)");

function makeHazardTexture() {
  const s = 64, c = document.createElement("canvas"); c.width = c.height = s;
  const g = c.getContext("2d");
  g.fillStyle = "#171a21"; g.fillRect(0, 0, s, s);
  g.fillStyle = "#f5b942";
  for (let i = -1; i < 3; i++) { g.beginPath(); g.moveTo(i * 22, 0); g.lineTo(i * 22 + 12, 0); g.lineTo(i * 22 + 12 - s, s); g.lineTo(i * 22 - s, s); g.closePath(); g.fill(); }
  return new THREE.CanvasTexture(c);
}
const HAZARD_TEX = makeHazardTexture();

// ------------------------------------------------------ real PBR materials
// Real photographed CC0 materials from ambientCG.com (public domain, no
// licence risk) — replaces flat procedural colour with actual photographed
// brick / stucco / roof tile / grass / asphalt / paving / wood / concrete.
const texLoader = new THREE.TextureLoader();
const PBR_SOURCES = {
  brick: "brick", stucco: "stucco", roof: "roof", grass: "grass",
  asphalt: "asphalt", paving: "paving", wood: "wood", concrete: "concrete",
};
function loadPBRSet(key) {
  const base = `assets/textures/${key}`;
  const color = texLoader.load(`${base}_color.jpg`);
  const normal = texLoader.load(`${base}_normal.jpg`);
  const roughness = texLoader.load(`${base}_roughness.jpg`);
  color.colorSpace = THREE.SRGBColorSpace;
  for (const t of [color, normal, roughness]) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  return { color, normal, roughness };
}
const PBR = {};
for (const key of Object.keys(PBR_SOURCES)) PBR[key] = loadPBRSet(key);

function pbrMat(key, repeat = 2, opts = {}) {
  const set = PBR[key];
  const color = set.color.clone(), normal = set.normal.clone(), roughness = set.roughness.clone();
  color.needsUpdate = normal.needsUpdate = roughness.needsUpdate = true;
  for (const t of [color, normal, roughness]) { t.repeat.set(repeat, repeat); t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  return new THREE.MeshStandardMaterial({ map: color, normalMap: normal, roughnessMap: roughness, ...opts });
}

// ------------------------------------------------------------------- state
const state = {
  scenarioKey: "normal", data: null, frameIdx: 40, playing: false, speed: 1,
  cam: "orbit", selected: null, maxKw: 1, hover: null,
  whatifEv: null, whatifAi: true, whatifSync: false, // null = not in what-if mode
  districtArm: {},          // pair key -> "raw" | "ai" | "full" currently displayed
  adoption: null,           // null = follow whatever the deploy buttons set
};

// ------------------------------------------------------------ three basics
const canvas = document.getElementById("stageCanvas");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.92;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a1020);
scene.fog = new THREE.FogExp2(0x0a1020, 0.0095);
// colony spans ~300 units and the district ~600, so both need far thinner
// fog than the society scale or they black out entirely
const FOG_DENSITY = { orbit: 0.0095, top: 0.0095, colony: 0.0018, district: 0.00022 };

const stageEl = document.querySelector(".stage");
const perspCam = new THREE.PerspectiveCamera(46, 1, 0.1, 800);
const orthoCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 800);
let camera = perspCam;

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 6;
controls.maxDistance = 150;
controls.maxPolarAngle = Math.PI * 0.49;
controls.target.set(0, 0, 0);

const composer = new EffectComposer(renderer);
const renderPass = new RenderPass(scene, camera);
composer.addPass(renderPass);
const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.45, 0.4, 0.4);
composer.addPass(bloomPass);
composer.addPass(new OutputPass());

// ---------------------------------------------------------------- lights
const sun = new THREE.DirectionalLight(0xffffff, 0);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -70; sun.shadow.camera.right = 70;
sun.shadow.camera.top = 70; sun.shadow.camera.bottom = -70;
sun.shadow.camera.far = 280;
sun.shadow.bias = -0.0008;
scene.add(sun, sun.target);

const hemi = new THREE.HemisphereLight(0x8fb0e8, 0x1b2233, 0.55);
scene.add(hemi);
const ambient = new THREE.AmbientLight(0x223047, 0.35);
scene.add(ambient);
const moonLight = new THREE.DirectionalLight(0x93a8d9, 0);
scene.add(moonLight, moonLight.target);

// Real, distinct sun and moon — previously the "moon" was just the sun
// sprite dimmed, which is why neither read as real. A crisp-edged disc plus
// a soft halo behind it reads as a body, not a blurry blob; the moon gets
// its own procedural cratered texture so it's visibly a different object.
function makeDiscTexture(coreColor, edgeColor, hardness = 0.72) {
  const s = 128, c = document.createElement("canvas"); c.width = c.height = s;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0, coreColor); grad.addColorStop(hardness, coreColor); grad.addColorStop(1, edgeColor);
  g.fillStyle = grad; g.fillRect(0, 0, s, s);
  return new THREE.CanvasTexture(c);
}
function makeMoonTexture() {
  const s = 256, c = document.createElement("canvas"); c.width = c.height = s;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(s * 0.42, s * 0.42, 0, s / 2, s / 2, s / 2);
  grad.addColorStop(0, "#f2f1ea"); grad.addColorStop(0.75, "#cdccc4"); grad.addColorStop(1, "#a8a79f");
  g.fillStyle = grad; g.beginPath(); g.arc(s / 2, s / 2, s / 2, 0, Math.PI * 2); g.fill();
  g.globalCompositeOperation = "multiply";
  for (let i = 0; i < 26; i++) {
    const cx = s * (0.15 + Math.random() * 0.7), cy = s * (0.15 + Math.random() * 0.7), r = s * (0.02 + Math.random() * 0.07);
    const dist = Math.hypot(cx - s / 2, cy - s / 2);
    if (dist + r > s / 2) continue;
    const cg = g.createRadialGradient(cx, cy, 0, cx, cy, r);
    cg.addColorStop(0, "rgba(150,148,140,0.8)"); cg.addColorStop(1, "rgba(150,148,140,0)");
    g.fillStyle = cg; g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.fill();
  }
  return new THREE.CanvasTexture(c);
}
const SUN_HALO_TEX = makeRadialTexture("rgba(255,244,214,0.85)", "rgba(255,244,214,0)");
const SUN_DISC_TEX = makeDiscTexture("#fffdf3", "rgba(255,253,243,0)");
const MOON_TEX = makeMoonTexture();

const sunHalo = new THREE.Sprite(new THREE.SpriteMaterial({ map: SUN_HALO_TEX, transparent: true, depthWrite: false }));
sunHalo.scale.set(16, 16, 1);
const sunSprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: SUN_DISC_TEX, transparent: true, depthWrite: false }));
sunSprite.scale.set(5.5, 5.5, 1);
scene.add(sunHalo, sunSprite);

const moonHalo = new THREE.Sprite(new THREE.SpriteMaterial({ color: 0xdfe8ff, map: SUN_HALO_TEX, transparent: true, opacity: 0.35, depthWrite: false }));
moonHalo.scale.set(9, 9, 1);
const moonSprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: MOON_TEX, transparent: true, depthWrite: false }));
moonSprite.scale.set(4.5, 4.5, 1);
scene.add(moonHalo, moonSprite);

const starGeo = new THREE.BufferGeometry();
const starCount = 900;
const starPos = new Float32Array(starCount * 3);
for (let i = 0; i < starCount; i++) {
  const r = 260 + Math.random() * 40;
  const th = Math.random() * Math.PI * 2, ph = Math.acos(Math.random() * 0.9);
  starPos[i * 3] = r * Math.sin(ph) * Math.cos(th);
  starPos[i * 3 + 1] = Math.abs(r * Math.cos(ph)) * 0.7 + 20;
  starPos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
}
starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 1.1, transparent: true, opacity: 0 }));
scene.add(stars);

// clouds — a handful of soft drifting billboards
const clouds = [];
const cloudGroup = new THREE.Group();
for (let i = 0; i < 7; i++) {
  const m = new THREE.Sprite(new THREE.SpriteMaterial({ map: CLOUD_TEX, transparent: true, opacity: 0.5, depthWrite: false }));
  const s = 22 + hash01(i * 7) * 20;
  m.scale.set(s, s * 0.45, 1);
  m.position.set((hash01(i) - 0.5) * 220, 46 + hash01(i * 3) * 14, (hash01(i * 5) - 0.5) * 220);
  m.userData.speed = 0.4 + hash01(i * 9) * 0.8;
  cloudGroup.add(m); clouds.push(m);
}
scene.add(cloudGroup);

// ----------------------------------------------------------------- ground
// Real photographed grass + asphalt (ambientCG, CC0) laid out as actual
// geometry — a tiled grass plane with real road-strip meshes on top, rather
// than a painted texture pretending to be a road.
let groundMesh = null, roadGroup = null;
function buildGround(cols, rows) {
  if (groundMesh) { scene.remove(groundMesh); groundMesh.geometry.dispose(); }
  if (roadGroup) { scene.remove(roadGroup); roadGroup.traverse(o => o.geometry && o.geometry.dispose()); }

  const w = (cols + 2) * TILE, d = (rows + 2) * TILE;
  const grassMat = pbrMat("grass", Math.max(cols, rows) * 1.6);
  groundMesh = new THREE.Mesh(new THREE.PlaneGeometry(w, d), grassMat);
  groundMesh.rotation.x = -Math.PI / 2;
  groundMesh.receiveShadow = true;
  groundMesh.position.set((cols - 1) * TILE / 2, 0, (rows - 1) * TILE / 2);
  scene.add(groundMesh);

  roadGroup = new THREE.Group();
  const roadMat = pbrMat("asphalt", 1);
  const roadW = TILE * 0.36;
  for (let x = 0; x <= cols; x++) {
    const m = roadMat.clone(); m.map = roadMat.map.clone(); m.map.repeat.set(1, d / TILE * 0.6); m.map.needsUpdate = true;
    m.normalMap = roadMat.normalMap; m.roughnessMap = roadMat.roughnessMap;
    const strip = new THREE.Mesh(new THREE.PlaneGeometry(roadW, d), m);
    strip.rotation.x = -Math.PI / 2;
    strip.position.set((x - 0.5) * TILE, 0.008, (rows - 1) * TILE / 2);
    strip.receiveShadow = true;
    roadGroup.add(strip);
  }
  for (let z = 0; z <= rows; z++) {
    const m = roadMat.clone(); m.map = roadMat.map.clone(); m.map.repeat.set(w / TILE * 0.6, 1); m.map.needsUpdate = true;
    m.normalMap = roadMat.normalMap; m.roughnessMap = roadMat.roughnessMap;
    const strip = new THREE.Mesh(new THREE.PlaneGeometry(w, roadW), m);
    strip.rotation.x = -Math.PI / 2;
    strip.position.set((cols - 1) * TILE / 2, 0.008, (z - 0.5) * TILE);
    strip.receiveShadow = true;
    roadGroup.add(strip);
  }
  scene.add(roadGroup);

  buildTraffic(cols, rows);
}

// ---------------------------------------------------------------- traffic
// Cars actually drive the road grid in real time (independent of playback
// speed) — motion, not decoration.
// Cars now drive one shared rectangular perimeter loop per society, with
// heading smoothly interpolated through corners — a handful of vehicles
// doing this convincingly beats many independently bouncing in straight
// lines and snap-turning at the end of their lane.
let trafficGroup = null, trafficCars = [];
function lerpAngle(a, b, t) {
  const diff = (((b - a + Math.PI) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
  return a + diff * t;
}
function buildPerimeterLoop(cols, rows, offsetX, offsetZ) {
  const mx = 0.55 * TILE, mz = 0.55 * TILE;
  const x0 = -mx + offsetX, x1 = (cols - 1) * TILE + mx + offsetX;
  const z0 = -mz + offsetZ, z1 = (rows - 1) * TILE + mz + offsetZ;
  const pts = [new THREE.Vector3(x0, 0, z0), new THREE.Vector3(x1, 0, z0), new THREE.Vector3(x1, 0, z1), new THREE.Vector3(x0, 0, z1)];
  // buildCar's body is longest along local +X (0.42) vs +Z (0.22), so "forward"
  // is local +X; rotation.y maps local +X to world (cos th, 0, -sin th) --
  // these four values are derived from that, not guessed, to fix the car
  // always facing 90 deg off its actual direction of travel
  const headings = [0, -Math.PI / 2, Math.PI, Math.PI / 2]; // +X, +Z, -X, -Z edge directions in order
  const segs = []; let total = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length], len = a.distanceTo(b);
    segs.push({ a, b, len, heading: headings[i] });
    total += len;
  }
  return { segs, total };
}
function sampleLoop(runner, dist) {
  let d = ((dist % runner.total) + runner.total) % runner.total;
  for (const seg of runner.segs) {
    if (d <= seg.len) return { pos: seg.a.clone().lerp(seg.b, seg.len > 0 ? d / seg.len : 0), heading: seg.heading };
    d -= seg.len;
  }
  const last = runner.segs[runner.segs.length - 1];
  return { pos: last.b.clone(), heading: last.heading };
}
function addCarOnLoop(runner, seed, startFrac, isBus = false) {
  const vehicle = isBus ? buildBus(0xffb020) : buildCar(seed, CAR_COLORS[seed % CAR_COLORS.length]);
  const headColor = isBus ? 0xffffff : 0xfff3c4;
  const head = new THREE.Mesh(new THREE.SphereGeometry(isBus ? 0.045 : 0.03, 6, 6), new THREE.MeshBasicMaterial({ color: headColor }));
  head.position.set(isBus ? 0.43 : 0.22, isBus ? 0.2 : 0.11, isBus ? 0.135 : 0.07);
  vehicle.add(head);
  vehicle.position.y = 0.001;
  trafficGroup.add(vehicle);
  const speed = isBus ? 0.85 + hash01(seed) * 0.25 : 1.5 + hash01(seed) * 0.9;
  trafficCars.push({ mesh: vehicle, runner, dist: startFrac * runner.total, speed, heading: 0 });
}
function buildTraffic(cols, rows) {
  if (trafficGroup) scene.remove(trafficGroup);
  trafficGroup = new THREE.Group();
  trafficCars = [];
  const loopA = buildPerimeterLoop(cols, rows, 0, 0);
  addCarOnLoop(loopA, 1, 0);
  addCarOnLoop(loopA, 2, 0.3);
  addCarOnLoop(loopA, 3, 0.62);
  addCarOnLoop(loopA, 4, 0.83);
  addCarOnLoop(loopA, 9, 0.15, true); // the society bus
  scene.add(trafficGroup);
}
function addColonyTraffic(cols, rows, offset, seed) {
  const loop = buildPerimeterLoop(cols, rows, offset.x, offset.z);
  addCarOnLoop(loop, seed, hash01(seed * 5));
  addCarOnLoop(loop, seed + 50, hash01(seed * 9));
  addCarOnLoop(loop, seed + 90, hash01(seed * 13), true);
}
function updateGridBrainVisuals(dtSec, now) {
  if (!gridBrain || !state.data) return;
  gridBrain.wire.rotation.y += dtSec * 0.15;
  gridBrain.wire.rotation.x += dtSec * 0.05;
  gridBrain.core.scale.setScalar(1 + Math.sin(now / 700) * 0.06);

  const fracByKey = { society_a: frame().grid.transformer_kva / frame().grid.rating_kva };
  const fb = colonyFrame("society_b"), fc = colonyFrame("society_c");
  if (fb) fracByKey.society_b = fb.grid.transformer_kva / fb.grid.rating_kva;
  if (fc) fracByKey.society_c = fc.grid.transformer_kva / fc.grid.rating_kva;

  for (const b of gridBrain.beams) {
    const frac = clamp(fracByKey[b.key] || 0.3, 0, 1.2);
    b.speed = 0.16 + frac * 0.35;
    b.t = (b.t + dtSec * b.speed) % 1;
    b.pulse.position.lerpVectors(b.from, b.to, b.t);
    const stressed = frac > 0.85;
    b.pulse.material.color.set(stressed ? 0xff3d5d : 0x39e0ff);
    b.pulse.scale.setScalar(stressed ? 1.4 : 1);
    b.line.material.color.set(stressed ? 0xff3d5d : 0x39e0ff);
    b.line.material.opacity = stressed ? 0.55 : 0.3;
  }
}

function updateTraffic(dtSec) {
  for (const c of trafficCars) {
    c.dist += c.speed * dtSec;
    const { pos, heading } = sampleLoop(c.runner, c.dist);
    c.mesh.position.set(pos.x, 0.001, pos.z);
    c.heading = lerpAngle(c.heading, heading, clamp(dtSec * 5, 0, 1));
    c.mesh.rotation.y = c.heading;
  }
}

// -------------------------------------------------------- shared geometry
const GEO = {
  boxUnit: new THREE.BoxGeometry(1, 1, 1),
  roofCone: new THREE.ConeGeometry(0.95, 1, 4, 1),
  windowPlane: new THREE.PlaneGeometry(0.5, 0.46),
  windowFrame: new THREE.PlaneGeometry(0.62, 0.58),
  doorPlane: new THREE.PlaneGeometry(0.22, 0.42),
  solarPlane: new THREE.PlaneGeometry(1.1, 0.75),
  ring: new THREE.TorusGeometry(0.85, 0.045, 8, 32),
  cyl: new THREE.CylinderGeometry(1, 1, 1, 16),
  tankCyl: new THREE.CylinderGeometry(1, 1, 1, 12),
  pole: new THREE.CylinderGeometry(0.04, 0.05, 1, 8),
  lampHead: new THREE.SphereGeometry(0.09, 10, 8),
  carBody: new THREE.BoxGeometry(1, 1, 1),
  hedge: new THREE.BoxGeometry(1, 1, 1),
  disc: new THREE.CircleGeometry(1, 24),
  padPlane: new THREE.PlaneGeometry(1, 1),
};
GEO.roofCone.rotateY(Math.PI / 4);

function wallMat(hex, rough = 0.85) { return new THREE.MeshStandardMaterial({ color: hex, roughness: rough, metalness: 0.05 }); }
function emissiveMat(hex) { return new THREE.MeshStandardMaterial({ color: 0x05070c, emissive: new THREE.Color(hex), emissiveIntensity: 0.2, roughness: 0.4 }); }

// real-photo wall/roof variants — each house clones one of these (cheap:
// shares GPU textures, only the tint colour differs) instead of a flat colour
const WALL_VARIANTS = [pbrMat("brick", 3.2), pbrMat("stucco", 2.2), pbrMat("wood", 2.6)];
const ROOF_BASE = pbrMat("roof", 3.2);
const CONCRETE_BASE = pbrMat("concrete", 2.4);
const PAVING_MAT = pbrMat("paving", 1.4);
// #26 archetype-correlated palettes. Hue is biased by household archetype so
// the neighbourhood reads as socially varied at a glance, not just
// electrically varied -- joint families in warmer earth tones, dual-income
// flats in cooler modern ones. Reuses the existing material variants, so no
// new textures and no extra draw calls.
const ARCHETYPE_HUE = {
  joint_family:            [0.055, 0.20],  // warm terracotta
  family_with_children:    [0.09,  0.16],  // sand
  elderly_couple:          [0.12,  0.10],  // pale ochre
  dual_income_no_children: [0.58,  0.09],  // cool grey-blue
  work_from_home:          [0.42,  0.10],  // muted green
  frequently_absent:       [0.66,  0.07],  // cool slate
};
function wallVariantFor(seed, archetype) {
  const m = WALL_VARIANTS[Math.floor(hash01(seed) * WALL_VARIANTS.length) % WALL_VARIANTS.length].clone();
  const band = ARCHETYPE_HUE[archetype];
  if (band) {
    const [h0, sat] = band;
    m.color.setHSL(h0 + (hash01(seed * 3) - 0.5) * 0.04, sat, 0.74 + hash01(seed * 5) * 0.16);
  } else {
    m.color.setHSL(hash01(seed * 3), 0.12, 0.78 + hash01(seed * 5) * 0.14);
  }
  return m;
}
function roofVariantFor(seed) {
  const m = ROOF_BASE.clone();
  m.color.setHSL(0.02 + hash01(seed) * 0.06, 0.15, 0.42 + hash01(seed * 2) * 0.14);
  return m;
}
function shadowDecal(scale) {
  const m = new THREE.Mesh(GEO.disc, new THREE.MeshBasicMaterial({ map: SHADOW_TEX, transparent: true, depthWrite: false }));
  m.rotation.x = -Math.PI / 2; m.position.y = 0.015; m.scale.setScalar(scale);
  m.renderOrder = 1;
  return m;
}

// ----------------------------------------------------------- prop builders
function buildCar(seed, colorHex) {
  const grp = new THREE.Group();
  const body = new THREE.Mesh(GEO.carBody, wallMat(colorHex, 0.4));
  body.scale.set(0.42, 0.16, 0.22);
  body.position.y = 0.1;
  const cabin = new THREE.Mesh(GEO.carBody, wallMat(0x1a2030, 0.3));
  cabin.scale.set(0.22, 0.1, 0.2);
  cabin.position.y = 0.19;
  grp.add(body, cabin);
  return grp;
}

function buildBus(colorHex) {
  const grp = new THREE.Group();
  const body = new THREE.Mesh(GEO.carBody, wallMat(colorHex, 0.45));
  body.scale.set(0.85, 0.32, 0.26);
  body.position.y = 0.19;
  body.castShadow = true;
  grp.add(body);
  const stripe = new THREE.Mesh(GEO.carBody, emissiveMat(0xffffff));
  stripe.scale.set(0.86, 0.05, 0.27);
  stripe.position.y = 0.1;
  grp.add(stripe);
  for (let i = 0; i < 5; i++) {
    const wm = emissiveMat(0xfff3c4);
    wm.emissiveIntensity = 0.5;
    const win = new THREE.Mesh(GEO.windowPlane, wm);
    win.scale.setScalar(0.16);
    win.position.set(-0.32 + i * 0.16, 0.24, 0.135);
    grp.add(win);
  }
  return grp;
}

// ----------------------------------------------------------- house builder
function buildHouseGroup(meta) {
  const grp = new THREE.Group();
  const floors = Math.max(1, meta.floors || 1);
  const dyn = { windowMats: [], solarMat: null, evRing: null, curtailRing: null, batteryBar: null, acLed: null, geyserLed: null };

  let footprintW = 1, footprintD = 0.85, floorH = 0.62, roofKind = "hip";
  switch (meta.archetype) {
    case "dual_income_no_children": footprintW = 0.9; footprintD = 0.8; roofKind = "flat"; break;
    case "family_with_children": footprintW = 1.15; footprintD = 0.95; roofKind = "hip"; break;
    case "elderly_couple": footprintW = 0.85; footprintD = 0.75; roofKind = "gable-low"; break;
    case "work_from_home": footprintW = 0.95; footprintD = 0.85; roofKind = "pod"; break;
    case "joint_family": footprintW = 1.35; footprintD = 1.1; roofKind = "hip"; break;
    case "frequently_absent": footprintW = 0.72; footprintD = 0.65; roofKind = "flat"; break;
  }

  const totalH = floorH * floors;
  const wallMatReal = wallVariantFor(meta.id + 0.31, meta.archetype);
  const body = new THREE.Mesh(GEO.boxUnit, wallMatReal);
  body.scale.set(footprintW, totalH, footprintD);
  body.position.y = totalH / 2;
  body.castShadow = true; body.receiveShadow = true;
  grp.add(body);

  // plinth (base trim) for a grounded, less "floating box" look
  const plinth = new THREE.Mesh(GEO.boxUnit, wallMat(0x20242e, 0.9));
  plinth.scale.set(footprintW * 1.03, 0.06, footprintD * 1.03);
  plinth.position.y = 0.03;
  grp.add(plinth);

  const roofMatReal = roofVariantFor(meta.id + 1.7);
  if (roofKind === "hip") {
    const roof = new THREE.Mesh(GEO.roofCone, roofMatReal);
    roof.scale.set(footprintW * 0.8, 0.44, footprintD * 0.8);
    roof.position.y = totalH + 0.22;
    roof.castShadow = true;
    grp.add(roof);
  } else if (roofKind === "gable-low") {
    const roof = new THREE.Mesh(GEO.boxUnit, roofMatReal);
    roof.scale.set(footprintW * 1.06, 0.12, footprintD * 1.06);
    roof.position.y = totalH + 0.06;
    grp.add(roof);
  } else if (roofKind === "pod") {
    const roof = new THREE.Mesh(GEO.boxUnit, roofMatReal);
    roof.scale.set(footprintW * 1.03, 0.1, footprintD * 1.03);
    roof.position.y = totalH + 0.05;
    grp.add(roof);
    const pod = new THREE.Mesh(GEO.boxUnit, wallVariantFor(meta.id + 4.2));
    pod.scale.set(footprintW * 0.45, 0.34, footprintD * 0.45);
    pod.position.set(footprintW * 0.2, totalH + 0.34, -footprintD * 0.15);
    pod.castShadow = true;
    grp.add(pod);
  } else {
    const roof = new THREE.Mesh(GEO.boxUnit, roofMatReal);
    roof.scale.set(footprintW * 1.04, 0.09, footprintD * 1.04);
    roof.position.y = totalH + 0.045;
    grp.add(roof);
    const parapet = new THREE.Mesh(GEO.boxUnit, roofMatReal);
    parapet.scale.set(footprintW * 1.02, 0.12, 0.04);
    parapet.position.set(0, totalH + 0.15, footprintD / 2);
    grp.add(parapet);
  }

  // rooftop water tank — small authenticity detail, purely decorative
  const tank = new THREE.Mesh(GEO.tankCyl, wallMat(0x274a52, 0.7));
  tank.scale.set(0.16, 0.22, 0.16);
  tank.position.set(-footprintW * 0.32, totalH + (roofKind === "hip" ? 0.5 : 0.16), footprintD * 0.28);
  grp.add(tank);

  // door
  const door = new THREE.Mesh(GEO.doorPlane, wallMat(0x2a2018, 0.6));
  door.position.set(footprintW * 0.22, 0.21, footprintD / 2 + 0.011);
  grp.add(door);

  // window bands with frames, one per floor on +Z and +X faces
  for (let fl = 0; fl < floors; fl++) {
    const wsize = Math.min(footprintW, footprintD) * 0.66;
    for (const face of ["z", "x"]) {
      const frame = new THREE.Mesh(GEO.windowFrame, wallMat(0x1c2029, 0.7));
      const wm = emissiveMat(0xf5b942);
      const win = new THREE.Mesh(GEO.windowPlane, wm);
      frame.scale.setScalar(wsize); win.scale.setScalar(wsize);
      if (face === "z") {
        const zoff = footprintD / 2;
        frame.position.set(-footprintW * 0.18, floorH * fl + floorH * 0.55, zoff + 0.005);
        win.position.set(-footprintW * 0.18, floorH * fl + floorH * 0.55, zoff + 0.012);
      } else {
        const xoff = footprintW / 2;
        frame.position.set(xoff + 0.005, floorH * fl + floorH * 0.55, 0);
        win.position.set(xoff + 0.012, floorH * fl + floorH * 0.55, 0);
        frame.rotation.y = Math.PI / 2; win.rotation.y = Math.PI / 2;
      }
      grp.add(frame, win);
      dyn.windowMats.push(wm);
    }
  }

  // wall-mounted AC condenser, with a real indicator light tied to hs.ac_on
  const ac = new THREE.Mesh(GEO.boxUnit, wallMat(0xcfd6e0, 0.5));
  ac.scale.set(0.16, 0.1, 0.08);
  ac.position.set(footprintW / 2 + 0.05, floorH * 0.35, -footprintD * 0.25);
  grp.add(ac);
  const acLed = new THREE.Mesh(GEO.lampHead, emissiveMat(0x39e0ff));
  acLed.scale.setScalar(0.35);
  acLed.position.set(footprintW / 2 + 0.09, floorH * 0.35 + 0.03, -footprintD * 0.25);
  grp.add(acLed);

  // geyser — a small wall-mounted tank, with its own indicator light tied to
  // hs.geyser_on. Common Indian residential fixture, previously data-only.
  const geyser = new THREE.Mesh(GEO.tankCyl, wallMat(0xb9c2cc, 0.45));
  geyser.rotation.z = Math.PI / 2;
  geyser.scale.set(0.09, 0.16, 0.09);
  geyser.position.set(-footprintW / 2 - 0.045, floorH * 0.62, footprintD * 0.15);
  grp.add(geyser);
  const geyserLed = new THREE.Mesh(GEO.lampHead, emissiveMat(0xff6a3d));
  geyserLed.scale.setScalar(0.3);
  geyserLed.position.set(-footprintW / 2 - 0.08, floorH * 0.62, footprintD * 0.15);
  grp.add(geyserLed);
  dyn.acLed = acLed; dyn.geyserLed = geyserLed;

  if (meta.has_solar) {
    const sm = emissiveMat(0x1c2b2a); sm.emissive = new THREE.Color(0x4fd1c5);
    const panel = new THREE.Mesh(GEO.solarPlane, sm);
    panel.scale.setScalar(footprintW * 0.58);
    panel.rotation.x = -Math.PI / 2 + 0.35;
    panel.position.set(0, totalH + (roofKind === "hip" ? 0.52 : 0.2), -footprintD * 0.1);
    grp.add(panel);
    dyn.solarMat = sm;
  }

  // boundary hedge along the street-facing edge
  const hedge = new THREE.Mesh(GEO.hedge, wallMat(0x2f4a34, 0.95));
  hedge.scale.set(footprintW * 1.15, 0.12, 0.05);
  hedge.position.set(0, 0.06, footprintD / 2 + 0.32);
  grp.add(hedge);

  // pathway from door to street
  const path = new THREE.Mesh(GEO.boxUnit, wallMat(0x8a8578, 0.9));
  path.scale.set(0.16, 0.015, 0.34);
  path.position.set(footprintW * 0.22, 0.012, footprintD / 2 + 0.2);
  path.receiveShadow = true;
  grp.add(path);


  // parked car (or a small charger post if it's an EV house)
  const carX = footprintW / 2 + 0.3, carZ = -footprintD * 0.1;
  if (meta.has_ev) {
    const post = new THREE.Mesh(GEO.boxUnit, wallMat(0x2c3244, 0.6));
    post.scale.set(0.06, 0.24, 0.06);
    post.position.set(carX - 0.32, 0.12, carZ);
    grp.add(post);
  }
  const car = buildCar(meta.id, CAR_COLORS[meta.id % CAR_COLORS.length]);
  car.position.set(carX, 0, carZ);
  car.rotation.y = Math.PI / 2;
  grp.add(car);

  // real paved yard pad beneath the whole plot
  const pad = new THREE.Mesh(GEO.padPlane, PAVING_MAT);
  pad.rotation.x = -Math.PI / 2;
  pad.position.y = 0.004;
  pad.scale.set((footprintW + 1.1), (footprintD + 1.3), 1);
  pad.receiveShadow = true;
  grp.add(pad);

  grp.add(shadowDecal(Math.max(footprintW, footprintD) * 0.62));

  if (meta.has_ev) {
    const rm = new THREE.MeshBasicMaterial({ color: 0x34d399, transparent: true, opacity: 0 });
    const ring = new THREE.Mesh(GEO.ring, rm);
    ring.rotation.x = -Math.PI / 2; ring.scale.setScalar(0.4);
    ring.position.set(carX, 0.03, carZ);
    grp.add(ring);
    dyn.evRing = ring;
  }
  {
    const rm = new THREE.MeshBasicMaterial({ color: 0xf87171, transparent: true, opacity: 0 });
    const ring = new THREE.Mesh(GEO.ring, rm);
    ring.rotation.x = -Math.PI / 2;
    ring.scale.setScalar(Math.max(footprintW, footprintD) * 0.95);
    ring.position.y = 0.025;
    grp.add(ring);
    dyn.curtailRing = ring;
  }
  if (meta.has_battery) {
    const track = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x1a2233 }));
    track.scale.set(0.09, 0.55, 0.09);
    track.position.set(-footprintW * 0.75, 0.28, -footprintD * 0.6);
    grp.add(track);
    const fill = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x4fd1c5, emissive: 0x1c3d3a, emissiveIntensity: 0.4 }));
    fill.scale.set(0.07, 0.1, 0.07);
    fill.position.set(-footprintW * 0.75, 0.06, -footprintD * 0.6);
    grp.add(fill);
    dyn.batteryBar = fill;
  }

  grp.userData = { type: "house", id: meta.id, dyn, footprintW, footprintD, baseY: totalH };
  return grp;
}

function buildWorkspaceGroup(meta) {
  const grp = new THREE.Group();
  const w = 2.9, d = 2.1, h = 2.2;
  const body = new THREE.Mesh(GEO.boxUnit, CONCRETE_BASE.clone());
  body.scale.set(w, h, d); body.position.y = h / 2;
  body.castShadow = true; body.receiveShadow = true;
  grp.add(body);
  const roof = new THREE.Mesh(GEO.boxUnit, roofVariantFor(99));
  roof.scale.set(w * 1.02, 0.08, d * 1.02); roof.position.y = h + 0.04;
  grp.add(roof);
  const signBoard = new THREE.Mesh(GEO.boxUnit, emissiveMat(0x4fd1c5));
  signBoard.scale.set(1.1, 0.22, 0.03);
  signBoard.position.set(0, h + 0.35, d / 2 + 0.02);
  grp.add(signBoard);

  const windowMats = [];
  const cols = 6, rows = 3;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const frame = new THREE.Mesh(GEO.windowFrame, wallMat(0x1c2029, 0.7));
      const wm = emissiveMat(0xf5b942);
      const win = new THREE.Mesh(GEO.windowPlane, wm);
      frame.scale.set(0.4, 0.4, 1); win.scale.set(0.34, 0.34, 1);
      const x = -w / 2 + (c + 0.5) * (w / cols), y = 0.35 + r * (h - 0.6) / rows;
      frame.position.set(x, y, d / 2 + 0.005); win.position.set(x, y, d / 2 + 0.012);
      grp.add(frame, win);
      windowMats.push(wm);
    }
  }
  const solarMat = emissiveMat(0x1c2b2a); solarMat.emissive = new THREE.Color(0x4fd1c5);
  const panel = new THREE.Mesh(GEO.solarPlane, solarMat);
  panel.scale.setScalar(1.5);
  panel.rotation.x = -Math.PI / 2 + 0.15;
  panel.position.set(0, h + 0.1, 0);
  grp.add(panel);

  for (let i = 0; i < 3; i++) {
    const car = buildCar(i, CAR_COLORS[i]);
    car.position.set(-w / 2 + 0.4 + i * 0.5, 0, d / 2 + 0.55);
    grp.add(car);
  }
  grp.add(shadowDecal(2.0));

  grp.userData = { type: "workspace", dyn: { windowMats, solarMat } };
  return grp;
}

function buildTransformerGroup() {
  const grp = new THREE.Group();
  const pad = new THREE.Mesh(GEO.boxUnit, CONCRETE_BASE.clone());
  pad.scale.set(2.0, 0.05, 2.0); pad.position.y = 0.025;
  pad.receiveShadow = true;
  grp.add(pad);

  const body = new THREE.Mesh(GEO.cyl, wallMat(0x565f78, 0.55));
  body.scale.set(0.5, 1.3, 0.5); body.position.y = 0.68;
  body.castShadow = true;
  grp.add(body);
  for (let i = 0; i < 5; i++) {
    const fin = new THREE.Mesh(GEO.boxUnit, wallMat(0x454e64, 0.55));
    fin.scale.set(0.05, 0.9, 0.16);
    const ang = (i / 5) * Math.PI * 2;
    fin.position.set(Math.cos(ang) * 0.34, 0.68, Math.sin(ang) * 0.34);
    fin.rotation.y = -ang;
    grp.add(fin);
  }

  // low hazard fence ring
  const fenceR = 0.95;
  for (let i = 0; i < 10; i++) {
    const post = new THREE.Mesh(GEO.pole, wallMat(0x22262e, 0.7));
    post.scale.set(1, 0.5, 1);
    const ang = (i / 10) * Math.PI * 2;
    post.position.set(Math.cos(ang) * fenceR, 0.25, Math.sin(ang) * fenceR);
    grp.add(post);
  }
  const sign = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 0.4), new THREE.MeshBasicMaterial({ map: HAZARD_TEX }));
  sign.position.set(0, 0.4, fenceR + 0.02);
  grp.add(sign);

  const barTrack = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x141822 }));
  barTrack.scale.set(0.28, 2.2, 0.28);
  barTrack.position.set(1.35, 1.1, 0);
  grp.add(barTrack);
  const barFill = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x34d399, emissive: 0x0d3a2a, emissiveIntensity: 0.6 }));
  barFill.scale.set(0.22, 0.1, 0.22);
  barFill.position.set(1.35, 0.05, 0);
  grp.add(barFill);
  const beacon = new THREE.PointLight(0x34d399, 1.2, 7, 2);
  beacon.position.set(0, 1.7, 0);
  grp.add(beacon);

  // ground stress ring — widens and brightens as loading climbs, the single
  // clearest "the whole society's coincident peak is stressing this" signal
  const stressRing = new THREE.Mesh(GEO.ring, new THREE.MeshBasicMaterial({ color: 0x34d399, transparent: true, opacity: 0 }));
  stressRing.rotation.x = -Math.PI / 2;
  stressRing.position.y = 0.02;
  stressRing.scale.setScalar(fenceR + 0.3);
  grp.add(stressRing);

  grp.add(shadowDecal(1.5));
  grp.userData = { type: "transformer", dyn: { barFill, barTrack, beacon, stressRing } };
  return grp;
}

// The shared community solar station -- one big array on its own pad, far
// larger than the rooftop panels on individual houses (60 kWp vs ~3-4 kWp
// each). Only rendered in scenarios whose data actually contains a
// non-zero community_solar_kw series; it is a real simulated generator
// (see society.py), not scenery, so it must not appear where none was
// simulated.
function buildSolarStationGroup() {
  const grp = new THREE.Group();
  const pad = new THREE.Mesh(GEO.boxUnit, CONCRETE_BASE.clone());
  pad.scale.set(5.4, 0.05, 3.4); pad.position.y = 0.025;
  pad.receiveShadow = true;
  grp.add(pad);

  const panelMats = [];
  const ROWS = 3, PER_ROW = 4;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < PER_ROW; c++) {
      const x = (c - (PER_ROW - 1) / 2) * 1.22;
      const z = (r - (ROWS - 1) / 2) * 1.02;
      const sm = emissiveMat(0x1c2b2a);
      sm.emissive = new THREE.Color(0x4fd1c5);
      const panel = new THREE.Mesh(GEO.solarPlane, sm);
      panel.scale.setScalar(1.05);
      panel.rotation.x = -Math.PI / 2 + 0.42;   // south-tilted, same as rooftops
      panel.position.set(x, 0.62, z);
      panel.castShadow = true;
      grp.add(panel);
      panelMats.push(sm);
      for (const lx of [-0.42, 0.42]) {
        const leg = new THREE.Mesh(GEO.pole, wallMat(0x39424f, 0.7));
        leg.scale.set(1, 0.55, 1);
        leg.position.set(x + lx, 0.28, z + 0.12);
        grp.add(leg);
      }
    }
  }

  // inverter / distribution cabinet -- the physical point the station's
  // output actually leaves from, and where the export beam originates
  const cab = new THREE.Mesh(GEO.boxUnit, wallMat(0x4a5568, 0.6));
  cab.scale.set(0.6, 0.85, 0.4); cab.position.set(2.35, 0.45, 1.35);
  cab.castShadow = true;
  grp.add(cab);
  const cabLed = new THREE.Mesh(GEO.lampHead, emissiveMat(0xe8b23d));
  cabLed.scale.setScalar(0.5);
  cabLed.position.set(2.35, 0.92, 1.35);
  grp.add(cabLed);
  const beacon = new THREE.PointLight(0xe8b23d, 0, 9, 2);
  beacon.position.set(2.35, 1.3, 1.35);
  grp.add(beacon);

  for (let i = 0; i < 12; i++) {
    const post = new THREE.Mesh(GEO.pole, wallMat(0x22262e, 0.7));
    post.scale.set(1, 0.45, 1);
    const ang = (i / 12) * Math.PI * 2;
    post.position.set(Math.cos(ang) * 2.9, 0.22, Math.sin(ang) * 1.9);
    grp.add(post);
  }

  grp.add(shadowDecal(2.6));
  grp.userData = { type: "solarstation", dyn: { panelMats, cabLed, beacon, cabLocal: cab.position.clone() } };
  return grp;
}

// Visible export path from the station's inverter to the society transformer:
// the station's output does not go to one house, it offsets the whole
// society's draw at the connection point. Pulses only travel while the
// station is actually generating in the current frame.
function buildSolarFeedBeam(fromWorld, toWorld) {
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([fromWorld, toWorld]),
    new THREE.LineBasicMaterial({ color: 0xe8b23d, transparent: true, opacity: 0 }));
  worldGroup.add(line);
  const pulses = [];
  for (let i = 0; i < 3; i++) {
    const p = new THREE.Mesh(new THREE.SphereGeometry(0.12, 8, 8), new THREE.MeshBasicMaterial({ color: 0xffd97a, transparent: true, opacity: 0 }));
    worldGroup.add(p);
    pulses.push({ mesh: p, t: i / 3 });
  }
  return { line, pulses, from: fromWorld.clone(), to: toWorld.clone() };
}

function buildWaterTankGroup() {
  const grp = new THREE.Group();
  const legs = [[-0.3, -0.3], [0.3, -0.3], [-0.3, 0.3], [0.3, 0.3]];
  for (const [x, z] of legs) {
    const leg = new THREE.Mesh(GEO.pole, wallMat(0x3a4152, 0.7));
    leg.scale.set(1.4, 1.1, 1.4); leg.position.set(x, 0.55, z);
    grp.add(leg);
  }
  const shell = new THREE.Mesh(GEO.cyl, wallMat(0x4a5568, 0.6));
  shell.scale.set(0.5, 0.7, 0.5); shell.position.y = 1.45;
  shell.castShadow = true;
  grp.add(shell);
  const fill = new THREE.Mesh(GEO.cyl, new THREE.MeshStandardMaterial({ color: 0x4fd1c5, emissive: 0x0c2c2a, emissiveIntensity: 0.3 }));
  fill.scale.set(0.4, 0.3, 0.4); fill.position.y = 1.25;
  grp.add(fill);
  grp.add(shadowDecal(0.8));
  grp.userData = { type: "watertank", dyn: { fill } };
  return grp;
}

function buildStreetlightGroup(withLight) {
  const grp = new THREE.Group();
  const pole = new THREE.Mesh(GEO.pole, new THREE.MeshStandardMaterial({ color: 0x3a4152 }));
  pole.scale.set(1, 1.7, 1); pole.position.y = 0.85;
  grp.add(pole);
  const arm = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x3a4152 }));
  arm.scale.set(0.22, 0.03, 0.03); arm.position.set(0.1, 1.68, 0);
  grp.add(arm);
  const head = new THREE.Mesh(GEO.lampHead, new THREE.MeshStandardMaterial({ color: 0x111318, emissive: 0xffe096, emissiveIntensity: 0 }));
  head.position.set(0.2, 1.65, 0);
  grp.add(head);
  let light = null;
  if (withLight) { light = new THREE.PointLight(0xffe096, 0, 5.5, 2); light.position.set(0.2, 1.6, 0); grp.add(light); }
  grp.add(shadowDecal(0.35));
  grp.userData = { type: "streetlight", dyn: { head, light } };
  return grp;
}

// ------------------------------------------------ colony (neighbour societies)
// Lower-fidelity neighbour societies: real per-house simulated data, simplified
// geometry (no yard props) — three full-detail societies at once would be pure
// mesh-count cost with no argument attached. Detail is spent where it earns it.
function buildSimpleHouseGroup(meta, tint) {
  const grp = new THREE.Group();
  const floors = Math.max(1, meta.floors || 1);
  const w = 0.85, d = 0.75, floorH = 0.6, totalH = floorH * floors;
  const body = new THREE.Mesh(GEO.boxUnit, wallVariantFor(meta.id * 3.1 + tint, meta.archetype));
  body.scale.set(w, totalH, d); body.position.y = totalH / 2;
  body.castShadow = true; body.receiveShadow = true;
  grp.add(body);
  const plinth = new THREE.Mesh(GEO.boxUnit, wallMat(0x20242e, 0.9));
  plinth.scale.set(w * 1.03, 0.05, d * 1.03); plinth.position.y = 0.025;
  grp.add(plinth);
  const roof = new THREE.Mesh(GEO.boxUnit, roofVariantFor(meta.id * 2.3 + tint));
  roof.scale.set(w * 1.05, 0.08, d * 1.05); roof.position.y = totalH + 0.04;
  grp.add(roof);

  const windowMats = [];
  for (const face of ["z", "x"]) {
    const wm = emissiveMat(0x39e0ff);
    const win = new THREE.Mesh(GEO.windowPlane, wm);
    win.scale.setScalar(0.36);
    if (face === "z") win.position.set(0, totalH * 0.55, d / 2 + 0.01);
    else { win.position.set(w / 2 + 0.01, totalH * 0.55, 0); win.rotation.y = Math.PI / 2; }
    grp.add(win); windowMats.push(wm);
  }
  const door = new THREE.Mesh(GEO.doorPlane, wallMat(0x2a2018, 0.6));
  door.scale.setScalar(0.85);
  door.position.set(w * 0.2, 0.19, d / 2 + 0.011);
  grp.add(door);

  const tank = new THREE.Mesh(GEO.tankCyl, wallMat(0x274a52, 0.7));
  tank.scale.set(0.13, 0.16, 0.13);
  tank.position.set(-w * 0.3, totalH + 0.14, d * 0.25);
  grp.add(tank);

  const ac = new THREE.Mesh(GEO.boxUnit, wallMat(0xcfd6e0, 0.5));
  ac.scale.set(0.13, 0.08, 0.06);
  ac.position.set(w / 2 + 0.04, floorH * 0.35, -d * 0.25);
  grp.add(ac);
  const acLed = new THREE.Mesh(GEO.lampHead, emissiveMat(0x39e0ff));
  acLed.scale.setScalar(0.3);
  acLed.position.set(w / 2 + 0.07, floorH * 0.35 + 0.02, -d * 0.25);
  grp.add(acLed);

  grp.add(shadowDecal(0.6));
  const pad = new THREE.Mesh(GEO.padPlane, PAVING_MAT);
  pad.rotation.x = -Math.PI / 2; pad.position.y = 0.003; pad.scale.set(w + 0.7, d + 0.8, 1);
  grp.add(pad);

  const rm = new THREE.MeshBasicMaterial({ color: 0xff6a6a, transparent: true, opacity: 0 });
  const ring = new THREE.Mesh(GEO.ring, rm);
  ring.rotation.x = -Math.PI / 2; ring.scale.setScalar(0.62); ring.position.y = 0.02;
  grp.add(ring);
  grp.userData = { type: "colonyHouse", id: meta.id, dyn: { windowMats, curtailRing: ring, acLed } };
  return grp;
}

function buildColonySociety(key, data, offset) {
  const root = new THREE.Group();
  root.position.set(offset.x, 0, offset.z);
  const cols = Math.max(...data.houses.map(h => h.grid_x)) + 1;
  const rows = Math.max(...data.houses.map(h => h.grid_z)) + 1;

  const padMat = pbrMat("grass", Math.max(cols, rows) * 0.9);
  const pad = new THREE.Mesh(new THREE.PlaneGeometry((cols + 1.5) * TILE, (rows + 1.5) * TILE), padMat);
  pad.rotation.x = -Math.PI / 2; pad.receiveShadow = true;
  pad.position.set((cols - 1) * TILE / 2, -0.01, (rows - 1) * TILE / 2);
  root.add(pad);

  const houseObjsLocal = new Map();
  const tintSeed = key === "society_b" ? 11 : 37;
  for (const meta of data.houses) {
    const g = buildSimpleHouseGroup(meta, tintSeed);
    g.position.set(meta.grid_x * TILE, 0, meta.grid_z * TILE);
    houseObjsLocal.set(meta.id, g);
    root.add(g);
  }

  const tx = new THREE.Group();
  const body = new THREE.Mesh(GEO.cyl, wallMat(0x565f78, 0.55));
  body.scale.set(0.42, 1.05, 0.42); body.position.y = 0.55; body.castShadow = true;
  tx.add(body);
  const barTrack = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x141822 }));
  barTrack.scale.set(0.2, 1.7, 0.2); barTrack.position.set(0.85, 0.85, 0);
  tx.add(barTrack);
  const barFill = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x2fe6a0, emissive: 0x0d3a2a, emissiveIntensity: 0.6 }));
  barFill.scale.set(0.15, 0.1, 0.15); barFill.position.set(0.85, 0.05, 0);
  tx.add(barFill);
  const beacon = new THREE.PointLight(0x2fe6a0, 1.0, 6, 2);
  beacon.position.set(0, 1.3, 0);
  tx.add(beacon);
  tx.position.set((cols + 0.5) * TILE, 0, (rows - 1) * TILE / 2);
  tx.userData = { type: "colonyTransformer", key };
  root.add(tx);

  scene.add(root);
  const txWorldPos = new THREE.Vector3(offset.x + tx.position.x, 1.3, offset.z + tx.position.z);
  const anchor = { type: "colonyTransformer", key, pos: txWorldPos.clone(), r: 40 };
  anchors.push(anchor);
  for (const [id, g] of houseObjsLocal) anchors.push({ type: "colonyHouse", key, id, pos: new THREE.Vector3(root.position.x + g.position.x, 0.6, root.position.z + g.position.z), r: 24 });

  return { key, label: COLONY[key].label, data, root, houseObjs: houseObjsLocal, transformer: { barFill, beacon }, txWorldPos, cols, rows };
}

let gridBrain = null;
function buildGridBrainHub(refs) {
  const hubPos = new THREE.Vector3();
  for (const r of refs) hubPos.add(r.txWorldPos);
  hubPos.divideScalar(refs.length);
  hubPos.y = 30;

  const grp = new THREE.Group();
  grp.position.copy(hubPos);
  const wire = new THREE.Mesh(new THREE.IcosahedronGeometry(2.4, 1), new THREE.MeshBasicMaterial({ color: 0x39e0ff, wireframe: true, transparent: true, opacity: 0.55 }));
  grp.add(wire);
  const core = new THREE.Mesh(new THREE.IcosahedronGeometry(1.5, 2), new THREE.MeshStandardMaterial({ color: 0x081018, emissive: 0x39e0ff, emissiveIntensity: 0.7, transparent: true, opacity: 0.9 }));
  grp.add(core);
  const glow = new THREE.PointLight(0x39e0ff, 1.6, 90, 2);
  grp.add(glow);
  scene.add(grp);
  anchors.push({ type: "gridbrain", pos: hubPos.clone(), r: 46 });

  const beams = [];
  for (const r of refs) {
    const geo = new THREE.BufferGeometry().setFromPoints([hubPos, r.txWorldPos]);
    const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0x39e0ff, transparent: true, opacity: 0.3 }));
    scene.add(line);
    const pulse = new THREE.Mesh(new THREE.SphereGeometry(0.4, 8, 8), new THREE.MeshBasicMaterial({ color: 0x39e0ff }));
    scene.add(pulse);
    beams.push({ from: hubPos, to: r.txWorldPos, line, pulse, t: hash01(beams.length * 3 + 1), speed: 0.18 + hash01(beams.length) * 0.1, key: r.key });
  }
  gridBrain = { group: grp, wire, core, hubPos, beams };
}

// -------------------------------------------------------------- world root
const houseObjs = new Map();
let workspaceObj = null, transformerObj = null, streetlightObjs = [], waterTankObj = null;
let solarStationObj = null, solarFeed = null;
let anchors = [];
const worldGroup = new THREE.Group();
scene.add(worldGroup);

function clearWorld() {
  for (const [, g] of houseObjs) worldGroup.remove(g);
  houseObjs.clear();
  if (workspaceObj) { worldGroup.remove(workspaceObj); workspaceObj = null; }
  if (transformerObj) { worldGroup.remove(transformerObj); transformerObj = null; }
  if (waterTankObj) { worldGroup.remove(waterTankObj); waterTankObj = null; }
  if (solarStationObj) { worldGroup.remove(solarStationObj); solarStationObj = null; }
  if (solarFeed) {
    worldGroup.remove(solarFeed.line);
    for (const p of solarFeed.pulses) worldGroup.remove(p.mesh);
    solarFeed = null;
  }
  for (const s of streetlightObjs) worldGroup.remove(s);
  streetlightObjs = [];
  // colony/GridBrain anchors are built once and persist across Society A
  // rescenarios — only Society A's own anchors need clearing here
  anchors = anchors.filter(a => a.type === "colonyHouse" || a.type === "colonyTransformer" || a.type === "gridbrain");
}

function buildWorld(data) {
  clearWorld();
  const cols = Math.max(...data.houses.map(h => h.grid_x)) + 1;
  const rows = Math.max(...data.houses.map(h => h.grid_z)) + 1;
  buildGround(cols, rows);

  for (const meta of data.houses) {
    const g = buildHouseGroup(meta);
    g.position.set(meta.grid_x * TILE, 0, meta.grid_z * TILE);
    houseObjs.set(meta.id, g);
    worldGroup.add(g);
    anchors.push({ type: "house", id: meta.id, pos: new THREE.Vector3(g.position.x, 1.0, g.position.z), r: 32 });
  }
  if (data.workspace) {
    workspaceObj = buildWorkspaceGroup(data.workspace);
    workspaceObj.position.set(data.workspace.grid_x * TILE, 0, data.workspace.grid_z * TILE);
    worldGroup.add(workspaceObj);
    anchors.push({ type: "workspace", pos: new THREE.Vector3(workspaceObj.position.x, 1.3, workspaceObj.position.z), r: 46 });
  }
  transformerObj = buildTransformerGroup();
  transformerObj.position.set((cols + 0.5) * TILE, 0, ((rows - 1) / 2) * TILE);
  worldGroup.add(transformerObj);
  anchors.push({ type: "transformer", pos: new THREE.Vector3(transformerObj.position.x, 1.1, transformerObj.position.z), r: 42 });

  waterTankObj = buildWaterTankGroup();
  waterTankObj.position.set(-1.7 * TILE, 0, (rows - 1) * TILE);
  worldGroup.add(waterTankObj);

  // only build the community station where one was actually simulated
  if (data.frames.some(fr => (fr.society.community_solar_kw || 0) > 0)) {
    solarStationObj = buildSolarStationGroup();
    solarStationObj.position.set(-2.3 * TILE, 0, ((rows - 1) / 2) * TILE);
    worldGroup.add(solarStationObj);
    anchors.push({ type: "solarstation", pos: new THREE.Vector3(solarStationObj.position.x, 1.0, solarStationObj.position.z), r: 52 });
    const cab = solarStationObj.userData.dyn.cabLocal;
    solarFeed = buildSolarFeedBeam(
      new THREE.Vector3(solarStationObj.position.x + cab.x, 1.0, solarStationObj.position.z + cab.z),
      new THREE.Vector3(transformerObj.position.x, 1.0, transformerObj.position.z));
  }

  const n = data.common_infra.streetlight_count || 8;
  for (let i = 0; i < n; i++) {
    const withLight = i % 3 === 0;
    const s = buildStreetlightGroup(withLight);
    const gx = (i % cols), gz = Math.floor(i / cols) % rows;
    s.position.set((gx + 0.5) * TILE, 0, (gz - 0.5) * TILE);
    worldGroup.add(s);
    streetlightObjs.push(s);
  }

  const cx = (cols - 1) * TILE / 2, cz = (rows - 1) * TILE / 2;
  const dist = Math.max(cols, rows) * TILE * 0.6;
  const newTarget = new THREE.Vector3(cx, 0.6, cz);
  const newPos = new THREE.Vector3(cx - dist * 0.72, dist * 0.62, cz + dist * 0.72);
  if (!camTween.active && perspCam.position.lengthSq() < 0.001) {
    controls.target.copy(newTarget); perspCam.position.copy(newPos);
    controls.update(); // orient the camera immediately, don't wait for the next rAF tick
  } else {
    startCamTween(newPos, newTarget);
  }
  frameOrtho(cx, cz, cols, rows);
}

function frameOrtho(cx, cz, cols, rows) {
  const half = Math.max(cols, rows) * TILE * 0.62 + 3;
  orthoCam.left = -half; orthoCam.right = half; orthoCam.top = half; orthoCam.bottom = -half;
  orthoCam.position.set(cx, 60, cz + 0.01);
  orthoCam.lookAt(cx, 0, cz);
  orthoCam.updateProjectionMatrix();
}

// smooth camera tween (used on scenario switch so cuts aren't jarring)
const camTween = { active: false, t: 0, dur: 700, fromPos: new THREE.Vector3(), toPos: new THREE.Vector3(), fromTarget: new THREE.Vector3(), toTarget: new THREE.Vector3(), t0: 0 };
function startCamTween(pos, target) {
  camTween.active = true; camTween.t0 = performance.now();
  camTween.fromPos.copy(perspCam.position); camTween.toPos.copy(pos);
  camTween.fromTarget.copy(controls.target); camTween.toTarget.copy(target);
}
function stepCamTween(now) {
  if (!camTween.active) return;
  const t = clamp((now - camTween.t0) / camTween.dur, 0, 1);
  const e = 1 - Math.pow(1 - t, 3);
  perspCam.position.lerpVectors(camTween.fromPos, camTween.toPos, e);
  controls.target.lerpVectors(camTween.fromTarget, camTween.toTarget, e);
  if (t >= 1) camTween.active = false;
}

// ------------------------------------------------------------ data loading
const cache = {};
async function loadScenario(key) {
  if (!cache[key]) { const res = await fetch(SCENARIO_FILES[key]); cache[key] = await res.json(); }
  return cache[key];
}
function computeMaxKw(data) {
  let m = 1;
  for (const f of data.frames) for (const h of f.houses) m = Math.max(m, h.kw);
  return m;
}
function frame() { return state.data.frames[state.frameIdx]; }

const colonyData = {}; // key -> loaded json, for society_b / society_c
async function loadColonyData() {
  const entries = await Promise.all(Object.entries(COLONY).map(async ([key, cfg]) => {
    const res = await fetch(cfg.file);
    return [key, await res.json()];
  }));
  for (const [key, data] of entries) { colonyData[key] = data; colonyData[key]._maxKw = computeMaxKw(data); }
}
function colonyFrame(key) {
  const d = colonyData[key]; if (!d) return null;
  return d.frames[Math.min(state.frameIdx, d.frames.length - 1)];
}

// ------------------------------------------------------------- per-frame
function applyFrame() {
  const data = state.data, f = frame(), env = f.environment;
  const maxKw = state.maxKw;

  const alt = env.sun_altitude, az = env.sun_azimuth, dist = 90;
  const sx = Math.cos(az) * Math.cos(alt) * dist, sy = Math.sin(alt) * dist, sz = Math.sin(az) * Math.cos(alt) * dist;
  // The sun used to be clamped to y >= -5 with a 0.15 intensity floor, so it
  // never actually set — it kept lighting the scene from just under the
  // horizon and "night" was really just dim daylight. It now goes below the
  // ground and reaches true zero, which is what lets the streetlights and
  // window glow (both already simulated) become the night light sources.
  sun.position.set(sx, sy, sz);
  sun.target.position.copy(controls.target);
  const dayness = clamp((alt + 0.05) / 0.35, 0, 1);
  const daylit = dayness * dayness * (3 - 2 * dayness);   // smoothstep, softer dusk
  sun.intensity = lerp(0, 2.5, daylit);
  sun.visible = daylit > 0.001;
  sun.color.setHSL(lerp(0.08, 0.14, dayness), 0.5, lerp(0.65, 0.92, dayness));
  hemi.intensity = lerp(0.04, 0.7, daylit);
  ambient.intensity = lerp(0.03, 0.4, daylit) * (1 - (env.cloud_factor || 0) * 0.3);
  sunSprite.position.set(sx, sy, sz);
  sunHalo.position.set(sx, sy, sz);
  const sunVisible = alt > -0.1;
  sunSprite.visible = sunHalo.visible = sunVisible;
  sunSprite.material.opacity = clamp(dayness * 1.1, 0, 1);
  sunHalo.material.opacity = clamp(dayness * 0.9, 0, 0.85);

  // moon sits opposite the sun across the sky and only shows at night —
  // a real second body, not the sun dimmed
  const mx = -sx, my = -sy * 0.6 + 40, mz = -sz;
  moonSprite.position.set(mx, my, mz);
  moonHalo.position.set(mx, my, mz);
  const moonVisible = alt < 0.05;
  moonSprite.visible = moonHalo.visible = moonVisible;
  const moonness = clamp(1 - dayness * 4, 0, 1);
  moonSprite.material.opacity = moonness;
  moonHalo.material.opacity = moonness * 0.6;
  // the moon is now a real light source, not just a sprite: a cool, dim
  // directional key from the moon's own position, ramping in as the sun
  // ramps out. Without this, killing the sun's floor left night pitch black.
  moonLight.position.set(mx, my, mz);
  moonLight.target.position.copy(controls.target);
  moonLight.intensity = moonness * 0.42;
  moonLight.visible = moonness > 0.01;

  stars.material.opacity = clamp(1 - dayness * 3, 0, 0.85);
  for (const c of clouds) c.material.opacity = lerp(0.12, 0.55, dayness) * (0.5 + (env.cloud_factor || 0));

  const nightColor = new THREE.Color(0x050914), duskColor = new THREE.Color(0x2a2140), dayColor = new THREE.Color(0x7fb2df);
  let bg;
  if (alt <= -0.05) bg = nightColor;
  else if (alt < 0.15) bg = nightColor.clone().lerp(duskColor, clamp((alt + 0.05) / 0.2, 0, 1));
  else bg = duskColor.clone().lerp(dayColor, clamp((alt - 0.15) / 0.4, 0, 1));
  // per-scenario grade: tints the sky/fog toward this scenario's mood so a
  // heatwave day and an outage day don't look like the same day. Graded on
  // top of the real sun position, never substituted for it.
  const mood = moodFor(state.scenarioKey);
  bg = bg.lerp(new THREE.Color(mood.tint), 0.16);
  scene.background = bg; scene.fog.color = bg;
  sun.color.lerp(new THREE.Color(mood.tint), 0.3);

  for (const meta of data.houses) {
    const g = houseObjs.get(meta.id); if (!g) continue;
    const hs = f.houses[meta.id], dyn = g.userData.dyn;
    const col = loadColor(hs.kw, maxKw);
    const glow = clamp(hs.kw / Math.max(maxKw * 0.55, 0.5), 0.05, 1);
    for (const wm of dyn.windowMats) { wm.emissive.copy(col); wm.emissiveIntensity = lerp(0.06, 1.05, glow) * lerp(1, 0.45, dayness); }
    if (dyn.solarMat) dyn.solarMat.emissiveIntensity = lerp(0.06, 0.9, clamp(hs.solar_kw / 4, 0, 1));
    if (dyn.evRing) dyn.evRing.material.opacity = hs.ev_state === "charging" ? (0.45 + 0.4 * Math.sin(performance.now() / 220)) : 0;
    if (dyn.curtailRing) dyn.curtailRing.material.opacity = hs.curtailed ? 0.85 : 0;
    if (dyn.batteryBar) { const soc = clamp(hs.battery_soc || 0, 0, 1); dyn.batteryBar.scale.y = 0.1 + soc * 0.45; dyn.batteryBar.position.y = (0.1 + soc * 0.45) / 2; }
    if (dyn.acLed) dyn.acLed.material.emissiveIntensity = hs.ac_on ? 1.4 : 0.05;
    if (dyn.geyserLed) dyn.geyserLed.material.emissiveIntensity = hs.geyser_on ? 1.4 : 0.05;
  }

  if (workspaceObj && f.workspace) {
    const ws = f.workspace, dyn = workspaceObj.userData.dyn, maxWs = 90;
    const col = loadColor(ws.kw, maxWs), glow = clamp(ws.kw / maxWs, 0.05, 1);
    for (const wm of dyn.windowMats) { wm.emissive.copy(col); wm.emissiveIntensity = lerp(0.06, 1.0, glow) * lerp(1, 0.45, dayness); }
    dyn.solarMat.emissiveIntensity = lerp(0.1, 1.4, clamp(ws.solar_kw / 10, 0, 1));
  }

  if (transformerObj) {
    const g = f.grid, dyn = transformerObj.userData.dyn;
    const frac = clamp(g.transformer_kva / g.rating_kva, 0, 1.3);
    const stateColors = { NORMAL: 0x34d399, WARNING: 0xfbbf24, CRITICAL: 0xf59e0b, BREACH: 0xf87171, TRIPPED: 0xef4444 };
    const col = new THREE.Color(stateColors[g.state] || 0x8b95ab);
    const stressed = g.state === "CRITICAL" || g.state === "BREACH" || g.state === "TRIPPED";
    const pulseHz = g.state === "TRIPPED" ? 130 : 420;
    const flashing = stressed && Math.sin(performance.now() / pulseHz) > 0;
    const fillH = Math.min(1, frac) * 2.2;
    dyn.barFill.scale.y = Math.max(0.02, fillH); dyn.barFill.position.y = dyn.barFill.scale.y / 2;
    dyn.barFill.material.color.copy(flashing ? new THREE.Color(0xffffff) : col);
    dyn.barFill.material.emissive.copy(col).multiplyScalar(0.5);
    dyn.beacon.color.copy(col);
    dyn.beacon.intensity = lerp(0.4, 2.4, clamp(frac, 0, 1)) + (flashing ? 1.5 : 0);
    // ground stress ring: invisible when comfortably under rating, widens
    // and brightens as the whole society's coincident load approaches and
    // breaches the transformer's limit
    dyn.stressRing.material.color.copy(col);
    dyn.stressRing.material.opacity = frac < 0.75 ? 0 : lerp(0.15, 0.9, clamp((frac - 0.75) / 0.55, 0, 1)) * (flashing ? 1.4 : 1);
    dyn.stressRing.scale.setScalar(1.25 + Math.max(0, frac - 0.75) * 0.9);
  }

  // #18 restoration dramatization -- explicitly NOT simulated. The engine
  // models no crew, travel or repair time; this is a labelled illustration of
  // the operational consequence of a trip, shown only while one is happening.
  const dispatchEl = document.getElementById("dispatch");
  if (dispatchEl) {
    const tripped = f.grid.state === "TRIPPED";
    dispatchEl.classList.toggle("hidden", !tripped);
    if (tripped) {
      let since = 0;
      for (let i = state.frameIdx; i >= 0 && state.data.frames[i].grid.state === "TRIPPED"; i--) since++;
      const elapsed = since * (state.data.meta.interval_minutes || 15);
      document.getElementById("dispatchTime").textContent = `${elapsed} min out · crew en route`;
    }
  }

  if (waterTankObj) {
    const lvl = clamp((f.society.common_infra.water_tank_level_pct || 0) / 100, 0, 1);
    waterTankObj.userData.dyn.fill.scale.y = 0.1 + lvl * 0.55;
  }

  if (solarStationObj) {
    // 60 kWp nameplate — panel glow and export-beam brightness are both a
    // direct read of the station's real simulated output this tick
    const csk = f.society.community_solar_kw || 0;
    const out = clamp(csk / 60, 0, 1);
    const dyn = solarStationObj.userData.dyn;
    for (const sm of dyn.panelMats) sm.emissiveIntensity = lerp(0.05, 1.1, out);
    dyn.cabLed.material.emissiveIntensity = out > 0.01 ? 1.4 : 0.08;
    dyn.beacon.intensity = out * 2.2;
    if (solarFeed) {
      solarFeed.line.material.opacity = out > 0.01 ? lerp(0.12, 0.5, out) : 0;
      const speed = 0.0004 + out * 0.0007;
      for (const p of solarFeed.pulses) {
        p.t = (p.t + speed * 16) % 1;
        p.mesh.position.lerpVectors(solarFeed.from, solarFeed.to, p.t);
        p.mesh.position.y = 1.0 + Math.sin(p.t * Math.PI) * 0.5;
        p.mesh.material.opacity = out > 0.01 ? 0.9 : 0;
      }
    }
  }

  const on = f.society.common_infra.streetlights_on;
  for (const s of streetlightObjs) {
    const dyn = s.userData.dyn;
    dyn.head.material.emissiveIntensity = on ? 1.4 : 0;
    if (dyn.light) dyn.light.intensity = on ? 1.0 : 0;
  }

  applyColonyFrame();
  applyDistrictFrame();
  updateGridBrainLedger();
  updateHUD();
  drawTopSpark();
}

// --------------------------------------------------------- colony / GridBrain
const stateColorHex = { NORMAL: 0x2fe6a0, WARNING: 0xffc857, CRITICAL: 0xffc857, BREACH: 0xff3d5d, TRIPPED: 0xff3d5d };

function applyColonyFrame() {
  for (const ref of colonyRefs) {
    if (ref.key === "society_a") continue; // already handled above
    const cf = colonyFrame(ref.key); if (!cf) continue;
    const maxKw = ref.data._maxKw;
    for (const meta of ref.data.houses) {
      const g = ref.houseObjs.get(meta.id); if (!g) continue;
      const hs = cf.houses[meta.id], dyn = g.userData.dyn;
      const col = loadColor(hs.kw, maxKw);
      const glow = clamp(hs.kw / Math.max(maxKw * 0.55, 0.5), 0.05, 1);
      for (const wm of dyn.windowMats) { wm.emissive.copy(col); wm.emissiveIntensity = lerp(0.06, 1.0, glow); }
      dyn.curtailRing.material.opacity = hs.curtailed ? 0.8 : 0;
      if (dyn.acLed) dyn.acLed.material.emissiveIntensity = hs.ac_on ? 1.4 : 0.05;
    }
    const g = cf.grid, frac = clamp(g.transformer_kva / g.rating_kva, 0, 1.3);
    const col = new THREE.Color(stateColorHex[g.state] || 0x8b95ab);
    ref.transformer.barFill.scale.y = Math.max(0.02, Math.min(1, frac) * 1.7);
    ref.transformer.barFill.position.y = ref.transformer.barFill.scale.y / 2;
    ref.transformer.barFill.material.color.copy(col);
    ref.transformer.barFill.material.emissive.copy(col).multiplyScalar(0.5);
    ref.transformer.beacon.color.copy(col);
    ref.transformer.beacon.intensity = lerp(0.4, 2.2, clamp(frac, 0, 1));
  }
}

// Decision ledger — sourced directly from the real, already-simulated
// curtailment state each society's own physics/transformer engine produced.
// Not a separate fabricated "AI layer" — this is that real output, read.
const ledgerState = { entries: [], lastCurtailed: { society_a: new Set(), society_b: new Set(), society_c: new Set() }, lastRecommendation: -999 };
function pushLedger(tmin, text, cls) {
  ledgerState.entries.push({ tmin, text, cls });
  if (ledgerState.entries.length > 80) ledgerState.entries.shift();
  renderLedger();
}
function checkCurtailmentDiff(key, label, curtailedIds, g, tmin) {
  const prev = ledgerState.lastCurtailed[key];
  const now = new Set(curtailedIds);
  for (const id of now) {
    if (!prev.has(id)) {
      const pct = ((g.transformer_kva / g.rating_kva) * 100).toFixed(0);
      pushLedger(tmin, `${label}: House #${id} curtailed — transformer at ${pct}% (${g.state}).`, "act");
    }
  }
  ledgerState.lastCurtailed[key] = now;
}
function updateGridBrainLedger() {
  if (!colonyRefs.length) return;
  const fa = frame();
  checkCurtailmentDiff("society_a", "Society A", fa.society.fairness.curtailed_house_ids, fa.grid, fa.t_min);
  const fb = colonyFrame("society_b"), fc = colonyFrame("society_c");
  if (fb) checkCurtailmentDiff("society_b", "Society B", fb.society.fairness.curtailed_house_ids, fb.grid, fa.t_min);
  if (fc) checkCurtailmentDiff("society_c", "Society C", fc.society.fairness.curtailed_house_ids, fc.grid, fa.t_min);

  const fracs = [["Society A", fa.grid.transformer_kva / fa.grid.rating_kva],
    ["Society B", fb ? fb.grid.transformer_kva / fb.grid.rating_kva : 0],
    ["Society C", fc ? fc.grid.transformer_kva / fc.grid.rating_kva : 0]];
  const stressed = fracs.filter(([, f]) => f > 0.85).sort((a, b) => b[1] - a[1]);
  const spare = fracs.filter(([, f]) => f < 0.65).sort((a, b) => a[1] - b[1]);
  if (stressed.length && spare.length && fa.t_min - ledgerState.lastRecommendation > 60) {
    const [sName, sFrac] = stressed[0], [spName, spFrac] = spare[0];
    pushLedger(fa.t_min, `GRIDBRAIN: ${sName} at ${(sFrac * 100).toFixed(0)}% of rating; ${spName} has ${((1 - spFrac) * 100).toFixed(0)}% headroom on a comparable transformer — cross-feeder support recommended.`, "rec");
    ledgerState.lastRecommendation = fa.t_min;
  }
  renderNodeMap();
}
function renderLedger() {
  const el = document.getElementById("ledger"); if (!el) return;
  if (!ledgerState.entries.length) { el.innerHTML = '<div class="ledger-empty">Watching all three transformers…</div>'; return; }
  el.innerHTML = ledgerState.entries.slice(-50).map(e =>
    `<div class="ledger-row ${e.cls || ""}"><span class="lt mono">${minToClock(e.tmin)}</span>${e.text}</div>`
  ).join("");
}
// ------------------------------------------------------------ solar tab
// Compares the sync-OFF baseline (whatif_ev{ev}_ai.json -- curtailment on,
// no retiming, no community station) against the sync-ON file for the same
// EV level (retimed EV charging + a 60 kWp community station both bundled
// together, see generate_solar_sync.py). Real numbers only: solar_kw and
// household kw are read straight from both real simulation runs, never
// invented. The "load shifted to daylight" figure is the increase in each
// house's own 06:00-18:00 consumption between the two runs -- a direct,
// honest proxy for how much the coordinator actually moved into sunshine
// hours, computable purely from data already in both files.
const DAYLIGHT_START_MIN = 6 * 60, DAYLIGHT_END_MIN = 18 * 60;
const solarStatsCache = {};
async function solarStats(ev) {
  if (solarStatsCache[ev]) return solarStatsCache[ev];
  const [offData, onData] = await Promise.all([loadScenario(whatifKey(ev, true)), loadScenario(`whatif_ev${ev}_ai_solarsync`)]);
  const stepH = (offData.meta.interval_minutes || 15) / 60;
  let totalSolarKwh = 0, totalStationKwh = 0, totalShiftKwh = 0, totalSavingRs = 0;
  const rows = [], byHouse = {};
  for (const meta of offData.houses) {
    let solarKwh = 0, daytimeOff = 0, daytimeOn = 0;
    for (let i = 0; i < offData.frames.length; i++) {
      const fo = offData.frames[i], fn = onData.frames[i];
      const ho = fo.houses[meta.id], hn = fn.houses[meta.id];
      solarKwh += (ho.solar_kw || 0) * stepH;
      if (fo.t_min >= DAYLIGHT_START_MIN && fo.t_min < DAYLIGHT_END_MIN) {
        daytimeOff += ho.kw * stepH;
        daytimeOn += hn.kw * stepH;
      }
    }
    const shiftKwh = Math.max(0, daytimeOn - daytimeOff);
    const savingRs = shiftKwh * (ILLUSTRATIVE_TARIFF.rate_per_kwh - ILLUSTRATIVE_EXPORT_RATE);
    totalSolarKwh += solarKwh; totalShiftKwh += shiftKwh; totalSavingRs += savingRs;
    const row = { id: meta.id, archetype: meta.archetype, hasEv: meta.has_ev, hasSolar: meta.has_solar, solarKwh, shiftKwh, savingRs };
    rows.push(row); byHouse[meta.id] = row;
  }
  for (const f of onData.frames) totalStationKwh += (f.society.community_solar_kw || 0) * stepH;
  solarStatsCache[ev] = { rows, byHouse, totalSolarKwh, totalStationKwh, totalShiftKwh, totalSavingRs };
  return solarStatsCache[ev];
}

let solarTabRenderToken = 0;
async function renderSolarTab() {
  const headlineEl = document.getElementById("solarHeadline");
  const tableEl = document.getElementById("solarTable");
  if (!headlineEl || !tableEl) return;
  if (state.whatifEv === null || state.whatifEv === undefined) {
    headlineEl.innerHTML = '<h2>Solar &middot; Society A</h2><div class="inspector-empty">Pick an EV level in the What-if panel to load solar data for that setting.</div>';
    tableEl.innerHTML = "";
    return;
  }
  const ev = state.whatifEv;
  const myToken = ++solarTabRenderToken;
  headlineEl.innerHTML = '<h2>Solar &middot; Society A</h2><div class="inspector-empty">Computing from real simulation data&hellip;</div>';
  tableEl.innerHTML = "";
  const st = await solarStats(ev);
  if (myToken !== solarTabRenderToken) return; // a newer request superseded this one
  const { totalSolarKwh, totalStationKwh, totalShiftKwh, totalSavingRs } = st;
  const rows = st.rows.slice();

  const rupee = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  headlineEl.innerHTML = `
    <h2>Solar &middot; Society A &middot; EV ${ev}%</h2>
    <div class="node-row"><span class="nname">Rooftop solar generated today</span><span class="nstate mono" style="color:var(--text)">${totalSolarKwh.toFixed(0)} kWh</span></div>
    <div class="node-row"><span class="nname">GridBrain community station</span><span class="nstate mono" style="color:var(--text)">${totalStationKwh.toFixed(0)} kWh</span></div>
    <div class="node-row"><span class="nname">Load shifted into daylight</span><span class="nstate mono" style="color:var(--text)">${totalShiftKwh.toFixed(1)} kWh</span></div>
    <div class="node-row"><span class="nname">AI-coordinated saving today</span><span class="nstate mono" style="color:var(--gold)">&#8377;${rupee.format(Math.round(totalSavingRs))}</span></div>
    <div class="whatif-readout" style="margin-top:6px">This is the incremental value of solar-synced charging plus the community station together, versus the same day without either &mdash; not total solar savings, which would happen regardless of coordination. It excludes a demand-charge component: solar generates nothing after sunset, so it can't shave the evening peak by itself &mdash; that needs storage, a separate lever.</div>
  `;
  rows.sort((a, b) => b.savingRs - a.savingRs);
  tableEl.innerHTML = '<h2>Per-house breakdown</h2>' + rows.map(r => `
    <div class="node-row node-row-jump" data-house-id="${r.id}">
      <span class="nname">House #${r.id} <span style="color:var(--muted);font-weight:400">(${r.archetype.replace(/_/g, " ")}${r.hasEv ? " &middot; EV" : ""}${!r.hasSolar ? " &middot; no rooftop panels" : ""})</span></span>
      <span class="nstate mono" style="color:${r.savingRs > 0 ? "var(--gold)" : "var(--muted)"}">&#8377;${r.savingRs.toFixed(0)}</span>
    </div>`).join("");
}
document.getElementById("solarTable").addEventListener("click", (e) => {
  const row = e.target.closest(".node-row-jump"); if (!row) return;
  state.selected = { kind: "house", id: +row.dataset.houseId };
  renderInspector();
  setRailTab("live");
});

function renderNodeMap() {
  const el = document.getElementById("nodeMap"); if (!el || !colonyRefs.length) return;
  const fa = frame(), fb = colonyFrame("society_b"), fc = colonyFrame("society_c");
  const rows = [
    ["society_a", "Society A", fa.grid, 60], ["society_b", "Society B", fb ? fb.grid : null, 48], ["society_c", "Society C", fc ? fc.grid : null, 48],
  ];
  el.innerHTML = `<div class="node-row node-row-jump" data-jump="colony"><span class="nname">Colony overview</span><span class="nstate" style="color:var(--accent)">ALL &rarr;</span></div>` +
    rows.map(([key, name, g, n]) => g ? `
    <div class="node-row node-row-jump" data-jump="${key}">
      <span class="nname">${name} <span style="color:var(--muted);font-weight:400">(${n} homes)</span></span>
      <span class="nstate pill ${g.state}">${g.state}</span>
    </div>` : "").join("");
}
document.getElementById("nodeMap").addEventListener("click", (e) => {
  const row = e.target.closest(".node-row-jump"); if (!row) return;
  const target = row.dataset.jump;
  document.querySelectorAll("#camGroup button").forEach(b => b.classList.toggle("active", b.dataset.cam === (target === "colony" ? "colony" : "orbit")));
  if (target === "colony") { state.cam = "colony"; camera = perspCam; controls.object = camera; controls.enableRotate = true; renderPass.camera = camera; scene.fog.density = FOG_DENSITY.colony; onResize(); }
  flyToSociety(target);
});

// --------------------------------------------------------------- HUD/UI
function updateHUD() {
  const f = frame(), g = f.grid, env = f.environment, data = state.data;
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
  for (const fr of data.frames) if (fr.grid.transformer_kva > peak) { peak = fr.grid.transformer_kva; peakT = fr.t_min; }
  document.getElementById("kpiPeak").textContent = peak.toFixed(1) + " kVA";
  document.getElementById("kpiPeakTime").textContent = minToClock(peakT);

  const bar = document.getElementById("kvaBar");
  const stateColors = { NORMAL: "var(--ok)", WARNING: "var(--warn)", CRITICAL: "var(--warn)", BREACH: "var(--tripped)", TRIPPED: "var(--tripped)" };
  bar.style.width = clamp((g.transformer_kva / g.rating_kva) * 100, 0, 100) + "%";
  bar.style.background = stateColors[g.state] || "var(--muted)";

  document.getElementById("gridDot").style.background = g.available ? "var(--ok)" : "var(--tripped)";
  document.getElementById("gridLabel").textContent = g.available ? "GRID " + g.state : "GRID OUTAGE";
  document.getElementById("timeLabel").textContent = minToClock(f.t_min);
  document.getElementById("dateLabel").textContent = data.meta.date + " · " + data.meta.scenario;

  // throttle the inspector's full DOM rebuild independent of simulation
  // speed — rebuilding it 30+ times/sec at high playback caused visible
  // layout thrashing in the rail
  const now = performance.now();
  if (now - lastInspectorRender > 120) { renderInspector(); lastInspectorRender = now; }
}
let lastInspectorRender = 0;

// Returns BOTH the running "so far today" figures and the full-day ones.
// The full-day numbers are exact rather than forecast: this dataset is a
// complete deterministic 24h run, so every remaining tick is already known.
// Reporting only "so far" made the recoverable amount read as a flat ₹0 at
// any time before 6pm — arithmetically correct, and completely unhelpful,
// since none of the peak window had elapsed yet.
function costExposure(houseId) {
  const data = state.data;
  const stepH = (data.meta.interval_minutes || 15) / 60;
  const acc = { kwhTotal: 0, kwhPeak: 0 }, day = { kwhTotal: 0, kwhPeak: 0 };
  for (let i = 0; i < data.frames.length; i++) {
    const fr = data.frames[i], kwh = fr.houses[houseId].kw * stepH;
    const inPeak = fr.t_min >= ILLUSTRATIVE_TARIFF.peak_start_min && fr.t_min < ILLUSTRATIVE_TARIFF.peak_end_min;
    day.kwhTotal += kwh; if (inPeak) day.kwhPeak += kwh;
    if (i <= state.frameIdx) { acc.kwhTotal += kwh; if (inPeak) acc.kwhPeak += kwh; }
  }
  const R = ILLUSTRATIVE_TARIFF.rate_per_kwh, M = ILLUSTRATIVE_TARIFF.peak_multiplier;
  const costOf = (o) => (o.kwhTotal - o.kwhPeak) * R + o.kwhPeak * R * M;
  // honest arithmetic, not a simulated optimizer decision: the extra amount
  // paid purely because that energy landed inside the peak window, at the
  // same illustrative rate — i.e. what shifting it off-peak would recover
  const savingOf = (o) => o.kwhPeak * R * (M - 1);
  return {
    kwhTotal: acc.kwhTotal, cost: costOf(acc), shiftSaving: savingOf(acc),
    peakShare: acc.kwhTotal > 0 ? (acc.kwhPeak / acc.kwhTotal) * 100 : 0,
    dayKwh: day.kwhTotal, dayCost: costOf(day), dayShiftSaving: savingOf(day),
    dayPeakShare: day.kwhTotal > 0 ? (day.kwhPeak / day.kwhTotal) * 100 : 0,
  };
}

// Real, not aspirational: this house's own recorded curtailment history so
// far today, from the engine's real transformer-protection decisions.
function aiProtectionStats(houseId) {
  const data = state.data;
  let ticks = 0, overrides = 0;
  for (let i = 0; i <= state.frameIdx; i++) {
    if (data.frames[i].houses[houseId].curtailed) ticks++;
    // real recorded override events, exported by the engine (see
    // household.py `overrode`) -- this field used to be a hardcoded []
    if ((data.frames[i].society.fairness.override_events || []).includes(houseId)) overrides++;
  }
  return { hours: ticks * (data.meta.interval_minutes || 15) / 60, overrides };
}

function drawSparkline(id, values, limitLine) {
  const c = document.getElementById(id); if (!c) return;
  const sctx = c.getContext("2d"); const w = c.width, h = c.height;
  sctx.clearRect(0, 0, w, h);
  const max = Math.max(...values, limitLine || 0) * 1.1 || 1;
  sctx.strokeStyle = "rgba(139,149,171,0.25)"; sctx.beginPath(); sctx.moveTo(0, h - 1); sctx.lineTo(w, h - 1); sctx.stroke();
  if (limitLine) {
    const ly = h - (limitLine / max) * h;
    sctx.strokeStyle = "rgba(248,113,113,0.5)"; sctx.setLineDash([3, 3]);
    sctx.beginPath(); sctx.moveTo(0, ly); sctx.lineTo(w, ly); sctx.stroke(); sctx.setLineDash([]);
  }
  sctx.beginPath();
  values.forEach((v, i) => { const x = (i / (values.length - 1)) * w, y = h - (v / max) * h; i === 0 ? sctx.moveTo(x, y) : sctx.lineTo(x, y); });
  sctx.strokeStyle = "#f5b942"; sctx.lineWidth = 1.6; sctx.stroke();
  const curX = (state.frameIdx / (values.length - 1)) * w, curY = h - (values[state.frameIdx] / max) * h;
  sctx.fillStyle = "#f5b942"; sctx.beginPath(); sctx.arc(curX, curY, 3, 0, 7); sctx.fill();
}

// Rendered only when the sync scenario is actually loaded and its paired
// stats are already computed (solarStats is warmed by setWhatIf) -- the
// inspector redraws every tick and must stay synchronous.
function solarSyncBoxHtml(houseId) {
  if (!state.whatifSync) return "";
  const st = solarStatsCache[state.whatifEv];
  const r = st && st.byHouse[houseId];
  if (!r) return "";
  if (r.shiftKwh < 0.01) {
    return `<div class="cost-box">
      <h4>Solar-sync contribution</h4>
      <div class="note">Nothing to retime in this house today — no flexible load that could move into daylight hours. It still benefits from the community station, which offsets the whole society's draw upstream.</div>
    </div>`;
  }
  return `<div class="save-box">
    <h4>Solar-sync contribution</h4>
    <div class="stat-row"><span class="k">Load moved into daylight</span><span class="v mono">${r.shiftKwh.toFixed(2)} kWh</span></div>
    <div class="v">₹${r.savingRs.toFixed(0)} saved today</div>
    <div class="note">Measured, not projected: the increase in this house's own 6am–6pm consumption between the real sync-off and sync-on simulation runs, valued at the import/export spread. The car still finishes charging — a 50% state-of-charge floor and a 5pm fallback guarantee it.</div>
  </div>`;
}

let lastInspectorSelKey = null;
function renderInspector() {
  const el = document.getElementById("inspector");
  if (!state.selected) { el.innerHTML = '<div class="inspector-empty">Tap any house, the workspace, or the transformer in the scene to see its live state — including what that household\'s own bill exposure looks like today.</div>'; lastInspectorSelKey = null; return; }
  // only play the fade-in on an actual new selection — replaying it on every
  // routine per-tick refresh during playback was the "blip blip" flicker
  const selKey = `${state.selected.kind}:${state.selected.id ?? ""}:${state.selected.key ?? ""}`;
  const freshClass = selKey !== lastInspectorSelKey ? "fresh" : "";
  lastInspectorSelKey = selKey;
  const f = frame(), data = state.data;
  if (state.selected.kind === "house") {
    const meta = data.houses[state.selected.id], hs = f.houses[state.selected.id];
    const ce = costExposure(meta.id);
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>House #${meta.id}</h3>
        <div class="archetype">${meta.archetype.replace(/_/g, " ")} &middot; ${meta.floors} floor${meta.floors > 1 ? "s" : ""}</div>
        <div class="badges">
          ${meta.has_ev ? `<span class="badge ${hs.ev_state === 'charging' ? 'on' : ''}">EV ${hs.ev_state}</span>` : ""}
          ${meta.has_solar ? `<span class="badge on">Solar</span>` : ""}
          ${meta.has_battery ? `<span class="badge">Battery ${(hs.battery_soc * 100).toFixed(0)}%</span>` : ""}
          ${hs.curtailed ? `<span class="badge" style="color:var(--crit)">Curtailed</span>` : ""}
        </div>
        <div class="stat-row"><span class="k">Load now</span><span class="v mono">${hs.kw.toFixed(2)} kW</span></div>
        <div class="stat-row"><span class="k">Occupants</span><span class="v mono">${hs.occupancy}</span></div>
        <div class="stat-row"><span class="k">Indoor temp</span><span class="v mono">${hs.indoor_temp_c.toFixed(1)}°C</span></div>
        <div class="stat-row"><span class="k">Comfort deviation</span><span class="v mono">${hs.comfort_dev_c.toFixed(1)}°C</span></div>
        <div class="stat-row"><span class="k">AC</span><span class="v mono">${hs.ac_on ? "on" : "off"}</span></div>
        <div class="stat-row"><span class="k">Geyser</span><span class="v mono">${hs.geyser_on ? "on" : "off"}</span></div>
        ${meta.has_ev ? `<div class="stat-row"><span class="k">EV SOC</span><span class="v mono">${(hs.ev_soc * 100).toFixed(0)}%</span></div>` : ""}
        ${meta.has_solar ? `<div class="stat-row"><span class="k">Solar now</span><span class="v mono">${hs.solar_kw.toFixed(2)} kW</span></div>` : ""}
        <div class="cost-box">
          <h4>Sub-meter reading</h4>
          <div class="stat-row"><span class="k">Energy so far today</span><span class="v mono">${ce.kwhTotal.toFixed(2)} kWh <span style="color:var(--muted)">/ ${ce.dayKwh.toFixed(1)} full day</span></span></div>
          <div class="stat-row"><span class="k">Illustrative cost so far</span><span class="v mono">₹${ce.cost.toFixed(0)} <span style="color:var(--muted)">/ ₹${ce.dayCost.toFixed(0)} full day</span></span></div>
          <div class="cost-split"><div style="width:${ce.dayPeakShare.toFixed(0)}%;background:var(--crit)"></div><div style="flex:1;background:var(--accent)"></div></div>
          <div class="stat-row"><span class="k">Share incurred 6–10pm peak</span><span class="v mono">${ce.dayPeakShare.toFixed(0)}% <span style="color:var(--muted)">full day</span></span></div>
          <div class="note">This is the same aggregate-power reading a real per-flat sub-meter reports — the feed a coordinator would use. Illustrative flat+ToD rate for demonstration, not this DISCOM's filed tariff.</div>
        </div>
        <div class="save-box">
          <h4>If peak-window load shifted off-peak</h4>
          <div class="v">₹${ce.dayShiftSaving.toFixed(0)} recoverable today</div>
          <div class="note">₹${ce.shiftSaving.toFixed(0)} of that has been incurred by ${minToClock(f.t_min)}; the rest lands in this evening's 6–10pm window. Both are exact, not forecast — this is a complete, deterministic 24-hour dataset, so the remaining ticks are already known rather than predicted. Direct arithmetic on the metered reading above (peak kWh × the peak-rate premium), not a controller decision.</div>
        </div>
        <div class="cost-box">
          <h4>GridBrain facilities on this house</h4>
          <div class="stat-row"><span class="k">Real-time sub-metering</span><span class="v" style="color:var(--ok)">active</span></div>
          <div class="stat-row"><span class="k">Fair-rotation protection</span><span class="v" style="color:var(--ok)">active</span></div>
          <div class="stat-row"><span class="k">Transformer-protection curtailment used today</span><span class="v mono">${aiProtectionStats(meta.id).hours.toFixed(2)} h</span></div>
          <div class="stat-row"><span class="k">Resident overrides honoured</span><span class="v mono" style="color:${aiProtectionStats(meta.id).overrides ? "var(--gold)" : "var(--muted)"}">${aiProtectionStats(meta.id).overrides}</span></div>
          <div class="stat-row"><span class="k">Colony headroom awareness</span><span class="v" style="color:var(--ok)">active</span></div>
          <div class="note">These are the real mechanisms already running, not a wishlist. "Curtailment used today" is this house's actual recorded shed time from the engine's real transformer protection. <b>"Overrides honoured"</b> counts the ticks where this household was asked to shed and simply kept its load running — proof the signal is a quota, not a command. Both are recorded engine decisions, not estimates.</div>
        </div>
        ${solarSyncBoxHtml(meta.id)}
        <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
      </div>`;
    drawSparkline("sparkCanvas", data.frames.map(fr => fr.houses[meta.id].kw));
  } else if (state.selected.kind === "workspace") {
    const ws = f.workspace;
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>Workspace</h3>
        <div class="archetype">${data.workspace.archetype.replace(/_/g, " ")}</div>
        <div class="stat-row"><span class="k">Load now</span><span class="v mono">${ws.kw.toFixed(1)} kW</span></div>
        <div class="stat-row"><span class="k">Occupancy</span><span class="v mono">${(ws.occupancy_frac * 100).toFixed(0)}%</span></div>
        <div class="stat-row"><span class="k">HVAC</span><span class="v mono">${ws.hvac_kw.toFixed(1)} kW</span></div>
        <div class="stat-row"><span class="k">Computers</span><span class="v mono">${ws.computer_kw.toFixed(1)} kW</span></div>
        <div class="stat-row"><span class="k">Solar now</span><span class="v mono">${ws.solar_kw.toFixed(1)} kW</span></div>
        <div class="stat-row"><span class="k">Battery SOC</span><span class="v mono">${(ws.battery_soc * 100).toFixed(0)}%</span></div>
        <div class="stat-row"><span class="k">EVs charging</span><span class="v mono">${ws.ev_count_charging}</span></div>
        <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
      </div>`;
    drawSparkline("sparkCanvas", data.frames.map(fr => fr.workspace.kw));
  } else if (state.selected.kind === "transformer") {
    const g = f.grid;
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>Transformer</h3>
        <div class="archetype">society connection point</div>
        <div class="stat-row"><span class="k">Loading</span><span class="v mono">${g.transformer_kva.toFixed(1)} kVA</span></div>
        <div class="stat-row"><span class="k">Rating</span><span class="v mono">${g.rating_kva} kVA</span></div>
        <div class="stat-row"><span class="k">State</span><span class="v"><span class="pill ${g.state}">${g.state}</span></span></div>
        <div class="stat-row"><span class="k">Curtailed households</span><span class="v mono">${f.society.fairness.curtailed_house_ids.length}</span></div>
        <div class="stat-row"><span class="k">Curtailed this step</span><span class="v mono">${f.society.fairness.total_curtailed_kwh.toFixed(2)} kWh</span></div>
        <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
      </div>`;
    drawSparkline("sparkCanvas", data.frames.map(fr => fr.grid.transformer_kva), data.frames[0].grid.rating_kva);
  } else if (state.selected.kind === "districtSociety") {
    const pair = state.selected.pair;
    const rec = districtRecord(pair), raw = districtRecord(pair, "raw"),
      ai = districtRecord(pair, "ai"), full = districtRecord(pair, "full");
    const t = districtTick();
    const kva = rec.series.kva[t], st = rec.series.state[t];
    const deployed = rec.arm !== "raw";
    const coordKva = raw.summary.peak_kva - ai.summary.peak_kva;
    const stationKva = ai.summary.peak_kva - full.summary.peak_kva;
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>${rec.label}</h3>
        <div class="archetype">${rec.n_households} households &middot; ${deployed ? "running under GridBrain" : "unmanaged"}</div>
        <div class="badges">
          <span class="badge ${deployed ? "on" : ""}">${rec.arm === "full" ? "GridBrain + solar" : rec.arm === "ai" ? "GridBrain" : "No coordination"}</span>
          <span class="badge">EV ${(rec.ev_penetration * 100).toFixed(0)}%</span>
          <span class="badge">Solar ${(rec.solar_penetration * 100).toFixed(0)}%</span>
        </div>
        <div class="stat-row"><span class="k">Loading now</span><span class="v mono">${kva.toFixed(1)} kVA</span></div>
        <div class="stat-row"><span class="k">Rating</span><span class="v mono">${rec.rating_kva} kVA</span></div>
        <div class="stat-row"><span class="k">State</span><span class="v"><span class="pill ${st}">${st}</span></span></div>
        <div class="stat-row"><span class="k">Peak today</span><span class="v mono">${rec.summary.peak_kva.toFixed(1)} kVA (${(rec.summary.peak_frac * 100).toFixed(0)}%)</span></div>
        <div class="stat-row"><span class="k">Trips today</span><span class="v mono" style="color:${rec.summary.tripped_ticks ? "var(--tripped)" : "var(--ok)"}">${rec.summary.tripped_ticks}</span></div>
        <div class="stat-row"><span class="k">Unserved energy</span><span class="v mono" style="color:${rec.summary.unserved_kwh > 0 ? "var(--tripped)" : "var(--ok)"}">${rec.summary.unserved_kwh.toFixed(1)} kWh</span></div>
        <button class="deploy-btn ${deployed ? "undo" : ""}" data-deploy="${pair}">
          ${deployed ? "Remove GridBrain from this society" : "Deploy GridBrain here"}
        </button>
        <div class="cost-box">
          <h4>Matched-triplet proof</h4>
          <div class="stat-row"><span class="k">Seed</span><span class="v mono">${raw.seed} &rarr; ${full.seed}</span></div>
          <div class="stat-row"><span class="k">Households</span><span class="v mono">${raw.n_households} &rarr; ${full.n_households}</span></div>
          <div class="stat-row"><span class="k">EV penetration</span><span class="v mono">${raw.ev_penetration} &rarr; ${full.ev_penetration}</span></div>
          <div class="stat-row"><span class="k">Transformer rating</span><span class="v mono">${raw.rating_kva} &rarr; ${full.rating_kva}</span></div>
          <div class="note">Both sides of that toggle are real, separately simulated runs of this same society. Every input above is identical between them — only the control flags differ. That is what makes this a controlled comparison rather than a demo.</div>
        </div>
        <div class="save-box">
          <h4>Attribution for this society</h4>
          <div class="stat-row"><span class="k">Coordination alone</span><span class="v mono" style="color:var(--accent)">${coordKva.toFixed(1)} kVA</span></div>
          <div class="stat-row"><span class="k">Solar station adds</span><span class="v mono" style="color:var(--gold)">${stationKva.toFixed(1)} kVA</span></div>
          <div class="note">Coordination costs nothing to install. The station is real capex. Reported separately because a third run (coordination without the station) exists for every society.</div>
        </div>
        <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
      </div>`;
    drawSparkline("sparkCanvas", rec.series.kva, rec.rating_kva);
  } else if (state.selected.kind === "solarstation") {
    const stepH = (data.meta.interval_minutes || 15) / 60;
    let kwhToday = 0, kwhSoFar = 0;
    data.frames.forEach((fr, i) => {
      const v = (fr.society.community_solar_kw || 0) * stepH;
      kwhToday += v;
      if (i <= state.frameIdx) kwhSoFar += v;
    });
    const nowKw = f.society.community_solar_kw || 0;
    const rooftopNow = f.society.solar_kw || 0;
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>Community solar station</h3>
        <div class="archetype">60 kWp shared array &middot; society-level generation</div>
        <div class="stat-row"><span class="k">Output now</span><span class="v mono">${nowKw.toFixed(1)} kW</span></div>
        <div class="stat-row"><span class="k">Generated so far today</span><span class="v mono">${kwhSoFar.toFixed(0)} kWh</span></div>
        <div class="stat-row"><span class="k">Full-day generation</span><span class="v mono">${kwhToday.toFixed(0)} kWh</span></div>
        <div class="stat-row"><span class="k">All rooftop panels combined, now</span><span class="v mono">${rooftopNow.toFixed(1)} kW</span></div>
        <div class="cost-box">
          <h4>Where this energy goes</h4>
          <div class="note">The station feeds the society's connection point, so its output offsets the whole society's draw before the transformer sees it — every serviced flat benefits, whether or not it has its own rooftop panels. Residents can still add individual rooftop solar on top of this; those arrays are simulated separately per house.</div>
        </div>
        <div class="save-box">
          <h4>What it does not do</h4>
          <div class="note">It generates nothing after sunset, so it cannot shave the evening transformer peak by itself. Its real value is daytime cost, which is why the Coordinator retimes flexible load into daylight rather than just installing panels. Evening peak still needs curtailment today, storage later.</div>
        </div>
        <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
      </div>`;
    drawSparkline("sparkCanvas", data.frames.map(fr => fr.society.community_solar_kw || 0));
  } else if (state.selected.kind === "colonyHouse") {
    const ref = colonyRefs.find(r => r.key === state.selected.key);
    const meta = ref.data.houses[state.selected.id], cf = colonyFrame(ref.key), hs = cf.houses[state.selected.id];
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>House #${meta.id} — ${ref.label}</h3>
        <div class="archetype">${meta.archetype.replace(/_/g, " ")} &middot; ${meta.floors} floor${meta.floors > 1 ? "s" : ""}</div>
        <div class="badges">${hs.curtailed ? `<span class="badge" style="color:var(--tripped)">Curtailed</span>` : ""}</div>
        <div class="stat-row"><span class="k">Load now</span><span class="v mono">${hs.kw.toFixed(2)} kW</span></div>
        <div class="stat-row"><span class="k">Occupants</span><span class="v mono">${hs.occupancy}</span></div>
        <div class="stat-row"><span class="k">AC</span><span class="v mono">${hs.ac_on ? "on" : "off"}</span></div>
        <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
      </div>`;
    drawSparkline("sparkCanvas", ref.data.frames.map(fr => fr.houses[meta.id].kw));
  } else if (state.selected.kind === "colonyTransformer") {
    const ref = colonyRefs.find(r => r.key === state.selected.key), cf = colonyFrame(ref.key), g = cf.grid;
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>${ref.label} transformer</h3>
        <div class="archetype">colony feeder node</div>
        <div class="stat-row"><span class="k">Loading</span><span class="v mono">${g.transformer_kva.toFixed(1)} kVA</span></div>
        <div class="stat-row"><span class="k">Rating</span><span class="v mono">${g.rating_kva} kVA</span></div>
        <div class="stat-row"><span class="k">State</span><span class="v"><span class="pill ${g.state}">${g.state}</span></span></div>
        <div class="stat-row"><span class="k">Curtailed households</span><span class="v mono">${cf.society.fairness.curtailed_house_ids.length}</span></div>
        <canvas class="spark" id="sparkCanvas" width="280" height="72"></canvas>
      </div>`;
    drawSparkline("sparkCanvas", ref.data.frames.map(fr => fr.grid.transformer_kva), ref.data.frames[0].grid.rating_kva);
  } else if (state.selected.kind === "gridbrain") {
    const fa = frame(), fb = colonyFrame("society_b"), fc = colonyFrame("society_c");
    el.innerHTML = `
      <div class="inspector-house ${freshClass}">
        <h3>GridBrain</h3>
        <div class="archetype">colony coordination hub</div>
        <div class="stat-row"><span class="k">Societies watched</span><span class="v mono">3</span></div>
        <div class="stat-row"><span class="k">Households sub-metered</span><span class="v mono">${data.houses.length + (colonyRefs[1]?.data.houses.length || 0) + (colonyRefs[2]?.data.houses.length || 0)}</span></div>
        <div class="stat-row"><span class="k">Society A</span><span class="v"><span class="pill ${fa.grid.state}">${fa.grid.state}</span></span></div>
        ${fb ? `<div class="stat-row"><span class="k">Society B</span><span class="v"><span class="pill ${fb.grid.state}">${fb.grid.state}</span></span></div>` : ""}
        ${fc ? `<div class="stat-row"><span class="k">Society C</span><span class="v"><span class="pill ${fc.grid.state}">${fc.grid.state}</span></span></div>` : ""}
        <div class="note" style="margin-top:9px;">See the GridBrain tab for the live decision ledger — sourced directly from each society's real, already-simulated sub-meter and curtailment state.</div>
      </div>`;
  }
}

function renderEvents() {
  const el = document.getElementById("eventsList");
  const events = state.data.events || [];
  if (!events.length) { el.innerHTML = '<div class="inspector-empty">No events in this scenario.</div>'; return; }
  el.innerHTML = events.map(e => {
    const active = frame().events_active.includes(e.id);
    return `<div class="event-row" style="${active ? 'border-color:var(--accent-glow)' : ''}"><span>${e.type.replace(/_/g, " ")}</span><span class="t mono">${minToClock(e.start_min)} +${(e.duration_min / 60).toFixed(1)}h</span></div>`;
  }).join("");
}

// ------------------------------------------------------------ interaction
// Selection uses screen-space projected anchors (not mesh raycasting) so hit
// targets stay generous and reliable on both mouse and touch regardless of
// how visually small a building is at a given zoom level.
const _v = new THREE.Vector3();
function worldToScreen(x, y, z) {
  camera.updateMatrixWorld();
  _v.set(x, y, z).project(camera);
  const rect = renderer.domElement.getBoundingClientRect();
  return { x: rect.left + (_v.x * 0.5 + 0.5) * rect.width, y: rect.top + (-_v.y * 0.5 + 0.5) * rect.height, visible: _v.z < 1 };
}
const DISTRICT_ANCHORS = new Set(["districtSociety", "districtBrain"]);
function pickAt(clientX, clientY) {
  let best = null, bestD = Infinity;
  const inDistrict = state.cam === "district";
  for (const a of anchors) {
    // the district sits ~1000 units behind the society scale and still
    // projects onto the screen from there — gate hit-testing by which
    // scale is actually being displayed
    if (DISTRICT_ANCHORS.has(a.type) !== inDistrict) continue;
    const s = worldToScreen(a.pos.x, a.pos.y, a.pos.z);
    if (!s.visible) continue;
    const d = Math.hypot(clientX - s.x, clientY - s.y);
    if (d < a.r && d < bestD) { bestD = d; best = a; }
  }
  return best;
}

let downPos = null, isTouch = false;
renderer.domElement.addEventListener("pointerdown", (e) => { downPos = { x: e.clientX, y: e.clientY }; isTouch = e.pointerType === "touch"; });
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downPos) return;
  const moved = Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y);
  downPos = null;
  if (moved > (isTouch ? 18 : 10)) return; // treat as a drag/orbit, not a tap
  const hit = pickAt(e.clientX, e.clientY);
  if (hit) {
    if (hit.type === "house") state.selected = { kind: "house", id: hit.id };
    else if (hit.type === "colonyHouse") state.selected = { kind: "colonyHouse", id: hit.id, key: hit.key };
    else if (hit.type === "colonyTransformer") state.selected = { kind: "colonyTransformer", key: hit.key };
    else if (hit.type === "gridbrain") state.selected = { kind: "gridbrain" };
    else if (hit.type === "districtSociety") state.selected = { kind: "districtSociety", pair: hit.pair };
    else if (hit.type === "districtBrain") state.selected = { kind: "gridbrain" };
    else state.selected = { kind: hit.type };
    renderInspector();
    setRailTab("live");
    if (window.matchMedia("(max-width:860px)").matches) setRailOpen(true);
  }
});
renderer.domElement.addEventListener("pointermove", (e) => {
  if (downPos) return;
  const hit = pickAt(e.clientX, e.clientY);
  state.hover = hit;
  renderer.domElement.style.cursor = hit ? "pointer" : "grab";
});
renderer.domElement.addEventListener("pointerleave", () => { state.hover = null; renderer.domElement.style.cursor = "grab"; });

// ------------------------------------------------------------------ UI wiring
function buildScenarioButtons() {
  const g = document.getElementById("scenarioGroup"); g.innerHTML = "";
  Object.keys(SCENARIO_LABELS).forEach((key) => {
    const b = document.createElement("button");
    b.textContent = SCENARIO_LABELS[key];
    b.className = key === state.scenarioKey ? "active" : "";
    b.onclick = () => setScenario(key);
    g.appendChild(b);
  });
}

async function setScenario(key, { fromWhatif = false } = {}) {
  document.getElementById("loadingHint").style.display = "flex";
  state.scenarioKey = key;
  if (!fromWhatif) {
    state.whatifEv = null;
    document.querySelectorAll("#whatifEvGroup button, #whatifAiGroup button").forEach(b => b.classList.remove("active"));
    document.getElementById("whatifCapex").textContent = "Pick an EV level below to watch the AI Coordinator hold the line in real, pre-simulated data — not a fudge-factor slider.";
  }
  const data = await loadScenario(key);
  state.data = data;
  state.maxKw = computeMaxKw(data);
  applyScenarioMood();
  if (railActive("analysis")) renderAnalysisTab();
  state.frameIdx = Math.min(state.frameIdx, data.frames.length - 1);
  state.selected = null;
  document.querySelectorAll("#scenarioGroup button").forEach(b => b.classList.toggle("active", !fromWhatif && b.textContent === SCENARIO_LABELS[key]));
  document.getElementById("scrub").max = data.frames.length - 1;
  buildWorld(data);
  if (colonyRefs.length) {
    addColonyTraffic(colonyRefs[1].cols, colonyRefs[1].rows, COLONY.society_b.offset, 21);
    addColonyTraffic(colonyRefs[2].cols, colonyRefs[2].rows, COLONY.society_c.offset, 22);
  }
  renderEvents();
  applyFrame();
  document.getElementById("loadingHint").style.display = "none";
}

// ------------------------------------------------------------- what-if
// Six real engine outputs (see aethergrid/worldsim/generate_whatif.py):
// three EV-penetration levels, each with the real AI Coordinator on and
// off. Not a live re-simulation, not a fudge-factor slider -- the slider
// snaps between real, distinct, pre-computed simulation runs.
const whatifPeakCache = {};
async function whatifPeak(ev, ai) {
  const k = whatifKey(ev, ai);
  if (!(k in whatifPeakCache)) {
    const d = await loadScenario(k);
    whatifPeakCache[k] = Math.max(...d.frames.map(f => f.grid.transformer_kva));
  }
  return whatifPeakCache[k];
}
function whatifSceneKey(ev, ai, sync) {
  if (sync && ai) return `whatif_ev${ev}_ai_solarsync`;
  return whatifKey(ev, ai);
}
async function setWhatIf(ev, ai, sync) {
  state.whatifEv = ev; state.whatifAi = ai; state.whatifSync = sync && ai;
  document.querySelectorAll("#whatifEvGroup button").forEach(b => b.classList.toggle("active", +b.dataset.ev === ev));
  document.querySelectorAll("#whatifAiGroup button").forEach(b => b.classList.toggle("active", (b.dataset.ai === "1") === ai));
  document.querySelectorAll("#whatifSyncGroup button").forEach(b => b.classList.toggle("active", (b.dataset.sync === "1") === state.whatifSync));
  document.getElementById("whatifSyncGroup").classList.toggle("disabled", !ai);
  await setScenario(whatifSceneKey(ev, ai, state.whatifSync), { fromWhatif: true });
  const [aiPeak, noaiPeak] = await Promise.all([whatifPeak(ev, true), whatifPeak(ev, false)]);
  const deferredKva = Math.max(0, noaiPeak - aiPeak);
  const rupee = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  const capexEl = document.getElementById("whatifCapex");
  if (deferredKva < 0.5) {
    capexEl.textContent = "No protection needed at this setting — transformer stays comfortably under rating either way.";
  } else {
    capexEl.innerHTML = `Real difference at this setting: <b>${deferredKva.toFixed(1)} kVA</b> held back by the Coordinator &rarr; illustrative capex deferred <b>₹${rupee.format(Math.round(deferredKva * CAPEX_PER_KVA))}</b> (same ₹1,200/kVA default as the commercial ROI calculator).`;
  }
  if (state.whatifSync) solarStats(ev).then(() => renderInspector());
  if (document.querySelector('.rail-tab[data-tab="solar"]').classList.contains("active")) renderSolarTab();
}
document.getElementById("whatifEvGroup").addEventListener("click", (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  setWhatIf(+btn.dataset.ev, state.whatifEv === null ? true : state.whatifAi, state.whatifSync);
});
document.getElementById("whatifAiGroup").addEventListener("click", (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  const ai = btn.dataset.ai === "1";
  setWhatIf(state.whatifEv ?? WHATIF_EV_LEVELS[0], ai, state.whatifSync);
});
document.getElementById("whatifSyncGroup").addEventListener("click", (e) => {
  const btn = e.target.closest("button"); if (!btn || !state.whatifAi) return;
  setWhatIf(state.whatifEv ?? WHATIF_EV_LEVELS[0], true, btn.dataset.sync === "1");
});

document.getElementById("camGroup").addEventListener("click", (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  state.cam = btn.dataset.cam;
  document.querySelectorAll("#camGroup button").forEach(b => { b.classList.toggle("active", b === btn); b.classList.toggle("alt", b === btn && b.dataset.cam === "top"); });
  camera = state.cam === "top" ? orthoCam : perspCam;
  controls.object = camera;
  controls.enableRotate = state.cam !== "top";
  renderPass.camera = camera;
  scene.fog.density = FOG_DENSITY[state.cam] ?? FOG_DENSITY.orbit;
  setCamFarForScale();
  applyScenarioMood();
  setDistrictVisible(state.cam === "district");
  if (state.cam === "colony" && gridBrain) flyToSociety("colony");
  else if (state.cam === "district") flyToDistrict();
  else if (state.cam === "orbit" && state.data) flyToSociety("society_a", false);
  onResize();
});

// The district sits ~1000 world units out and needs the camera another ~550
// back to frame all 24 societies, so the default 800-unit far plane clips it
// away entirely. Pushed out only for that scale, since a far plane 3x further
// costs depth precision the society view has no reason to pay for.
// near is raised alongside far at district scale: a 0.1 near plane against a
// 2600 far plane leaves almost no depth precision (everything lands within
// 0.001 of the far end of the buffer, which is how you get z-fighting). At
// district scale nothing is ever closer than ~100 units, so 5 is safe.
const CAM_RANGE = {
  orbit: [0.1, 800], top: [0.1, 800], colony: [0.1, 800], district: [5, 2600],
};
function setCamFarForScale() {
  const [near, far] = CAM_RANGE[state.cam] ?? CAM_RANGE.orbit;
  for (const c of [perspCam, orthoCam]) { c.near = near; c.far = far; c.updateProjectionMatrix(); }
}

// The district lives ~1000 units away from the society/colony scale, so it
// is hidden unless you're actually looking at it — 24 societies of geometry
// is not worth culling through on every society-scale frame.
function setDistrictVisible(on) {
  if (districtGroup) districtGroup.visible = on;
  if (worldGroup) worldGroup.visible = !on;
  for (const r of colonyRefs) if (r.root) r.root.visible = !on;
  if (gridBrain) {
    gridBrain.group.visible = !on;
    for (const b of gridBrain.beams) { b.line.visible = !on; b.pulse.visible = !on; }
  }
  if (on) applyDistrictFrame();
}
function flyToDistrict() {
  const rows = Math.ceil(districtRefs.length / DISTRICT_COLS);
  const cz = DISTRICT_ORIGIN.z + (rows - 1) * DISTRICT_SPACING_Z / 2;
  // frame the whole grid: 6 columns spans ~520 units, so pull back far
  // enough that all 24 societies are in shot at once — the entire point of
  // this view is seeing the managed and unmanaged cohorts side by side
  const spanX = (DISTRICT_COLS - 1) * DISTRICT_SPACING_X + 80;
  const fov = (perspCam.fov * Math.PI) / 180;
  const aspect = Math.max(0.6, perspCam.aspect);
  const distForWidth = (spanX / 2) / Math.tan((fov / 2) * aspect);
  const distForDepth = ((rows - 1) * DISTRICT_SPACING_Z + 90) / 2 / Math.tan(fov / 2);
  const d = Math.max(distForWidth, distForDepth) * 1.15;
  startCamTween(new THREE.Vector3(DISTRICT_ORIGIN.x, d * 0.72, cz + d * 0.78), new THREE.Vector3(DISTRICT_ORIGIN.x, 0, cz));
}

// shared camera-framing helper — used by the topbar cam buttons and by the
// per-society quick-jump rows in the GridBrain tab
function societyCenterAndDist(houses, offset) {
  const cols = Math.max(...houses.map(h => h.grid_x)) + 1, rows = Math.max(...houses.map(h => h.grid_z)) + 1;
  return { cx: offset.x + (cols - 1) * TILE / 2, cz: offset.z + (rows - 1) * TILE / 2, dist: Math.max(cols, rows) * TILE * 0.6 };
}
function flyToSociety(target, switchMode = true) {
  if (target === "colony") {
    if (!gridBrain) return;
    const hub = gridBrain.hubPos;
    startCamTween(new THREE.Vector3(hub.x, 210, hub.z + 260), new THREE.Vector3(hub.x, 10, hub.z));
    return;
  }
  let cx, cz, dist;
  if (target === "society_a") { if (!state.data) return; ({ cx, cz, dist } = societyCenterAndDist(state.data.houses, { x: 0, z: 0 })); }
  else {
    const ref = colonyRefs.find(r => r.key === target); if (!ref) return;
    ({ cx, cz, dist } = societyCenterAndDist(ref.data.houses, COLONY[target].offset));
  }
  startCamTween(new THREE.Vector3(cx - dist * 0.72, dist * 0.62, cz + dist * 0.72), new THREE.Vector3(cx, 0.6, cz));
  if (switchMode && state.cam !== "orbit") {
    state.cam = "orbit"; camera = perspCam; controls.object = camera; controls.enableRotate = true; renderPass.camera = camera;
    scene.fog.density = FOG_DENSITY.orbit;
    document.querySelectorAll("#camGroup button").forEach(b => b.classList.toggle("active", b.dataset.cam === "orbit"));
    onResize();
  }
}

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
playBtn.addEventListener("click", () => { state.playing = !state.playing; playBtn.innerHTML = state.playing ? "&#10074;&#10074;" : "&#9654;"; });

const scrub = document.getElementById("scrub");
scrub.addEventListener("input", () => { state.frameIdx = +scrub.value; applyFrame(); });

function setRailOpen(open) {
  document.getElementById("rail").classList.toggle("open", open);
  document.getElementById("railScrim").classList.toggle("open", open);
}
document.getElementById("railToggle").addEventListener("click", () => setRailOpen(!document.getElementById("rail").classList.contains("open")));
document.getElementById("railScrim").addEventListener("click", () => setRailOpen(false));
document.getElementById("railClose").addEventListener("click", () => setRailOpen(false));

document.getElementById("themePicker").addEventListener("click", (e) => {
  const btn = e.target.closest("button"); if (!btn) return;
  document.documentElement.setAttribute("data-theme", btn.dataset.theme);
  document.querySelectorAll("#themePicker button").forEach(b => b.classList.toggle("active", b === btn));
});

function setRailTab(tab) {
  document.querySelectorAll(".rail-tab").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  document.getElementById("tabLive").classList.toggle("hidden", tab !== "live");
  document.getElementById("tabBrain").classList.toggle("hidden", tab !== "brain");
  document.getElementById("tabSolar").classList.toggle("hidden", tab !== "solar");
  document.getElementById("tabDistrict").classList.toggle("hidden", tab !== "district");
  document.getElementById("tabAnalysis").classList.toggle("hidden", tab !== "analysis");
  document.getElementById("tabAbout").classList.toggle("hidden", tab !== "about");
  if (tab === "brain") { renderNodeMap(); renderLedger(); }
  if (tab === "solar") renderSolarTab();
  if (tab === "district") renderDistrictTab();
  if (tab === "analysis") renderAnalysisTab();
}
document.querySelectorAll(".rail-tab").forEach(b => b.addEventListener("click", () => setRailTab(b.dataset.tab)));

// -------------------------------------------------------------- presentation
function setPresenting(on) {
  document.body.classList.toggle("presenting", on);
  document.getElementById("presentBtn").classList.toggle("active", on);
}
document.getElementById("presentBtn").addEventListener("click", () => setPresenting(!document.body.classList.contains("presenting")));
window.addEventListener("keydown", (e) => { if (e.key === "p" || e.key === "P") setPresenting(!document.body.classList.contains("presenting")); });

// -------------------------------------------------------------- scripted tour
// Beat-matched to the 60-second world-sim pitch in PITCH_PREP.md. Fixed
// timings, fixed scenario/seed data -- reproduces the same sequence every
// run, and never leaves interaction permanently disabled if interrupted.
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
// ------------------------------------------------------------------ resize
function onResize() {
  const rect = stageEl.getBoundingClientRect();
  renderer.setSize(rect.width, rect.height);
  composer.setSize(rect.width, rect.height);
  bloomPass.setSize(rect.width, rect.height);
  perspCam.aspect = rect.width / rect.height; perspCam.updateProjectionMatrix();
  orthoCam.updateProjectionMatrix();
}
new ResizeObserver(onResize).observe(stageEl);

// -------------------------------------------------------------- main loop
let lastTick = performance.now();
let lastRealTick = performance.now();
function loop(now) {
  stepCamTween(now);
  controls.update();
  const dtSec = Math.min(0.1, (now - lastRealTick) / 1000);
  lastRealTick = now;
  for (const c of clouds) c.position.x += c.userData.speed * 0.01;
  updateTraffic(dtSec);
  updateGridBrainVisuals(dtSec, now);
  const dt = now - lastTick;
  if (state.playing && state.data && dt > Math.max(30, 220 / state.speed)) {
    lastTick = now;
    state.frameIdx = (state.frameIdx + 1) % state.data.frames.length;
    scrub.value = state.frameIdx;
    applyFrame();
  } else if (state.data) {
    updateAnimatedOnly();
  }
  composer.render();
  requestAnimationFrame(loop);
}

function updateAnimatedOnly() {
  const f = frame();
  for (const meta of state.data.houses) {
    const g = houseObjs.get(meta.id); if (!g) continue;
    const hs = f.houses[meta.id], dyn = g.userData.dyn;
    if (dyn.evRing && hs.ev_state === "charging") dyn.evRing.material.opacity = 0.45 + 0.4 * Math.sin(performance.now() / 220);
  }
  if (transformerObj && f.grid.state === "TRIPPED") {
    const flashing = Math.sin(performance.now() / 130) > 0;
    transformerObj.userData.dyn.barFill.material.color.set(flashing ? 0xffffff : 0xef4444);
  }
}

// ------------------------------------------------------------------- boot
// ============================================================ DISTRICT
// 24 societies on one shared feeder, each simulated at the same depth as
// Society A (aethergrid/worldsim/generate_district.py). 6 run under
// GridBrain; 18 run unmanaged and genuinely trip.
//
// Each society was simulated as a matched TRIPLET -- raw / ai / full --
// sharing seed, size, EV and solar penetration and transformer rating, so
// (ai - raw) is the value of coordination alone at zero capex and
// (full - ai) is what the solar station adds. Only the displayed arm is
// rendered; the others are real datasets sitting behind the "deploy
// GridBrain here" toggle.
//
// Rendering is LOD'd out of necessity: ~1,300 detailed house groups is not
// a drawable scene, so each society's houses are one InstancedMesh and the
// per-tick visual channel is the society's own real aggregate load.
const DISTRICT_ORIGIN = { x: 0, z: -980 };
const DISTRICT_COLS = 6, DISTRICT_SPACING_X = 104, DISTRICT_SPACING_Z = 92;
let districtData = null, districtRefs = [], districtGroup = null, districtBrainPos = null;

async function loadDistrictData() {
  const res = await fetch("../viz/data/district.json");
  districtData = await res.json();
  // which arm each society is currently showing: the deployed six start on
  // their full package, everyone else starts on raw (nothing deployed).
  // `in_cohort` is only ever set on the `full` record, so read it from there
  // rather than from whichever arm happens to come first in the file.
  for (const s of districtData.societies) {
    if (s.arm !== "full") continue;
    if (!(s.pair in state.districtArm)) state.districtArm[s.pair] = s.in_cohort ? "full" : "raw";
  }
}
function districtPairs() {
  const seen = [];
  for (const s of districtData.societies) if (!seen.includes(s.pair)) seen.push(s.pair);
  return seen;
}
function districtRecord(pair, arm) {
  return districtData.societies.find(s => s.pair === pair && s.arm === (arm || state.districtArm[pair]));
}
function districtTick() { return Math.min(state.frameIdx, 95); }

function labelSprite(text, color = "#dfe9f5", px = 44) {
  const c = document.createElement("canvas");
  c.width = 512; c.height = 96;
  const g = c.getContext("2d");
  g.font = `700 ${px}px Rajdhani, sans-serif`;
  g.textAlign = "center"; g.textBaseline = "middle";
  // dark plate behind the text: over a bright daytime sky a pure glow label
  // washed out completely, and these names are how you identify a society
  const tw = g.measureText(text).width;
  g.fillStyle = "rgba(4,8,14,0.72)";
  g.fillRect(256 - tw / 2 - 14, 48 - px * 0.72, tw + 28, px * 1.44);
  g.shadowColor = "rgba(0,0,0,0.95)"; g.shadowBlur = 6;
  g.fillStyle = color;
  g.fillText(text, 256, 48);
  const t = new THREE.CanvasTexture(c);
  t.anisotropy = 4;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false, depthTest: false }));
  sp.scale.set(46, 8.6, 1);
  return sp;
}

function buildDistrictSociety(pair, idx) {
  const rec = districtRecord(pair, "raw"); // static geometry is arm-independent
  const grp = new THREE.Group();
  const col = idx % DISTRICT_COLS, row = Math.floor(idx / DISTRICT_COLS);
  const x = DISTRICT_ORIGIN.x + (col - (DISTRICT_COLS - 1) / 2) * DISTRICT_SPACING_X;
  const z = DISTRICT_ORIGIN.z + row * DISTRICT_SPACING_Z;
  grp.position.set(x, 0, z);

  // pad
  const pad = new THREE.Mesh(new THREE.PlaneGeometry(78, 62), new THREE.MeshStandardMaterial({ color: 0x070c15, roughness: 1 }));
  pad.rotation.x = -Math.PI / 2; pad.position.y = -0.02; pad.receiveShadow = true;
  grp.add(pad);

  // state rim -- the single clearest "is this society in trouble" signal
  const rim = new THREE.Mesh(new THREE.RingGeometry(43, 47, 4, 1),
    new THREE.MeshBasicMaterial({ color: 0x2fe6a0, transparent: true, opacity: 0.5, side: THREE.DoubleSide }));
  rim.rotation.x = -Math.PI / 2; rim.rotation.z = Math.PI / 4; rim.position.y = 0.02;
  grp.add(rim);

  // houses as ONE instanced mesh -- real household count, real grid layout
  const n = rec.n_households;
  const cols = 10, sp = 6.2;
  const houseMat = new THREE.MeshStandardMaterial({ color: 0x2a3446, roughness: 0.85, emissive: new THREE.Color(0x39e0ff), emissiveIntensity: 0.1 });
  const inst = new THREE.InstancedMesh(GEO.boxUnit, houseMat, n);
  inst.castShadow = false; inst.receiveShadow = false;
  const m4 = new THREE.Matrix4();
  const rws = Math.ceil(n / cols);
  for (let i = 0; i < n; i++) {
    const gx = (i % cols - (cols - 1) / 2) * sp;
    const gz = (Math.floor(i / cols) - (rws - 1) / 2) * sp;
    const h = 3.4 + hash01(i * 7.3 + idx) * 3.2;
    m4.makeScale(3.6, h, 3.2);
    m4.setPosition(gx, h / 2, gz);
    inst.setMatrixAt(i, m4);
  }
  inst.instanceMatrix.needsUpdate = true;
  grp.add(inst);

  // transformer pylon + loading bar
  const tx = new THREE.Group();
  tx.position.set(34, 0, -24);
  const body = new THREE.Mesh(GEO.cyl, wallMat(0x565f78, 0.55));
  body.scale.set(1.6, 4.2, 1.6); body.position.y = 2.1;
  tx.add(body);
  const barTrack = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x141822 }));
  barTrack.scale.set(1.1, 15, 1.1); barTrack.position.set(4.6, 7.5, 0);
  tx.add(barTrack);
  const barFill = new THREE.Mesh(GEO.boxUnit, new THREE.MeshStandardMaterial({ color: 0x2fe6a0, emissive: 0x0d3a2a, emissiveIntensity: 0.7 }));
  barFill.scale.set(0.85, 1, 0.85); barFill.position.set(4.6, 0.5, 0);
  tx.add(barFill);
  const beacon = new THREE.PointLight(0x2fe6a0, 1.2, 60, 2);
  beacon.position.set(0, 7, 0);
  tx.add(beacon);
  grp.add(tx);

  // name label + a managed/unmanaged badge label under it
  const name = labelSprite(rec.label, "#dfe9f5", 44);
  name.position.set(0, 26, 0);
  grp.add(name);
  const badge = labelSprite("", "#8b95ab", 34);
  badge.position.set(0, 20, 0);
  badge.scale.set(40, 7.5, 1);
  grp.add(badge);

  // gold canopy ring marking a society GridBrain is actually deployed on
  // #24 data-path badge, in the world rather than buried in the About tab:
  // states plainly which data route this society is on. Every society here is
  // Path A (its own billing sub-meters) -- said out loud so the honesty claim
  // is visible where the society is, not only in a tab nobody opens.
  const dpath = labelSprite("PATH A · OWN SUB-METERS", "#5f7290", 26);
  dpath.position.set(0, 15.5, 0);
  dpath.scale.set(34, 6.4, 1);
  grp.add(dpath);

  const canopy = new THREE.Mesh(new THREE.TorusGeometry(30, 0.55, 6, 40),
    new THREE.MeshBasicMaterial({ color: 0xe8b23d, transparent: true, opacity: 0 }));
  canopy.rotation.x = -Math.PI / 2; canopy.position.y = 0.5;
  grp.add(canopy);

  districtGroup.add(grp);
  const worldPos = new THREE.Vector3(x, 7, z);
  anchors.push({ type: "districtSociety", pair, pos: worldPos.clone(), r: 44 });
  return { pair, group: grp, inst, houseMat, rim, barFill, beacon, canopy, badge, worldPos, label: rec.label };
}

function buildDistrict() {
  districtGroup = new THREE.Group();
  scene.add(districtGroup);
  const pairs = districtPairs();
  districtRefs = pairs.map((p, i) => buildDistrictSociety(p, i));

  // GridBrain hub above the district, beaming only to societies it runs
  const rows = Math.ceil(pairs.length / DISTRICT_COLS);
  districtBrainPos = new THREE.Vector3(DISTRICT_ORIGIN.x, 118, DISTRICT_ORIGIN.z + (rows - 1) * DISTRICT_SPACING_Z / 2);
  const hub = new THREE.Group();
  hub.position.copy(districtBrainPos);
  hub.add(new THREE.Mesh(new THREE.IcosahedronGeometry(9, 1), new THREE.MeshBasicMaterial({ color: 0x39e0ff, wireframe: true, transparent: true, opacity: 0.5 })));
  hub.add(new THREE.Mesh(new THREE.IcosahedronGeometry(5.5, 2), new THREE.MeshStandardMaterial({ color: 0x081018, emissive: 0x39e0ff, emissiveIntensity: 0.8 })));
  hub.add(new THREE.PointLight(0x39e0ff, 2.2, 400, 2));
  const hubLabel = labelSprite("GRIDBRAIN", "#39e0ff", 40);
  hubLabel.position.set(0, 16, 0); hubLabel.scale.set(52, 9.8, 1);
  hub.add(hubLabel);
  districtGroup.add(hub);
  anchors.push({ type: "districtBrain", pos: districtBrainPos.clone(), r: 50 });

  // one beam per society; visibility is driven per-tick by whether that
  // society is currently running under GridBrain
  for (const ref of districtRefs) {
    const line = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([districtBrainPos, ref.worldPos]),
      new THREE.LineBasicMaterial({ color: 0x39e0ff, transparent: true, opacity: 0 }));
    districtGroup.add(line);
    const pulse = new THREE.Mesh(new THREE.SphereGeometry(1.5, 8, 8), new THREE.MeshBasicMaterial({ color: 0x9beeff, transparent: true, opacity: 0 }));
    districtGroup.add(pulse);
    ref.beam = { line, pulse, t: hash01(districtRefs.indexOf(ref) * 5.1) };
  }
  districtGroup.visible = false;
}

function applyDistrictFrame() {
  if (!districtRefs.length || !districtGroup.visible) return;
  const t = districtTick();
  for (const ref of districtRefs) {
    const rec = districtRecord(ref.pair);
    const kva = rec.series.kva[t], st = rec.series.state[t], kw = rec.series.total_kw[t];
    const frac = clamp(kva / rec.rating_kva, 0, 1.35);
    const col = new THREE.Color(stateColorHex[st] || 0x8b95ab);
    const stressed = st === "BREACH" || st === "TRIPPED" || st === "CRITICAL";
    const flashing = stressed && Math.sin(performance.now() / (st === "TRIPPED" ? 130 : 430)) > 0;

    ref.rim.material.color.copy(col);
    ref.rim.material.opacity = stressed ? (flashing ? 0.95 : 0.45) : 0.28;
    ref.barFill.scale.y = Math.max(0.4, Math.min(1, frac) * 15);
    ref.barFill.position.y = ref.barFill.scale.y / 2 + 0.5;
    ref.barFill.material.color.copy(flashing ? new THREE.Color(0xffffff) : col);
    ref.barFill.material.emissive.copy(col).multiplyScalar(0.55);
    ref.beacon.color.copy(col);
    ref.beacon.intensity = lerp(0.5, 3.0, clamp(frac, 0, 1)) + (flashing ? 2 : 0);

    // window glow across the whole society tracks its real aggregate load
    const loadNorm = clamp(kw / (rec.n_households * 3.2), 0, 1);
    ref.houseMat.emissive.copy(loadColor(loadNorm * 4, 4));
    ref.houseMat.emissiveIntensity = lerp(0.06, 0.42, loadNorm);

    const managed = rec.arm !== "raw";
    ref.canopy.material.opacity = managed ? 0.55 + 0.2 * Math.sin(performance.now() / 700) : 0;
    ref.badge.material.map.image && setBadge(ref, rec);
    if (ref.beam) {
      ref.beam.line.material.opacity = managed ? 0.32 : 0;
      ref.beam.t = (ref.beam.t + 0.006) % 1;
      ref.beam.pulse.material.opacity = managed ? 0.9 : 0;
      ref.beam.pulse.position.lerpVectors(districtBrainPos, ref.worldPos, ref.beam.t);
    }
  }
}

// badge text only changes when a society's arm changes, so it is redrawn
// on demand rather than every tick
function setBadge(ref, rec) {
  const want = rec.arm === "full" ? "GRIDBRAIN + SOLAR" : rec.arm === "ai" ? "GRIDBRAIN" : "UNMANAGED";
  if (ref._badgeText === want) return;
  ref._badgeText = want;
  ref.badge.material.map.dispose();
  const colr = rec.arm === "raw" ? "#8b95ab" : "#e8b23d";
  const s = labelSprite(want, colr, 34);
  ref.badge.material.map = s.material.map;
  ref.badge.material.needsUpdate = true;
}

// ------------------------------------------------------- district readouts
// Every figure below is summed straight off the real per-society rollups in
// district.json. The only external constants are the illustrative tariff and
// the capex-per-kVA default already used elsewhere in this app.
function districtCohorts() {
  const shown = districtPairs().map(p => districtRecord(p));
  return {
    shown,
    managed: shown.filter(r => r.arm !== "raw"),
    unmanaged: shown.filter(r => r.arm === "raw"),
  };
}
function sumS(rs, k) { return rs.reduce((a, r) => a + r.summary[k], 0); }

// --- shared upstream feeder, computed coincidentally -----------------------
// The feeder carries all 24 societies at once, so its peak is the peak of the
// SUM of the per-tick series -- max_t (sum_i kva_i(t)) -- not the sum of each
// society's own peak. Those are very different numbers: societies peak at
// slightly different times, so summing individual peaks overstates the load
// the feeder actually sees, and would therefore overstate what coordination
// saves. Every society's kVA is derived at the same assumed power factor, so
// they are directly additive here.
const ADOPTION_ORDER_CACHE = {};
function adoptionOrder() {
  // A utility rolls out to its worst-stressed feeders first, so adoption is
  // ordered by how far over its own rating each society runs unmanaged.
  if (!ADOPTION_ORDER_CACHE.list) {
    ADOPTION_ORDER_CACHE.list = districtPairs()
      .map(p => ({ p, frac: districtRecord(p, "raw").summary.peak_frac }))
      .sort((a, b) => b.frac - a.frac).map(o => o.p);
  }
  return ADOPTION_ORDER_CACHE.list;
}
function feederPeakAtAdoption(n, arm = "full") {
  const order = adoptionOrder();
  const adopted = new Set(order.slice(0, n));
  const steps = districtRecord(order[0], "raw").series.kva.length;
  // skip the same warm-up tick the generator excludes from its statistics --
  // the first step evaluates every appliance state machine at once and spikes
  // above the genuine evening peak
  let peak = 0, peakT = districtData.meta.warmup_ticks || 0;
  for (let t = (districtData.meta.warmup_ticks || 0); t < steps; t++) {
    let s = 0;
    for (const p of order) s += districtRecord(p, adopted.has(p) ? arm : "raw").series.kva[t];
    if (s > peak) { peak = s; peakT = t; }
  }
  return { peak, peakT };
}
// a cohort can legitimately be empty (deploy/withdraw everything), so these
// return an em-dash rather than -Infinity / NaN
function worstComfort(rs) { return rs.length ? Math.max(...rs.map(r => r.summary.worst_comfort_dev_c)).toFixed(1) : "—"; }

let adoptionCurve = null;
function updateAdoptionReadout(n) {
  if (!adoptionCurve) return;
  const { curve, cw, ch, cmin, cmax, nSoc } = adoptionCurve;
  const at0 = curve[0], atAll = curve[nSoc];
  const cur = feederPeakAtAdoption(n);
  const saved = at0 - cur.peak;
  const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
  const dot = document.getElementById("adoptionDot");
  if (dot) {
    dot.setAttribute("cx", ((n / nSoc) * cw).toFixed(1));
    dot.setAttribute("cy", (ch - ((cur.peak - cmin) / Math.max(1e-6, cmax - cmin)) * ch).toFixed(1));
  }
  const sl = document.getElementById("adoptionSlider");
  if (sl && +sl.value !== n) sl.value = n;
  set("adCovered", `${n} / ${nSoc}`);
  set("adPct", `${((n / nSoc) * 100).toFixed(0)}%`);
  set("adPeak", `${cur.peak.toFixed(0)} kVA`);
  set("adWas", `was ${at0.toFixed(0)}`);
  set("adHeld", `${saved.toFixed(0)} kVA`);
  set("adHeldPct", `${at0 > 0 ? ((saved / at0) * 100).toFixed(1) : 0}%`);
  const note = document.getElementById("adNote");
  if (note) note.innerHTML = `Coincident peak: <b>the maximum over the day of all ${nSoc} societies' summed load</b>, occurring at ${minToClock(state.data.frames[cur.peakT].t_min)} — not the sum of each society's own peak, which would overstate it because societies peak at different times. Rollout order is worst-stressed feeder first, the way a utility would actually deploy. At full coverage the feeder peak falls <b>${(at0 - atAll).toFixed(0)} kVA</b>.`;
}

function renderDistrictTab() {
  if (!districtData) return;
  renderDistrictScore();
  renderDistrictAdoption();
  renderDistrictAttribution();
  renderDistrictHeatmap();
  renderDistrictLeague();
}

function renderDistrictScore() {
  if (!districtData) return;
  const { shown, managed, unmanaged } = districtCohorts();

  // --- scoreboard: the two cohorts as they stand right now -----------------
  const perHouse = (rs, k) => {
    const h = rs.reduce((a, r) => a + r.n_households, 0);
    return h ? sumS(rs, k) / h : 0;
  };
  const vaPerHome = (rs) => rs.length ? (perHouse(rs, "peak_kva") * 1000).toFixed(0) : "—";
  const row = (label, a, b, unit = "", good = "low") => {
    const better = Number.isFinite(+a) && Number.isFinite(+b) && (good === "low" ? +a <= +b : +a >= +b);
    return `<div class="drow">
      <span class="dk">${label}</span>
      <span class="dv mono" style="color:${better ? "var(--ok)" : "var(--text)"}">${a}${unit}</span>
      <span class="dv mono" style="color:var(--muted)">${b}${unit}</span>
    </div>`;
  };
  document.getElementById("districtScore").innerHTML = `
    <h2>District scoreboard</h2>
    <div class="drow dhead"><span class="dk">${shown.length} societies today</span>
      <span class="dv" style="color:var(--gold)">GridBrain &middot; ${managed.length}</span>
      <span class="dv" style="color:var(--muted)">Unmanaged &middot; ${unmanaged.length}</span></div>
    ${row("Transformer trips", sumS(managed, "tripped_ticks"), sumS(unmanaged, "tripped_ticks"))}
    ${row("Breach intervals", sumS(managed, "breach_ticks"), sumS(unmanaged, "breach_ticks"))}
    ${row("Unserved energy", sumS(managed, "unserved_kwh").toFixed(0), sumS(unmanaged, "unserved_kwh").toFixed(0), " kWh")}
    ${row("Peak load, mean", vaPerHome(managed), vaPerHome(unmanaged), " VA/home")}
    ${row("Worst comfort dev.", worstComfort(managed), worstComfort(unmanaged), "°C")}
    <div class="whatif-readout" style="margin-top:8px">Both columns are real simulation runs on the same engine. The unmanaged societies trip because nothing is protecting them — not because they were made to.</div>
  `;
}

function renderDistrictAdoption() {
  const { managed } = districtCohorts();
  // --- adoption curve on the shared upstream feeder -----------------------
  // Rendered once with stable ids; the slider then patches only the numbers
  // via updateAdoptionReadout(). Rewriting innerHTML on every input event
  // would destroy the range input mid-drag.
  const nSoc = districtPairs().length;
  const el = document.getElementById("districtAdoption");
  if (!document.getElementById("adoptionSlider")) {
    const curve = [];
    for (let i = 0; i <= nSoc; i++) curve.push(feederPeakAtAdoption(i).peak);
    const cw = 260, ch = 54, cmin = Math.min(...curve), cmax = Math.max(...curve);
    adoptionCurve = { curve, cw, ch, cmin, cmax, nSoc };
    const pts = curve.map((v, i) => `${(i / nSoc) * cw},${ch - ((v - cmin) / Math.max(1e-6, cmax - cmin)) * ch}`).join(" ");
    el.innerHTML = `
      <h2>Upstream feeder &middot; adoption</h2>
      <svg viewBox="0 0 ${cw} ${ch}" style="width:100%;height:58px;display:block;margin-bottom:6px" preserveAspectRatio="none">
        <polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
        <circle id="adoptionDot" cx="0" cy="0" r="4" fill="var(--gold)"/>
      </svg>
      <input type="range" id="adoptionSlider" min="0" max="${nSoc}" value="0" style="width:100%">
      <div class="drow"><span class="dk">Societies covered</span><span class="dv mono" id="adCovered">–</span><span class="dv mono" style="color:var(--muted)" id="adPct">–</span></div>
      <div class="drow"><span class="dk">Feeder peak</span><span class="dv mono" style="color:var(--gold)" id="adPeak">–</span><span class="dv mono" style="color:var(--muted)" id="adWas">–</span></div>
      <div class="drow"><span class="dk">Peak held back</span><span class="dv mono" style="color:var(--ok)" id="adHeld">–</span><span class="dv mono" style="color:var(--muted)" id="adHeldPct">–</span></div>
      <div class="whatif-readout" style="margin-top:6px" id="adNote"></div>`;
  }
  updateAdoptionReadout(state.adoption ?? managed.length);
}

function renderDistrictAttribution() {
  const rupee = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
  // --- attribution: coordination vs solar hardware ------------------------
  // Summed over ALL 24 societies' triplets, so this is the district-wide
  // answer to "how much of this is the AI and how much is the panels".
  let coordKva = 0, stationKva = 0, coordUnserved = 0;
  for (const p of districtPairs()) {
    const raw = districtRecord(p, "raw"), ai = districtRecord(p, "ai"), full = districtRecord(p, "full");
    coordKva += raw.summary.peak_kva - ai.summary.peak_kva;
    stationKva += ai.summary.peak_kva - full.summary.peak_kva;
    coordUnserved += raw.summary.unserved_kwh - ai.summary.unserved_kwh;
  }
  const totalKva = Math.max(0, coordKva) + Math.max(0, stationKva);
  const coordPct = totalKva > 0 ? (Math.max(0, coordKva) / totalKva) * 100 : 100;
  document.getElementById("districtAttribution").innerHTML = `
    <h2>What is doing the work</h2>
    <div class="cost-split" style="margin-bottom:8px">
      <div style="width:${coordPct.toFixed(0)}%;background:var(--accent)"></div>
      <div style="flex:1;background:var(--gold)"></div>
    </div>
    <div class="drow"><span class="dk" style="color:var(--accent)">Coordination alone</span><span class="dv mono">${coordKva >= 0 ? "−" : "+"}${Math.abs(coordKva).toFixed(0)} kVA</span><span class="dv mono" style="color:var(--muted)">zero capex</span></div>
    <div class="drow"><span class="dk" style="color:var(--gold)">Solar package adds</span><span class="dv mono" style="color:${stationKva >= 0 ? "var(--text)" : "var(--muted)"}">${stationKva >= 0 ? "−" : "+"}${Math.abs(stationKva).toFixed(0)} kVA</span><span class="dv mono" style="color:var(--muted)">capex</span></div>
    <div class="save-box" style="margin-top:9px">
      <h4>Zero-capex result</h4>
      <div class="v">${coordUnserved.toFixed(0)} kWh of outage avoided</div>
      <div class="note">Coordination — no hardware purchased — takes <b>${coordKva.toFixed(0)} kVA</b> off the district's summed peak and removes every trip. Saying "our AI saved X" while quietly including the panels would be an attribution error, so each society was run three ways to keep them separate.</div>
    </div>
    <div class="cost-box" style="margin-top:8px">
      <h4>What solar does and doesn't do</h4>
      <div class="note">The solar package's effect on <b>peak</b> comes out ${stationKva < 0 ? `<b style="color:var(--warn)">slightly negative (${stationKva.toFixed(0)} kVA)</b>` : `<b>${stationKva.toFixed(0)} kVA</b>`}, and that is reported rather than smoothed over. Solar is a <b>cost</b> lever, not a peak lever: syncing EV charging into daylight buys cheaper self-consumed energy but moves load out of the empty small hours, and the station generates nothing after sunset — so neither can touch the evening peak that actually sizes the transformer. Shaving that evening peak is what the coordination row above is for; doing it with solar would need storage.</div>
    </div>
    <div class="whatif-readout" style="margin-top:6px">Illustrative capex deferred across the district: <b>₹${rupee.format(Math.round(totalKva * CAPEX_PER_KVA))}</b> at the same ₹1,200/kVA default used by the commercial ROI calculator.</div>
  `;
}

function renderDistrictHeatmap() {
  const { shown } = districtCohorts();
  // --- failure heatmap: 24 rows x 96 ticks --------------------------------
  const t = districtTick();
  let hm = '<h2>Where the day goes wrong</h2><div class="heatmap">';
  for (const r of shown) {
    hm += `<div class="hm-row" data-pair="${r.pair}"><span class="hm-label" style="color:${r.arm === "raw" ? "var(--muted)" : "var(--gold)"}">${r.label}</span><span class="hm-cells">`;
    for (let i = 0; i < r.series.state.length; i++) {
      const st = r.series.state[i];
      const cls = st === "TRIPPED" ? "t" : st === "BREACH" ? "b" : st === "CRITICAL" ? "c" : st === "WARNING" ? "w" : "n";
      hm += `<i class="${cls}${i === t ? " now" : ""}"></i>`;
    }
    hm += "</span></div>";
  }
  hm += '</div><div class="whatif-readout" style="margin-top:7px">One cell per 15 minutes. <b style="color:var(--ok)">Green</b> normal, <b style="color:var(--warn)">amber</b> warning, <b style="color:var(--crit)">orange</b> critical, <b style="color:var(--tripped)">red</b> breach or trip. GridBrain rows are the clean stripes.</div>';
  document.getElementById("districtHeatmap").innerHTML = hm;
}

function renderDistrictLeague() {
  const { shown } = districtCohorts();
  // --- league table -------------------------------------------------------
  const ranked = shown.slice().sort((a, b) => a.summary.peak_frac - b.summary.peak_frac);
  document.getElementById("districtLeague").innerHTML = `
    <h2>League table &middot; headroom</h2>
    ${ranked.map((r, i) => `
      <div class="node-row node-row-jump" data-pair="${r.pair}">
        <span class="nname">${i + 1}. ${r.label}
          <span style="color:var(--muted);font-weight:400">${r.n_households} homes &middot; EV ${(r.ev_penetration * 100).toFixed(0)}%${r.arm !== "raw" ? " &middot; <b style='color:var(--gold)'>GridBrain</b>" : ""}</span></span>
        <span class="nstate mono" style="color:${r.summary.peak_frac > 1 ? "var(--tripped)" : r.summary.peak_frac > 0.9 ? "var(--warn)" : "var(--ok)"}">${(r.summary.peak_frac * 100).toFixed(0)}%</span>
      </div>`).join("")}
    <div class="whatif-readout" style="margin-top:7px">Peak load as a share of each transformer's own rating. Above 100% is a real breach. Tap any society to inspect it.</div>
  `;
}

// "Deploy GridBrain here" — swaps which of that society's three real
// pre-simulated runs is being displayed. Nothing is recomputed and nothing
// is faked: the after state is a dataset that already existed on disk.
function setDistrictArm(pair, arm) {
  state.districtArm[pair] = arm;
  const rec = districtRecord(pair);
  const raw = districtRecord(pair, "raw");
  pushLedger(frame().t_min, arm === "raw"
    ? `DISTRICT: GridBrain withdrawn from ${rec.label} — peak returns to ${raw.summary.peak_kva.toFixed(0)} kVA, ${raw.summary.tripped_ticks} trip${raw.summary.tripped_ticks === 1 ? "" : "s"}.`
    : `DISTRICT: GridBrain deployed on ${rec.label} — peak ${raw.summary.peak_kva.toFixed(0)} → ${rec.summary.peak_kva.toFixed(0)} kVA, unserved energy ${raw.summary.unserved_kwh.toFixed(0)} → ${rec.summary.unserved_kwh.toFixed(0)} kWh.`,
    arm === "raw" ? "act" : "rec");
  applyDistrictFrame();
  renderDistrictTab();
  renderInspector();
}
document.getElementById("rail").addEventListener("input", (e) => {
  if (e.target.id !== "adoptionSlider") return;
  state.adoption = +e.target.value;
  // the slider drives the world too: adopt in the same worst-first order
  adoptionOrder().forEach((p, i) => { state.districtArm[p] = i < state.adoption ? "full" : "raw"; });
  applyDistrictFrame();
  updateAdoptionReadout(state.adoption);   // patch in place — never re-render mid-drag
  renderDistrictScore();
  renderDistrictHeatmap();
  renderDistrictLeague();
});
document.getElementById("rail").addEventListener("click", (e) => {
  const dep = e.target.closest("[data-deploy]");
  if (dep) { const p = dep.dataset.deploy; setDistrictArm(p, state.districtArm[p] === "raw" ? "full" : "raw"); return; }
  const row = e.target.closest(".hm-row, .node-row-jump");
  if (row && row.dataset.pair) {
    state.selected = { kind: "districtSociety", pair: row.dataset.pair };
    if (state.cam !== "district") document.querySelector('#camGroup button[data-cam="district"]').click();
    renderInspector(); setRailTab("live");
  }
});

// ---------------------------------------------------- topbar day sparkline
// Society A's whole-day loading, always visible. Previously the day's shape
// only appeared once you clicked the transformer, so the story of the day was
// invisible unless you knew where to look.
function drawTopSpark() {
  const c = document.getElementById("topSpark"); if (!c || !state.data) return;
  // it's a full-width strip now, so the backing store has to track the
  // element's real size or the line ends up stretched and blurry
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const cssW = c.clientWidth || 600, cssH = c.clientHeight || 34;
  if (c.width !== Math.round(cssW * dpr) || c.height !== Math.round(cssH * dpr)) {
    c.width = Math.round(cssW * dpr); c.height = Math.round(cssH * dpr);
  }
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const w = cssW, h = cssH;
  g.clearRect(0, 0, w, h);
  const vals = state.data.frames.map(f => f.grid.transformer_kva);
  const rating = state.data.frames[0].grid.rating_kva;
  const max = Math.max(...vals, rating) * 1.08;
  const ry = h - (rating / max) * h;
  g.strokeStyle = "rgba(255,106,106,.55)"; g.setLineDash([3, 3]);
  g.beginPath(); g.moveTo(0, ry); g.lineTo(w, ry); g.stroke(); g.setLineDash([]);
  g.beginPath();
  vals.forEach((v, i) => { const x = (i / (vals.length - 1)) * w, y = h - (v / max) * h; i ? g.lineTo(x, y) : g.moveTo(x, y); });
  g.strokeStyle = "#39e0ff"; g.lineWidth = 1.3; g.stroke();
  const cx = (state.frameIdx / (vals.length - 1)) * w;
  g.strokeStyle = "rgba(232,178,61,.85)"; g.lineWidth = 1;
  g.beginPath(); g.moveTo(cx, 0); g.lineTo(cx, h); g.stroke();
  g.fillStyle = "#e8b23d";
  g.beginPath(); g.arc(cx, h - (vals[state.frameIdx] / max) * h, 2.4, 0, 7); g.fill();
}

// ------------------------------------------------ per-scenario lighting mood
// Each scenario gets its own grade so it reads as a different day, not the
// same day relabelled. Applied on top of the real sun/moon calculation --
// this tints and grades, it never fakes the time of day.
const SCENARIO_MOOD = {
  normal:   { fog: 0x0a1020, bloom: 0.62, tint: 0xffffff, exposure: 0.92 },
  heatwave: { fog: 0x1a1208, bloom: 0.80, tint: 0xffd9a8, exposure: 1.02 },
  high_ev:  { fog: 0x070f1c, bloom: 0.70, tint: 0xd8ecff, exposure: 0.92 },
  outage:   { fog: 0x120409, bloom: 0.46, tint: 0xffb3b8, exposure: 0.80 },
};
function moodFor(key) {
  if (key && key.startsWith("whatif")) return SCENARIO_MOOD.high_ev;
  return SCENARIO_MOOD[key] || SCENARIO_MOOD.normal;
}
function applyScenarioMood() {
  const m = moodFor(state.scenarioKey);
  if (state.cam === "district") {
    // The district shows 24 societies at once -- every emissive window,
    // transformer beacon and gold canopy stacking into the same frame. At the
    // society-scale bloom setting that reads as a white haze with the labels
    // barely legible, so this scale gets a much flatter grade.
    bloomPass.strength = 0.22;
    renderer.toneMappingExposure = 0.74;
  } else {
    bloomPass.strength = m.bloom;
    renderer.toneMappingExposure = m.exposure;
  }
}

function updateOpsCounters() {
  const meters = document.getElementById("opsMeters"), coord = document.getElementById("opsCoord");
  if (!meters || !districtData) return;
  const shown = districtPairs().map(p => districtRecord(p));
  meters.textContent = shown.reduce((a, r) => a + r.n_households, 0).toLocaleString("en-IN");
  coord.textContent = shown.filter(r => r.arm !== "raw").length;
}

// ------------------------------------------------------------------ reset
// Pure demo insurance: puts every control back to a known-good state after a
// judge has been clicking around. Restores the curated GridBrain cohort too,
// which the adoption slider deliberately overrides.
function resetAll() {
  state.adoption = null;
  state.districtArm = {};
  for (const s of districtData ? districtData.societies : []) {
    if (s.arm === "full") state.districtArm[s.pair] = s.in_cohort ? "full" : "raw";
  }
  state.whatifEv = null; state.whatifAi = true; state.whatifSync = false;
  document.querySelectorAll("#whatifEvGroup button, #whatifSyncGroup button").forEach(b => b.classList.remove("active"));
  document.querySelectorAll("#whatifAiGroup button").forEach(b => b.classList.toggle("active", b.dataset.ai === "1"));
  document.getElementById("whatifSyncGroup").classList.add("disabled");
  document.getElementById("whatifCapex").textContent =
    "Pick an EV level to watch the AI Coordinator hold the line in real, pre-simulated data — not a fudge-factor slider.";
  state.selected = null; state.playing = false; state.speed = 1; state.frameIdx = 40;
  document.querySelectorAll(".speed-btn").forEach(b => b.classList.toggle("active", b.textContent === "1x"));
  document.getElementById("scrub").value = 40;
  document.querySelector('#camGroup button[data-cam="orbit"]').click();
  setScenario("normal").then(() => { renderInspector(); renderDistrictTab(); setRailTab("live"); });
}
document.getElementById("resetBtn").addEventListener("click", resetAll);
window.addEventListener("keydown", (e) => {
  if (e.key === "r" && !e.metaKey && !e.ctrlKey && !/input|textarea/i.test(e.target.tagName)) resetAll();
});

// ================================================================ ANALYSIS
// Everything here is arithmetic over fields already present in the loaded
// scenario JSON, plus two cited external constants. Nothing is simulated
// here and nothing is forecast.
const CEA_GRID_KGCO2_PER_KWH = 0.716;  // CEA CO2 Baseline Database, weighted avg
const LOAD_GROWTH_PA = 0.06;           // stated assumption, shown on the chart

function railActive(tab) {
  const b = document.querySelector(`.rail-tab[data-tab="${tab}"]`);
  return b && b.classList.contains("active");
}

function renderAnalysisTab() {
  if (!state.data) return;
  const d = state.data, stepH = (d.meta.interval_minutes || 15) / 60;
  const frames = d.frames;

  // --- #5 duck curve ------------------------------------------------------
  const gross = frames.map(f => f.houses.reduce((a, h) => a + h.kw + (h.solar_kw || 0), 0));
  const solar = frames.map(f => (f.society.solar_kw || 0) + (f.society.community_solar_kw || 0));
  const net = frames.map((f, i) => Math.max(0, gross[i] - solar[i]));
  const W = 280, H = 84, mx = Math.max(...gross, 1);
  const path = (arr) => arr.map((v, i) => `${(i / (arr.length - 1)) * W},${H - (v / mx) * H}`).join(" ");
  // steepest sustained evening ramp, in kW/h
  let ramp = 0, rampAt = 0;
  for (let i = 0; i < net.length - 8; i++) {
    const r = (net[i + 8] - net[i]) / (8 * stepH);
    if (r > ramp) { ramp = r; rampAt = i; }
  }
  const bellyIdx = net.indexOf(Math.min(...net));
  document.getElementById("anDuck").innerHTML = `
    <h2>Duck curve &middot; net load after solar</h2>
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:92px;display:block" preserveAspectRatio="none">
      <polyline points="${path(gross)}" fill="none" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>
      <polyline points="${path(net)}" fill="none" stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
      <line x1="${(bellyIdx / 95) * W}" y1="0" x2="${(bellyIdx / 95) * W}" y2="${H}" stroke="var(--gold)" stroke-width="1" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/>
    </svg>
    <div class="drow"><span class="dk">Midday belly</span><span class="dv mono">${net[bellyIdx].toFixed(1)} kW</span><span class="dv mono" style="color:var(--muted)">${minToClock(frames[bellyIdx].t_min)}</span></div>
    <div class="drow"><span class="dk">Steepest evening ramp</span><span class="dv mono" style="color:var(--warn)">${ramp.toFixed(1)} kW/h</span><span class="dv mono" style="color:var(--muted)">from ${minToClock(frames[rampAt].t_min)}</span></div>
    <div class="whatif-readout" style="margin-top:6px">Dashed = gross demand, solid = what the transformer actually sees after on-site solar. The midday belly and the evening ramp back up are the classic duck curve — the reason a feeder can be fine on energy and still fail on <i>ramp rate</i>. Computed from this scenario's own <code>solar_kw</code> and per-house load.</div>`;

  // --- #9 per-archetype comfort ------------------------------------------
  const byArch = {};
  d.houses.forEach((h, i) => {
    const a = (byArch[h.archetype] ||= { n: 0, sum: 0, worst: 0, curt: 0 });
    a.n++;
    for (const f of frames) {
      a.sum += Math.abs(f.houses[i].comfort_dev_c);
      a.worst = Math.max(a.worst, Math.abs(f.houses[i].comfort_dev_c));
      if (f.houses[i].curtailed) a.curt++;
    }
  });
  const archRows = Object.entries(byArch).sort((x, y) => y[1].worst - x[1].worst);
  document.getElementById("anComfort").innerHTML = `
    <h2>Who pays the comfort cost</h2>
    <div class="drow dhead"><span class="dk">Archetype</span><span class="dv">Mean dev</span><span class="dv">Worst</span></div>
    ${archRows.map(([k, a]) => `<div class="drow">
      <span class="dk" style="${k === "elderly_couple" ? "color:var(--gold)" : ""}">${k.replace(/_/g, " ")} <span style="color:var(--muted)">&times;${a.n}</span></span>
      <span class="dv mono">${(a.sum / (a.n * frames.length)).toFixed(2)}°C</span>
      <span class="dv mono" style="color:${a.worst > 1 ? "var(--warn)" : "var(--ok)"}">${a.worst.toFixed(2)}°C</span></div>`).join("")}
    <div class="whatif-readout" style="margin-top:6px">Deviation outside each archetype's own comfort band, broken out because "average comfort was fine" hides whether curtailment lands on the households least able to absorb it. <b>Elderly couple</b> is highlighted as the vulnerable cohort a real RWA would ask about first.</div>`;

  // --- #11 transformer thermal aging -------------------------------------
  // Simplified IEC 60076-7-style relative ageing: rate doubles roughly every
  // 6 K of hot-spot rise, approximated here from per-unit loading.
  let aging = 0;
  for (const f of frames) {
    const pu = f.grid.transformer_kva / f.grid.rating_kva;
    aging += Math.pow(2, (pu - 1) * 6) * stepH;
  }
  const normalDay = 24;
  document.getElementById("anAging").innerHTML = `
    <h2>Transformer ageing</h2>
    <div class="drow"><span class="dk">Insulation life used today</span><span class="dv mono" style="color:${aging > normalDay ? "var(--warn)" : "var(--ok)"}">${aging.toFixed(1)} h</span><span class="dv mono" style="color:var(--muted)">of 24 h</span></div>
    <div class="drow"><span class="dk">Effective ageing rate</span><span class="dv mono">${(aging / normalDay).toFixed(2)}&times;</span><span class="dv mono" style="color:var(--muted)">nominal</span></div>
    <div class="whatif-readout" style="margin-top:6px"><b>Illustrative model, real input.</b> The loading series is this scenario's real simulated kVA; the ageing curve is a simplified IEC 60076-7-style relative-rate approximation (rate doubling per ~6 K hot-spot rise), not a thermal model of a specific transformer. Directionally right, not a warranty calculation.</div>`;

  // --- #16 carbon + #14 unserved energy ----------------------------------
  const gridKwh = frames.reduce((a, f) => a + Math.max(0, f.houses.reduce((s, h) => s + h.kw, 0)) * stepH, 0);
  const solarKwh = frames.reduce((a, f) => a + ((f.society.solar_kw || 0) + (f.society.community_solar_kw || 0)) * stepH, 0);
  const trippedKwh = frames.filter(f => f.grid.state === "TRIPPED")
    .reduce((a, f) => a + f.houses.reduce((s, h) => s + h.kw, 0) * stepH, 0);
  const outageMin = frames.filter(f => f.grid.state === "TRIPPED").length * (d.meta.interval_minutes || 15);
  document.getElementById("anCarbon").innerHTML = `
    <h2>Carbon &amp; reliability</h2>
    <div class="drow"><span class="dk">Grid energy drawn</span><span class="dv mono">${gridKwh.toFixed(0)} kWh</span><span class="dv mono" style="color:var(--muted)">${(gridKwh * CEA_GRID_KGCO2_PER_KWH).toFixed(0)} kg CO&#8322;</span></div>
    <div class="drow"><span class="dk">Solar generated on site</span><span class="dv mono" style="color:var(--ok)">${solarKwh.toFixed(0)} kWh</span><span class="dv mono" style="color:var(--ok)">&minus;${(solarKwh * CEA_GRID_KGCO2_PER_KWH).toFixed(0)} kg</span></div>
    <div class="drow"><span class="dk">Unserved energy</span><span class="dv mono" style="color:${trippedKwh > 0 ? "var(--tripped)" : "var(--ok)"}">${trippedKwh.toFixed(1)} kWh</span><span class="dv mono" style="color:var(--muted)">${outageMin} outage-min</span></div>
    <div class="whatif-readout" style="margin-top:6px">Emission factor <b>${CEA_GRID_KGCO2_PER_KWH} kg CO&#8322;/kWh</b> — CEA CO&#8322; Baseline Database weighted average for the Indian grid, cited rather than assumed. Unserved energy is the DISCOM-facing reliability quantity (what a SAIDI/SAIFI penalty is computed from), distinct from the resident-facing savings figure.</div>`;

  // --- #17 five-year capex deferral --------------------------------------
  const peak = Math.max(...frames.map(f => f.grid.transformer_kva));
  const rating = frames[0].grid.rating_kva;
  const yrs = [0, 1, 2, 3, 4, 5].map(y => ({ y, p: peak * Math.pow(1 + LOAD_GROWTH_PA, y) }));
  const breach = yrs.find(o => o.p > rating);
  document.getElementById("anCapex").innerHTML = `
    <h2>Five-year headroom</h2>
    ${yrs.map(o => {
      const pct = Math.min(120, (o.p / rating) * 100);
      return `<div class="drow"><span class="dk">Year ${o.y}</span>
        <span class="dv mono" style="color:${o.p > rating ? "var(--tripped)" : "var(--text)"}">${o.p.toFixed(0)} kVA</span>
        <span class="dv mono" style="color:var(--muted)">${pct.toFixed(0)}%</span></div>`;
    }).join("")}
    <div class="whatif-readout" style="margin-top:6px">Today's real peak compounded at a <b>stated ${(LOAD_GROWTH_PA * 100).toFixed(0)}%/yr load-growth assumption</b> — an assumption, not a forecast, and shown so it can be argued with. ${breach ? `On this trajectory the ${rating} kVA transformer is exceeded in <b>year ${breach.y}</b>; holding the peak down is what defers that spend.` : `The ${rating} kVA transformer stays within rating across the whole window at this growth rate.`}</div>`;
}

// --- #23 one-shot coach marks for an unattended booth viewer ---
const COACH_KEY = "aethergrid_coached_v1";
function showCoachMarks() {
  let seen = false;
  try { seen = localStorage.getItem(COACH_KEY) === "1"; } catch (e) { seen = false; }
  if (seen) return;
  const el = document.getElementById("coach");
  el.classList.remove("hidden");
  el.addEventListener("click", () => {
    el.classList.add("hidden");
    try { localStorage.setItem(COACH_KEY, "1"); } catch (e) { /* private mode */ }
  }, { once: true });
}

let colonyRefs = [];
async function boot() {
  onResize();
  buildScenarioButtons();
  buildSpeedButtons();
  await Promise.all([setScenario("normal"), loadColonyData(), loadDistrictData()]);

  const refA = { key: "society_a", label: "Society A", txWorldPos: new THREE.Vector3(transformerObj.position.x, 1.1, transformerObj.position.z) };
  const refB = buildColonySociety("society_b", colonyData.society_b, COLONY.society_b.offset);
  const refC = buildColonySociety("society_c", colonyData.society_c, COLONY.society_c.offset);
  colonyRefs = [refA, refB, refC];
  buildGridBrainHub(colonyRefs);
  addColonyTraffic(refB.cols, refB.rows, COLONY.society_b.offset, 21);
  addColonyTraffic(refC.cols, refC.rows, COLONY.society_c.offset, 22);
  buildDistrict();
  renderNodeMap();
  renderDistrictTab();
  updateOpsCounters();
  applyScenarioMood();
  showCoachMarks();

  requestAnimationFrame(loop);
}
boot();
