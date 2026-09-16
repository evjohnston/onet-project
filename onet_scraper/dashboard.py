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
addEventListener('resize', () => renderAll());
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
) -> Path:
    occ = [
        {
            "c": o["onet_soc_code"], "t": o["title"],
            "ty": (o.get("stem_occupation_types") or "").split(";")[0].strip(),
            "s": _f(o, "susceptibility"), "e": _f(o, "exposure"),
            "a": _f(o, "anchoring"), "g": _f(o, "deployment_gap"),
            "hi": _f(o, "share_tasks_high_susceptibility"),
            "n": int(_f(o, "n_tasks_scored")), "q": o.get("quadrant", ""),
            "z": o.get("job_zone") or "",
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
    payload = {"occ": occ, "task": tsk, "sub": sub, "splits": splits, "meta": meta,
               "soc": soc_rows, "emp": employment or {}}

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
                           .replace("__SCRIPTS__", _SCRIPTS + _EMP_SCRIPT))
    path.write_text(html, encoding="utf-8")
    log.info("wrote %-28s %.1f MB", path.name, path.stat().st_size / 1e6)
    return path


_BODY = """
<div class="kpis" id="kpis"></div>

<div class="card">
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

<div class="grid2">
  <div class="card">
    <h2>Most susceptible occupations</h2>
    <p class="note">High exposure, low human anchoring.</p>
    <div id="bars-top"></div>
  </div>
  <div class="card">
    <h2>Least susceptible occupations</h2>
    <p class="note">Work a human must do, or answer for.</p>
    <div id="bars-bot"></div>
  </div>
</div>

<div class="card">
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

<div class="card">
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

<div class="card">
  <h2 id="task-title">Tasks &mdash; click an occupation above</h2>
  <p class="note">Task-level scores, inherited from the subtasks each task maps to.
  Sorted by susceptibility.</p>
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

function renderAll() { renderKpis(); renderScatter(); renderBars(); renderDumbbell();
                       renderEmployment(); renderSub(); renderTasks(); }

const types = [...new Set(DATA.occ.map(o => o.ty).filter(Boolean))].sort();
$('#f-type').innerHTML = '<option value="">All</option>' +
  types.map(t => `<option>${esc(t)}</option>`).join('');
for (const id of ['#f-type', '#f-hl'])
  $(id).onchange = () => { renderScatter(); renderBars(); renderDumbbell(); };
$('#f-q').oninput = () => { renderScatter(); renderBars(); renderDumbbell(); };
$('#f-sub').oninput = renderSub;
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
