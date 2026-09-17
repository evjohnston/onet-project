"""A single self-contained HTML dashboard: no build step, no CDN, no server.

Open the file and it works offline. Data is embedded as JSON; charts are plain
SVG drawn by a small amount of vanilla JS.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger(__name__)

TEMPLATE_HEAD = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>STEM work &amp; automation susceptibility</title>
<style>
/* Palette roles - light and dark are each selected steps, not an auto-flip. */
.viz-root {
  color-scheme: light;
  --surface-1: #fcfcfb; --surface-2: #f4f3f0; --surface-3: #eceae6;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #85837c;
  --grid: #e2e0da; --axis: #c9c6be;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
  --div-low: #2a78d6; --div-mid: #f0efec; --div-high: #e34948;
  --seq-1: #cde2fb; --seq-2: #9ec5f4; --seq-3: #5598e7; --seq-4: #2a78d6;
  --seq-5: #256abf; --seq-6: #184f95; --seq-7: #0d366b;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --surface-2: #232321; --surface-3: #2d2d2a;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #918f85;
    --grid: #333330; --axis: #4a4a45;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
    --div-low: #3987e5; --div-mid: #383835; --div-high: #e66767;
  }
}
:root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-1: #1a1a19; --surface-2: #232321; --surface-3: #2d2d2a;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #918f85;
  --grid: #333330; --axis: #4a4a45;
  --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70;
  --div-low: #3987e5; --div-mid: #383835; --div-high: #e66767;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface-2); }
.viz-root {
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--surface-2); color: var(--text-primary);
  padding: 28px 32px 64px; min-height: 100vh;
}
h1 { font-size: 22px; margin: 0 0 4px; font-weight: 650; letter-spacing: -0.01em; }
h2 { font-size: 15px; margin: 0 0 2px; font-weight: 620; }
.sub { color: var(--text-secondary); font-size: 13px; margin: 0 0 22px; max-width: 78ch; }
.note { color: var(--text-muted); font-size: 12px; margin: 6px 0 0; max-width: 84ch; }
.card { background: var(--surface-1); border: 1px solid var(--grid);
        border-radius: 10px; padding: 18px 20px; margin-bottom: 18px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 18px; }
.kpi { background: var(--surface-1); border: 1px solid var(--grid); border-radius: 10px; padding: 14px 16px; }
.kpi .v { font-size: 30px; font-weight: 640; letter-spacing: -0.02em; line-height: 1.1; }
.kpi .l { color: var(--text-secondary); font-size: 12px; margin-top: 3px; }
.controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 16px; }
select, button, input { font: inherit; padding: 6px 10px; border-radius: 7px;
  border: 1px solid var(--axis); background: var(--surface-1); color: var(--text-primary); }
button { cursor: pointer; }
button.active { background: var(--series-1); color: #fff; border-color: var(--series-1); }
.legend { display: flex; gap: 14px; flex-wrap: wrap; align-items: center;
          font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }
.sw { width: 11px; height: 11px; border-radius: 3px; display: inline-block; margin-right: 5px; vertical-align: -1px; }
table { border-collapse: collapse; width: 100%; font-size: 12.5px; }
th, td { text-align: left; padding: 6px 9px; border-bottom: 1px solid var(--grid); }
th { color: var(--text-secondary); font-weight: 600; cursor: pointer; user-select: none;
     position: sticky; top: 0; background: var(--surface-1); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.scroll { max-height: 440px; overflow: auto; }
.tip { position: fixed; pointer-events: none; opacity: 0; transition: opacity .1s;
  background: var(--surface-1); border: 1px solid var(--axis); border-radius: 8px;
  padding: 9px 11px; font-size: 12.5px; max-width: 330px; z-index: 50;
  box-shadow: 0 6px 20px rgba(0,0,0,.18); color: var(--text-primary); }
.tip b { display: block; margin-bottom: 4px; font-size: 13px; }
.tip .r { display: flex; justify-content: space-between; gap: 18px; color: var(--text-secondary); }
.tip .r span:last-child { color: var(--text-primary); font-variant-numeric: tabular-nums; }
.pill { display: inline-block; padding: 1px 7px; border-radius: 20px; font-size: 11px;
        background: var(--surface-3); color: var(--text-secondary); }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 1000px) { .grid2 { grid-template-columns: 1fr; } }
.topbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
.card { position: relative; }
.png { position: absolute; top: 14px; right: 16px; font-size: 11px; padding: 3px 9px;
       opacity: .45; transition: opacity .15s; }
.card:hover .png { opacity: 1; }
.pending { color: var(--text-muted); font-size: 12.5px; padding: 26px 0; }
text { font-family: inherit; }
</style></head>
<body><div class="viz-root">
<div class="topbar">
  <div>
    <h1>Which STEM work is susceptible to automation</h1>
    <p class="sub">__SUBTITLE__</p>
  </div>
  <button id="theme" title="Toggle light/dark">&#9681; Theme</button>
</div>
"""

TEMPLATE_TAIL = """
<div class="tip" id="tip"></div>
</div>
<script>
const DATA = __DATA__;
const $ = s => document.querySelector(s);
const tip = $('#tip');
const NS = 'http://www.w3.org/2000/svg';
const el = (n, a = {}) => { const e = document.createElementNS(NS, n);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const css = v => getComputedStyle($('.viz-root')).getPropertyValue(v).trim();
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

/* Diverging blue->gray->red, anchored on the neutral midpoint. */
function divergingColor(v, mid = 50, span = 26) {
  const t = Math.max(-1, Math.min(1, (v - mid) / span));
  const lo = css('--div-low'), hi = css('--div-high'), md = css('--div-mid');
  return mix(md, t >= 0 ? hi : lo, Math.abs(t));
}
function mix(a, b, t) {
  const p = h => { h = h.replace('#',''); return [0,2,4].map(i => parseInt(h.slice(i,i+2),16)); };
  const [r1,g1,b1] = p(a), [r2,g2,b2] = p(b);
  const c = (x,y) => Math.round(x + (y - x) * t).toString(16).padStart(2,'0');
  return `#${c(r1,r2)}${c(g1,g2)}${c(b1,b2)}`;
}
function showTip(e, html) {
  tip.innerHTML = html; tip.style.opacity = 1;
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
const hideTip = () => tip.style.opacity = 0;
const row = (k, v) => `<div class="r"><span>${k}</span><span>${v}</span></div>`;

__SCRIPTS__

$('#theme').onclick = () => {
  const cur = document.documentElement.getAttribute('data-theme');
  const isDark = cur ? cur === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
  renderAll();
};
addEventListener('resize', () => { clearTimeout(window._rz);
  window._rz = setTimeout(renderAll, 200); });

/* Export any chart as PNG: serialise the SVG, paint it to a canvas at 2x for a
   crisp raster, and hand back a download. No server, no library. */
function svgToPng(svg, filename, scale) {
  scale = scale || 2;
  const clone = svg.cloneNode(true);
  const W = +svg.getAttribute('width'), H = +svg.getAttribute('height');
  clone.setAttribute('xmlns', NS);
  // Inline the resolved surface colour - the SVG has no stylesheet once detached.
  const bg = css('--surface-1');
  const rect = document.createElementNS(NS, 'rect');
  rect.setAttribute('width', W); rect.setAttribute('height', H); rect.setAttribute('fill', bg);
  clone.insertBefore(rect, clone.firstChild);
  clone.querySelectorAll('text').forEach(t => {
    if (!t.getAttribute('font-family')) t.setAttribute('font-family', 'Helvetica, Arial, sans-serif');
  });
  const blob = new Blob([new XMLSerializer().serializeToString(clone)],
                        {type: 'image/svg+xml;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const img = new Image();
  img.onload = () => {
    const cv = document.createElement('canvas');
    cv.width = W*scale; cv.height = H*scale;
    const ctx = cv.getContext('2d');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    cv.toBlob(b => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(b); a.download = filename + '.png';
      a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    });
  };
  img.src = url;
}

function addPngButtons() {
  document.querySelectorAll('.card').forEach(card => {
    if (card.querySelector('.png')) return;
    const svg = card.querySelector('svg');
    if (!svg) return;
    const name = (card.querySelector('h2')?.textContent || 'chart')
      .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 48);
    const b = document.createElement('button');
    b.className = 'btn png'; b.textContent = 'PNG';
    b.title = 'Download this chart as a PNG';
    b.onclick = () => {
      const svgs = [...card.querySelectorAll('svg')];
      svgs.forEach((s, i) => svgToPng(s, svgs.length > 1 ? `${name}-${i+1}` : name));
    };
    card.appendChild(b);
  });
}

/* Render in stages, yielding to the browser between each, so the page paints
   immediately instead of waiting on the whole batch. */
function renderAll() {
  const steps = [renderKpis, renderAnswer, renderFrontier, renderStages,
                 renderScatter, renderBars, renderDumbbell, renderEmployment,
                 renderValidation, renderNetwork, renderLeverage,
                 renderSub, renderTasks];
  let i = 0;
  (function step() {
    if (i >= steps.length) { addPngButtons(); return; }
    try { steps[i](); } catch (err) { console.error('chart failed:', err); }
    i++;
    // setTimeout, not requestAnimationFrame: rAF does not advance under
    // headless Chrome's virtual clock, so screenshots caught a half-drawn page.
    setTimeout(step, 0);
  })();
}
renderAll();
</script></body></html>
"""


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_dashboard(
    path: Path,
    occupations: Sequence[dict[str, Any]],
    tasks: Sequence[dict[str, Any]],
    subtasks: Sequence[dict[str, Any]],
    splits: dict[str, float],
    meta: dict[str, Any],
    soc: Sequence[dict[str, Any]] | None = None,
    employment: dict[str, Any] | None = None,
    benchmarks: Sequence[dict[str, Any]] | None = None,
    net_edges: Sequence[dict[str, Any]] | None = None,
    net_nodes: Sequence[dict[str, Any]] | None = None,
    handoff: Sequence[dict[str, Any]] | None = None,
    dimensions: Sequence[dict[str, Any]] | None = None,
) -> Path:
    layout = {n["onet_soc_code"]: (_f(n, "layout_x", -1), _f(n, "layout_y", -1))
              for n in (net_nodes or [])}
    occ = [
        {
            "c": o["onet_soc_code"], "t": o["title"],
            "ty": (o.get("stem_occupation_types") or "").split(";")[0].strip(),
            "s": _f(o, "susceptibility"), "e": _f(o, "exposure"),
            "a": _f(o, "anchoring"), "g": _f(o, "deployment_gap"),
            "hi": _f(o, "share_tasks_high_susceptibility"),
            "n": int(_f(o, "n_tasks_scored")), "q": o.get("quadrant", ""),
            "z": o.get("job_zone") or "",
            "x": layout.get(o["onet_soc_code"], (-1, -1))[0],
            "y": layout.get(o["onet_soc_code"], (-1, -1))[1],
        }
        for o in occupations
    ]
    tsk = [
        {
            "c": t["onet_soc_code"], "t": t["task"][:200],
            "s": _f(t, "susceptibility"), "e": _f(t, "exposure"),
            "a": _f(t, "anchoring"), "g": _f(t, "deployment_gap"),
            "i": _f(t, "importance"), "k": t.get("task_category") or "",
            "v": t.get("dominant_verdict", ""),
        }
        for t in tasks
    ]
    sub = [
        {
            "d": s["dwa_id"], "t": s["dwa_title"],
            "s": _f(s, "susceptibility"), "e": _f(s, "exposure"),
            "a": _f(s, "anchoring"), "g": _f(s, "deployment_gap"),
            "no": int(_f(s, "n_occupations")), "nt": int(_f(s, "n_tasks")),
            "v": s.get("verdict", ""), "r": (s.get("rationale") or "")[:240],
        }
        for s in subtasks
    ]
    soc_rows = [
        {
            "c": r["soc_code"], "t": r["soc_title"],
            "s": _f(r, "susceptibility"), "e": _f(r, "exposure"),
            "a": _f(r, "anchoring"), "q": r.get("quadrant", ""),
            "emp": _f(r, "total_employment"), "wage": _f(r, "annual_mean_wage"),
            "nd": int(_f(r, "n_onet_occupations", 1)),
            "sd": _f(r, "susceptibility_sd_within_soc"),
        }
        for r in (soc or []) if r.get("total_employment")
    ]
    val = [
        {"c": b["onet_soc_code"], "t": b["title"], "s": _f(b, "our_susceptibility"),
         "hg": _f(b, "human_gamma", -1), "hb": _f(b, "human_beta", -1),
         "fo": _f(b, "frey_osborne", -1)}
        for b in (benchmarks or [])
        if b.get("our_susceptibility") not in (None, "")
    ]
    # A top-3-neighbours-per-node backbone: all 4,656 edges render as a hairball.
    keep: set[tuple[str, str]] = set()
    per_node: dict[str, list[tuple[float, str]]] = {}
    for e in (net_edges or []):
        c = _f(e, "cosine")
        per_node.setdefault(e["source"], []).append((c, e["target"]))
        per_node.setdefault(e["target"], []).append((c, e["source"]))
    for node, lst in per_node.items():
        for c, other in sorted(lst, reverse=True)[:3]:
            keep.add(tuple(sorted((node, other))))
    net = [{"s": a, "t": b} for a, b in sorted(keep)]

    DIMS = ("automation_feasibility_today", "llm_exposure", "physical_embodiment_required",
            "interpersonal_demand", "judgment_under_uncertainty",
            "accountability_requirement", "error_cost")
    dims = {d["onet_soc_code"]: [_f(d, k) for k in DIMS] for d in (dimensions or [])}

    hand = [
        {"c": h["onet_soc_code"], "t": h["title"],
         "T": _f(h, "tractability"), "R": _f(h, "resistance"),
         "now": int(_f(h, "stage_now")), "reach": int(_f(h, "stage_reachable")),
         "nowL": h.get("stage_now_label", ""), "reachL": h.get("stage_reachable_label", ""),
         "gap": _f(h, "willingness_gap"), "cls": h.get("classification", ""),
         "ero": _f(h, "erosion_risk"), "sur": _f(h, "surprise_potential"),
         "emp": _f(h, "total_employment", 0), "wx": h.get("weighty_crossing", ""),
         "ty": (h.get("stem_occupation_types") or "").split(";")[0].strip()}
        for h in (handoff or [])
    ]
    payload = {"hand": hand,
               "occ": occ, "task": tsk, "sub": sub, "splits": splits, "meta": meta,
               "soc": soc_rows, "emp": employment or {}, "val": val, "net": net,
               "dims": dims, "dimNames": [
                   "Automatable today", "LLM exposure", "Physical embodiment",
                   "Interpersonal demand", "Judgment under uncertainty",
                   "Accountability required", "Error cost"]}

    subtitle = (
        f"{len(occ)} STEM occupations &middot; {len(tsk):,} tasks &middot; {len(sub)} distinct subtasks. "
        f"Every task rated through the subtask it belongs to, by {meta.get('model','a model')}. "
        "<strong>Exposure</strong> is whether a machine could do the work; "
        "<strong>anchoring</strong> is whether a human must. Susceptibility is the gap between them "
        "&mdash; positions are relative to other STEM occupations, not absolute risk."
    )

    html = (TEMPLATE_HEAD.replace("__SUBTITLE__", subtitle)
            + _BODY
            + TEMPLATE_TAIL.replace("__DATA__", json.dumps(payload, separators=(",", ":")))
                           .replace("__SCRIPTS__", _SCRIPTS + _EMP_SCRIPT + _VIZ2_SCRIPT + _HANDOFF_SCRIPT))
    path.write_text(html, encoding="utf-8")
    log.info("wrote %-28s %.1f MB", path.name, path.stat().st_size / 1e6)
    return path


_BODY = """
<div class="kpis" id="kpis"></div>

<div class="card" id="card-answer">
  <h2>Which jobs are most exposed to displacement</h2>
  <p class="note">Pick the question you actually want answered &mdash; the ranking changes a
  lot depending on which one it is. Click any row to load that occupation's tasks and
  dimension profile at the bottom of the page.</p>
  <div class="controls">
    <label>Rank by
      <select id="a-metric">
        <option value="s">Susceptibility (exposure net of anchoring)</option>
        <option value="gap">Willingness gap (capability minus deployment)</option>
        <option value="ero">Erosion risk (crossing without an event)</option>
        <option value="sur">Surprise potential (Watson)</option>
        <option value="emp">Workers in the occupation</option>
        <option value="empatrisk">Workers &times; susceptibility</option>
      </select>
    </label>
    <label>Handoff class
      <select id="a-cls"><option value="">All</option></select>
    </label>
    <label>STEM type
      <select id="a-type"><option value="">All</option></select>
    </label>
    <label><input type="checkbox" id="a-emp" style="vertical-align:-2px"> Only jobs with
      employment data</label>
    <input id="a-q" placeholder="Search..." style="min-width:170px">
    <span class="pill" id="a-n"></span>
  </div>
  <div class="scroll" style="max-height:520px"><table id="t-answer"></table></div>
</div>

<div class="card" id="card-frontier">
  <h2>The handoff frontier</h2>
  <p class="note"><strong>Tractability</strong> (right) is whether AI can lead the work;
  <strong>resistance</strong> (up) is whether it will be permitted to. The curve is the
  frontier &mdash; the resistance a given tractability can currently overcome. Work below it
  has crossed; work above it is still human-held. Framework from Watson (2026);
  axis positions are relative to other STEM occupations, and the curve is calibrated to
  this corpus, not derived from theory.</p>
  <div class="legend" id="frontier-legend"></div>
  <div id="frontier"></div>
</div>

<div class="card" id="card-stages">
  <h2>Where cognitive leadership sits, and where it could</h2>
  <p class="note">Watson's six-stage scale. The light dot is how many occupations sit at each
  stage given what is actually deployed today; the dark dot is where current AI capability
  could already put them. The distance between the two is pending handoff.
  He expects two crossings to carry most of the strategic weight: proposing action to taking
  it, and human veto to after-the-fact audit &mdash; the second being a crossing by erosion,
  with no event to observe.</p>
  <div class="legend">
    <span><span class="sw" style="background:var(--seq-2)"></span>Occupations at this stage today</span>
    <span><span class="sw" style="background:var(--seq-6)"></span>Where capability could put them</span>
  </div>
  <div id="stages"></div>
</div>

<div class="card" id="card-scatter">
  <h2>Where each occupation sits</h2>
  <p class="note">Each dot is one occupation, placed by the importance-weighted average of its
  tasks. Right = a machine could do more of this work. Up = more of it requires a human to do it
  or answer for it. The dividing lines are the medians across these STEM occupations, so a
  quadrant label means "relative to other STEM work", not "safe" or "doomed".
  Dot size = number of scored tasks. Click a dot to load that occupation's tasks below.</p>
  <div class="controls">
    <label>STEM type
      <select id="f-type"><option value="">All</option></select>
    </label>
    <label>Highlight
      <select id="f-hl">
        <option value="">None</option>
        <option value="Displaceable">Displaceable</option>
        <option value="Contested">Contested</option>
        <option value="Human-anchored">Human-anchored</option>
        <option value="Insulated">Insulated</option>
      </select>
    </label>
    <input id="f-q" placeholder="Search occupations..." style="min-width:210px">
    <span class="pill" id="scatter-n"></span>
  </div>
  <div class="legend">
    <span><span class="sw" style="background:var(--div-low)"></span>Lower susceptibility</span>
    <span><span class="sw" style="background:var(--div-mid);border:1px solid var(--axis)"></span>Median</span>
    <span><span class="sw" style="background:var(--div-high)"></span>Higher susceptibility</span>
  </div>
  <div id="scatter"></div>
</div>

<div class="card" id="val-card" style="display:none">
  <h2>Does this agree with anyone else?</h2>
  <p class="note" id="val-note"></p>
  <div class="grid2">
    <div>
      <h2 style="font-size:13px;margin-bottom:6px">vs. human expert ratings</h2>
      <div id="val-human"></div>
    </div>
    <div>
      <h2 style="font-size:13px;margin-bottom:6px">vs. Frey &amp; Osborne (2013)</h2>
      <div id="val-frey"></div>
    </div>
  </div>
  <p class="note">Left: agreement with human annotators is the evidence the index measures
  what it claims. Right: the pre-LLM measure disagrees, and should &mdash; Frey &amp; Osborne
  scored the routine/manual gradient, while LLMs land hardest on non-routine cognitive work
  they called safe. A tight line on the right would have been the warning sign.</p>
</div>

<div class="card" id="card-network">
  <h2>The occupation network</h2>
  <p class="note">Occupations linked to their three most similar peers by shared subtasks
  (575 of 4,656 edges &mdash; the full graph is a hairball). Position is force-directed, so
  clusters are groups of occupations that do the same kind of work. Colour is
  susceptibility. Click a node to load its tasks.</p>
  <div class="legend">
    <span><span class="sw" style="background:var(--div-low)"></span>Lower susceptibility</span>
    <span><span class="sw" style="background:var(--div-high)"></span>Higher susceptibility</span>
    <span style="color:var(--text-muted)">Dot size = tasks scored</span>
  </div>
  <div id="network"></div>
</div>

<div class="card" id="card-leverage">
  <h2>Which subtasks have the most leverage</h2>
  <p class="note">A susceptible subtask used by 50 occupations matters far more than one used
  by a single job. Up and to the right = automatable <em>and</em> widespread &mdash; the
  activities whose automation would touch the most of STEM work.</p>
  <div id="leverage"></div>
</div>

<div class="grid2" id="grid-bars">
  <div class="card" id="card-bars-top">
    <h2>Most susceptible occupations</h2>
    <p class="note">High exposure, low human anchoring.</p>
    <div id="bars-top"></div>
  </div>
  <div class="card" id="card-bars-bot">
    <h2>Least susceptible occupations</h2>
    <p class="note">Work a human must do, or answer for.</p>
    <div id="bars-bot"></div>
  </div>
</div>

<div class="card" id="card-dumbbell">
  <h2>Capability is ahead of deployment</h2>
  <p class="note">The left dot is what today's deployed technology can actually do; the right dot
  is what a current model could do in principle. The gap is where change is pending rather than
  finished &mdash; these are the near-term candidates, not the already-automated ones.</p>
  <div class="legend">
    <span><span class="sw" style="background:var(--seq-2)"></span>Automatable today</span>
    <span><span class="sw" style="background:var(--seq-6)"></span>Within current AI capability</span>
  </div>
  <div id="dumbbell"></div>
</div>

<div class="card" id="emp-card" style="display:none">
  <h2>Weighted by how many people actually do the work</h2>
  <p class="note" id="emp-note"></p>
  <div class="kpis" id="emp-kpis" style="margin-bottom:14px"></div>
  <div class="grid2">
    <div>
      <h2 style="font-size:13px;margin-bottom:6px">Workers by quadrant</h2>
      <div id="emp-quad"></div>
    </div>
    <div>
      <h2 style="font-size:13px;margin-bottom:6px">Most workers in susceptible occupations</h2>
      <div id="emp-bars"></div>
    </div>
  </div>
  <p class="note">These charts are at the 6-digit SOC level, not the O*NET level used
  above. BLS reports employment per SOC, and several O*NET occupations roll into one
  SOC &mdash; attaching SOC employment to each O*NET row would count the same workers
  repeatedly (3.4 million registered nurses, five times over). Susceptibility is
  averaged across an SOC's O*NET occupations before the employment is attached once.</p>
</div>

<div class="card" id="card-subtasks">
  <h2>Subtasks ranked by susceptibility</h2>
  <p class="note">The shared vocabulary underneath every task. <strong>Jobs</strong> is how many
  occupations use this subtask &mdash; a highly susceptible subtask used by 50 occupations matters
  far more than one used by a single job. Click a column to sort.</p>
  <div class="controls">
    <input id="f-sub" placeholder="Search subtasks..." style="min-width:260px">
    <span class="pill" id="sub-n"></span>
  </div>
  <div class="scroll"><table id="t-sub"></table></div>
</div>

<div class="card" id="card-tasks">
  <h2 id="task-title">Tasks &mdash; click an occupation above</h2>
  <p class="note">Task-level scores, inherited from the subtasks each task maps to.
  Sorted by susceptibility.</p>
  <div id="profile" style="margin-bottom:14px"></div>
  <p class="note" style="margin-top:0;margin-bottom:12px">Bars are this occupation's seven
  rated dimensions; the vertical tick is the median across all 268 STEM occupations.</p>
  <div class="scroll"><table id="t-task"></table></div>
</div>
"""

_SCRIPTS = """
let SEL = DATA.occ[0] || null, SUBSORT = {k:'s', d:-1}, TASKSORT = {k:'s', d:-1};

function filteredOcc() {
  const ty = $('#f-type').value, q = $('#f-q').value.toLowerCase();
  return DATA.occ.filter(o => (!ty || o.ty === ty) && (!q || o.t.toLowerCase().includes(q)));
}

function renderKpis() {
  const o = DATA.occ, t = DATA.task, s = DATA.sub;
  const hi = t.filter(x => x.s >= 70).length;
  const gap = t.filter(x => x.g > 45).length;
  const anchored = o.filter(x => x.q === 'Human-anchored').length;
  const disp = o.filter(x => x.q === 'Displaceable').length;
  const k = [
    [o.length, 'occupations scored'],
    [t.length.toLocaleString(), 'tasks scored'],
    [Math.round(100*hi/t.length) + '%', 'tasks highly susceptible'],
    [Math.round(100*gap/t.length) + '%', 'tasks where capability<br>outruns deployment'],
    [disp, 'occupations in the<br>displaceable quadrant'],
    [anchored, 'occupations human-anchored'],
  ];
  $('#kpis').innerHTML = k.map(([v,l]) =>
    `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
}

function renderScatter() {
  const host = $('#scatter'); host.innerHTML = '';
  const data = filteredOcc();
  const hl = $('#f-hl').value;
  $('#scatter-n').textContent = data.length + ' shown';
  const W = host.clientWidth || 900, H = 470;
  const m = {t: 16, r: 20, b: 46, l: 58};
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xs = v => m.l + (v - 10) / 80 * iw;
  const ys = v => m.t + ih - (v - 10) / 70 * ih;
  const svg = el('svg', {width: W, height: H, role: 'img',
    'aria-label': 'Occupations plotted by AI exposure against human anchoring'});

  for (let v = 20; v <= 90; v += 10) {
    svg.appendChild(el('line', {x1: xs(v), x2: xs(v), y1: m.t, y2: m.t+ih,
      stroke: css('--grid'), 'stroke-width': 1}));
    const tx = el('text', {x: xs(v), y: H-26, 'text-anchor':'middle',
      fill: css('--text-muted'), 'font-size': 11}); tx.textContent = v; svg.appendChild(tx);
  }
  for (let v = 20; v <= 80; v += 10) {
    svg.appendChild(el('line', {x1: m.l, x2: m.l+iw, y1: ys(v), y2: ys(v),
      stroke: css('--grid'), 'stroke-width': 1}));
    const ty = el('text', {x: m.l-9, y: ys(v)+4, 'text-anchor':'end',
      fill: css('--text-muted'), 'font-size': 11}); ty.textContent = v; svg.appendChild(ty);
  }
  const sp = DATA.splits;
  for (const [x1,y1,x2,y2] of [[xs(sp.x_split),m.t,xs(sp.x_split),m.t+ih],
                               [m.l,ys(sp.y_split),m.l+iw,ys(sp.y_split)]])
    svg.appendChild(el('line', {x1,y1,x2,y2, stroke: css('--axis'),
      'stroke-width': 1.5, 'stroke-dasharray': '5 4'}));

  const q = [['Insulated', m.l+12, m.t+ih-10, 'start'],
             ['Displaceable', m.l+iw-12, m.t+ih-10, 'end'],
             ['Human-anchored', m.l+12, m.t+14, 'start'],
             ['Contested', m.l+iw-12, m.t+14, 'end']];
  for (const [lab,x,y,an] of q) {
    const t = el('text', {x, y, 'text-anchor': an, fill: css('--text-muted'),
      'font-size': 11, 'font-weight': 600, 'letter-spacing': '.03em'});
    t.textContent = lab.toUpperCase(); svg.appendChild(t);
  }
  const ax = el('text', {x: m.l+iw/2, y: H-6, 'text-anchor':'middle',
    fill: css('--text-secondary'), 'font-size': 12});
  ax.textContent = 'AI capability exposure \\u2192'; svg.appendChild(ax);
  const ay = el('text', {x: 14, y: m.t+ih/2, 'text-anchor':'middle',
    fill: css('--text-secondary'), 'font-size': 12,
    transform: `rotate(-90 14 ${m.t+ih/2})`});
  ay.textContent = 'Human anchoring \\u2192'; svg.appendChild(ay);

  for (const o of data) {
    const dim = hl && o.q !== hl;
    const c = el('circle', {cx: xs(o.e), cy: ys(o.a), r: Math.max(4, Math.sqrt(o.n)*1.15),
      fill: dim ? css('--surface-3') : divergingColor(o.s),
      stroke: css('--surface-1'), 'stroke-width': 2,
      opacity: dim ? .45 : .92, cursor: 'pointer'});
    c.addEventListener('mousemove', e => showTip(e,
      `<b>${esc(o.t)}</b>${row('Susceptibility', o.s)}${row('Exposure', o.e)}` +
      `${row('Anchoring', o.a)}${row('Deployment gap', '+' + o.g)}` +
      `${row('Tasks scored', o.n)}${row('Quadrant', o.q)}`));
    c.addEventListener('mouseleave', hideTip);
    c.addEventListener('click', () => { SEL = o; hideTip(); renderTasks(); 
      document.getElementById('task-title').scrollIntoView({behavior:'smooth', block:'center'}); });
    svg.appendChild(c);
  }
  // Direct-label only the extremes: a label on every point is unreadable.
  const lab = [...data].sort((a,b) => b.s-a.s).slice(0,3)
      .concat([...data].sort((a,b) => a.s-b.s).slice(0,3));
  // Greedy vertical de-collision: extreme points cluster, so raw placement overlaps.
  const placed = [];
  for (const o of lab.sort((a,b) => ys(a.a) - ys(b.a))) {
    const r = Math.max(4, Math.sqrt(o.n)*1.15);
    let y = ys(o.a) - r - 5;
    while (placed.some(p => Math.abs(p.y - y) < 12 && Math.abs(p.x - xs(o.e)) < 110))
      y -= 12;
    placed.push({x: xs(o.e), y});
    const t = el('text', {x: xs(o.e), y, 'text-anchor':'middle',
      fill: css('--text-secondary'), 'font-size': 10.5});
    t.textContent = o.t.length > 30 ? o.t.slice(0,29) + '\\u2026' : o.t;
    svg.appendChild(t);
  }
  host.appendChild(svg);
}

function barChart(hostId, rows, valueKey, labelKey) {
  const host = $(hostId); host.innerHTML = '';
  const W = host.clientWidth || 440, rowH = 23, m = {t: 6, r: 44, b: 20, l: 200};
  const maxChars = Math.max(12, Math.floor((m.l - 12) / 6.1));
  const H = m.t + rows.length*rowH + m.b;
  const iw = W - m.l - m.r;
  const max = 100;
  const svg = el('svg', {width: W, height: H, role: 'img'});
  rows.forEach((d, i) => {
    const y = m.t + i*rowH, w = Math.max(2, d[valueKey]/max*iw);
    const g = el('g', {cursor: 'pointer'});
    g.appendChild(el('rect', {x: m.l, y: y+3, width: w, height: rowH-9, rx: 4,
      fill: divergingColor(d[valueKey]), stroke: css('--axis'), 'stroke-width': 1}));
    const lt = el('text', {x: m.l-9, y: y+rowH/2+3, 'text-anchor':'end',
      fill: css('--text-primary'), 'font-size': 11.5});
    lt.textContent = d[labelKey].length > maxChars
      ? d[labelKey].slice(0, maxChars-1)+'\\u2026' : d[labelKey];
    g.appendChild(lt);
    const vt = el('text', {x: m.l+w+7, y: y+rowH/2+3, fill: css('--text-secondary'),
      'font-size': 11.5}); vt.textContent = d[valueKey].toFixed(0); g.appendChild(vt);
    g.addEventListener('mousemove', e => showTip(e, `<b>${esc(d.t)}</b>` +
      row('Susceptibility', d.s) + row('Exposure', d.e) + row('Anchoring', d.a) +
      row('Tasks', d.n) + row('Quadrant', d.q)));
    g.addEventListener('mouseleave', hideTip);
    g.addEventListener('click', () => { SEL = d; renderTasks();
      document.getElementById('task-title').scrollIntoView({behavior:'smooth', block:'center'}); });
    svg.appendChild(g);
  });
  host.appendChild(svg);
}

function renderBars() {
  const d = filteredOcc();
  barChart('#bars-top', [...d].sort((a,b) => b.s-a.s).slice(0,15), 's', 't');
  barChart('#bars-bot', [...d].sort((a,b) => a.s-b.s).slice(0,15), 's', 't');
}

function renderDumbbell() {
  const host = $('#dumbbell'); host.innerHTML = '';
  const rows = [...filteredOcc()].sort((a,b) => b.g-a.g).slice(0,18);
  const W = host.clientWidth || 900, rowH = 25, m = {t: 8, r: 46, b: 26, l: 230};
  const H = m.t + rows.length*rowH + m.b, iw = W - m.l - m.r;
  const xs = v => m.l + v/100*iw;
  const svg = el('svg', {width: W, height: H, role: 'img'});
  for (let v = 0; v <= 100; v += 20) {
    svg.appendChild(el('line', {x1: xs(v), x2: xs(v), y1: m.t, y2: m.t+rows.length*rowH,
      stroke: css('--grid'), 'stroke-width': 1}));
    const t = el('text', {x: xs(v), y: H-8, 'text-anchor':'middle',
      fill: css('--text-muted'), 'font-size': 11}); t.textContent = v; svg.appendChild(t);
  }
  rows.forEach((d, i) => {
    const y = m.t + i*rowH + rowH/2;
    const today = Math.max(0, d.e - d.g);
    const g = el('g');
    g.appendChild(el('line', {x1: xs(today), x2: xs(d.e), y1: y, y2: y,
      stroke: css('--seq-3'), 'stroke-width': 2}));
    g.appendChild(el('circle', {cx: xs(today), cy: y, r: 5.5, fill: css('--seq-2'),
      stroke: css('--surface-1'), 'stroke-width': 2}));
    g.appendChild(el('circle', {cx: xs(d.e), cy: y, r: 5.5, fill: css('--seq-6'),
      stroke: css('--surface-1'), 'stroke-width': 2}));
    const lt = el('text', {x: m.l-10, y: y+4, 'text-anchor':'end',
      fill: css('--text-primary'), 'font-size': 11.5});
    const dbMax = Math.max(14, Math.floor((m.l - 14) / 6.1));
    lt.textContent = d.t.length > dbMax ? d.t.slice(0, dbMax-1)+'\\u2026' : d.t;
    g.appendChild(lt);
    const vt = el('text', {x: xs(d.e)+9, y: y+4, fill: css('--text-secondary'),
      'font-size': 11.5}); vt.textContent = '+' + d.g.toFixed(0); g.appendChild(vt);
    g.addEventListener('mousemove', e => showTip(e, `<b>${esc(d.t)}</b>` +
      row('Automatable today', today.toFixed(0)) + row('AI could do', d.e.toFixed(0)) +
      row('Gap', '+' + d.g.toFixed(0))));
    g.addEventListener('mouseleave', hideTip);
    svg.appendChild(g);
  });
  host.appendChild(svg);
}

function sortRows(rows, st) {
  return [...rows].sort((a,b) => {
    const x = a[st.k], y = b[st.k];
    return (typeof x === 'string' ? x.localeCompare(y) : x - y) * st.d;
  });
}
function headerRow(cols, st, onSort) {
  const tr = document.createElement('tr');
  cols.forEach(c => {
    const th = document.createElement('th');
    th.className = c.num ? 'num' : '';
    th.textContent = c.label + (st.k === c.k ? (st.d < 0 ? ' \\u2193' : ' \\u2191') : '');
    th.onclick = () => onSort(c.k);
    tr.appendChild(th);
  });
  return tr;
}

function renderSub() {
  const q = $('#f-sub').value.toLowerCase();
  const rows = sortRows(DATA.sub.filter(s => !q || s.t.toLowerCase().includes(q)), SUBSORT).slice(0, 300);
  $('#sub-n').textContent = rows.length + ' of ' + DATA.sub.length + ' shown';
  const cols = [{k:'t',label:'Subtask'}, {k:'s',label:'Suscept.',num:1},
    {k:'e',label:'Exposure',num:1}, {k:'a',label:'Anchoring',num:1},
    {k:'no',label:'Jobs',num:1}, {k:'v',label:'Verdict'}];
  const t = $('#t-sub'); t.innerHTML = '';
  t.appendChild(headerRow(cols, SUBSORT,
    k => { SUBSORT = {k, d: SUBSORT.k === k ? -SUBSORT.d : -1}; renderSub(); }));
  for (const s of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${esc(s.t)}</td>` +
      `<td class="num" style="color:${divergingColor(s.s)};font-weight:600">${s.s.toFixed(0)}</td>` +
      `<td class="num">${s.e.toFixed(0)}</td><td class="num">${s.a.toFixed(0)}</td>` +
      `<td class="num">${s.no}</td><td><span class="pill">${esc(s.v.replace(/_/g,' '))}</span></td>`;
    tr.addEventListener('mousemove', e => s.r && showTip(e, `<b>${esc(s.t)}</b>${esc(s.r)}`));
    tr.addEventListener('mouseleave', hideTip);
    t.appendChild(tr);
  }
}

function renderTasks() {
  const t = $('#t-task'); t.innerHTML = '';
  if (typeof renderProfile === 'function') renderProfile();
  if (!SEL) { $('#task-title').innerHTML = 'Tasks &mdash; click an occupation above'; return; }
  $('#task-title').textContent = `Tasks: ${SEL.t}`;
  const rows = sortRows(DATA.task.filter(x => x.c === SEL.c), TASKSORT);
  const cols = [{k:'t',label:'Task'}, {k:'s',label:'Suscept.',num:1},
    {k:'e',label:'Exposure',num:1}, {k:'a',label:'Anchoring',num:1},
    {k:'i',label:'Importance',num:1}, {k:'v',label:'Verdict'}];
  t.appendChild(headerRow(cols, TASKSORT,
    k => { TASKSORT = {k, d: TASKSORT.k === k ? -TASKSORT.d : -1}; renderTasks(); }));
  for (const r of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${esc(r.t)}</td>` +
      `<td class="num" style="color:${divergingColor(r.s)};font-weight:600">${r.s.toFixed(0)}</td>` +
      `<td class="num">${r.e.toFixed(0)}</td><td class="num">${r.a.toFixed(0)}</td>` +
      `<td class="num">${r.i ? r.i.toFixed(0) : '\\u2014'}</td>` +
      `<td><span class="pill">${esc(r.v.replace(/_/g,' '))}</span></td>`;
    t.appendChild(tr);
  }
}



const types = [...new Set(DATA.occ.map(o => o.ty).filter(Boolean))].sort();
$('#f-type').innerHTML = '<option value="">All</option>' +
  types.map(t => `<option>${esc(t)}</option>`).join('');
for (const id of ['#f-type', '#f-hl'])
  $(id).onchange = () => { renderScatter(); renderBars(); renderDumbbell(); };
$('#f-q').oninput = () => { renderScatter(); renderBars(); renderDumbbell(); };
$('#f-sub').oninput = renderSub;

(function initAnswer() {
  const hand = DATA.hand || [];
  const classes = [...new Set(hand.map(h => h.cls).filter(Boolean))];
  const order = ['Watch point','Crossing now','Handed off','Human held'];
  $('#a-cls').innerHTML = '<option value="">All</option>' +
    order.filter(c => classes.includes(c)).map(c => `<option>${c}</option>`).join('');
  const types = [...new Set(DATA.occ.map(o => o.ty).filter(Boolean))].sort();
  $('#a-type').innerHTML = '<option value="">All</option>' +
    types.map(t => `<option>${esc(t)}</option>`).join('');
  $('#a-metric').onchange = e => { FILTER.metric = e.target.value; renderAnswer(); };
  $('#a-cls').onchange = e => { FILTER.cls = e.target.value; renderAnswer(); renderFrontier(); };
  $('#a-type').onchange = e => { FILTER.type = e.target.value; renderAnswer(); };
  $('#a-emp').onchange = e => { FILTER.empOnly = e.target.checked; renderAnswer(); };
  $('#a-q').oninput = e => { FILTER.q = e.target.value.toLowerCase(); renderAnswer(); };
})();
"""


_EMP_SCRIPT = """
function renderEmployment() {
  if (!DATA.soc || !DATA.soc.length) return;
  $('#emp-card').style.display = '';
  const h = DATA.emp || {};
  const fmtM = v => (v/1e6).toFixed(1) + 'M';
  const shift = h.weighting_shifts_result_by;
  $('#emp-note').innerHTML =
    `Employment and wages from BLS OEWS ${esc(h.release || '')}. Weighting by headcount moves ` +
    `mean susceptibility from <strong>${h.unweighted_susceptibility}</strong> to ` +
    `<strong>${h.employment_weighted_susceptibility}</strong> ` +
    `(${shift >= 0 ? '+' : ''}${shift}) &mdash; ` +
    (Math.abs(shift) < 2
      ? 'a small shift, so headcount is <em>not</em> concentrated at either end of the distribution.'
      : 'a large shift, so headcount is concentrated at one end and the unweighted average misleads.');
  const k = [
    [fmtM(h.total_employment), 'workers covered'],
    [fmtM(h.workers_in_high_susceptibility_occupations),
      'in high-susceptibility<br>occupations (' + Math.round(100*h.share_workers_high_susceptibility) + '%)'],
    ['$' + (h.annual_wage_bill_usd/1e9).toFixed(0) + 'B', 'annual wage bill'],
    [h.soc_codes, 'SOC codes matched'],
  ];
  $('#emp-kpis').innerHTML = k.map(([v,l]) =>
    `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');

  // Workers by quadrant: part-to-whole, so one horizontal stacked bar.
  const host = $('#emp-quad'); host.innerHTML = '';
  const order = ['Displaceable','Contested','Human-anchored','Insulated'];
  const qs = order.filter(q => h.by_quadrant && h.by_quadrant[q])
                  .map(q => ({q, ...h.by_quadrant[q]}));
  const W = host.clientWidth || 420, barH = 40;
  const svg = el('svg', {width: W, height: barH + 84, role: 'img'});
  let x = 0;
  const shade = {Displaceable: '--div-high', Contested: '--seq-3',
                 'Human-anchored': '--div-low', Insulated: '--seq-2'};
  qs.forEach(d => {
    const w = d.share_of_employment * W;
    const g = el('g');
    g.appendChild(el('rect', {x: x + 1, y: 0, width: Math.max(1, w - 2), height: barH,
      rx: 4, fill: css(shade[d.q])}));
    if (w > 44) {
      const t = el('text', {x: x + w/2, y: barH/2 + 4, 'text-anchor': 'middle',
        fill: '#fff', 'font-size': 12, 'font-weight': 600});
      t.textContent = Math.round(100*d.share_of_employment) + '%';
      g.appendChild(t);
    }
    g.addEventListener('mousemove', e => showTip(e, `<b>${esc(d.q)}</b>` +
      row('Workers', Math.round(d.employment).toLocaleString()) +
      row('Share', Math.round(100*d.share_of_employment) + '%') +
      row('Wage bill', '$' + (d.wage_bill_usd/1e9).toFixed(0) + 'B')));
    g.addEventListener('mouseleave', hideTip);
    svg.appendChild(g);
    x += w;
  });
  qs.forEach((d, i) => {
    const y = barH + 20 + i*15;
    svg.appendChild(el('rect', {x: 0, y: y-9, width: 10, height: 10, rx: 2,
      fill: css(shade[d.q])}));
    const t = el('text', {x: 16, y: y, fill: css('--text-secondary'), 'font-size': 11.5});
    t.textContent = `${d.q} \\u2014 ${(d.employment/1e6).toFixed(2)}M workers`;
    svg.appendChild(t);
  });
  host.appendChild(svg);

  // Headcount actually at stake = workers x susceptibility.
  const host2 = $('#emp-bars'); host2.innerHTML = '';
  const rows = [...DATA.soc].sort((a,b) => b.emp*b.s - a.emp*a.s).slice(0, 12);
  const W2 = host2.clientWidth || 420, rowH = 25, m = {t: 4, r: 56, b: 18, l: 196};
  const iw = W2 - m.l - m.r, maxE = Math.max(...rows.map(r => r.emp));
  const maxChars = Math.max(12, Math.floor((m.l - 12) / 6.1));
  const svg2 = el('svg', {width: W2, height: m.t + rows.length*rowH + m.b, role: 'img'});
  rows.forEach((d, i) => {
    const y = m.t + i*rowH, w = Math.max(2, d.emp/maxE*iw);
    const g = el('g');
    g.appendChild(el('rect', {x: m.l, y: y+3, width: w, height: rowH-9, rx: 4,
      fill: divergingColor(d.s), stroke: css('--axis'), 'stroke-width': 1}));
    const lt = el('text', {x: m.l-9, y: y+rowH/2+3, 'text-anchor':'end',
      fill: css('--text-primary'), 'font-size': 11.5});
    lt.textContent = d.t.length > maxChars ? d.t.slice(0, maxChars-1)+'\\u2026' : d.t;
    g.appendChild(lt);
    const vt = el('text', {x: m.l+w+7, y: y+rowH/2+3, fill: css('--text-secondary'),
      'font-size': 11.5});
    vt.textContent = (d.emp/1000).toFixed(0) + 'k';
    g.appendChild(vt);
    g.addEventListener('mousemove', e => showTip(e, `<b>${esc(d.t)}</b>` +
      row('Workers', Math.round(d.emp).toLocaleString()) +
      row('Susceptibility', d.s) + row('Quadrant', d.q) +
      (d.wage ? row('Mean wage', '$' + Math.round(d.wage).toLocaleString()) : '') +
      (d.nd > 1 ? row('O*NET occupations', d.nd + (d.sd ? ` (sd ${d.sd})` : '')) : '')));
    g.addEventListener('mouseleave', hideTip);
    svg2.appendChild(g);
  });
  host2.appendChild(svg2);
}
"""


_VIZ2_SCRIPT = """
function pearsonJS(a, b) {
  const ma = a.reduce((s,x)=>s+x,0)/a.length, mb = b.reduce((s,x)=>s+x,0)/b.length;
  let n=0, da=0, db=0;
  for (let i=0;i<a.length;i++){ n+=(a[i]-ma)*(b[i]-mb); da+=(a[i]-ma)**2; db+=(b[i]-mb)**2; }
  return da && db ? n/Math.sqrt(da*db) : 0;
}

/* One series against one benchmark: emphasis, not categorical. Single hue, a
   fitted line, and direct labels on the points that carry the story. */
function scatterVs(hostId, pts, yKey, yLabel, highlight) {
  const host = $(hostId); host.innerHTML = '';
  const data = pts.filter(p => p[yKey] >= 0);
  if (!data.length) return;
  const W = host.clientWidth || 440, H = 330, m = {t: 14, r: 18, b: 44, l: 54};
  const iw = W-m.l-m.r, ih = H-m.t-m.b;
  const ys_ = data.map(d => d[yKey]);
  const yMin = Math.min(...ys_), yMax = Math.max(...ys_);
  const xs = v => m.l + (v-10)/80*iw;
  const ys = v => m.t + ih - (v-yMin)/((yMax-yMin)||1)*ih;
  const svg = el('svg', {width: W, height: H, role: 'img',
    'aria-label': `Susceptibility index against ${yLabel}`});

  for (let v=20; v<=90; v+=20) {
    svg.appendChild(el('line', {x1:xs(v),x2:xs(v),y1:m.t,y2:m.t+ih,
      stroke:css('--grid'),'stroke-width':1}));
    const t = el('text', {x:xs(v),y:H-26,'text-anchor':'middle',
      fill:css('--text-muted'),'font-size':11}); t.textContent=v; svg.appendChild(t);
  }
  for (let i=0;i<=4;i++) {
    const v = yMin + (yMax-yMin)*i/4;
    svg.appendChild(el('line', {x1:m.l,x2:m.l+iw,y1:ys(v),y2:ys(v),
      stroke:css('--grid'),'stroke-width':1}));
    const t = el('text', {x:m.l-8,y:ys(v)+4,'text-anchor':'end',
      fill:css('--text-muted'),'font-size':11});
    t.textContent = (yMax<=1 ? v.toFixed(2) : v.toFixed(0)); svg.appendChild(t);
  }

  const X = data.map(d=>d.s), Y = data.map(d=>d[yKey]);
  const r = pearsonJS(X, Y);
  const mx = X.reduce((s,x)=>s+x,0)/X.length, my = Y.reduce((s,x)=>s+x,0)/Y.length;
  let num=0, den=0;
  for (let i=0;i<X.length;i++){ num+=(X[i]-mx)*(Y[i]-my); den+=(X[i]-mx)**2; }
  const slope = den ? num/den : 0;
  svg.appendChild(el('line', {x1: xs(15), y1: ys(my + slope*(15-mx)),
    x2: xs(88), y2: ys(my + slope*(88-mx)),
    stroke: css('--text-muted'), 'stroke-width': 2, 'stroke-dasharray': '6 4'}));

  for (const d of data) {
    const c = el('circle', {cx: xs(d.s), cy: ys(d[yKey]), r: 4.5,
      fill: css('--series-1'), opacity: .55, stroke: css('--surface-1'),
      'stroke-width': 1.5, cursor: 'pointer'});
    c.addEventListener('mousemove', e => showTip(e, `<b>${esc(d.t)}</b>` +
      row('Our index', d.s) + row(yLabel, d[yKey])));
    c.addEventListener('mouseleave', hideTip);
    svg.appendChild(c);
  }
  for (const name of (highlight||[])) {
    const d = data.find(p => p.t.startsWith(name));
    if (!d) continue;
    svg.appendChild(el('circle', {cx: xs(d.s), cy: ys(d[yKey]), r: 6,
      fill: css('--div-high'), stroke: css('--surface-1'), 'stroke-width': 2}));
    const ly = Math.max(m.t + 11, ys(d[yKey]) - 11);
    const lx = Math.min(Math.max(xs(d.s), m.l + 40), m.l + iw - 40);
    const t = el('text', {x: lx, y: ly, 'text-anchor':'middle',
      fill: css('--text-primary'), 'font-size': 11, 'font-weight': 600});
    t.textContent = d.t.length>22 ? d.t.slice(0,21)+'\\u2026' : d.t;
    svg.appendChild(t);
  }
  const rt = el('text', {x: m.l+8, y: m.t+16, fill: css('--text-primary'),
    'font-size': 13, 'font-weight': 650});
  rt.textContent = `r = ${r.toFixed(3)}`; svg.appendChild(rt);
  const ax = el('text', {x: m.l+iw/2, y: H-6, 'text-anchor':'middle',
    fill: css('--text-secondary'), 'font-size': 12});
  ax.textContent = 'Our susceptibility index \\u2192'; svg.appendChild(ax);
  const ay = el('text', {x: 13, y: m.t+ih/2, 'text-anchor':'middle',
    fill: css('--text-secondary'), 'font-size': 12,
    transform: `rotate(-90 13 ${m.t+ih/2})`});
  ay.textContent = yLabel; svg.appendChild(ay);
  host.appendChild(svg);
}

function renderValidation() {
  if (!DATA.val || !DATA.val.length) return;
  $('#val-card').style.display = '';
  $('#val-note').innerHTML =
    'Both panels plot the same 268 occupations. Benchmarks from Eloundou, Manning, ' +
    'Mishkin &amp; Rock (2023) and Frey &amp; Osborne (2017). Dashed line is the ' +
    'least-squares fit.';
  scatterVs('#val-human', DATA.val, 'hg', 'Human expert rating (gamma)',
            ['Mathematicians']);
  scatterVs('#val-frey', DATA.val, 'fo', 'Frey & Osborne P(computerisation)',
            ['Mathematicians']);
}

/* --- force-directed occupation network ------------------------------------ */
function renderNetwork() {
  const host = $('#network');
  if (!DATA.net || !DATA.net.length) return;
  const nodes = DATA.occ.filter(n => n.x >= 0);
  if (!nodes.length) { host.innerHTML =
    '<p class="note">No layout coordinates - re-run the network stage.</p>'; return; }
  host.innerHTML = '';
  const W = host.clientWidth || 900, H = 620, pad = 26;
  // Coordinates arrive precomputed and normalised 0-1 from the network stage.
  const sx = v => pad + v*(W-2*pad), sy = v => pad + v*(H-2*pad);
  const pos = new Map(nodes.map(n => [n.c, n]));
  const svg = el('svg', {width: W, height: H, role: 'img',
    'aria-label': 'Force-directed network of STEM occupations linked by shared subtasks'});

  for (const e of DATA.net) {
    const a = pos.get(e.s), b = pos.get(e.t);
    if (!a || !b) continue;
    svg.appendChild(el('line', {x1: sx(a.x), y1: sy(a.y), x2: sx(b.x), y2: sy(b.y),
      stroke: css('--grid'), 'stroke-width': 1.2}));
  }
  for (const n of nodes) {
    const c = el('circle', {cx: sx(n.x), cy: sy(n.y), r: Math.max(4, Math.sqrt(n.n)*1.0),
      fill: divergingColor(n.s), stroke: css('--surface-1'), 'stroke-width': 1.6,
      cursor: 'pointer'});
    c.addEventListener('mousemove', e => showTip(e, `<b>${esc(n.t)}</b>` +
      row('Susceptibility', n.s) + row('Exposure', n.e) + row('Anchoring', n.a) +
      row('Quadrant', n.q)));
    c.addEventListener('mouseleave', hideTip);
    c.addEventListener('click', () => { SEL = n; hideTip(); renderTasks();
      $('#task-title').scrollIntoView({behavior:'smooth', block:'center'}); });
    svg.appendChild(c);
  }
  host.appendChild(svg);
}

function renderLeverage() {
  const host = $('#leverage'); if (!DATA.sub || !DATA.sub.length) return;
  host.innerHTML = '';
  const W = host.clientWidth || 900, H = 420, m = {t: 16, r: 22, b: 46, l: 56};
  const iw = W-m.l-m.r, ih = H-m.t-m.b;
  const maxN = Math.max(...DATA.sub.map(d => d.no));
  const xs = v => m.l + Math.sqrt(v/maxN)*iw;          // sqrt: reach is long-tailed
  const ys = v => m.t + ih - (v-10)/85*ih;
  const svg = el('svg', {width: W, height: H, role: 'img',
    'aria-label': 'Subtask susceptibility against how many occupations use it'});
  for (const v of [1,2,5,10,20,40,60]) {
    if (v > maxN) continue;
    svg.appendChild(el('line', {x1:xs(v),x2:xs(v),y1:m.t,y2:m.t+ih,
      stroke:css('--grid'),'stroke-width':1}));
    const t=el('text',{x:xs(v),y:H-26,'text-anchor':'middle',
      fill:css('--text-muted'),'font-size':11}); t.textContent=v; svg.appendChild(t);
  }
  for (let v=20; v<=90; v+=10) {
    svg.appendChild(el('line', {x1:m.l,x2:m.l+iw,y1:ys(v),y2:ys(v),
      stroke:css('--grid'),'stroke-width':1}));
    const t=el('text',{x:m.l-8,y:ys(v)+4,'text-anchor':'end',
      fill:css('--text-muted'),'font-size':11}); t.textContent=v; svg.appendChild(t);
  }
  // Reach is an integer count, so points stack into hard columns; a small
  // deterministic jitter makes density readable without moving anything far.
  const jit = d => ((d.d.charCodeAt(d.d.length-1) % 11) - 5) * 1.6;
  for (const d of DATA.sub) {
    const c = el('circle', {cx: xs(d.no) + jit(d), cy: ys(d.s), r: 4.5,
      fill: divergingColor(d.s), opacity: .8, stroke: css('--surface-1'),
      'stroke-width': 1.4});
    c.addEventListener('mousemove', e => showTip(e, `<b>${esc(d.t)}</b>` +
      row('Susceptibility', d.s) + row('Used by', d.no + ' occupations') +
      row('Tasks', d.nt) + row('Verdict', d.v.replace(/_/g,' '))));
    c.addEventListener('mouseleave', hideTip);
    svg.appendChild(c);
  }
  // Label the genuinely high-leverage corner: susceptible AND widespread.
  const lev = [...DATA.sub].filter(d => d.no >= 8)
      .sort((a,b) => (b.s*Math.sqrt(b.no)) - (a.s*Math.sqrt(a.no))).slice(0,5);
  const used = [];
  for (const d of lev) {
    let y = Math.max(m.t + 10, ys(d.s) - 10);
    while (used.some(u => Math.abs(u-y) < 13)) y += 13;   // push DOWN from the clamp
    used.push(y);
    const near = xs(d.no) > m.l + iw - 150;
    const t = el('text', {x: near ? m.l+iw : xs(d.no),
      y, 'text-anchor': near ? 'end' : 'middle',
      fill: css('--text-primary'), 'font-size': 10.5, 'font-weight': 600});
    t.textContent = d.t.length>40 ? d.t.slice(0,39)+'\\u2026' : d.t;
    svg.appendChild(t);
  }
  const ax=el('text',{x:m.l+iw/2,y:H-6,'text-anchor':'middle',
    fill:css('--text-secondary'),'font-size':12});
  ax.textContent='Occupations using this subtask (square-root scale) \\u2192';
  svg.appendChild(ax);
  const ay=el('text',{x:13,y:m.t+ih/2,'text-anchor':'middle',
    fill:css('--text-secondary'),'font-size':12,transform:`rotate(-90 13 ${m.t+ih/2})`});
  ay.textContent='Susceptibility \\u2192'; svg.appendChild(ay);
  host.appendChild(svg);
}

/* Dimension profile for the selected occupation, against the STEM median. */
function renderProfile() {
  const host = $('#profile'); if (!host) return;
  host.innerHTML = '';
  if (!SEL || !DATA.dims || !DATA.dims[SEL.c]) return;
  const vals = DATA.dims[SEL.c], names = DATA.dimNames;
  const all = Object.values(DATA.dims);
  const med = names.map((_, i) => {
    const col = all.map(v => v[i]).sort((a,b)=>a-b);
    return col[Math.floor(col.length/2)];
  });
  const W = host.clientWidth || 520, rowH = 27, m = {t: 6, r: 42, b: 6, l: 176};
  const iw = W-m.l-m.r;
  const svg = el('svg', {width: W, height: m.t + names.length*rowH + m.b, role:'img'});
  names.forEach((n, i) => {
    const y = m.t + i*rowH;
    svg.appendChild(el('rect', {x:m.l, y:y+4, width:iw, height:rowH-11, rx:4,
      fill: css('--surface-3')}));
    svg.appendChild(el('rect', {x:m.l, y:y+4, width:Math.max(2, vals[i]/100*iw),
      height:rowH-11, rx:4, fill: css('--seq-4')}));
    // median reference tick: the number only means something in context
    svg.appendChild(el('line', {x1:m.l+med[i]/100*iw, x2:m.l+med[i]/100*iw,
      y1:y+1, y2:y+rowH-8, stroke:css('--text-primary'), 'stroke-width':2}));
    const lt = el('text', {x:m.l-9, y:y+rowH/2+3, 'text-anchor':'end',
      fill:css('--text-primary'), 'font-size':11.5}); lt.textContent = n;
    svg.appendChild(lt);
    const vt = el('text', {x:m.l+iw+7, y:y+rowH/2+3, fill:css('--text-secondary'),
      'font-size':11.5}); vt.textContent = vals[i].toFixed(0); svg.appendChild(vt);
  });
  host.appendChild(svg);
}
"""


_HANDOFF_SCRIPT = """
/* Watson's four categories. Three validated categorical slots plus the
   de-emphasis grey for "Human held" - the all-pairs scatter gate caps colour
   identity at three, and "nothing crossing here" is the right thing to mute. */
const CLS_COLOR = {
  'Watch point': '--series-2', 'Crossing now': '--series-1',
  'Handed off': '--series-3', 'Human held': '--text-muted',
};
const CLS_ORDER = ['Watch point', 'Crossing now', 'Handed off', 'Human held'];
const HAND = new Map((window.DATA?.hand || []).map(h => [h.c, h]));

function frontierR(T) { return Math.min(100, (53*53)/Math.max(T,1)); }

function renderFrontier() {
  const host = $('#frontier'); if (!DATA.hand || !DATA.hand.length) return;
  host.innerHTML = '';
  $('#frontier-legend').innerHTML = CLS_ORDER.map(c =>
    `<span><span class="sw" style="background:var(${CLS_COLOR[c]})"></span>${c}</span>`
  ).join('') + '<span style="color:var(--text-muted)">Dot size = workers</span>';

  const W = host.clientWidth || 900, H = 560, m = {t: 16, r: 20, b: 46, l: 58};
  const iw = W-m.l-m.r, ih = H-m.t-m.b;
  const xs = v => m.l + (v-22)/62*iw, ys = v => m.t + ih - (v-24)/64*ih;
  const svg = el('svg', {width: W, height: H, role: 'img',
    'aria-label': 'Occupations plotted by tractability against resistance, with the handoff frontier'});
  for (let v=30; v<=80; v+=10) {
    svg.appendChild(el('line',{x1:xs(v),x2:xs(v),y1:m.t,y2:m.t+ih,stroke:css('--grid'),'stroke-width':1}));
    const t=el('text',{x:xs(v),y:H-26,'text-anchor':'middle',fill:css('--text-muted'),'font-size':11});
    t.textContent=v; svg.appendChild(t);
    svg.appendChild(el('line',{x1:m.l,x2:m.l+iw,y1:ys(v),y2:ys(v),stroke:css('--grid'),'stroke-width':1}));
    const u=el('text',{x:m.l-8,y:ys(v)+4,'text-anchor':'end',fill:css('--text-muted'),'font-size':11});
    u.textContent=v; svg.appendChild(u);
  }
  // the frontier itself
  let d = '';
  for (let T=24; T<=84; T+=1) {
    const R = frontierR(T);
    if (R < 24 || R > 88) continue;
    d += (d ? ' L' : 'M') + xs(T).toFixed(1) + ' ' + ys(R).toFixed(1);
  }
  svg.appendChild(el('path', {d, fill:'none', stroke:css('--series-2'), 'stroke-width':2.5}));
  const fl = el('text', {x: xs(38), y: ys(frontierR(38))-10, 'text-anchor':'start',
    fill: css('--series-2'), 'font-size': 11.5, 'font-weight': 640});
  fl.textContent = 'frontier today'; svg.appendChild(fl);
  // The tractability floor: left of this, AI cannot lead the work at all, so
  // resistance is not what is holding it and the frontier does not apply.
  svg.appendChild(el('line', {x1: xs(50), x2: xs(50), y1: m.t, y2: m.t+ih,
    stroke: css('--text-muted'), 'stroke-width': 1.5, 'stroke-dasharray': '4 4'}));
  const ft = el('text', {x: xs(50)-7, y: m.t+ih-8, 'text-anchor':'end',
    fill: css('--text-muted'), 'font-size': 10.5});
  ft.textContent = 'not yet tractable'; svg.appendChild(ft);
  for (const [lab, tx, ty, an] of [['HUMAN HELD', m.l+12, m.t+16, 'start'],
                                   ['HANDED OFF', m.l+iw-12, m.t+ih-10, 'end']]) {
    const t = el('text', {x: tx, y: ty, 'text-anchor': an, fill: css('--text-muted'),
      'font-size': 11, 'font-weight': 600, 'letter-spacing': '.04em'});
    t.textContent = lab; svg.appendChild(t);
  }

  const maxE = Math.max(...DATA.hand.map(h => h.emp || 0), 1);
  const shown = DATA.hand.filter(h => !FILTER.cls || h.cls === FILTER.cls);
  for (const h of shown) {
    const r = h.emp ? Math.max(4, Math.sqrt(h.emp/maxE)*22) : 4;
    const c = el('circle', {cx: xs(h.T), cy: ys(h.R), r,
      fill: css(CLS_COLOR[h.cls] || '--text-muted'),
      opacity: h.cls === 'Human held' ? .5 : .82,
      stroke: css('--surface-1'), 'stroke-width': 1.8, cursor: 'pointer'});
    c.addEventListener('mousemove', e => showTip(e, `<b>${esc(h.t)}</b>` +
      row('Classification', h.cls) + row('Tractability', h.T) + row('Resistance', h.R) +
      row('Stage today', h.nowL) + row('Reachable now', h.reachL) +
      row('Willingness gap', '+' + h.gap) +
      (h.emp ? row('Workers', Math.round(h.emp).toLocaleString()) : '')));
    c.addEventListener('mouseleave', hideTip);
    c.addEventListener('click', () => selectOcc(h.c));
    svg.appendChild(c);
  }
  // Label the watch points - they are the point of the chart.
  const wp = shown.filter(h => h.cls === 'Watch point')
                  .sort((a,b) => b.gap - a.gap).slice(0, 5);
  const used = [];
  for (const h of wp) {
    let y = Math.max(m.t+11, ys(h.R) - 11);
    while (used.some(u => Math.abs(u-y) < 12)) y += 12;
    used.push(y);
    const t = el('text', {x: Math.min(Math.max(xs(h.T), m.l+50), m.l+iw-50), y,
      'text-anchor':'middle', fill: css('--text-primary'), 'font-size': 10.5,
      'font-weight': 600});
    t.textContent = h.t.length>28 ? h.t.slice(0,27)+'\\u2026' : h.t;
    svg.appendChild(t);
  }
  const ax=el('text',{x:m.l+iw/2,y:H-6,'text-anchor':'middle',fill:css('--text-secondary'),'font-size':12});
  ax.textContent='Tractability: can AI lead this work \\u2192'; svg.appendChild(ax);
  const ay=el('text',{x:13,y:m.t+ih/2,'text-anchor':'middle',fill:css('--text-secondary'),
    'font-size':12,transform:`rotate(-90 13 ${m.t+ih/2})`});
  ay.textContent='Resistance: will it be permitted \\u2192'; svg.appendChild(ay);
  host.appendChild(svg);
}

const STAGES = ['Human only','AI informed','AI recommended','AI executed, human veto',
                'AI led, human audit','AI led, unreviewed'];
function renderStages() {
  const host = $('#stages'); if (!DATA.hand || !DATA.hand.length) return;
  host.innerHTML = '';
  const now = new Array(6).fill(0), reach = new Array(6).fill(0);
  for (const h of DATA.hand) { now[h.now]++; reach[h.reach]++; }
  const W = host.clientWidth || 900, rowH = 42, m = {t: 8, r: 60, b: 24, l: 210};
  const iw = W-m.l-m.r, max = Math.max(...now, ...reach, 1);
  const xs = v => m.l + v/max*iw;
  const svg = el('svg', {width: W, height: m.t + 6*rowH + m.b, role: 'img'});
  STAGES.forEach((name, i) => {
    const y = m.t + i*rowH + rowH/2;
    svg.appendChild(el('line', {x1: xs(0), x2: xs(Math.max(now[i], reach[i])), y1: y, y2: y,
      stroke: css('--seq-3'), 'stroke-width': 2}));
    svg.appendChild(el('circle', {cx: xs(now[i]), cy: y, r: 7, fill: css('--seq-2'),
      stroke: css('--surface-1'), 'stroke-width': 2}));
    svg.appendChild(el('circle', {cx: xs(reach[i]), cy: y, r: 7, fill: css('--seq-6'),
      stroke: css('--surface-1'), 'stroke-width': 2}));
    const lt = el('text', {x: m.l-12, y: y+4, 'text-anchor':'end',
      fill: css('--text-primary'), 'font-size': 12}); lt.textContent = `${i}. ${name}`;
    svg.appendChild(lt);
    const vt = el('text', {x: Math.max(xs(now[i]), xs(reach[i]))+10, y: y+4,
      fill: css('--text-secondary'), 'font-size': 11.5});
    vt.textContent = `${now[i]} \\u2192 ${reach[i]}`; svg.appendChild(vt);
    if (i === 2 || i === 3) {
      const wx = el('text', {x: m.l-12, y: y+18, 'text-anchor':'end',
        fill: css('--series-2'), 'font-size': 10, 'font-weight': 600});
      wx.textContent = i === 2 ? 'weighty crossing \\u2193' : 'erosion crossing \\u2193';
      svg.appendChild(wx);
    }
  });
  host.appendChild(svg);
}

/* ---- the answer panel ---------------------------------------------------- */
const FILTER = {cls: '', type: '', q: '', empOnly: false, metric: 's'};
const METRIC_LABEL = {s:'Susceptibility', gap:'Willingness gap', ero:'Erosion risk',
                      sur:'Surprise potential', emp:'Workers', empatrisk:'Workers x susceptibility'};

function answerRows() {
  return DATA.occ.map(o => {
    const h = HAND.get(o.c) || {};
    return {...o, gap: h.gap ?? o.g, ero: h.ero ?? 0, sur: h.sur ?? 0,
            emp: h.emp ?? 0, cls: h.cls ?? '', nowL: h.nowL ?? '', reachL: h.reachL ?? '',
            empatrisk: (h.emp ?? 0) * o.s / 100};
  }).filter(r =>
      (!FILTER.cls || r.cls === FILTER.cls) &&
      (!FILTER.type || r.ty === FILTER.type) &&
      (!FILTER.empOnly || r.emp > 0) &&
      (!FILTER.q || r.t.toLowerCase().includes(FILTER.q)))
    .sort((a,b) => (b[FILTER.metric]||0) - (a[FILTER.metric]||0));
}

function renderAnswer() {
  if (!DATA.occ || !DATA.occ.length) return;
  const rows = answerRows();
  $('#a-n').textContent = rows.length + ' occupations';
  const m = FILTER.metric;
  const fmt = v => m === 'emp' ? Math.round(v).toLocaleString()
    : m === 'empatrisk' ? Math.round(v).toLocaleString() : (+v).toFixed(0);
  const t = $('#t-answer'); t.innerHTML = '';
  const head = document.createElement('tr');
  head.innerHTML = '<th>#</th><th>Occupation</th>' +
    `<th class="num">${METRIC_LABEL[m]}</th>` +
    '<th class="num">Suscept.</th><th class="num">Workers</th>' +
    '<th>Handoff class</th><th>Stage today &rarr; reachable</th>';
  t.appendChild(head);
  rows.slice(0, 120).forEach((r, i) => {
    const tr = document.createElement('tr');
    tr.style.cursor = 'pointer';
    const clsColor = CLS_COLOR[r.cls] || '--text-muted';
    tr.innerHTML = `<td class="num" style="color:var(--text-muted)">${i+1}</td>` +
      `<td>${esc(r.t)}</td>` +
      `<td class="num" style="font-weight:650">${fmt(r[m]||0)}</td>` +
      `<td class="num" style="color:${divergingColor(r.s)}">${r.s.toFixed(0)}</td>` +
      `<td class="num">${r.emp ? Math.round(r.emp).toLocaleString() : '\\u2014'}</td>` +
      `<td><span class="sw" style="background:var(${clsColor})"></span>${esc(r.cls)}</td>` +
      `<td style="color:var(--text-secondary)">${esc(r.nowL)} &rarr; ${esc(r.reachL)}</td>`;
    tr.onclick = () => selectOcc(r.c);
    t.appendChild(tr);
  });
}

function selectOcc(code) {
  const o = DATA.occ.find(x => x.c === code);
  if (!o) return;
  SEL = o; hideTip(); renderTasks();
  $('#task-title').scrollIntoView({behavior:'smooth', block:'center'});
}
"""
