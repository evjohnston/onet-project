"""One type and colour system, shared by every page the pipeline emits.

The landing page, the story and the methodology were built on a set of design
tokens. The dashboard and the security matrix were not: they shipped with a raw
`-apple-system` stack, no serif, no monospace, and their own surface colours
(#fcfcfb against the system's #faf9f5, #0b0b0b against #1c1c18). Read end to
end, that is the single thing that makes the site feel assembled rather than
designed, so the tokens live here and every page pulls from the same place.

WHY THE FONT LINK IS SAFE TO INCLUDE EVERYWHERE. The dashboard's contract is
that it opens from a `file://` URL with no network and still works. A stylesheet
`<link>` that fails to resolve does not break a page - the families fall back
through Helvetica / Georgia / ui-monospace - so including it costs nothing
offline and makes the published page match the rest of the site.

THE TYPOGRAPHIC RULES THAT WERE MISSING, and why each one matters:

  tracking on uppercase   Small caps-styled labels set at their natural
                          letter-spacing look cramped and accidental. Uppercase
                          wants 0.06-0.1em. This was the most visible defect.
  tabular numerals        A column of figures in proportional digits does not
                          line up, so the eye cannot compare down the column.
  no negative tracking    DM Serif Display is already tightly fitted. The
    on the display serif  dashboard applied -0.01/-0.02em, which collides the
                          terminals at display sizes.
  inline code padding     5px of horizontal padding detaches a code span from
                          the punctuation next to it, so "(`?t=0`)" reads as
                          "( ?t=0 )". 3px plus a compensating negative margin
                          keeps the bracket tight.
"""

from __future__ import annotations

# Loaded by every page. Weights are the ones actually used: Manrope 400/500/600
# for body and labels, DM Serif Display for titles, IBM Plex Mono 400/500 for
# eyebrows, figures and code.
FONTS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=IBM+Plex+Mono:wght@400;500&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">"""

# The families and the paper/ink palette, identical to scroller.css and the
# landing page. Chart-specific roles (grid, axis, series, diverging, sequential)
# are kept because the charts need them, but they are re-pinned onto the paper
# surface rather than the near-white one they were drawn against.
TOKENS = """
  --serif: 'DM Serif Display', Georgia, 'Times New Roman', serif;
  --sans: 'Manrope', Helvetica, Arial, sans-serif;
  --mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace;

  --ink: #1c1c18; --paper: #faf9f5; --paper-2: #f2efe5; --paper-3: #f8f6f0;
  --rust: #bf5540; --amber: #d9a43a; --blue: #5b8fc9; --violet: #4a3aa7;
  --line: rgba(28, 28, 24, .15);

  --surface-1: #faf9f5; --surface-2: #f2efe5; --surface-3: #ebe7da;
  --text-primary: #1c1c18; --text-secondary: #55554d; --text-muted: #6e6e66;
  --grid: #e2ded0; --axis: #c9c4b4;
  --series-1: #2a78d6; --series-2: #bf5540; --series-3: #1baf7a;
  --div-low: #2a78d6; --div-mid: #f2efe5; --div-high: #bf5540;
  --seq-1: #cde2fb; --seq-2: #9ec5f4; --seq-3: #5598e7; --seq-4: #2a78d6;
  --seq-5: #256abf; --seq-6: #184f95; --seq-7: #0d366b;
"""

TOKENS_DARK = """
  --ink: #faf9f5; --paper: #1c1c18; --paper-2: #26261f; --paper-3: #232321;
  --line: rgba(250, 249, 245, .16);

  --surface-1: #1c1c18; --surface-2: #16160f; --surface-3: #26261f;
  --text-primary: #faf9f5; --text-secondary: #c3c2b7; --text-muted: #a9a9a0;
  --grid: #333330; --axis: #4a4a45;
  --series-1: #6fa4e6; --series-2: #d9765d; --series-3: #34c193;
  --div-low: #6fa4e6; --div-mid: #26261f; --div-high: #d9765d;
"""

# The typographic base. Everything here is about how type sits, not layout, so a
# page can adopt it without its own structure changing.
BASE = """
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body { margin: 0; }

/* Body copy. Manrope needs no tracking adjustment at text sizes. */
.viz-root, .m3-root {
  font-family: var(--sans);
  font-size: 14px;
  line-height: 1.55;
  font-feature-settings: 'kern' 1, 'liga' 1;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  color: var(--text-primary);
}

/* Page and card titles in the display serif. No negative tracking: DM Serif
   Display is already tightly fitted and pulling it in collides the terminals. */
.viz-root h1, .m3-root h1 {
  font: 400 clamp(1.7rem, 3.2vw, 2.25rem)/1.1 var(--serif);
  letter-spacing: 0;
  margin: 0 0 6px;
}
.viz-root h2, .m3-root h2 {
  font: 400 1.22rem/1.25 var(--serif);
  letter-spacing: 0;
  margin: 0 0 4px;
}

/* The eyebrow/label style: uppercase monospace WITH tracking. Uppercase set at
   its natural spacing is the single most common "unfinished" tell. */
.lbl, .viz-root .lbl, .m3-root .lbl,
.axes b, .ctl > label {
  font: 500 10px/1.5 var(--mono);
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--text-muted);
}

/* Figures line up or they cannot be compared down a column. */
.num, td.num, th.num, .kpi .v, .stat .v,
[data-num], .tip dd, .tip .r span:last-child {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}

/* Table headers are labels, so they get the label treatment. */
.viz-root th, .m3-root th {
  font: 500 10px/1.5 var(--mono);
  text-transform: uppercase;
  letter-spacing: .085em;
  color: var(--text-muted);
  font-weight: 500;
}

/* Inline code hugs its punctuation: 3px of padding plus a matching negative
   margin, so "(`?t=0`)" does not read as "( ?t=0 )". */
code, .mono {
  font: 500 .88em var(--mono);
  font-variant-ligatures: none;
}
code {
  background: var(--paper-2);
  padding: 1px 3px;
  margin: 0 -1px;
  border-radius: 3px;
}

/* SVG text inherits nothing useful by default. */
svg text { font-family: var(--sans); }
svg text.mono, svg .axis-label, svg .corner-label {
  font-family: var(--mono);
  letter-spacing: .085em;
}
"""


def head(title: str, extra_css: str = "", root_class: str = "viz-root",
         extra_tokens: str = "", extra_tokens_dark: str = "") -> str:
    """The shared <head> for a standalone page.

    extra_tokens lets a page add its own custom properties (a chart-specific
    ramp, say) to the same three selectors the shared tokens use, so a page
    never has to restate the light/dark plumbing.
    """
    light = TOKENS + extra_tokens
    dark = TOKENS_DARK + extra_tokens_dark
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
{FONTS}
<style>
.{root_class} {{ color-scheme: light;{light}}}
@media (prefers-color-scheme: dark) {{
  :root:where(:not([data-theme="light"])) .{root_class} {{ color-scheme: dark;{dark}}}
}}
:root[data-theme="dark"] .{root_class} {{ color-scheme: dark;{dark}}}
{BASE}
{extra_css}
</style></head>
"""
