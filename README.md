# onet-job-taskings

Builds a research dataset of **which tasks belong to which STEM jobs, and which
subtasks belong to which tasks**, from [O*NET OnLine's STEM occupation
list](https://www.onetonline.org/find/stem?t=0).

As last built: **287 occupations → 5,717 tasks → 7,215 task↔subtask links** across
963 distinct subtasks, with importance ratings, Core/Supplemental/New flags and
the full activity hierarchy. All eleven validation checks pass.

## The data model

O*NET describes work at four levels of granularity. This scraper captures all of
them and the edges between them:

```
Occupation  15-2011.00  Actuaries
  └─ Task   24015       "Analyze data to determine premium rates..."   importance 94, Core
       └─ DWA  4.A.4.b.4.h.6   "Manage financial activities of the organization."   ← the subtask
            └─ IWA  4.A.4.b.4.h  "Manage financial activities."
                 └─ GWA  4.A.4.b.4  "Performing Administrative Activities."
```

- **Task** — an occupation-specific statement. Has an O*NET task id, an importance
  score (0–100) and a category of `Core`, `Supplemental` or `New`.
- **DWA (Detailed Work Activity)** — the *subtask* layer: a standardised activity
  shared across occupations. This is what lets you compare work across jobs.
- **IWA / GWA** — progressively more general roll-ups of the DWA.

### Where each piece comes from

The website publishes tasks and an occupation's DWAs, but **not** the edge between
an individual task and its DWAs. That crosswalk only exists in the O*NET bulk
database, so the build pulls it from `onetcenter.org` and joins on task id. Run
with `--no-bulk` to stay web-only; you then get occupation→subtask links but no
task→subtask links.

| Output | Source |
| --- | --- |
| STEM roster, categories | `onetonline.org/find/stem?t=…` (scraped) |
| Tasks, importance, category | `onetonline.org/link/details/<code>` (scraped) |
| Occupation → DWA | `onetonline.org/link/details/<code>` (scraped) |
| **Task → DWA** | `onetcenter.org` bulk `tasks_to_dwas.csv` |
| DWA → IWA → GWA | `onetcenter.org` bulk `gwas_to_iwas_to_dwas.csv` |

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Identify yourself to O*NET — courteous, and it keeps you unblocked.
export ONET_CONTACT="you@example.edu"

.venv/bin/python -m onet_scraper
```

A full run is roughly 300 HTTP requests at 1.5 req/s plus ~15 MB of bulk files —
about four minutes. Everything is cached on disk, so a second run is instant and
`--offline` rebuilds with no network at all.

## Outputs

All under `data/out/`, as CSV, plus a SQLite database (`onet_stem.sqlite`) with the
same tables and indexes, and a nested `occupations.json`.

| Table | Grain | What it is |
| --- | --- | --- |
| `occupations` | occupation | title, description, STEM type, job zone, bright outlook, reported job titles |
| `tasks` | occupation × task | task statement, importance, Core/Supplemental/New |
| `task_subtasks` | occupation × task × DWA | **the task→subtask edge** |
| `occupation_subtasks` | occupation × DWA | subtasks as listed on the occupation page |
| `subtask_hierarchy` | DWA | DWA → IWA → GWA roll-up |
| `stem_categories`, `occupation_stem_categories` | — | the STEM taxonomy and its many-to-many membership |
| `tasks_wide` | occupation × task × DWA | **denormalised join of all of the above — start here** |
| `task_ratings` | occupation × task × scale × category | only with `--with-ratings` |
| `occupation_indices` | occupation | collaboration + bottleneck indices (`fetch-descriptors`) |
| `occupation_work_context`, `occupation_abilities`, `occupation_work_activities`, `occupation_essential_skills` | occupation × element × scale | raw O*NET descriptor measures |
| `emerging_tasks`, `related_occupations` | — | newly-emerging work; O*NET's own relatedness baseline |
| `network_*_edges` / `network_*_nodes` | pair / node | occupation and subtask networks (`network`) |
| `subtask_automation_scores`, `task_automation_scores`, `occupation_automation_scores` | subtask / task / occupation | LLM ratings and roll-ups (`score`) |

Alongside them: `manifest.json` (provenance — source URLs, bulk release, content
hashes, run settings) and `validation_report.json`.

Most analyses only need `tasks_wide.csv`:

```python
import pandas as pd
df = pd.read_csv("data/out/tasks_wide.csv")

# Which subtasks show up across the most STEM occupations?
df.groupby("dwa_title")["onet_soc_code"].nunique().sort_values(ascending=False).head(20)

# The task profile of one job
df[df.onet_soc_code == "15-1252.00"][["task", "importance", "dwa_title"]]
```

Or in SQL:

```sql
SELECT o.title, t.task, t.importance, ts.dwa_title
FROM tasks t
JOIN occupations o USING (onet_soc_code)
LEFT JOIN task_subtasks ts USING (onet_soc_code, task_id)
WHERE o.stem_occupation_types LIKE '%Computer%'
ORDER BY t.importance DESC;
```

## Analysis layers

Three optional stages build on the core dataset. Each is independent — run what you need.

### Networks (`network`)

Projects the bipartite occupation×subtask graph two ways:

```bash
python -m onet_scraper network                        # all occupations
python -m onet_scraper network --network-exclude-soc 25   # drop postsecondary teachers
```

- `network_occupation_edges` — a pair per occupation pair sharing ≥3 subtasks, with
  `cosine`, `jaccard`, and `weighted_cosine` (weighted by the importance of the task
  each subtask came from). `same_soc_major_group` lets you isolate cross-family bridges.
- `network_occupation_nodes` / `network_subtask_nodes` — node attributes with degree.
- `network_subtask_edges` — subtask co-occurrence across occupations.
- `network_occupations.graphml` / `network_subtasks.graphml` — open in Gephi or
  Cytoscape, or load with `networkx.read_graphml`.

**Validate before you interpret.** When `related_occupations` is present (from
`fetch-descriptors`), the stage scores itself against O*NET's own related-occupation
list and writes the result to `network_report.json`.

Current result: **recall@10 = 32.4%**, against a structural ceiling of 61.1% — so the
network recovers **53% of what is reachable at k=10**. The ceiling matters: O*NET lists
a median of 17 STEM-related occupations each, and a top-10 list cannot recall 17 items.
The report gives all three numbers so a capped figure isn't mistaken for a bad network.

Perfect agreement would actually be a bad sign — O*NET's relatedness uses skills,
knowledge and abilities as well as activities, so this network is *supposed* to differ.

Cosine, Jaccard, weighted cosine and raw shared-count all score within 1 point of each
other at every k tested. The structure is robust to the weighting choice, and
importance weighting does not improve agreement with O*NET (it is marginally worse).
Use `cosine` unless you have a reason not to.

**`--network-exclude-soc 25` is usually right.** O*NET gives every postsecondary
teaching occupation a near-identical profile; Economics Teachers and Political Science
Teachers score cosine 1.00. They will dominate any ranking or clustering.

### Collaboration and automation-bottleneck indices (`fetch-descriptors`)

Downloads work context, abilities, work activities and essential skills (~80 MB) and
builds `occupation_indices` — five composite 0–100 measures per occupation:

| Index | Built from |
| --- | --- |
| `collaboration` | Contact With Others; Work With or Contribute to a Work Group or Team; Face-to-Face Discussions; Coordinate or Lead Others |
| `responsibility_for_others` | Health and Safety of Other Workers; Work Outcomes and Results of Other Workers |
| `bottleneck_perception_manipulation` | Finger Dexterity; Manual Dexterity; Arm-Hand Steadiness |
| `bottleneck_creative_intelligence` | Originality; Fluency of Ideas |
| `bottleneck_social_intelligence` | Assisting and Caring for Others; Establishing and Maintaining Interpersonal Relationships; Resolving Conflicts and Negotiating with Others |

The last three are Frey & Osborne's engineering bottlenecks to computerisation,
operationalised in O*NET variables.

Indices are defined by element *name* in `config.py`, not by element id, and each
element is rescaled to its observed 0–1 range before averaging so different O*NET
scales mix cleanly. If O*NET renames an element the build logs a warning and leaves
the index null — it never silently returns zero. (This caught three renamed
work-context elements during development.)

Also fetched: `emerging_tasks` (O*NET's own flag for newly-emerging work) and
`related_occupations` (the network validation baseline).

### LLM subtask scoring (`score`)

Rates the ~963 distinct subtasks on seven automation dimensions, then propagates the
scores to all 5,717 tasks and 287 occupations.

```bash
pip install -r requirements-scoring.txt
export ANTHROPIC_API_KEY=...            # or: ant auth login
python -m onet_scraper score --dry-run   # cost estimate, sends nothing
python -m onet_scraper score
```

**Why score subtasks rather than tasks.** There are 5,717 tasks but only 963 distinct
subtasks behind them. Rating the subtask layer is ~6× less work *and* more consistent:
the same activity cannot receive different ratings in two different occupations, which
is exactly the artefact that makes task-level ratings hard to compare across jobs.

Dimensions, each 0–100: `automation_feasibility_today`, `llm_exposure`,
`physical_embodiment_required`, `interpersonal_demand`, `judgment_under_uncertainty`,
`accountability_requirement`, `error_cost` — plus a verdict of
`largely_automatable` / `augmentable` / `resistant` / `human_anchored`, a confidence
level, and a one-line rationale naming the binding constraint.

The dimensions are deliberately separable. An activity can score high on
`llm_exposure` *and* be `human_anchored`: drafting a legal opinion is largely a
language task, but a named human must still be answerable for it. Collapsing that into
one "automation risk" number is the main thing this rubric is built to avoid.

Propagation: subtask → task (mean over the task's subtasks) → occupation
(**importance-weighted** mean over the occupation's tasks, so a job is characterised
by what matters in it, not by its longest tail).

Cost at default settings (`claude-opus-5`, chunks of 12, adaptive thinking): about
**$8**, 81 requests. `--score-model claude-sonnet-5` is about $3.30. Runs are cached
per subtask in `data/raw/subtask_scores.jsonl` and resume automatically; a failed
chunk only re-runs itself.

`RUBRIC_VERSION` in `score.py` is stamped on every row. Change the rubric and bump it —
cached scores from an older rubric are not comparable and will be re-run rather than
silently mixed in.

**This is a model's judgment, not ground truth.** Validate a sample by hand before
building on it, and consider joining published measures (Eloundou et al. 2023 for LLM
exposure keyed to O*NET DWAs; Webb 2020; Brynjolfsson, Mitchell & Rock 2018) as
external comparisons.

### Susceptibility index and dashboard (`report`)

```bash
.venv/bin/python -m onet_scraper report
open data/out/dashboard.html
```

Builds a composite susceptibility index at all three levels and renders a
self-contained interactive dashboard (no server, no CDN, works offline).

**The index is not a mean of the seven dimensions.** Two pairs are near-collinear in
the scored data, and averaging all seven would silently double-count them:

| Pair | r |
| --- | --- |
| `llm_exposure` ↔ `physical_embodiment_required` | −0.89 |
| `accountability_requirement` ↔ `error_cost` | +0.90 |

So each pair collapses to one factor first, leaving two axes:

- **exposure** — can a machine do the work (`llm_exposure`; physical embodiment is its
  mirror, so it is not subtracted again)
- **anchoring** — must a human do it or answer for it (stakes, interpersonal demand,
  judgment under uncertainty, physical embodiment)

`susceptibility = 50 + (exposure − anchoring) / 2`, clamped to 0–100.

**Validation.** The index uses only the numeric dimensions, yet it orders the model's
*independently produced* categorical verdict monotonically — largely_automatable 74.9
> augmentable 65.9 > resistant 43.6 > human_anchored 40.3. That convergence is the
main evidence it measures what it claims. The `report` stage recomputes this every run
and warns if monotonicity ever breaks.

**Quadrants are split at the observed medians, not at 50.** A label means "relative to
other STEM work", not "safe" or "doomed". Current split: exposure 65.3, anchoring 43.5
→ 98 Displaceable, 36 Contested, 100 Human-anchored, 34 Insulated.

Outputs: `subtask_susceptibility`, `task_susceptibility`, `occupation_susceptibility`
(CSV + SQLite), `susceptibility_report.json`, and `dashboard.html`.

### Employment weighting (`employment`)

```bash
export ONET_CONTACT="you@example.edu"     # BLS blocks unidentified bots
.venv/bin/python -m onet_scraper employment
.venv/bin/python -m onet_scraper report   # re-render the dashboard with it
```

Downloads the BLS OEWS national employment and wage file (release discovered at
runtime) and joins it to the susceptibility index. This turns "which occupations are
susceptible" into "how many people are in susceptible occupations".

**The join has one trap, and it is the reason this is a module rather than a
one-liner.** O*NET reports at the 8-digit O*NET-SOC level (`29-1141.01` Acute Care
Nurses); OEWS reports employment at the 6-digit SOC level (`29-1141` Registered
Nurses, 3.38 M people). Five O*NET occupations roll into that one SOC. Attaching OEWS
employment to each O*NET row counts those 3.38 M nurses **five times**. In this
dataset 37 SOC codes have more than one O*NET detail occupation, so the error is large
and completely silent.

So susceptibility is averaged up to the SOC level *first*, then employment is attached
once. `susceptibility_sd_within_soc` reports the spread across each SOC's O*NET
occupations, so a mean that hides a real disagreement is visible rather than assumed
away. There are tests for both behaviours.

Two smaller wrinkles handled: BLS publishes some occupations only at the broad level
(`29-2011` and `29-2012` are both reported as `29-2010`), so codes fall back to the
broad group — and because both then land in the same group, the fallback cannot
double-count either. And BLS suppression markers (`*`, `**`, `#`, `~`) are parsed as
missing, not as numbers.

Results as built: **21.5 M workers across 195 SOC codes.** Employment weighting moves
mean susceptibility only from 58.2 to 58.7 — a small shift, meaning headcount is *not*
concentrated at either end, so the unweighted ranking was not misleading. 43% of STEM
workers sit in the Displaceable quadrant ($1.14 T wage bill), 41% Human-anchored.

Outputs: `soc_susceptibility`, `oews_occupations`, `employment_report.json`, plus an
employment section in the dashboard.

### External validation (`validate-external`)

```bash
.venv/bin/python -m onet_scraper validate-external
```

Everything else in this pipeline is self-consistent by construction. This stage is
the only part that can actually be wrong in a way the rest would not catch, because
it compares the index to measures produced by other people.

Benchmarks come from Eloundou, Manning, Mishkin & Rock (2023), *GPTs are GPTs* —
`occ_level.csv` is keyed to the 8-digit O*NET-SOC code, so it joins directly with no
crosswalk, and carries **human annotator ratings** alongside GPT-4 ones. Their
`autoScores.csv` bundles Frey & Osborne (2017), Felten/Raj/Seamans, and the
Brynjolfsson/Mitchell/Rock SML score at the 6-digit SOC level.

**All 268 occupations matched.** Results:

| Benchmark | Pearson | Spearman | n |
| --- | --- | --- | --- |
| **Human ratings, gamma (broadest)** | **0.846** | 0.820 | 268 |
| **Human ratings, beta (+tools)** | **0.831** | 0.819 | 268 |
| Human ratings, alpha (no tools) | 0.605 | 0.623 | 268 |
| GPT-4, beta | 0.847 | 0.845 | 268 |
| Frey & Osborne (2017) | 0.006 | 0.119 | 150 |
| Felten, Raj & Seamans | −0.178 | −0.245 | 188 |
| Brynjolfsson SML | −0.088 | −0.094 | 188 |

Both halves of that table matter.

**r ≈ 0.85 against independent human experts** is the evidence that the index measures
what it claims. The weaker agreement with *alpha* is expected and coherent: alpha
excludes tools, and this rubric explicitly asks what a model could do *given the right
inputs and tools*, which is the beta/gamma definition.

**The pre-LLM measures do not agree, and should not.** Frey & Osborne give
Mathematicians a 4.7% probability of computerisation; this index ranks them the single
most susceptible STEM occupation. Those measures scored the routine/manual gradient;
LLMs run the other way, landing hardest on non-routine cognitive work that the older
measures called safe. A strong positive correlation here would have been the warning
sign, not the reassurance. (These three expectations were originally written down as
"moderate positive" and the data refuted them — the code records that.)

### The handoff framing (Watson 2026)

Phil Watson's *Considering Handoffs of Cognitive Leadership from Humans to AI*
(Applied Emergence, July 2026) proposes scoring work on two independent axes and
locating each unit on a six-stage scale of cognitive leadership. A handoff is a
crossing between stages. The paper names this corpus directly: *"Machine-readable
decompositions of work already exist, e.g. the Department of Labor's O\*NET database.
The novel work is to identify which tasks are decisions, and then to score where each
decision's authority resides."*

`occupation_handoff.csv` maps the scored dimensions onto that framework.

| Watson's property | Our measure |
| --- | --- |
| **Tractability** — machine-readable state | `100 − physical_embodiment_required` |
| **Tractability** — formalizable options | `100 − judgment_under_uncertainty` |
| **Tractability** — general capability | `llm_exposure` |
| **Tractability** — recurrence | **missing** — O\*NET's FT scale in `task_ratings.csv` would supply it |
| **Tractability** — feedback speed/clarity | **missing** — not in O\*NET; needs new scoring |
| **Resistance** — stakes, irreversibility | `error_cost` |
| **Resistance** — legitimacy needs a human | `accountability_requirement` |
| **Resistance** — relational demand | `interpersonal_demand` |

Watson scores capability and deployment separately and reads the gap between them as
**willingness to permit the handoff**. We already computed that gap; the framing is his.

**Two things do not map, and they matter.** Our unit is the O\*NET *task*; his is the
recurring *decision*, and he is explicit that identifying which tasks are decisions is
the novel work. We have not done it, so the stage numbers are provisional. And six of
his eight properties are covered — recurrence and feedback speed are absent, and
recurrence is the cheaper of the two to add.

Results across 268 occupations: **105 Human held, 98 Crossing now, 36 Handed off, 29
Watch points.** 179 have a pending crossing; 120 of those sit at one of the two
crossings Watson expects to carry most of the strategic weight.

The sharpest single number: **8 occupations are at "AI executed, human veto" today;
current capability could already put 140 there.**

Watch points — capability present, accountability holding the line, wide willingness
gap — are led by Genetic Counselors, Actuaries, Preventive Medicine Physicians and
Epidemiologists.

**Calibration is not theory.** Watson's figure shows the frontier's shape but no
numbers. `FRONTIER_K` is set so the curve passes through the median of the observed
cloud, and `TRACTABILITY_FLOOR` exists because a constant-product curve alone puts
"low on both axes" on the same side as "high tractability, low resistance" — and the
first is not a handoff, it is work AI cannot lead at any level of consequence. Both
constants are fitted to this corpus; re-fit them if it changes.

### The scrollable story (`story`)

```bash
.venv/bin/python -m onet_scraper story
open data/out/story.html
```

A scroll-driven narrative over the same tables the dashboard reads. Seven chapters,
each a sticky hand-inked figure that draws itself as you scroll past its beats:
the inversion against Frey & Osborne, the subtask vocabulary, exposure versus
anchoring, Watson's handoff frontier, the six-stage ladder, the employment weighting,
and the external validation.

Where the dashboard is for interrogating the data, this is for being walked through
what it says. One self-contained file; the only external request is the Google Fonts
link.

The design system — tokens, type pairing, hand-inked SVG marks, the sticky-stage
scroll mechanic — follows `sample_scroller/`. The scenes, copy and data are this
project's. `window.__story.freeze(id, p)` drives any scene to a given progress, which
is how the stills are captured.

**One claim the data corrected.** The story originally opened "in 2013 the safest job
in America was mathematician". Frey & Osborne did put mathematicians in their
lowest-risk band at 4.7%, but within this STEM subset 85 of 150 occupations score
*lower* — STEM is selected for being safe on that measure. The headline now leads
with the r = 0.006 finding, which is what the data actually supports.

### Static figures (`figures`)

```bash
.venv/bin/python -m onet_scraper figures            # data/out/figures/*.png
.venv/bin/python -m onet_scraper figures --dark
.venv/bin/python -m onet_scraper figures --only frontier,network
```

Twelve publication-resolution PNGs at 2× device scale, auto-cropped to content.
A figure page is the dashboard with every card but one hidden, screenshotted by
headless Chrome — so the PNGs cannot drift from what the dashboard shows, because
there is only one implementation of each chart. Every chart in the dashboard also
has its own PNG button, which needs no external tool.

## Known characteristics of the data

Not bugs — things the validation surfaces that you should know before analysing:

- **19 occupations have no tasks.** They are SOC "All Other" residual categories
  (`Engineers, All Other`, `Physicians, All Other`, …). O*NET publishes no task
  data for these anywhere, including the bulk database. The validator counts them
  separately so a real gap would still stand out.
- **98.2% of tasks have at least one subtask.** The 105 unlinked ones are all
  tasks added to the website since the current bulk release (31.0), so O*NET has
  not yet assigned them DWAs. This is a release-lag ceiling, not a scrape gap.
- **264 of 5,717 tasks have no importance score**, and the column is left empty
  rather than filled with a placeholder. Two causes: 102 belong to occupations
  with no incumbent survey, which list their tasks instead of tabulating them (no
  `task_category` either); 157 are `New` tasks O*NET has not rated yet, which the
  site displays as "Not available" behind a `-2` sort sentinel. Scored tasks run
  19–100. A validation check rejects any rating outside 0–100.
- **STEM categories are many-to-many.** The individual category pages hold 302
  rows against 287 unique occupations, because some appear under more than one
  STEM discipline. Use `occupation_stem_categories` rather than assuming one
  category per job.
- **`tasks_wide` has more rows than `tasks`** (7,320 vs 5,717) — one row per
  task×subtask pair. Deduplicate on `task_id` before counting tasks.

## Robustness

The things that usually break a scraper, and what this does about them:

- **Re-runs are free.** Every response is cached on disk by URL hash with its
  fetch time and SHA-256. Parsed occupations are checkpointed to
  `data/raw/occupations.jsonl`, so an interrupted run resumes where it stopped.
- **Self-checking parse.** O*NET prints how many rows each section contains
  ("… 16 displayed"). The build compares that number against the rows it actually
  parsed and fails if they disagree — the check that catches a silently truncated
  table.
- **Layout-independent extraction.** Cells are read by O*NET's own `data-title`
  labels and `data-text` values, not by column position, so a re-ordered table
  does not scramble columns. There is a test for exactly that.
- **Polite by default.** 1.5 req/s shared across workers with jitter, robots.txt
  respected, identifying User-Agent, exponential backoff honouring `Retry-After`.
- **Failures are isolated.** One bad page is logged to `data/raw/failures.json`
  and the run continues; re-running picks up only what is missing.
- **Eleven post-build validations** (see `validation_report.json`) covering coverage,
  orphaned joins, duplicate grain and roster completeness. Errors exit non-zero.
- **Join grain is enforced.** Every table declares its primary key and the writer
  raises on a duplicate, so a fan-out in a join cannot quietly inflate counts.

## Usage

```
python -m onet_scraper [stage] [options]

Stages:  run (default) | fetch-stem | fetch-occupations | fetch-bulk
         fetch-descriptors | build | validate | network | score | report
         employment | validate-external | figures | story | clean-cache
```

| Option | Purpose |
| --- | --- |
| `--contact you@example.edu` | User-Agent contact (or `$ONET_CONTACT`) |
| `--rate 1.5` / `--workers 4` | politeness / throughput |
| `--refresh` | ignore cache and checkpoints, re-fetch everything |
| `--offline` | rebuild from cache only, no network |
| `--cache-ttl-days 7` | re-fetch pages older than this (`0` = never expire) |
| `--limit 10` | smoke test on the first N occupations |
| `--no-bulk` | web-only; leaves `task_subtasks` empty |
| `--with-ratings` | also fetch `task_ratings.csv` (~29 MB): frequency and relevance distributions |
| `--categories 1,2` | only some top-level STEM pages |
| `--save-html` | keep readable page snapshots under `data/raw/html/` |
| `--with-descriptors` | fetch descriptor files (~80 MB) during `run` |
| `--network-exclude-soc 25` | drop SOC prefixes from the network |
| `--network-min-shared 3` | minimum shared subtasks for an occupation edge |
| `--score-model` / `--score-chunk-size` | scoring model and batch size |
| `--dry-run` | for `score`: print the cost estimate and stop |

Run the tests with `python -m unittest discover -s tests`.

## Refreshing later

O*NET updates occupations on a rolling basis and cuts a new database release a few
times a year. To rebuild:

```bash
.venv/bin/python -m onet_scraper --refresh
```

The bulk release is discovered at runtime from `onetcenter.org/database.html`, so a
new release is picked up automatically; the version actually used is recorded in
`manifest.json`.

## What is committed, and what is not

`data/out/` holds the result tables, the dashboard and every validation report — you
can read the findings without running anything. Four kinds of file are gitignored
because they regenerate from what is committed:

| Not committed | Rebuild with |
| --- | --- |
| `onet_stem.sqlite`, `dashboard.html` tables | `python -m onet_scraper report` |
| `*.graphml` | `python -m onet_scraper network` |
| `occupation_work_context.csv` and other descriptor mirrors | `fetch-descriptors` then `build` |
| `data/cache/` (246 MB), `data/raw/` (95 MB) | any fetch stage |

## Data sources and attribution

This repository redistributes data derived from three public sources. If you build on
it, carry these forward.

**O\*NET** — occupations, tasks, detailed work activities, descriptors. Provided by
the U.S. Department of Labor, Employment and Training Administration under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). O\*NET® is a trademark of
USDOL/ETA. Database release recorded per-run in `data/out/manifest.json`.

**BLS OEWS** — employment and wages. U.S. Bureau of Labor Statistics, Occupational
Employment and Wage Statistics, national cross-industry file. U.S. government work,
public domain. Release recorded in `data/out/employment_report.json`.

**Eloundou, Manning, Mishkin & Rock (2023)**, *GPTs are GPTs: An early look at the
labor market impact potential of large language models* — the human and GPT-4
exposure ratings used as the external benchmark.
<https://github.com/openai/GPTs-are-GPTs>

**The automation scores in `subtask_automation_scores.csv` are model-generated**
(Claude Opus 5, rubric version stamped on every row), not survey data and not human
expert judgment. They correlate at r ≈ 0.85 with the human ratings above, which is
evidence of validity, not a substitute for it. Treat them as an instrument with known
provenance, and cite the rubric version if you use them.
