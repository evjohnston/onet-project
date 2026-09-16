"""O*NET descriptor files -> per-occupation measures and composite indices.

The scraped task data says *what* a job does. These files say *how* it is done:
how much contact with other people, how much manual dexterity, how much
originality. That is what turns the task dataset into something you can ask
collaboration and automation questions of.
"""

from __future__ import annotations

import logging
import statistics
from typing import Any, Iterable, Sequence

from .config import AUGMENT_FILES, INDEX_DEFINITIONS

log = logging.getLogger(__name__)

# The long-format descriptor files all share these column names.
CODE, ELEM_ID, ELEM_NAME = "O*NET-SOC Code", "Element ID", "Element Name"
SCALE, VALUE = "Scale ID", "Data Value"

DESCRIPTOR_TABLES = {
    "work_context.csv": "occupation_work_context",
    "abilities.csv": "occupation_abilities",
    "work_activities.csv": "occupation_work_activities",
    "essential_skills.csv": "occupation_essential_skills",
}

# work_context's percentage scales (CXP/CTP) emit one row per response category,
# so category is part of the grain even though the other files leave it blank.
DESCRIPTOR_COLUMNS = ("onet_soc_code", "element_id", "element_name", "scale_id",
                      "scale_name", "category", "data_value", "n", "standard_error",
                      "recommend_suppress", "date")


class DescriptorError(RuntimeError):
    pass


def _f(value: str | None) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def normalise_descriptor(rows: Iterable[dict[str, str]],
                         stem_codes: set[str]) -> list[dict[str, Any]]:
    """Filter a long-format descriptor file to STEM occupations."""
    out = []
    for row in rows:
        if row.get(CODE) not in stem_codes:
            continue
        out.append(
            {
                "onet_soc_code": row[CODE],
                "element_id": row.get(ELEM_ID, ""),
                "element_name": row.get(ELEM_NAME, ""),
                "scale_id": row.get(SCALE, ""),
                "scale_name": row.get("Scale Name", ""),
                "category": row.get("Category", ""),
                "data_value": _f(row.get(VALUE)),
                "n": _f(row.get("N")),
                "standard_error": _f(row.get("Standard Error")),
                "recommend_suppress": row.get("Recommend Suppress", ""),
                "date": row.get("Date", ""),
            }
        )
    return sorted(out, key=lambda r: (r["onet_soc_code"], r["element_id"],
                                      r["scale_id"], r["category"]))


def build_emerging_tasks(rows: Iterable[dict[str, str]],
                         stem_codes: set[str]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get(CODE) not in stem_codes:
            continue
        out.append(
            {
                "onet_soc_code": row[CODE],
                "task": row.get("Task", ""),
                "category": row.get("Category", ""),
                "original_task_id": row.get("Original Task ID", ""),
                "original_task": row.get("Original Task", ""),
                "date": row.get("Date", ""),
                "domain_source": row.get("Domain Source", ""),
            }
        )
    return sorted(out, key=lambda r: (r["onet_soc_code"], r["task"]))


def build_related_occupations(rows: Iterable[dict[str, str]],
                              stem_codes: set[str]) -> list[dict[str, Any]]:
    """O*NET's own relatedness list - the validation baseline for our network."""
    out = []
    for row in rows:
        if row.get(CODE) not in stem_codes:
            continue
        out.append(
            {
                "onet_soc_code": row[CODE],
                "related_onet_soc_code": row.get("Related O*NET-SOC Code", ""),
                "related_title": row.get("Related Title", ""),
                "relatedness_tier": row.get("Relatedness Tier", ""),
                "rank": _f(row.get("Index")),
                "related_is_stem": int(row.get("Related O*NET-SOC Code", "") in stem_codes),
            }
        )
    return sorted(out, key=lambda r: (r["onet_soc_code"], r["rank"] or 0))


# --------------------------------------------------------------------------- #
# Composite indices                                                             #
# --------------------------------------------------------------------------- #
INDEX_COLUMNS = ("onet_soc_code", "occupation_title", *sorted(INDEX_DEFINITIONS),
                 "elements_matched", "elements_expected")


def build_indices(
    tables: dict[str, list[dict[str, str]]],
    occupations: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Mean of the named elements per occupation, rescaled to 0-100.

    Returns the rows plus a list of element names that were not found, so a
    silent zero from an O*NET rename becomes a visible validation warning.
    """
    missing: list[str] = []
    per_index: dict[str, dict[str, list[float]]] = {}

    for index_name, (filename, scale_id, element_names) in INDEX_DEFINITIONS.items():
        rows = tables.get(filename)
        if rows is None:
            log.warning("index %r needs %s, which was not fetched", index_name, filename)
            continue
        wanted = set(element_names)
        # O*NET scales differ per file; normalise each element to 0-1 by its own
        # observed range before averaging, so a 1-5 and a 1-7 scale mix cleanly.
        by_element: dict[str, dict[str, float]] = {name: {} for name in wanted}
        for row in rows:
            if row["scale_id"] != scale_id or row["element_name"] not in wanted:
                continue
            if row["data_value"] is not None:
                by_element[row["element_name"]][row["onet_soc_code"]] = row["data_value"]

        for name, values in by_element.items():
            if not values:
                missing.append(f"{index_name}:{name}")
                log.warning("index %r: element %r not found in %s (scale %s)",
                            index_name, name, filename, scale_id)

        scores: dict[str, list[float]] = {}
        for name, values in by_element.items():
            if not values:
                continue
            lo, hi = min(values.values()), max(values.values())
            span = (hi - lo) or 1.0
            for code, value in values.items():
                scores.setdefault(code, []).append((value - lo) / span)
        per_index[index_name] = scores

    expected = sum(len(spec[2]) for spec in INDEX_DEFINITIONS.values())
    out = []
    for occ in occupations:
        code = occ["onet_soc_code"]
        row: dict[str, Any] = {"onet_soc_code": code,
                               "occupation_title": occ.get("title", "")}
        matched = 0
        for index_name in sorted(INDEX_DEFINITIONS):
            values = per_index.get(index_name, {}).get(code, [])
            matched += len(values)
            row[index_name] = round(100 * statistics.fmean(values), 1) if values else None
        row["elements_matched"] = matched
        row["elements_expected"] = expected
        out.append(row)
    return out, sorted(set(missing))


def summarise(tables: dict[str, list[dict[str, Any]]]) -> None:
    for name in AUGMENT_FILES:
        rows = tables.get(name)
        if rows is not None:
            log.info("descriptor %-24s %7d rows", name, len(rows))
