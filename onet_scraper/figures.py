"""Render each dashboard chart to a standalone PNG.

Reuses the dashboard's own chart code rather than redrawing anything: a figure
page is the full dashboard with every card but one hidden, screenshotted by
headless Chrome and auto-cropped to its content. So the PNGs cannot drift away
from what the dashboard shows - there is only one implementation of each chart.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge",
)


@dataclass(frozen=True)
class Figure:
    name: str
    card_id: str          # the card to keep visible
    width: int = 1100
    height: int = 1500    # generous; the result is cropped to content


FIGURES = (
    Figure("01-handoff-frontier", "card-frontier", 1200),
    Figure("02-cognitive-leadership-stages", "card-stages", 1150),
    Figure("03-displacement-ranking", "card-answer", 1350, 1200),
    Figure("04-quadrant-scatter", "card-scatter", 1150),
    Figure("05-validation-benchmarks", "val-card", 1250),
    Figure("06-occupation-network", "card-network", 1200, 1100),
    Figure("07-subtask-leverage", "card-leverage", 1200),
    Figure("08-most-susceptible", "card-bars-top", 620),
    Figure("09-least-susceptible", "card-bars-bot", 620),
    Figure("10-willingness-gap", "card-dumbbell", 1100),
    Figure("11-employment", "emp-card", 1250),
    Figure("12-subtask-table", "card-subtasks", 1150, 1200),
)


def find_chrome(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit if Path(explicit).exists() or shutil.which(explicit) else None
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


def figure_page(dashboard_html: str, figure: Figure, dark: bool) -> str:
    """The dashboard with one card visible. Hidden cards take no layout space."""
    theme = "dark" if dark else "light"
    inject = f"""
<script>
document.documentElement.setAttribute('data-theme', '{theme}');
(function () {{
  const keep = {figure.card_id!r};
  function isolate() {{
    document.querySelectorAll('.card, .kpis, .topbar').forEach(n => {{
      if (n.id !== keep && !n.contains(document.getElementById(keep)))
        n.style.display = 'none';
    }});
    const card = document.getElementById(keep);
    if (card) {{
      card.style.display = '';
      card.style.margin = '0';
      card.querySelectorAll('.png').forEach(b => b.remove());
    }}
    document.querySelector('.viz-root').style.padding = '18px';
    document.body.style.background = getComputedStyle(
      document.querySelector('.viz-root')).getPropertyValue('--surface-1');
  }}
  // Run after the dashboard's staged render has finished laying out.
  window.addEventListener('load', () => setTimeout(() => {{
    isolate();
    if (typeof renderAll === 'function') renderAll();
    setTimeout(isolate, 120);
  }}, 60));
}})();
</script>
"""
    return dashboard_html.replace("</body>", inject + "</body>")


def autocrop(path: Path, pad: int = 14) -> tuple[int, int] | None:
    """Trim the uniform background margin left by a generous window size."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        log.warning("pillow not installed; PNGs keep their full window height")
        return None
    with Image.open(path) as im:
        im = im.convert("RGB")
        bg = Image.new("RGB", im.size, im.getpixel((1, 1)))
        box = ImageChops.difference(im, bg).getbbox()
        if not box:
            return im.size
        left, top, right, bottom = box
        left, top = max(0, left - pad), max(0, top - pad)
        right, bottom = min(im.width, right + pad), min(im.height, bottom + pad)
        out = im.crop((left, top, right, bottom))
        out.save(path)
        return out.size


def render(
    dashboard: Path,
    out_dir: Path,
    *,
    chrome: str | None = None,
    dark: bool = False,
    scale: int = 2,
    only: tuple[str, ...] = (),
) -> list[Path]:
    binary = find_chrome(chrome)
    if binary is None:
        raise SystemExit(
            "no Chrome/Chromium found for PNG rendering. Install Chrome, or pass "
            "--chrome /path/to/binary. (The dashboard also has a PNG button on "
            "every chart, which needs no external tool.)"
        )
    dashboard = dashboard.resolve()
    html = dashboard.read_text(encoding="utf-8")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_pages"
    work.mkdir(exist_ok=True)

    written = []
    figures = [f for f in FIGURES if not only or f.name in only or
               any(o in f.name for o in only)]
    for fig in figures:
        page = work / f"{fig.name}.html"
        page.write_text(figure_page(html, fig, dark), encoding="utf-8")
        suffix = "-dark" if dark else ""
        png = out_dir / f"{fig.name}{suffix}.png"
        cmd = [
            binary, "--headless", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", f"--force-device-scale-factor={scale}",
            "--virtual-time-budget=8000",
            f"--window-size={fig.width},{fig.height}",
            f"--screenshot={png}", page.as_uri(),
        ]
        if dark:
            cmd.insert(4, "--force-dark-mode")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if not png.exists():
            log.error("failed to render %s: %s", fig.name, result.stderr[-300:])
            continue
        size = autocrop(png)
        written.append(png)
        log.info("wrote %-34s %s", png.name,
                 f"{size[0]}x{size[1]}" if size else "(uncropped)")

    shutil.rmtree(work, ignore_errors=True)
    return written
