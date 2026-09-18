"""Check the prose against the data it describes.

METHODOLOGY.md quotes several hundred figures, and nothing verified any of them.
They have now rotted twice in one session: the test count drifted to 66 while
the suite passed 170, and consolidating the two scoring passes moved every
security-matrix cell and the whole scenarios table while the document went on
reporting the old ones. Both times the document was wrong for hours and looked
completely normal.

The difficulty is that a claim in prose is not machine-checkable in general. So
this does not try. It carries an explicit register of (claim in the document ->
where the number actually comes from), which has two useful properties: the
coupling between prose and data becomes visible in one place, and a figure that
moves fails the build instead of quietly misreporting.

The register is not exhaustive and does not pretend to be. It covers the tables
and headline figures - the numbers a reader is most likely to quote - and each
entry names its own source so a mismatch says where to look.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)


def _csv(out: Path, name: str) -> list[dict[str, str]]:
    path = out / f"{name}.csv"
    return list(csv.DictReader(path.open())) if path.exists() else []


def _json(out: Path, name: str) -> dict[str, Any]:
    path = out / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def _num(text: str) -> str:
    return text.replace(",", "").replace("−", "-").strip()


# --------------------------------------------------------------------------- #
# The register
# --------------------------------------------------------------------------- #
# Each check gets the document text and the out directory, and returns a list of
# (label, expected, found) for anything that disagrees. Returning [] is a pass.

def _counts_table(md: str, out: Path) -> list[tuple[str, str, str]]:
    want = {
        "STEM occupations": len(_csv(out, "occupations")),
        "Task statements": len(_csv(out, "tasks")),
        "Occupations with automation scores": len(_csv(out, "occupation_susceptibility")),
        "Tasks with automation scores": len(_csv(out, "task_automation_scores")),
    }
    bad = []
    for label, n in want.items():
        m = re.search(re.escape(label) + r" \| ([\d,]+)", md)
        if not m:
            bad.append((label, str(n), "absent from the document"))
        elif _num(m.group(1)) != str(n):
            bad.append((label, f"{n:,}", m.group(1)))
    return bad


def _scenarios_table(md: str, out: Path) -> list[tuple[str, str, str]]:
    rep = _json(out, "scenarios_report").get("scenarios", {})
    bad = []
    for key in ("modest", "substantial", "extreme"):
        s = rep.get(key)
        if not s:
            continue
        m = re.search(r"\| " + key.capitalize() + r" \|[^|]*\| ([\d,]+) \((\d+)%\)", md)
        if not m:
            bad.append((f"scenarios/{key}", str(s["automated"]), "absent"))
            continue
        if _num(m.group(1)) != str(s["automated"]):
            bad.append((f"scenarios/{key} count", f"{s['automated']:,}", m.group(1)))
        pct = round(100 * s["share_automated"])
        if int(m.group(2)) != pct:
            bad.append((f"scenarios/{key} share", f"{pct}%", m.group(2) + "%"))
    return bad


def _security_cells(md: str, out: Path) -> list[tuple[str, str, str]]:
    rep = _json(out, "security_report").get("scenarios", {})
    bad = []
    for name, cell in (rep.get("substantial", {}).get("by_octant") or {}).items():
        m = re.search(r"\| " + re.escape(name) + r" \| ([\d]+) / ([\d.]+)% \| ([\d]+) / ([\d.]+)%",
                      md)
        if not m:
            continue
        if int(m.group(3)) != cell["occupations"]:
            bad.append((f"security/{name}", str(cell["occupations"]), m.group(3)))
    return bad


def _benchmark_table(md: str, out: Path) -> list[tuple[str, str, str]]:
    """The benchmark table, row by row.

    A first version of this looked for the correlations in PROSE and passed
    while the table beside it was stale - a false pass, which is worse than no
    check at all. The figures live in the table, so the table is what gets read.
    """
    rep = _json(out, "external_validation")
    by = {r["measure"]: r for r in rep.get("susceptibility_vs", [])}
    # document label -> measure key in the report
    LABELS = {
        "Human expert ratings, γ": "human_gamma",
        "Human expert ratings, β": "human_beta",
        "Human expert ratings, α (no tools)": "human_alpha",
        "GPT-4, β": "gpt4_beta",
        "Frey & Osborne (2017)": "frey_osborne",
        "Felten, Raj & Seamans": "felten_raj_seamans",
        "Brynjolfsson/Mitchell/Rock SML": "brynjolfsson_sml",
    }
    bad = []
    for row in re.findall(r"^\| ([^|]+?) \| ([^|]+?) \| ([\d]+) \|$", md, re.M):
        label = row[0].strip().strip("*").strip()
        key = LABELS.get(label)
        if not key or key not in by:
            continue
        doc = float(_num(row[1].strip().strip("*")))
        real = by[key]["pearson"]
        if abs(doc - real) > 0.005:
            bad.append((f"r vs {key}", f"{real:+.3f}", f"{doc:+.3f}"))
        if int(row[2]) != by[key]["n"]:
            bad.append((f"n for {key}", str(by[key]["n"]), row[2]))
    if not bad and not any(LABELS.get(r[0].strip().strip("*").strip()) in by
                           for r in re.findall(r"^\| ([^|]+?) \| ([^|]+?) \| ([\d]+) \|$",
                                               md, re.M)):
        # the table moved or was renamed: silence here would be a false pass
        bad.append(("benchmark table", "found", "no recognised rows"))
    return bad


def _test_count(md: str, out: Path) -> list[tuple[str, str, str]]:
    import unittest
    root = Path(__file__).resolve().parents[1]
    tests = root / "tests"
    if not tests.exists():
        return []
    actual = unittest.TestLoader().discover(str(tests)).countTestCases()
    bad = []
    for quoted in set(re.findall(r"(\d+) tests", md)):
        if int(quoted) != actual:
            bad.append(("quoted test count", str(actual), quoted))
    return bad


CHECKS: tuple[tuple[str, Callable[[str, Path], list[tuple[str, str, str]]]], ...] = (
    ("counts table", _counts_table),
    ("scenarios table", _scenarios_table),
    ("security cells", _security_cells),
    ("benchmark table", _benchmark_table),
    ("quoted test count", _test_count),
)


def validate_doc(md_path: Path, out_dir: Path) -> list[dict[str, Any]]:
    md = md_path.read_text()
    results = []
    for label, fn in CHECKS:
        try:
            bad = fn(md, out_dir)
        except Exception as exc:                            # noqa: BLE001
            results.append({"check": label, "passed": False,
                            "detail": f"{type(exc).__name__}: {exc}", "rows": []})
            continue
        results.append({"check": label, "passed": not bad,
                        "detail": "in step with the data" if not bad
                                  else f"{len(bad)} figure(s) disagree",
                        "rows": [{"figure": a, "data": b, "document": c} for a, b, c in bad]})
    return results


def log_report(results: list[dict[str, Any]]) -> int:
    failed = 0
    for r in results:
        log.info("%-5s %-26s %s", "PASS" if r["passed"] else "FAIL",
                 r["check"], r["detail"])
        for row in r["rows"]:
            failed += 1
            log.error("        %-34s data %-10s document %s",
                      row["figure"], row["data"], row["document"])
    return failed
