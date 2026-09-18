"""Load every published page in a real browser and assert it rendered.

The dashboard shipped for an unknown length of time reading `window.DATA.hand`
when the payload was declared `const DATA = ...`. A `const` at script scope does
not become a window property, so the lookup returned undefined, the handoff Map
was empty, and three columns rendered blank while the page itself looked fine.
No test caught it because no test ever loaded a page.

Two things are checked per page:

  console      any `Uncaught` on the console fails the page. Chrome reports
               these on stderr under --enable-logging, which is the only way to
               see them without a driver library.
  content      assertions against the post-JavaScript DOM. This is the half
               that matters: the window.DATA bug threw nothing at all. It
               produced a page whose Workers column was an em dash on every one
               of 268 rows, so the assertion that catches it has to be "this
               column is not entirely placeholder", not "the page loaded".

Deliberately no Selenium/Playwright: headless Chrome with --dump-dom is already
in the image for the figure export, and a dependency that only runs in CI is a
dependency that rots.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Callable, Sequence

log = logging.getLogger(__name__)

RENDER_WAIT_MS = 6000     # story.html builds 14 scenes before it settles


def _count(pattern: str) -> Callable[[str], int]:
    rx = re.compile(pattern, re.I)
    return lambda dom: len(rx.findall(dom))


def _cells(column_header: str) -> Callable[[str], list[str]]:
    """Pull one column's cell text out of the table that declares that header.

    Scoped to the enclosing <table>. A first version searched every <tr> in the
    document and applied the header's column index to all of them, so rows from
    other tables leaked in - it returned 437 cells for a 268-row table, and the
    borrowed rows were enough to mask a column that had come through empty.

    Crude on purpose: a real parser would need lxml on the DOM dump, and the
    only question being asked is whether a column populated at all.
    """
    def extract(dom: str) -> list[str]:
        for table in re.findall(r"<table[^>]*>(.*?)</table>", dom, re.S | re.I):
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
            header = next((r for r in rows if "<th" in r.lower()
                           and column_header.lower()
                           in re.sub(r"<[^>]+>", " ", r).lower()), None)
            if header is None:
                continue
            cols = re.findall(r"<th[^>]*>(.*?)</th>", header, re.S | re.I)
            idx = next((i for i, c in enumerate(cols)
                        if column_header.lower()
                        in re.sub(r"<[^>]+>", "", c).lower()), None)
            if idx is None:
                continue
            out = []
            for r in rows:
                tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S | re.I)
                if len(tds) > idx:
                    out.append(re.sub(r"<[^>]+>", "", tds[idx]).strip())
            return out
        return []
    return extract



def _runners_traverse(dom: str) -> bool:
    """Read the probe's verdict out of the dumped DOM."""
    m = re.search(r'data-probe="([^"]*)"', dom)
    if not m:
        return False
    entries = [e for e in m.group(1).split() if ":" in e]
    if not entries:
        return False                    # the probe ran and found no runners
    for entry in entries:
        moved, _, total = entry.partition(":")[2].partition("/")
        if not total or int(moved) != int(total):
            return False
    return True


Assertion = tuple[str, Callable[[str], bool]]

# Some occupations genuinely have no BLS employment match, so a column is not
# required to be wholly populated - but 268 placeholders out of 268 is a failed
# join, not a data gap. A fraction is the honest test. The first version asked
# whether ANY value was non-placeholder, which passed the exact bug this module
# exists to catch.
MAX_PLACEHOLDER_SHARE = 0.5
PLACEHOLDERS = {"n/a", "\u2014", "-", "", "0", "none"}


def _mostly_populated(column: str,
                      limit: float = MAX_PLACEHOLDER_SHARE) -> Callable[[str], bool]:
    get = _cells(column)

    def ok(dom: str) -> bool:
        vals = [v for v in get(dom) if v]
        if not vals:
            return False
        blank = sum(1 for v in vals if v.lower() in PLACEHOLDERS)
        return blank / len(vals) <= limit
    return ok


# name -> (assertion label, predicate over the rendered DOM)
PAGES: dict[str, Sequence[Assertion]] = {
    "index.html": (
        ("links to all three entry points", lambda d: all(
            x in d for x in ("story.html", "dashboard.html", "security_matrix.html"))),
        ("stat row rendered", lambda d: _count(r"class=\"[^\"]*stat")(d) >= 4),
    ),
    "methodology.html": (
        ("sections rendered", lambda d: _count(r"<h2")(d) >= 8),
        ("tables rendered", lambda d: _count(r"<table")(d) >= 6),
        ("numeric columns aligned", lambda d: _count(r'class="num"')(d) >= 20),
    ),
    "dashboard.html": (
        ("occupation table populated", lambda d: _count(r"<tr")(d) >= 100),
        ("kpi figures rendered", lambda d: _count(r"class=\"v\"")(d) >= 5),
        ("charts drawn", lambda d: _count(r"<circle")(d) >= 200),
        # the window.DATA regression, stated as content
        ("workers column populated", _mostly_populated("Workers")),
        ("handoff class column populated",
         _mostly_populated("Handoff class")),
        ("stage column populated",
         _mostly_populated("Stage today")),
    ),
    "security_matrix.html": (
        ("cloud drawn", lambda d: _count(r"<circle")(d) >= 200),
        ("eight cells listed", lambda d: _count(r"class='oct'|class=\"oct\"")(d) >= 8),
        ("cell counts are not all zero", _mostly_populated("n")),
        ("axis frame drawn", lambda d: _count(r"<line")(d) >= 12),
    ),
    "story.html": (
        ("scenes drawn", lambda d: _count(r"<svg")(d) >= 8),
        ("marks drawn", lambda d: _count(r"<path")(d) >= 100),
        # The stage viewBox is recomputed to the container's aspect ratio; if it
        # is ever back to a literal 1600 900 the drawing is letterboxing again.
        ("stage viewbox is fitted, not fixed",
         lambda d: 'viewBox="0 0 1600 900"' not in d),
        ("heading rules inked", lambda d: _count(r'class="headrule"')(d) >= 10),
        # The Sankey's ribbons are built at scene-build time, so they are in the
        # DOM before any scrolling. The dots are not - they appear once the
        # scene reaches the progress that reveals each band - so only the
        # ribbons can be asserted from a static dump.
        ("sankey ribbons built", lambda d: _count(r'class="ribbon')(d) >= 3),
        ("motion is gated on scroll",
         lambda d: "animation-play-state:paused" in d.replace(" ", "")),
        # Every scene that builds runners must have them traversing their path.
        # "n/n" for each scene the probe found dots in; a scene reporting 0/n
        # has dots that are wired but going nowhere.
        ("runners traverse their paths", _runners_traverse),
    ),
}


# Headless Chrome does not advance the animation clock - a plain translateX
# keyframe reports the same position a second later, and getAnimations()
# currentTime stays at 0. So "does it animate" cannot be observed by waiting.
# It CAN be observed by driving the timeline: setting an animation's currentTime
# forces the computed style at that moment, so sampling a mark's position at two
# points on its own timeline proves the animation is wired and traverses its
# path. That is what this probe does, and it is the only way to catch an
# animation regression in CI.
ANIMATION_PROBE = """
(function(){
  var out = [];
  /* Runners are created when a scene reaches the progress that reveals them,
     so at page load - every scene at 0 - there are none to sample. Drive them
     all to the end first. Without this the probe found nothing and reported
     success by vacuity, which is the one result a check must never give. */
  if(window.__story){ window.__story.pause(); window.__story.freezeAll(1); }
  document.querySelectorAll('[data-scene]').forEach(function(sec){
    var dots = sec.querySelectorAll('.sankey-dot');
    if(!dots.length) return;
    var moved = 0;
    dots.forEach(function(d){
      var a = d.getAnimations()[0];
      if(!a || !a.effect) return;
      var dur = a.effect.getTiming().duration;
      if(!dur) return;
      a.currentTime = 0;       var p0 = d.getBoundingClientRect();
      a.currentTime = dur*0.4; var p1 = d.getBoundingClientRect();
      a.currentTime = 0;
      if(Math.abs(p1.left-p0.left) + Math.abs(p1.top-p0.top) > 1) moved++;
    });
    out.push(sec.id + ':' + moved + '/' + dots.length);
  });
  document.body.setAttribute('data-probe', out.join(' '));
})();
"""


def render(binary: str, path: Path, wait_ms: int = RENDER_WAIT_MS,
           probe: str = "") -> tuple[str, list[str]]:
    """Return (post-JS DOM, console errors).

    `probe` is script run against the loaded page before the DOM is dumped; it
    is expected to record its findings in an attribute so they survive into the
    dump. Injected by rewriting the page into a temporary copy, because
    --dump-dom offers no way to evaluate script.
    """
    target = path
    tmp = None
    if probe:
        html = path.read_text()
        if "</body>" in html:
            tmp = path.parent / (".smoke-probe-" + path.name)
            tmp.write_text(html.replace(
                "</body>", "<script>addEventListener('load', function(){"
                           "setTimeout(function(){" + probe + "}, 400);});</script></body>", 1))
            target = tmp
    try:
        proc = subprocess.run(
            [binary, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
             "--enable-logging=stderr", "--log-level=0",
             f"--virtual-time-budget={wait_ms}", "--dump-dom", target.as_uri()],
            capture_output=True, text=True, timeout=180)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()
    errors = [ln for ln in proc.stderr.splitlines()
              if "Uncaught" in ln or "SEVERE:" in ln]
    return proc.stdout, errors


def check(binary: str, docs: Path,
          pages: dict[str, Sequence[Assertion]] | None = None) -> list[dict[str, object]]:
    pages = pages or PAGES
    results: list[dict[str, object]] = []
    for name, assertions in pages.items():
        path = docs / name
        if not path.exists():
            results.append({"page": name, "assertion": "file exists",
                            "passed": False, "detail": f"{path} not found"})
            continue
        dom, errors = render(binary, path,
                             probe=ANIMATION_PROBE if name == "story.html" else "")
        results.append({"page": name, "assertion": "no uncaught console errors",
                        "passed": not errors,
                        "detail": "; ".join(errors[:3]) or "clean"})
        for label, predicate in assertions:
            try:
                passed = bool(predicate(dom))
                detail = "" if passed else "assertion returned false"
            except Exception as exc:                      # noqa: BLE001
                passed, detail = False, f"{type(exc).__name__}: {exc}"
            results.append({"page": name, "assertion": label,
                            "passed": passed, "detail": detail})
    return results


def log_report(results: Sequence[dict[str, object]]) -> int:
    failed = 0
    current = None
    for r in results:
        if r["page"] != current:
            current = r["page"]
            log.info("%s", current)
        mark = "PASS" if r["passed"] else "FAIL"
        if not r["passed"]:
            failed += 1
        log.info("  %-5s %-42s %s", mark, r["assertion"], r["detail"])
    return failed
