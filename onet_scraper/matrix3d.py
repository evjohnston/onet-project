"""The national-security matrix as an interactive 3D scatter.

A THREE-DIMENSIONAL SCATTER IS A BAD WAY TO READ VALUES and we build one anyway,
because the question being asked here - where does an occupation sit on all
three axes at once - is genuinely three-dimensional, and the alternative (three
separate 2D charts) makes the reader hold the join in their head.

The known failure modes of 3D scatter, and what we do about each:

  occlusion         near points hide far ones. Mitigated by depth sorting, a
                    surface-coloured ring on every mark, and rotation - the
                    reader can always turn the cloud.
  depth ambiguity   you cannot tell how far along z a point is. This is the real
                    problem and rotation alone does not fix it, so the page also
                    ships FACE VIEWS: three buttons that snap the camera onto an
                    axis-aligned plane and turn the plot into an honest 2D
                    scatter with no perspective. That is where values get read;
                    the 3D view is for seeing the shape of the cloud.
  no shared baseline  bar-like comparison is impossible. We do not attempt it -
                    the octant table below the plot carries the counts.

Colour encodes severity, not field. Position already carries all three axes, so
colour has to add something; the seven STEM fields cannot be given seven
distinguishable hues (an all-pairs check tops out around three), while severity
is ordinal and takes a validated single-hue ramp. Field is a filter instead.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

from . import theme
from .security import OCTANTS, SEVERITY_LABELS

log = logging.getLogger(__name__)

# Ordinal severity ramp, one hue (OKLCH h=32.9), monotone lightness, validated
# against both surfaces with scripts/validate_palette.js --ordinal.
RAMP_LIGHT = ("#d4a499", "#c87b6a", "#b6513d", "#98250e")
RAMP_DARK = ("#edc7be", "#e29e8e", "#d17561", "#bc4b35")

SEV_TOKENS = """
  --sev-0: #d4a499; --sev-1: #c87b6a; --sev-2: #b6513d; --sev-3: #98250e;
"""
SEV_TOKENS_DARK = """
  --sev-0: #edc7be; --sev-1: #e29e8e; --sev-2: #d17561; --sev-3: #bc4b35;
"""

CSS = """
.m3-root { background: var(--surface-2); padding: 28px 32px 64px; min-height: 100vh; }
body { background: var(--surface-2); }
.sub { color: var(--text-secondary); font-size: 13px; margin: 0 0 20px; max-width: 82ch; }
.axes { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
        margin: 0 0 22px; max-width: 1080px; }
.axes div { background: var(--surface-1); border: 1px solid var(--rule);
            border-radius: 8px; padding: 12px 14px; }
.axes span { font-size: 12.5px; color: var(--text-secondary); }
/* Controls sit in one row above the plot. */
.controls { display: flex; flex-wrap: wrap; gap: 18px; align-items: flex-end;
            margin: 0 0 16px; }
.ctl { display: flex; flex-direction: column; gap: 5px; }
.seg { display: inline-flex; border: 1px solid var(--axis); border-radius: 7px;
       overflow: hidden; background: var(--surface-1); }
.seg button { font: inherit; font-size: 12.5px; padding: 6px 12px; border: 0;
              background: transparent; color: var(--text-secondary);
              cursor: pointer; border-right: 1px solid var(--rule); }
.seg button:last-child { border-right: 0; }
.seg button[aria-pressed="true"] { background: var(--text-primary);
                                   color: var(--surface-1); font-weight: 600; }
select { font: inherit; font-size: 12.5px; padding: 6px 8px; border-radius: 7px;
         border: 1px solid var(--axis); background: var(--surface-1);
         color: var(--text-primary); }
.layout { display: grid; grid-template-columns: minmax(0,1fr) 336px; gap: 26px;
          align-items: start; max-width: 1260px; }
@media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
.plotwrap { background: var(--surface-1); border: 1px solid var(--rule);
            border-radius: 10px; padding: 8px; position: relative; }
svg { display: block; width: 100%; height: auto; touch-action: none; cursor: grab; }
svg.dragging { cursor: grabbing; }
.hint { font-size: 11.5px; color: var(--text-muted); margin: 6px 4px 2px; }
/* Legend is always present; severity also carries a text label in the tooltip
   and the table, so identity is never colour-alone. */
.legend { display: flex; flex-wrap: wrap; gap: 4px 14px; margin: 10px 4px 0; }
.legend span { display: inline-flex; align-items: center; gap: 6px;
               font-size: 12px; color: var(--text-secondary); }
.legend i { width: 11px; height: 11px; border-radius: 50%; display: inline-block;
            box-shadow: 0 0 0 1.5px var(--surface-1); }
.side h2 { margin-top: 0; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
th, td { text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--rule); }
td.num, th.num { text-align: right; }
/* The axis cards' term is a label, so it takes the label type. */
.axes b { display: block; margin-bottom: 4px; }
tr.oct { cursor: pointer; }
tr.oct:hover td { background: var(--surface-3); }
tr.oct[aria-selected="true"] td { background: var(--surface-3); font-weight: 600; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%;
       vertical-align: -1px; }
td.sw, th.sw { width: 16px; padding-right: 0; }
.tip { position: absolute; pointer-events: none; opacity: 0;
       transition: opacity .08s; background: var(--surface-1);
       border: 1px solid var(--axis); border-radius: 8px; padding: 9px 11px;
       font-size: 12.5px; box-shadow: 0 4px 14px rgba(0,0,0,.13);
       max-width: 290px; z-index: 5; }
.tip b { display: block; margin-bottom: 4px; font-size: 13px; }
.tip dl { display: grid; grid-template-columns: auto auto; gap: 1px 10px; margin: 5px 0 0; }
.tip dt { color: var(--text-muted); }
.tip dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
details { margin-top: 30px; max-width: 1260px; }
summary { cursor: pointer; font-weight: 620; font-size: 14px; padding: 6px 0; }
.scroll { max-height: 460px; overflow: auto; border: 1px solid var(--rule);
          border-radius: 8px; background: var(--surface-1); }
.note { font-size: 12px; color: var(--text-muted); max-width: 82ch;
        margin: 26px 0 0; padding-top: 14px; border-top: 1px solid var(--rule); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chips button { font: inherit; font-size: 12px; padding: 4px 10px; border-radius: 20px;
                border: 1px solid var(--axis); background: var(--surface-1);
                color: var(--text-secondary); cursor: pointer; }
.chips button[aria-pressed="true"] { background: var(--text-primary);
                                     color: var(--surface-1); border-color: var(--text-primary); }
"""


JS = r"""
const DATA = __DATA__;
const OCTANTS = __OCTANTS__;
const OCT_BY_KEY = __OCT_BY_KEY__;
const SEV_LABELS = __SEV_LABELS__;

const AXES = {
  efficiency:    {label: "AI efficiency",     short: "Efficiency"},
  removal_risk:  {label: "Risk of removing humans", short: "Removal risk"},
  reconstitution:{label: "Reconstitution difficulty", short: "Reconstitution"},
  scarcity:      {label: "Workforce scarcity", short: "Scarcity"},
  training_depth:{label: "Training depth",     short: "Training depth"},
  isolation:     {label: "Isolation from neighbours", short: "Isolation"},
  erosion_risk:  {label: "Erosion risk",       short: "Erosion risk"},
  willingness_gap:{label: "Willingness gap",   short: "Willingness gap"},
  risk_at_stake: {label: "Risk of the work being handed over", short: "Risk at stake"},
};

const S = {
  scenario: "substantial",
  grain: "occupations",
  zKey: "reconstitution",
  view: "3d",
  yaw: 0.62, pitch: 0.42, zoom: 1,
  field: null,
  octant: null,
  split: "fifty",
};

/* The cube is carved at a threshold on each axis. Absolute 50 is the
   interpretable choice and the default, but reconstitution is skewed high
   across this corpus - the mean sits near 69 - so an absolute split leaves the
   easy-to-rebuild half of the cube almost empty. Splitting at the corpus median
   instead balances the cells at the cost of making them relative. Both readings
   are legitimate and they answer different questions, so the page offers both
   rather than picking one. */
function median(xs){
  const v = xs.filter(x => x != null && !isNaN(x)).slice().sort((a, b) => a - b);
  if (!v.length) return 50;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

function thresholds(){
  if (S.split === "fifty") return {eff: 50, risk: 50, z: 50};
  const rs = rows();
  return {eff: median(rs.map(r => r.efficiency)),
          risk: median(rs.map(r => r.removal_risk)),
          z: median(rs.map(r => Number(r[S.zKey])))};
}

function cellOf(r, th){
  const key = [(r.efficiency >= th.eff) ? 1 : 0,
               (r.removal_risk >= th.risk) ? 1 : 0,
               ((Number(r[S.zKey]) || 0) >= th.z) ? 1 : 0].join(",");
  return OCT_BY_KEY[key];
}

const W = 760, H = 620, CX = W / 2, CY = H / 2 + 6, SCALE = 3.15;
const svg = document.getElementById("plot");
const tip = document.getElementById("tip");
const NS = "http://www.w3.org/2000/svg";

/* ---- projection -------------------------------------------------------- */
/* Face views drop perspective entirely: an axis-aligned orthographic view is
   an honest 2D scatter, which is the whole point of offering them. */
function isFace(){ return S.view !== "3d"; }

function project(x, y, z){
  const px = x - 50, py = y - 50, pz = z - 50;
  const cy = Math.cos(S.yaw), sy = Math.sin(S.yaw);
  const rx = px * cy + pz * sy;
  const rz = -px * sy + pz * cy;
  const cp = Math.cos(S.pitch), sp = Math.sin(S.pitch);
  const ry = py * cp - rz * sp;
  const rz2 = py * sp + rz * cp;
  const k = isFace() ? S.zoom : (520 / (520 + rz2)) * S.zoom;
  return {x: CX + rx * k * SCALE, y: CY - ry * k * SCALE, d: rz2};
}

function el(tag, attrs, parent){
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  (parent || svg).appendChild(n);
  return n;
}

/* ---- the frame --------------------------------------------------------- */
const CORNERS = [[0,0,0],[100,0,0],[100,100,0],[0,100,0],
                 [0,0,100],[100,0,100],[100,100,100],[0,100,100]];
const EDGES = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],
               [0,4],[1,5],[2,6],[3,7]];

function drawFrame(g){
  const p = CORNERS.map(c => project(c[0], c[1], c[2]));
  // Split edges by depth so the box reads as a box: far edges recede.
  EDGES.forEach(([a, b]) => {
    const far = (p[a].d + p[b].d) / 2 > 0;
    el("line", {x1: p[a].x, y1: p[a].y, x2: p[b].x, y2: p[b].y,
                stroke: "var(--axis)", "stroke-width": far ? 1 : 1.4,
                "stroke-opacity": far ? 0.35 : 0.85}, g);
  });

  // The three midplanes at 50 are what carve the cube into eight cells. Drawn
  // as outlines, not fills: filled planes at 35% opacity turn every point
  // behind them a different colour, which breaks the severity ramp.
  const planes = [
    [[50,0,0],[50,100,0],[50,100,100],[50,0,100]],
    [[0,50,0],[100,50,0],[100,50,100],[0,50,100]],
    [[0,0,50],[100,0,50],[100,100,50],[0,100,50]],
  ];
  planes.forEach(q => {
    const pts = q.map(c => project(c[0], c[1], c[2]));
    el("polygon", {points: pts.map(v => v.x + "," + v.y).join(" "),
                   fill: "none", stroke: "var(--grid)", "stroke-width": 1,
                   "stroke-dasharray": "3 4", "stroke-opacity": 0.9}, g);
  });

  // Ticks and axis titles on three chosen edges.
  const zLabel = AXES[S.zKey].short;
  // tick: offset for the 0/50/100 numbers.  title: offset for the axis name,
  // pushed further out so it clears the tick it used to sit on top of.
  // originTick: only the x axis labels 0 - all three axes meet there and three
  // zeroes on the same point is just a smudge.
  const spec = [
    {axis: "x", from: [0,0,0], to: [100,0,0], title: AXES.efficiency.short,
     tick: [0, 16], titleAt: [0, 40], originTick: true},
    {axis: "y", from: [0,0,0], to: [0,100,0], title: AXES.removal_risk.short,
     tick: [-16, 3], titleAt: [-4, -16], titleT: 1, originTick: false},
    {axis: "z", from: [0,0,0], to: [0,0,100], title: zLabel,
     tick: [-10, 17], titleAt: [74, 26], originTick: false},
  ];
  // Which axis is pointing at the camera in each face view.
  const HIDDEN = {xy: "z", xz: "y", yz: "x"};
  spec.filter(s => HIDDEN[S.view] !== s.axis).forEach(s => {
    [0, 50, 100].forEach(t => {
      if (t === 0 && !s.originTick) return;
      const c = s.from.map((v, i) => v + (s.to[i] - v) * (t / 100));
      const q = project(c[0], c[1], c[2]);
      el("circle", {cx: q.x, cy: q.y, r: 1.6, fill: "var(--axis)"}, g);
      const lab = el("text", {x: q.x + s.tick[0], y: q.y + s.tick[1],
                              "text-anchor": "middle", "font-size": 10,
                              fill: "var(--text-muted)"}, g);
      lab.textContent = t;
    });
    const at = s.titleT == null ? 0.5 : s.titleT;
    const mid = s.from.map((v, i) => v + (s.to[i] - v) * at);
    const m = project(mid[0], mid[1], mid[2]);
    const t = el("text", {x: m.x + s.titleAt[0], y: m.y + s.titleAt[1],
                          "text-anchor": "middle", "font-size": 12,
                          "font-weight": 600, fill: "var(--text-secondary)"}, g);
    t.textContent = s.title;
  });
}

/* ---- data selection ---------------------------------------------------- */
function rows(){
  const src = S.grain === "fields" ? DATA.fields : DATA.occupations;
  return src.filter(r => r.scenario === S.scenario);
}

function visible(r){
  if (S.field && r.field !== S.field) return false;
  if (S.octant && cell(r).name !== S.octant) return false;
  return true;
}

function radius(r){
  if (S.grain === "fields") return Math.max(9, Math.min(30, Math.sqrt(r.total_employment || 0) / 62));
  return Math.max(3.2, Math.min(15, Math.sqrt(r.total_employment || 0) / 150));
}

/* ---- render ------------------------------------------------------------ */
let placed = [];
let TH = {eff: 50, risk: 50, z: 50};

/* One entry point so the thresholds are computed once, not per row. */
function refresh(){
  TH = thresholds();
  render();
  renderTable();
}

function cell(r){ return cellOf(r, TH); }

function render(){
  svg.textContent = "";
  el("rect", {x: 0, y: 0, width: W, height: H, fill: "transparent"});
  const gFrame = el("g", {});
  drawFrame(gFrame);

  const gPts = el("g", {});
  const all = rows();
  placed = all.map(r => {
    const p = project(r.efficiency, r.removal_risk, Number(r[S.zKey]) || 0);
    return {r, p, show: visible(r)};
  }).sort((a, b) => b.p.d - a.p.d);   // far first, so near marks land on top

  placed.forEach(o => {
    const rr = radius(o.r) * (isFace() ? 1 : (520 / (520 + o.p.d)));
    const dim = !o.show;
    // Depth cue is size + opacity, never hue: hue is carrying severity.
    const depthFade = isFace() ? 1 : (0.55 + 0.45 * (1 - (o.p.d + 87) / 174));
    el("circle", {
      cx: o.p.x, cy: o.p.y, r: Math.max(1.6, rr),
      fill: dim ? "var(--grid)" : "var(--sev-" + cell(o.r).severity + ")",
      "fill-opacity": dim ? 0.5 : (0.9 * depthFade).toFixed(3),
      stroke: "var(--surface-1)", "stroke-width": 1.6,
      "stroke-opacity": dim ? 0.5 : 1,
    }, gPts);
    o.rr = Math.max(1.6, rr);
  });

  // Field grain is few enough to label directly, but the seven fields sit in a
  // tight cluster, so centred labels land on top of each other. Push each one
  // out to the side its mark already leans toward, de-collide the two columns
  // vertically, and draw a leader back to the mark.
  if (S.grain === "fields") labelFields(gPts);
  syncControls();
  renderOctants();
  renderTraps();
}

const LABEL_H = 15;   // minimum vertical gap between two field labels

function labelFields(g){
  const shown = placed.filter(o => o.show);
  const sides = {left: [], right: []};
  shown.forEach(o => sides[o.p.x < CX ? "left" : "right"].push(o));
  Object.keys(sides).forEach(side => {
    const col = sides[side].slice().sort((a, b) => a.p.y - b.p.y);
    // Greedy downward push: each label sits at its mark's height unless that
    // would land within LABEL_H of the one above it.
    let last = -Infinity;
    col.forEach(o => {
      let y = o.p.y;
      if (y - last < LABEL_H) y = last + LABEL_H;
      last = y;
      o.labelY = y;
    });
    // Re-centre the column on the cloud so the push does not drift everything
    // downward when several marks share a height.
    if (col.length){
      const drift = (col[col.length - 1].labelY - col[col.length - 1].p.y) / 2;
      col.forEach(o => { o.labelY -= drift; });
    }
    col.forEach(o => {
      const dir = side === "left" ? -1 : 1;
      const lx = o.p.x + dir * (o.rr + 9);
      el("line", {x1: o.p.x + dir * o.rr, y1: o.p.y, x2: lx, y2: o.labelY,
                  stroke: "var(--axis)", "stroke-width": 1,
                  "stroke-opacity": 0.75}, g);
      const t = el("text", {x: lx + dir * 3, y: o.labelY + 3.5,
                            "text-anchor": side === "left" ? "end" : "start",
                            "font-size": 11, "font-weight": 600,
                            fill: "var(--text-primary)"}, g);
      t.textContent = o.r.field;
    });
  });
}

/* ---- hover ------------------------------------------------------------- */
/* One spatial search over projected marks rather than per-mark handlers: with
   occlusion the topmost mark is the one the reader means, and that is the last
   match in draw order. */
function pick(mx, my){
  let best = null;
  for (let i = placed.length - 1; i >= 0; i--){
    const o = placed[i];
    if (!o.show) continue;
    const dx = mx - o.p.x, dy = my - o.p.y;
    const hit = Math.max(o.rr + 5, 9);      // hit target bigger than the mark
    if (dx * dx + dy * dy <= hit * hit){ best = o; break; }
  }
  return best;
}

function fmt(n){ return n == null ? "n/a" : Number(n).toLocaleString("en-US"); }
/* Axis values always carry one decimal: a column mixing "79" and "88.7" does
   not line up, which defeats the tabular figures. */
function ax(n){ return (n == null || isNaN(n)) ? "n/a" : Number(n).toFixed(1); }

function showTip(o, ev){
  const r = o.r;
  const name = S.grain === "fields" ? r.field : r.title;
  const rowsHtml = [
    ["AI efficiency", r.efficiency],
    ["Removal risk", r.removal_risk],
    [AXES[S.zKey].short, r[S.zKey]],
  ].map(([k, v]) => "<dt>" + k + "</dt><dd>" + ax(v) + "</dd>").join("");
  tip.innerHTML = "<b>" + name + "</b>"
    + "<div style='color:var(--text-secondary)'>" + cell(r).name
    + " · " + SEV_LABELS[cell(r).severity] + "</div>"
    + "<dl>" + rowsHtml
    + "<dt>Workers</dt><dd>" + fmt(r.total_employment) + "</dd>"
    + (S.grain === "fields" ? "<dt>Occupations</dt><dd>" + r.occupations + "</dd>"
                            : "<dt>Field</dt><dd>" + r.field + "</dd>")
    + "</dl>";
  const box = svg.getBoundingClientRect();
  const sx = box.left + (o.p.x / W) * box.width;
  const sy = box.top + (o.p.y / H) * box.height;
  const wrap = document.querySelector(".plotwrap").getBoundingClientRect();
  tip.style.left = Math.min(sx - wrap.left + 14, wrap.width - 300) + "px";
  tip.style.top = (sy - wrap.top - 10) + "px";
  tip.style.opacity = 1;
}

svg.addEventListener("pointermove", ev => {
  if (drag.on){ return; }
  const box = svg.getBoundingClientRect();
  const mx = ((ev.clientX - box.left) / box.width) * W;
  const my = ((ev.clientY - box.top) / box.height) * H;
  const hit = pick(mx, my);
  if (hit) showTip(hit, ev); else tip.style.opacity = 0;
});
svg.addEventListener("pointerleave", () => { tip.style.opacity = 0; });

/* ---- drag to rotate ---------------------------------------------------- */
const drag = {on: false, x: 0, y: 0, yaw: 0, pitch: 0};
svg.addEventListener("pointerdown", ev => {
  drag.on = true; drag.x = ev.clientX; drag.y = ev.clientY;
  drag.yaw = S.yaw; drag.pitch = S.pitch;
  svg.classList.add("dragging"); tip.style.opacity = 0;
  svg.setPointerCapture(ev.pointerId);
});
svg.addEventListener("pointerup", ev => {
  drag.on = false; svg.classList.remove("dragging");
  try { svg.releasePointerCapture(ev.pointerId); } catch (e) {}
});
svg.addEventListener("pointermove", ev => {
  if (!drag.on) return;
  S.yaw = drag.yaw + (ev.clientX - drag.x) * 0.008;
  S.pitch = Math.max(-1.45, Math.min(1.45, drag.pitch + (ev.clientY - drag.y) * 0.006));
  // Any rotation leaves a face view; say so in the control state.
  if (S.view !== "3d"){ S.view = "3d"; }
  render();
});
svg.addEventListener("wheel", ev => {
  ev.preventDefault();
  S.zoom = Math.max(0.55, Math.min(2.2, S.zoom * (ev.deltaY < 0 ? 1.08 : 0.926)));
  render();
}, {passive: false});

/* ---- face views -------------------------------------------------------- */
const VIEWS = {
  "3d": {yaw: 0.62, pitch: 0.42},
  xy:   {yaw: 0, pitch: 0},              // efficiency x removal risk
  xz:   {yaw: 0, pitch: -Math.PI / 2},   // efficiency x z
  yz:   {yaw: Math.PI / 2, pitch: 0},    // z x removal risk
};
const FACE_ZOOM = 1.6;   // a 100-unit square at SCALE 3.15 fills ~500 of 620px
function setView(v){
  S.view = v; S.yaw = VIEWS[v].yaw; S.pitch = VIEWS[v].pitch;
  S.zoom = (v === "3d") ? 1 : FACE_ZOOM;
  render();
}
"""


JS2 = r"""
/* ---- the octant table (where values actually get read) ----------------- */
function renderOctants(){
  const all = rows().filter(r => !S.field || r.field === S.field);
  const body = document.getElementById("octbody");
  body.textContent = "";
  // Sum the per-occupation employment share, not the SOC figure. Employment is
  // published at 6-digit SOC and 18 of the 37 multi-occupation SOCs have members
  // in different cells; crediting each cell the full SOC figure makes the shares
  // add to 130%. security.employment_shares() splits it. See METHODOLOGY.md 6.8.
  const empOf = rs => rs.reduce((a, r) => a + (r.employment_share || 0), 0);
  const total = empOf(all);
  OCTANTS.forEach(o => {
    const mine = all.filter(r => cell(r).name === o.name);
    const emp = empOf(mine);
    const tr = document.createElement("tr");
    tr.className = "oct";
    tr.setAttribute("role", "button");
    tr.setAttribute("aria-selected", S.octant === o.name ? "true" : "false");
    tr.title = o.blurb;
    tr.innerHTML =
      "<td class='sw'><span class='dot' style='background:var(--sev-"
      + o.severity + ")'></span></td><td>" + o.name + "</td>"
      + "<td class='num'>" + mine.length + "</td>"
      + "<td class='num'>" + (total ? (100 * emp / total).toFixed(1) + "%" : "—") + "</td>";
    tr.onclick = () => { S.octant = (S.octant === o.name) ? null : o.name; render(); };
    body.appendChild(tr);
  });
  document.getElementById("octtotal").textContent =
    all.length + " " + (S.grain === "fields" ? "fields" : "occupations")
    + " · " + Number(total).toLocaleString("en-US") + " workers";
}

function renderTraps(){
  const box = document.getElementById("traps");
  const all = rows()
    .filter(r => !S.field || r.field === S.field)
    .slice().sort((a, b) => b.trap_score - a.trap_score).slice(0, 12);
  box.textContent = "";
  all.forEach(r => {
    const tr = document.createElement("tr");
    const name = S.grain === "fields" ? r.field : r.title;
    tr.innerHTML = "<td class='sw'><span class='dot' style='background:var(--sev-"
      + cell(r).severity + ")'></span></td><td>" + name + "</td>"
      + "<td class='num'>" + ax(r.efficiency) + "</td>"
      + "<td class='num'>" + ax(r.removal_risk) + "</td>"
      + "<td class='num'>" + ax(r[S.zKey]) + "</td>"
      + "<td class='num'>" + ax(r.trap_score) + "</td>";
    box.appendChild(tr);
  });
  document.getElementById("trapz").textContent = AXES[S.zKey].short;
}

/* ---- the full table (the non-visual route to every number) ------------- */
function renderTable(){
  const body = document.getElementById("tablebody");
  body.textContent = "";
  rows().filter(visible)
    .slice().sort((a, b) => b.trap_score - a.trap_score)
    .forEach(r => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + (S.grain === "fields" ? r.field : r.title) + "</td>"
        + "<td>" + (S.grain === "fields" ? r.occupations + " occ" : r.field) + "</td>"
        + "<td class='num'>" + ax(r.efficiency) + "</td>"
        + "<td class='num'>" + ax(r.removal_risk) + "</td>"
        + "<td class='num'>" + ax(r.reconstitution) + "</td>"
        + "<td>" + cell(r).name + "</td>"
        + "<td>" + SEV_LABELS[cell(r).severity] + "</td>"
        + "<td class='num'>" + fmt(r.total_employment) + "</td>";
      body.appendChild(tr);
    });
}

/* ---- controls ---------------------------------------------------------- */
function syncControls(){
  document.querySelectorAll("[data-scenario]").forEach(b =>
    b.setAttribute("aria-pressed", b.dataset.scenario === S.scenario));
  document.querySelectorAll("[data-grain]").forEach(b =>
    b.setAttribute("aria-pressed", b.dataset.grain === S.grain));
  document.querySelectorAll("[data-view]").forEach(b =>
    b.setAttribute("aria-pressed", b.dataset.view === S.view));
  document.querySelectorAll("[data-split]").forEach(b =>
    b.setAttribute("aria-pressed", b.dataset.split === S.split));
  document.getElementById("split-note").textContent = S.split === "fifty"
    ? "Cells split at 50 on every axis."
    : "Cells split at this selection's median: efficiency "
      + TH.eff.toFixed(0) + ", risk " + TH.risk.toFixed(0)
      + ", " + AXES[S.zKey].short.toLowerCase() + " " + TH.z.toFixed(0) + ".";
  document.querySelectorAll("[data-field]").forEach(b =>
    b.setAttribute("aria-pressed", (b.dataset.field || null) === S.field));
  document.getElementById("zsel").value = S.zKey;
  const v = {"3d": "Drag to rotate · scroll to zoom",
             xy: "Face view: efficiency (x) against removal risk (y). No perspective — read values here.",
             xz: "Face view: efficiency (x) against " + AXES[S.zKey].short.toLowerCase() + " (y).",
             yz: "Face view: " + AXES[S.zKey].short.toLowerCase() + " (x) against removal risk (y)."};
  document.getElementById("hint").textContent = v[S.view];
}

function wire(){
  document.querySelectorAll("[data-scenario]").forEach(b =>
    b.onclick = () => { S.scenario = b.dataset.scenario; refresh(); });
  document.querySelectorAll("[data-grain]").forEach(b =>
    b.onclick = () => { S.grain = b.dataset.grain; S.octant = null; refresh(); });
  document.querySelectorAll("[data-view]").forEach(b =>
    b.onclick = () => setView(b.dataset.view));
  document.querySelectorAll("[data-field]").forEach(b =>
    b.onclick = () => {
      const f = b.dataset.field || null;
      S.field = (S.field === f) ? null : f;
      refresh();
    });
  document.getElementById("zsel").onchange = e => {
    S.zKey = e.target.value; refresh();
  };
  document.querySelectorAll("[data-split]").forEach(b =>
    b.onclick = () => { S.split = b.dataset.split; S.octant = null; refresh(); });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape"){ S.field = null; S.octant = null; refresh(); }
  });
}

wire(); refresh();
"""


def _fields_of(rows: Sequence[dict[str, Any]]) -> list[str]:
    seen: dict[str, float] = {}
    for r in rows:
        seen[r["field"]] = seen.get(r["field"], 0.0) + float(r.get("total_employment") or 0)
    return [f for f, _ in sorted(seen.items(), key=lambda kv: -kv[1])]


def build_matrix3d(
    matrix: Sequence[dict[str, Any]],
    fields: Sequence[dict[str, Any]],
    out_path: Path,
    soc_of: dict[str, str] | None = None,
) -> Path:
    """Render the standalone interactive page."""
    soc_of = soc_of or {}

    def occ_row(r: dict[str, Any]) -> dict[str, Any]:
        keep = ("title", "field", "scenario", "octant", "severity", "trap_score",
                "efficiency", "removal_risk", "reconstitution", "scarcity",
                "training_depth", "isolation", "erosion_risk", "willingness_gap",
                "risk_at_stake", "total_employment", "employment_share",
                "job_zone")
        out = {k: r.get(k) for k in keep}
        for k in ("efficiency", "removal_risk", "reconstitution", "scarcity",
                  "training_depth", "isolation", "erosion_risk",
                  "willingness_gap", "risk_at_stake", "trap_score"):
            out[k] = None if r.get(k) in (None, "") else float(r[k])
        out["severity"] = int(r.get("severity") or 0)
        out["total_employment"] = (None if not r.get("total_employment")
                                   else float(r["total_employment"]))
        out["employment_share"] = (None if not r.get("employment_share")
                                   else float(r["employment_share"]))
        # Carry the SOC so the page can collapse employment without re-deriving it.
        out["soc"] = soc_of.get(r["onet_soc_code"], r["onet_soc_code"])
        return out

    def field_row(r: dict[str, Any]) -> dict[str, Any]:
        out = {k: r.get(k) for k in ("field", "scenario", "octant", "occupations")}
        for k in ("efficiency", "removal_risk", "reconstitution", "trap_score"):
            out[k] = float(r[k])
        out["total_employment"] = float(r.get("total_employment") or 0)
        out["employment_share"] = out["total_employment"]
        out["occupations"] = int(r.get("occupations") or 0)
        # Field aggregates only carry the three headline axes, so any z the
        # reader picks beyond those falls back to reconstitution.
        for k in ("scarcity", "training_depth", "isolation", "erosion_risk",
                  "willingness_gap", "risk_at_stake"):
            out[k] = out["reconstitution"]
        out["severity"] = _severity_of(r["octant"])
        out["title"] = r["field"]
        out["soc"] = r["field"]
        return out

    payload = {"occupations": [occ_row(r) for r in matrix],
               "fields": [field_row(r) for r in fields]}
    octants = [{"name": name, "blurb": blurb, "severity": _severity_of(name)}
               for name, blurb in sorted(OCTANTS.values(),
                                         key=lambda nb: -_severity_of(nb[0]))]
    # Keyed by the same (efficiency, risk, reconstitution) booleans
    # security.octant() switches on, so the page's cell assignment is the
    # module's, not a second implementation of it.
    by_key = {",".join("1" if b else "0" for b in key):
              {"name": name, "severity": _severity_of(name)}
              for key, (name, _) in OCTANTS.items()}

    js = (JS + JS2) \
        .replace("__DATA__", json.dumps(payload, separators=(",", ":"))) \
        .replace("__OCTANTS__", json.dumps(octants)) \
        .replace("__OCT_BY_KEY__", json.dumps(by_key)) \
        .replace("__SEV_LABELS__", json.dumps(list(SEVERITY_LABELS)))

    field_chips = "".join(
        f'<button data-field="{f}" aria-pressed="false">{f}</button>'
        for f in _fields_of(matrix))
    z_options = "".join(
        f'<option value="{k}">{v}</option>' for k, v in (
            ("reconstitution", "Reconstitution difficulty (default)"),
            ("training_depth", "· Training depth only"),
            ("scarcity", "· Workforce scarcity only"),
            ("isolation", "· Isolation from neighbours only"),
            ("erosion_risk", "Erosion risk"),
            ("willingness_gap", "Willingness gap"),
            ("risk_at_stake", "Risk of the work handed over"),
        ))
    legend = "".join(
        f'<span><i style="background:var(--sev-{i})"></i>{lab}</span>'
        for i, lab in enumerate(SEVERITY_LABELS))

    head = theme.head(
        "National security matrix \u2014 STEM work and AI",
        CSS, root_class="m3-root",
        extra_tokens=SEV_TOKENS, extra_tokens_dark=SEV_TOKENS_DARK)
    html = f"""{head}<body><div class="m3-root">
<h1>National security matrix</h1>
<p class="sub">Every STEM occupation placed on three axes at once: what AI
deployment buys, what it costs to take the human out of the loop, and how hard
the human capability would be to rebuild afterwards. The first two say whether a
handoff is attractive. The third says whether it is reversible &mdash; and that is
the question a planner actually has to answer.</p>

<div class="axes">
  <div><b>x &middot; AI efficiency</b><span>Importance-weighted share of the
    occupation's task mass AI can carry. Moves with the scenario.</span></div>
  <div><b>y &middot; Risk of removing humans</b><span>Error cost, accountability
    and judgment under uncertainty. Deliberately excludes interpersonal demand
    and physical embodiment.</span></div>
  <div><b>z &middot; Reconstitution difficulty</b><span>Training depth (Job
    Zone), workforce scarcity, and isolation from occupations that could
    cross-train in.</span></div>
</div>

<div class="controls">
  <div class="ctl"><label>Scenario</label><div class="seg">
    <button data-scenario="modest">Modest</button>
    <button data-scenario="substantial">Substantial</button>
    <button data-scenario="extreme">Extreme</button></div></div>
  <div class="ctl"><label>Grain</label><div class="seg">
    <button data-grain="occupations">Occupations</button>
    <button data-grain="fields">Fields</button></div></div>
  <div class="ctl"><label>View</label><div class="seg">
    <button data-view="3d">3D</button>
    <button data-view="xy">Eff &times; Risk</button>
    <button data-view="xz">Eff &times; Z</button>
    <button data-view="yz">Z &times; Risk</button></div></div>
  <div class="ctl"><label for="zsel">Z axis</label>
    <select id="zsel">{z_options}</select></div>
  <div class="ctl"><label>Split cells at</label><div class="seg">
    <button data-split="fifty">50</button>
    <button data-split="median">Median</button></div></div>
</div>
<p class="hint" id="split-note" style="margin:-6px 0 14px"></p>
<div class="controls" style="margin-top:-6px">
  <div class="ctl"><label>Field &mdash; click to isolate, Esc to clear</label>
    <div class="chips">{field_chips}</div></div>
</div>

<div class="layout">
  <div>
    <div class="plotwrap">
      <svg id="plot" viewBox="0 0 760 620" role="img"
           aria-label="Three-dimensional scatter of STEM occupations by AI
           efficiency, risk of removing humans, and reconstitution difficulty.
           The same values are in the table below."></svg>
      <div class="tip" id="tip"></div>
    </div>
    <p class="hint" id="hint"></p>
    <div class="legend">{legend}
      <span style="color:var(--text-muted)">&middot; mark size = workers</span></div>
  </div>
  <div class="side">
    <h2>The eight cells</h2>
    <table><thead><tr><th class="sw"></th><th>Cell</th><th class="num">n</th>
      <th class="num">Workers</th></tr></thead>
      <tbody id="octbody"></tbody></table>
    <p class="hint" id="octtotal"></p>
    <h2 style="margin-top:22px">Highest combined exposure</h2>
    <table><thead><tr><th class="sw"></th><th>Name</th><th class="num">Eff</th><th class="num">Risk</th>
      <th class="num" id="trapz">Z</th><th class="num">Score</th></tr></thead>
      <tbody id="traps"></tbody></table>
  </div>
</div>

<details>
  <summary>All values as a table</summary>
  <div class="scroll"><table><thead><tr>
    <th>Name</th><th>Field</th><th class="num">Efficiency</th>
    <th class="num">Removal risk</th><th class="num">Reconstitution</th>
    <th>Cell</th><th>Severity</th><th class="num">Workers</th>
  </tr></thead><tbody id="tablebody"></tbody></table></div>
</details>

<p class="note">A 3D scatter is a poor instrument for reading exact values:
near marks hide far ones and depth is ambiguous. That is why the three face
views exist &mdash; they drop perspective and give an axis-aligned 2D scatter, which
is where values should be read. The 3D view is for the shape of the cloud.
Colour encodes severity on a validated single-hue ordinal ramp, not field;
position already carries all three axes, and seven fields cannot be given seven
distinguishable hues. Employment is collapsed to 6-digit SOC before any sum.</p>
</div>
<script>{js}</script>
</body></html>
"""
    out_path.write_text(html)
    log.info("wrote %s  %.0f KB", out_path.name, len(html) / 1024)
    return out_path


def _severity_of(octant_name: str) -> int:
    from .security import severity
    return severity(octant_name)
