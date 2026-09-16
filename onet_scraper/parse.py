"""HTML -> structured records.

Parsing is driven by O*NET's own ``data-title`` cell labels and section ids rather
than by column position, so a re-ordered or re-styled table does not silently
corrupt the dataset. Where the page states how many rows it is showing
("... 16 displayed") we keep that number and assert against it later.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

from .config import SOC_CODE_RE

log = logging.getLogger(__name__)

_DISPLAYED_RE = re.compile(r"(\d+)\s*displayed")
_TASK_ID_RE = re.compile(r"/moreinfo/task/(\d+)")
_DWA_ID_RE = re.compile(r"/moreinfo/dwa/([0-9A-Za-z.]+)")
_SOC_RE = re.compile(SOC_CODE_RE)
_JOB_ZONE_RE = re.compile(r"Job Zone (One|Two|Three|Four|Five)\b")
_UPDATED_RE = re.compile(r"Updated\s+(\d{4})")

_JOB_ZONE_NUMBERS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class ParseError(RuntimeError):
    """The page did not look like what we expect; better to fail loudly."""


def soup_of(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # lxml missing or broken install
        return BeautifulSoup(html, "html.parser")


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _cells(row: Tag) -> dict[str, Tag]:
    """Map a row's cells by their ``data-title`` label, falling back to position."""
    out: dict[str, Tag] = {}
    for idx, cell in enumerate(row.find_all("td", recursive=False)):
        key = cell.get("data-title") or f"col{idx}"
        out[_clean(key)] = cell
    return out


def _cell_value(cell: Tag | None) -> str:
    """Prefer the sortable ``data-text`` attribute: it is the unadorned value."""
    if cell is None:
        return ""
    if cell.has_attr("data-text"):
        return _clean(cell["data-text"])
    return _clean(cell.get_text(" ", strip=True))


def _displayed_count(section: Tag | None) -> int | None:
    if section is None:
        return None
    match = _DISPLAYED_RE.search(section.get_text(" ", strip=True))
    return int(match.group(1)) if match else None


def _main_table(section: Tag) -> Tag | None:
    table = section.find("table")
    return table if table and table.find("tbody") else None


def _list_items(section: Tag, id_pattern: re.Pattern[str]) -> list[tuple[str | None, str]]:
    """Read a ``<ul><li>`` section, returning (element id, text) per item.

    O*NET uses this shape for detailed work activities, and also for Tasks on
    occupations that have no incumbent ratings to put in a table.
    """
    container = section.find("ul")
    if container is None:
        return []
    items: list[tuple[str | None, str]] = []
    for li in container.find_all("li", recursive=False):
        link = li.find("a", href=id_pattern)
        element_id = id_pattern.search(link["href"]).group(1) if link else None
        label = li.find("div", class_="order-2")
        text = _clean(label.get_text(" ", strip=True)) if label else _clean(li.get_text(" ", strip=True))
        if text:
            items.append((element_id, text))
    return items


# --------------------------------------------------------------------------- #
# STEM index                                                                    #
# --------------------------------------------------------------------------- #
def _index_rows(table: Tag) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tr in table.find("tbody").find_all("tr"):
        cells = _cells(tr)
        code_cell = cells.get("Code")
        code = _clean(code_cell.get_text()) if code_cell else ""
        if not _SOC_RE.fullmatch(code):
            # Defensive: skip spacer/"no results" rows instead of emitting junk.
            log.debug("skipping non-occupation row %r", code)
            continue
        occ_cell = cells.get("Occupation")
        link = occ_cell.find("a") if occ_cell else None
        title = _clean(link.get_text()) if link else _cell_value(occ_cell)
        rows.append(
            {
                "onet_soc_code": code,
                "title": title,
                "occupation_types": _cell_value(cells.get("Occupation Types")),
                "bright_outlook": bool(occ_cell and occ_cell.find(class_="bright-outlook-icon")),
            }
        )
    return rows


def parse_stem_index(html: str) -> list[dict[str, Any]]:
    """Sections of https://www.onetonline.org/find/stem?t=<n>.

    The two large STEM types are split into sub-discipline sections on one page
    (``?t=1#f1`` ... ``#f4``); the smaller types render a single unsectioned table.
    Each returned section carries its anchor so callers can rebuild the category id.
    """
    soup = soup_of(html)
    sections: list[dict[str, Any]] = []

    for table in soup.find_all("table"):
        headers = [_clean(th.get_text()) for th in table.find_all("th")]
        if "Code" not in headers or "Occupation" not in headers or table.find("tbody") is None:
            continue
        heading = table.find_previous(["h2", "h3", "h4"])
        anchor = heading.get("id") if heading is not None else None
        label = _clean(heading.get_text(" ", strip=True)) if heading is not None else ""
        sections.append(
            {
                "anchor": anchor if (anchor or "").startswith("f") else None,
                "heading": label,
                "rows": _index_rows(table),
            }
        )

    if not sections:
        raise ParseError("no occupation table found on the STEM index page")
    if not any(section["rows"] for section in sections):
        raise ParseError("STEM index tables parsed to zero occupations")
    return sections


# --------------------------------------------------------------------------- #
# Occupation details report                                                     #
# --------------------------------------------------------------------------- #
def _parse_header(soup: BeautifulSoup) -> dict[str, Any]:
    h1 = soup.find("h1")
    if h1 is None:
        raise ParseError("details page has no <h1>")
    main = h1.find("span", class_="main")
    sub = h1.find("span", class_="sub")
    sub_text = _clean(sub.get_text(" ", strip=True)) if sub else ""
    code_match = _SOC_RE.search(sub_text)
    updated = _UPDATED_RE.search(sub_text)
    return {
        "title": _clean(main.get_text()) if main else "",
        "onet_soc_code": code_match.group(0) if code_match else "",
        "updated_year": int(updated.group(1)) if updated else None,
        "bright_outlook": "Bright Outlook" in sub_text,
    }


def _parse_intro(soup: BeautifulSoup) -> dict[str, Any]:
    content = soup.find(id="content")
    description, reported_titles = "", []
    if content:
        for para in content.find_all("p", recursive=False):
            label = para.find("b")
            text = _clean(para.get_text(" ", strip=True))
            if label and "reported job titles" in _clean(label.get_text()).lower():
                reported_titles = [
                    t.strip()
                    for t in text.split(":", 1)[-1].split(",")
                    if t.strip()
                ]
            elif not label and not description:
                description = text
    return {"description": description, "reported_job_titles": reported_titles}


def _parse_job_zone(soup: BeautifulSoup) -> int | None:
    section = soup.find(id="JobZone")
    if section is None:
        return None
    match = _JOB_ZONE_RE.search(section.get_text(" ", strip=True))
    return _JOB_ZONE_NUMBERS.get(match.group(1)) if match else None


def parse_tasks(soup: BeautifulSoup) -> tuple[list[dict[str, Any]], int | None]:
    section = soup.find(id="Tasks")
    if section is None:
        return [], None
    declared = _displayed_count(section)
    table = _main_table(section)
    if table is None:
        # Occupations with no incumbent ratings list their tasks instead of
        # tabulating them; there is no importance or Core/Supplemental label.
        tasks = [
            {
                "task_id": int(task_id) if task_id else None,
                "task": text,
                "task_category": None,
                "importance": None,
                "relevance": None,
                "display_rank": rank,
            }
            for rank, (task_id, text) in enumerate(_list_items(section, _TASK_ID_RE), start=1)
        ]
        return tasks, declared

    tasks: list[dict[str, Any]] = []
    for position, tr in enumerate(table.find("tbody").find_all("tr"), start=1):
        cells = _cells(tr)
        task_cell = cells.get("Task")
        statement = _cell_value(task_cell)
        if not statement:
            continue
        task_id = None
        if task_cell is not None:
            link = task_cell.find("a", href=_TASK_ID_RE)
            if link:
                task_id = int(_TASK_ID_RE.search(link["href"]).group(1))

        # O*NET renders unrated scores as "Not available" with a negative
        # data-text sort sentinel (-2 for New tasks); those are missing, not zero.
        raw_importance = _score_value(cells.get("Importance"))
        raw_relevance = _score_value(cells.get("Relevance"))
        tasks.append(
            {
                "task_id": task_id,
                "task": statement,
                "task_category": _cell_value(cells.get("Category")) or None,
                "importance": _as_float(raw_importance),
                "relevance": _as_float(raw_relevance),
                "display_rank": position,
            }
        )
    return tasks, declared


def _score_value(cell: Tag | None) -> str:
    """A 0-100 rating, or "" when the page says the rating is unavailable."""
    if cell is None:
        return ""
    if "not available" in _clean(cell.get_text(" ", strip=True)).lower():
        return ""
    value = _cell_value(cell)
    parsed = _as_float(value)
    return "" if parsed is not None and parsed < 0 else value


def _as_float(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return None


def parse_dwas(soup: BeautifulSoup) -> tuple[list[dict[str, Any]], int | None]:
    """Occupation-level detailed work activities (O*NET's 'subtask' layer)."""
    section = soup.find(id="DetailedWorkActivities")
    if section is None:
        return [], None
    declared = _displayed_count(section)
    dwas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, (dwa_id, title) in enumerate(_list_items(section, _DWA_ID_RE), start=1):
        key = dwa_id or title
        if key in seen:
            continue
        seen.add(key)
        dwas.append({"dwa_id": dwa_id, "dwa_title": title, "display_rank": position})
    return dwas, declared


def parse_occupation(html: str, expected_code: str | None = None) -> dict[str, Any]:
    soup = soup_of(html)
    record: dict[str, Any] = _parse_header(soup)
    record.update(_parse_intro(soup))
    record["job_zone"] = _parse_job_zone(soup)

    tasks, tasks_declared = parse_tasks(soup)
    dwas, dwas_declared = parse_dwas(soup)
    record["tasks"] = tasks
    record["dwas"] = dwas
    record["counts"] = {
        "tasks_parsed": len(tasks),
        "tasks_declared": tasks_declared,
        "dwas_parsed": len(dwas),
        "dwas_declared": dwas_declared,
    }

    if expected_code and record["onet_soc_code"] and record["onet_soc_code"] != expected_code:
        raise ParseError(
            f"page for {expected_code} reports code {record['onet_soc_code']}"
        )
    if expected_code and not record["onet_soc_code"]:
        record["onet_soc_code"] = expected_code
    return record
