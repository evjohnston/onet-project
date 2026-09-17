"""Assemble docs/ for GitHub Pages.

Pages serves a directory, not a build step, so this copies the finished
artefacts out of data/out into docs/ and writes a landing page around them.
data/out stays the working directory the stages write to; docs/ is what the
world sees, refreshed explicitly rather than on every run.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DOMAIN = "onet.emersonjohnston.org"
REPO = "https://github.com/evjohnston/onet-project"

COPY = ("story.html", "dashboard.html")
COPY_DIRS = ("figures",)
DATA_FILES = (
    "occupation_susceptibility.csv", "task_susceptibility.csv",
    "subtask_susceptibility.csv", "occupation_handoff.csv",
    "soc_susceptibility.csv", "external_benchmarks.csv",
    "transitions.csv", "stranded_occupations.csv", "wage_deciles.csv",
    "task_churn_occupations.csv", "task_churn_steps.csv", "tasks_wide.csv",
)


def _read(out_dir: Path, name: str) -> dict[str, Any]:
    path = out_dir / name
    return json.loads(path.read_text()) if path.exists() else {}


def build_index(out_dir: Path) -> str:
    v = _read(out_dir, "validation_report.json").get("summary", {})
    emp = _read(out_dir, "employment_report.json").get("headline", {})
    ext = _read(out_dir, "external_validation.json")
    pw = _read(out_dir, "pathways_report.json")
    ch = _read(out_dir, "churn_report.json")
    sc = _read(out_dir, "scoring_report.json")

    human = next((c for c in ext.get("susceptibility_vs", [])
                  if c["measure"] == "human_gamma"), {})
    trans = pw.get("transitions", {})
    wages = pw.get("wages", {})

    stats = [
        (f"{v.get('occupations', 0)}", "STEM occupations"),
        (f"{v.get('tasks', 0):,}", "tasks scored"),
        (f"{v.get('distinct_subtasks', 0)}", "distinct subtasks"),
        (f"{emp.get('total_employment', 0)/1e6:.1f}M", "workers matched"),
        (f"{human.get('pearson', 0):.2f}", "vs human expert ratings"),
        (f"{trans.get('stranded', 0)}", "occupations with nowhere to move"),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="n">{n}</div><div class="k">{k}</div></div>'
        for n, k in stats)

    findings = [
        ("The old measure does not survive",
         "Frey &amp; Osborne&rsquo;s 2013 computerisation scores correlate with LLM "
         "exposure at <b>r&nbsp;=&nbsp;0.006</b> across the 150 occupations carrying "
         "both. Not weak agreement — none."),
        ("Capability is not what holds most work",
         f"Pay barely correlates with exposure (r&nbsp;=&nbsp;"
         f"{wages.get('wage_vs_exposure', 0)}) but does with accountability "
         f"(r&nbsp;=&nbsp;{wages.get('wage_vs_anchoring', 0)}). Only "
         f"<b>9%</b> of STEM workers are in work a model could do but is not "
         f"permitted to."),
        ("Exposure is clustered, so there is nowhere to go",
         f"<b>{trans.get('stranded', 0)} of "
         f"{trans.get('stranded', 0) + trans.get('with_a_destination', 0)}</b> "
         "occupations have no close, meaningfully safer neighbour in the activity "
         "network. Moving to an adjacent role fails where it is most needed."),
        ("And the work has already started moving",
         f"Across eleven years of archived releases, task turnover is "
         f"<b>{100*ch.get('refreshed_only', {}).get('turnover_rate', 0):.1f}%</b> "
         "among occupations O*NET actually re-surveyed — and roughly three times "
         "faster in the exposed ones than the protected ones."),
    ]
    find_html = "".join(
        f'<article><h3>{t}</h3><p>{b}</p></article>' for t, b in findings)

    data_links = "".join(
        f'<li><a href="data/{n}">{n}</a></li>' for n in DATA_FILES)

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#1c1c18">
<title>STEM work and the handoff to AI — an O*NET task dataset</title>
<meta name="description" content="287 STEM occupations, 5,717 tasks and 963 subtasks scored
for automation exposure, validated against human expert ratings at r = 0.85.">
<meta property="og:title" content="STEM work and the handoff to AI">
<meta property="og:description" content="Which tasks in which jobs are exposed to
automation — and what actually protects the rest.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{--ink:#1c1c18;--paper:#faf9f5;--paper2:#f2efe5;--paper3:#f8f6f0;
  --rust:#bf5540;--muted:#6e6e66;--line:rgba(28,28,24,.15);
  --sans:'Manrope',Helvetica,Arial,sans-serif;--serif:'DM Serif Display',Georgia,serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  -webkit-font-smoothing:antialiased}}
a{{color:inherit}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 clamp(20px,5vw,48px)}}
.hero{{background:var(--ink);color:var(--paper);padding:clamp(60px,11vh,130px) 0 clamp(46px,8vh,90px)}}
.eyebrow{{font:500 10.5px/1.6 var(--mono);letter-spacing:.14em;text-transform:uppercase;
  color:#d9a43a;margin:0 0 20px}}
h1{{font:400 clamp(2.1rem,5.6vw,4rem)/1.04 var(--serif);letter-spacing:-.022em;margin:0 0 22px;max-width:17ch}}
.dek{{font-size:clamp(1rem,1.5vw,1.14rem);line-height:1.65;color:#c9c6bc;max-width:60ch;margin:0}}
.cta{{display:flex;gap:12px;flex-wrap:wrap;margin-top:34px}}
.btn{{display:inline-block;padding:13px 22px;border-radius:3px;text-decoration:none;
  font:500 11px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase}}
.btn.p{{background:#d9a43a;color:var(--ink)}}
.btn.ghost{{border:1px solid rgba(250,249,245,.32);color:var(--paper)}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:1px;background:var(--line);border-block:1px solid var(--line);margin:0}}
.stat{{background:var(--paper);padding:26px 22px}}
.stat .n{{font:400 clamp(1.7rem,3.4vw,2.3rem)/1 var(--serif);color:var(--rust);letter-spacing:-.02em}}
.stat .k{{font:500 9.5px/1.6 var(--mono);letter-spacing:.11em;text-transform:uppercase;
  color:var(--muted);margin-top:8px}}
section.body{{padding:clamp(52px,9vh,96px) 0}}
h2{{font:400 clamp(1.5rem,3vw,2.1rem)/1.15 var(--serif);letter-spacing:-.018em;margin:0 0 10px}}
.lead{{color:var(--muted);line-height:1.7;max-width:68ch;margin:0 0 40px}}
.finds{{display:grid;grid-template-columns:1fr 1fr;gap:28px 40px}}
@media(max-width:760px){{.finds{{grid-template-columns:1fr}}}}
.finds h3{{font:600 .95rem/1.4 var(--sans);margin:0 0 8px}}
.finds p{{margin:0;color:var(--muted);font-size:.92rem;line-height:1.68}}
.finds b{{color:var(--ink);font-weight:600}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:8px}}
@media(max-width:760px){{.cards{{grid-template-columns:1fr}}}}
.card{{display:block;text-decoration:none;background:var(--paper3);
  border:1px solid var(--line);border-radius:4px;padding:26px 26px 28px;
  transition:transform .15s ease,box-shadow .15s ease}}
.card:hover{{transform:translateY(-2px);box-shadow:0 8px 26px rgba(28,28,24,.09)}}
.card .t{{font:400 1.35rem/1.2 var(--serif);margin:0 0 8px}}
.card .d{{color:var(--muted);font-size:.9rem;line-height:1.6;margin:0}}
.card .go{{font:500 10px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase;
  color:var(--rust);margin-top:18px;display:block}}
.tint{{background:var(--paper2)}}
.gal{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}}
.gal a{{display:block;border:1px solid var(--line);border-radius:3px;overflow:hidden;background:var(--paper)}}
.gal img{{width:100%;height:150px;object-fit:cover;object-position:top left;display:block}}
.gal span{{display:block;padding:9px 12px;font:500 9.5px/1.5 var(--mono);
  letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
ul.data{{columns:2;gap:30px;padding-left:18px;margin:0}}
@media(max-width:600px){{ul.data{{columns:1}}}}
ul.data li{{font:500 11.5px/2.1 var(--mono);color:var(--muted)}}
footer{{border-top:1px solid var(--line);padding:38px 0 60px;color:var(--muted);font-size:.84rem;line-height:1.7}}
footer a{{color:var(--ink)}}
.note{{font-size:.84rem;color:var(--muted);line-height:1.7;max-width:70ch}}
</style></head>
<body>

<header class="hero"><div class="wrap">
  <p class="eyebrow">O*NET · {v.get('occupations', 0)} STEM occupations · {v.get('tasks', 0):,} tasks · {v.get('distinct_subtasks', 0)} subtasks</p>
  <h1>Which work is exposed to AI, and what protects the rest.</h1>
  <p class="dek">A scraped, scored and externally validated dataset of STEM work.
  Every task rated through the standardised activity beneath it, weighted by BLS
  employment, and checked against independent human expert ratings at
  r&nbsp;=&nbsp;{human.get('pearson', 0):.2f}.</p>
  <div class="cta">
    <a class="btn p" href="story.html">Read the story</a>
    <a class="btn ghost" href="dashboard.html">Open the dashboard</a>
    <a class="btn ghost" href="{REPO}">Source &amp; data</a>
  </div>
</div></header>

<div class="stats">{stat_html}</div>

<section class="body"><div class="wrap">
  <h2>Four findings</h2>
  <p class="lead">Each comes from a different data source, and they point the same way.</p>
  <div class="finds">{find_html}</div>
</div></section>

<section class="body tint"><div class="wrap">
  <h2>Two ways in</h2>
  <p class="lead">The story walks through the argument in twelve chapters with two
  interactives. The dashboard lets you interrogate the same tables directly.</p>
  <div class="cards">
    <a class="card" href="story.html">
      <p class="t">The story</p>
      <p class="d">Scroll-driven, twelve chapters. The inversion against Frey &amp;
      Osborne, what a job is made of, the handoff frontier, who actually does the work,
      and whether any of it has moved yet. Includes an explorer for any occupation and
      a side-by-side comparison of any two.</p>
      <span class="go">Read &rarr;</span>
    </a>
    <a class="card" href="dashboard.html">
      <p class="t">The dashboard</p>
      <p class="d">Every occupation, task and subtask, rankable by six different
      measures. Network projections, the employment join, the validation panel, and a
      PNG export on every chart.</p>
      <span class="go">Explore &rarr;</span>
    </a>
  </div>
</div></section>

<section class="body"><div class="wrap">
  <h2>Figures</h2>
  <p class="lead">Publication-resolution PNGs, rendered from the dashboard itself so they
  cannot drift from what it shows.</p>
  <div class="gal">__GALLERY__</div>
</div></section>

<section class="body tint"><div class="wrap">
  <h2>The data</h2>
  <p class="lead">Result tables as CSV. The full pipeline, tests and rebuild
  instructions are in the repository.</p>
  <ul class="data">{data_links}</ul>
</div></section>

<footer><div class="wrap">
  <p><b>Scores are model-generated.</b> The {v.get('distinct_subtasks', 0)} subtask ratings come from
  {sc.get('model', 'a language model')} under a versioned rubric, not from a survey. They
  correlate with independent human expert ratings at r&nbsp;=&nbsp;{human.get('pearson', 0):.2f},
  which is evidence of validity rather than a substitute for it.</p>
  <p>O*NET data is provided by the U.S. Department of Labor under
  <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>; O*NET® is a
  trademark of USDOL/ETA. Employment and wages from the BLS Occupational Employment and
  Wage Statistics (public domain). Benchmark ratings from Eloundou, Manning, Mishkin
  &amp; Rock (2023).</p>
  <p><a href="{REPO}">Source on GitHub</a></p>
</div></footer>

</body></html>"""


def publish(out_dir: Path, docs_dir: Path, domain: str = DOMAIN) -> Path:
    docs_dir.mkdir(parents=True, exist_ok=True)
    for name in COPY:
        src = out_dir / name
        if src.exists():
            shutil.copy2(src, docs_dir / name)
        else:
            log.warning("%s missing - the site will link to a page that is not there", name)
    for d in COPY_DIRS:
        src = out_dir / d
        if src.exists():
            shutil.copytree(src, docs_dir / d, dirs_exist_ok=True)

    data_dir = docs_dir / "data"
    data_dir.mkdir(exist_ok=True)
    for name in DATA_FILES:
        src = out_dir / name
        if src.exists():
            shutil.copy2(src, data_dir / name)

    gallery = ""
    fig_dir = docs_dir / "figures"
    if fig_dir.exists():
        for png in sorted(p for p in fig_dir.glob("*.png") if "-dark" not in p.name):
            label = png.stem.split("-", 1)[-1].replace("-", " ")
            gallery += (f'<a href="figures/{png.name}"><img src="figures/{png.name}" '
                        f'alt="{label}" loading="lazy"><span>{label}</span></a>')

    (docs_dir / "index.html").write_text(
        build_index(out_dir).replace("__GALLERY__", gallery), encoding="utf-8")
    (docs_dir / "CNAME").write_text(domain + "\n")
    # Pages runs Jekyll by default, which skips files and folders beginning with
    # an underscore; this project has none today but the guard is free.
    (docs_dir / ".nojekyll").write_text("")

    size = sum(f.stat().st_size for f in docs_dir.rglob("*") if f.is_file())
    log.info("published %d files to %s (%.1f MB) for %s",
             sum(1 for f in docs_dir.rglob("*") if f.is_file()), docs_dir,
             size / 1e6, domain)
    return docs_dir
