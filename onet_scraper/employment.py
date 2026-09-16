"""BLS OEWS employment and wages, joined to the susceptibility index.

The join is the whole problem, and it has one trap worth stating plainly.

O*NET reports at the 8-digit O*NET-SOC level (29-1141.01 Acute Care Nurses);
OEWS reports employment at the 6-digit SOC level (29-1141 Registered Nurses,
3.38 million people). Five O*NET occupations roll up into that one SOC. Joining
naively - attaching OEWS employment to each O*NET row - counts those 3.38 million
nurses five times. In this dataset 38 SOC codes have more than one O*NET detail
occupation, so the error is large and silent.

So: aggregate susceptibility up to the SOC level FIRST (mean across the detail
occupations, with their spread reported so a hidden disagreement is visible),
then attach employment exactly once per SOC.

Second wrinkle: BLS sometimes publishes only a broad group where O*NET has
detail - 29-2011 and 29-2012 are both reported as 29-2010. Codes resolve to the
6-digit row when it exists and fall back to the broad code otherwise, and both
O*NET codes then land in the same group, so the fallback cannot double-count.
"""

from __future__ import annotations

import io
import logging
import re
import statistics
import zipfile
from typing import Any, Sequence

log = logging.getLogger(__name__)

OEWS_TABLES_URL = "https://www.bls.gov/oes/tables.htm"
OEWS_ZIP_URL = "https://www.bls.gov/oes/special-requests/oesm{yy}nat.zip"
OEWS_ZIP_FALLBACK_YY = "25"

# BLS suppression markers. Parsing these as numbers is how wage means go wrong.
#   *  = not available / does not meet publication criteria
#   ** = employment not released
#   #  = wage >= $115.00/hour or $239,200/year
SENTINELS = {"*", "**", "#", "~"}

OEWS_COLUMNS = ("soc_code", "soc_title", "total_employment", "employment_prse",
                "annual_mean_wage", "annual_median_wage", "hourly_mean_wage",
                "wage_top_coded", "release")
SOC_SUSC_COLUMNS = ("soc_code", "soc_title", "n_onet_occupations", "onet_codes",
                    "total_employment", "annual_mean_wage", "annual_median_wage",
                    "susceptibility", "susceptibility_sd_within_soc", "exposure",
                    "anchoring", "deployment_gap", "quadrant", "wage_bill_usd",
                    "stem_occupation_types")


class EmploymentError(RuntimeError):
    pass


def _num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in SENTINELS or not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def discover_release(client) -> str:
    """Latest oesm<YY>nat.zip advertised on the OEWS tables page."""
    try:
        page = client.get(OEWS_TABLES_URL)
    except Exception as exc:
        log.warning("could not read %s (%s); pinning 20%s", OEWS_TABLES_URL, exc,
                    OEWS_ZIP_FALLBACK_YY)
        return OEWS_ZIP_FALLBACK_YY
    years = set(re.findall(r"oesm(\d{2})nat\.zip", page.text))
    if not years:
        return OEWS_ZIP_FALLBACK_YY
    latest = max(years, key=int)
    log.info("OEWS national release: May 20%s", latest)
    return latest


def fetch_oews(client, settings) -> dict[str, Any]:
    """Download the national OEWS workbook and return its detailed rows."""
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise EmploymentError("the employment stage needs openpyxl: pip install openpyxl") from exc

    release = discover_release(client)
    url = OEWS_ZIP_URL.format(yy=release)
    page = client.get(url)
    (settings.bulk_dir / f"oesm{release}nat.zip").write_bytes(page.content)

    with zipfile.ZipFile(io.BytesIO(page.content)) as archive:
        names = [n for n in archive.namelist() if n.endswith(".xlsx")]
        if not names:
            raise EmploymentError(f"no .xlsx inside {url}")
        with archive.open(names[0]) as handle:
            workbook = openpyxl.load_workbook(io.BytesIO(handle.read()), read_only=True)

    sheet = workbook[workbook.sheetnames[0]]
    rows = sheet.iter_rows(values_only=True)
    header = {name: i for i, name in enumerate(next(rows)) if name}
    required = ("OCC_CODE", "OCC_TITLE", "O_GROUP", "TOT_EMP", "A_MEAN")
    if missing := [c for c in required if c not in header]:
        raise EmploymentError(f"OEWS workbook is missing columns: {missing}")

    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if (row[header["O_GROUP"]] or "").strip() != "detailed":
            continue
        code = str(row[header["OCC_CODE"]]).strip()
        raw_mean = row[header["A_MEAN"]]
        out[code] = {
            "soc_code": code,
            "soc_title": row[header["OCC_TITLE"]],
            "total_employment": _num(row[header["TOT_EMP"]]),
            "employment_prse": _num(row[header.get("EMP_PRSE", -1)]) if "EMP_PRSE" in header else None,
            "annual_mean_wage": _num(raw_mean),
            "annual_median_wage": _num(row[header["A_MEDIAN"]]) if "A_MEDIAN" in header else None,
            "hourly_mean_wage": _num(row[header["H_MEAN"]]) if "H_MEAN" in header else None,
            # '#' means the true wage is above the publication ceiling, not missing.
            "wage_top_coded": int(str(raw_mean).strip() == "#"),
            "release": f"May 20{release}",
        }
    log.info("OEWS: %d detailed occupations", len(out))
    return {"release": release, "rows": out}


def resolve_soc(onet_code: str, available: set[str]) -> str | None:
    """O*NET-SOC -> the OEWS code that actually carries employment for it."""
    soc = onet_code.split(".")[0]
    if soc in available:
        return soc
    broad = soc[:-1] + "0"          # 29-2011 -> 29-2010
    if broad in available:
        return broad
    return None


def build_soc_table(
    occupation_susceptibility: Sequence[dict[str, Any]],
    oews: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    available = set(oews)
    groups: dict[str, list[dict[str, Any]]] = {}
    unmatched: list[str] = []

    for occ in occupation_susceptibility:
        code = resolve_soc(occ["onet_soc_code"], available)
        if code is None:
            unmatched.append(occ["onet_soc_code"])
            continue
        groups.setdefault(code, []).append(occ)

    f = lambda row, key: float(row[key]) if row.get(key) not in (None, "") else 0.0
    out = []
    for code, members in sorted(groups.items()):
        bls = oews[code]
        susc = [f(m, "susceptibility") for m in members]
        employment = bls["total_employment"]
        wage = bls["annual_mean_wage"]
        out.append({
            "soc_code": code,
            "soc_title": bls["soc_title"],
            "n_onet_occupations": len(members),
            "onet_codes": ";".join(m["onet_soc_code"] for m in members),
            "total_employment": employment,
            "annual_mean_wage": wage,
            "annual_median_wage": bls["annual_median_wage"],
            "susceptibility": round(statistics.fmean(susc), 1),
            # Flags SOCs whose O*NET details disagree - the mean hides those.
            "susceptibility_sd_within_soc": (
                round(statistics.stdev(susc), 1) if len(susc) > 1 else 0.0),
            "exposure": round(statistics.fmean(f(m, "exposure") for m in members), 1),
            "anchoring": round(statistics.fmean(f(m, "anchoring") for m in members), 1),
            "deployment_gap": round(statistics.fmean(f(m, "deployment_gap") for m in members), 1),
            "quadrant": statistics.mode(m.get("quadrant", "") for m in members),
            "wage_bill_usd": round(employment * wage) if employment and wage else None,
            "stem_occupation_types": members[0].get("stem_occupation_types", ""),
        })

    diagnostics = {
        "onet_occupations_in": len(occupation_susceptibility),
        "soc_codes_out": len(out),
        "collapsed_socs": sum(1 for r in out if r["n_onet_occupations"] > 1),
        "unmatched_onet_codes": unmatched,
        "employment_covered": sum(r["total_employment"] or 0 for r in out),
    }
    return sorted(out, key=lambda r: -(r["total_employment"] or 0)), diagnostics


def headline_stats(soc_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The numbers the employment join exists to produce."""
    rows = [r for r in soc_rows if r["total_employment"]]
    total = sum(r["total_employment"] for r in rows)
    if not total:
        return {"employment": 0}

    wmean = lambda key: round(
        sum(r[key] * r["total_employment"] for r in rows) / total, 1)
    by_quadrant: dict[str, dict[str, float]] = {}
    for row in rows:
        q = by_quadrant.setdefault(row["quadrant"], {"employment": 0, "wage_bill_usd": 0})
        q["employment"] += row["total_employment"]
        q["wage_bill_usd"] += row["wage_bill_usd"] or 0
    for q in by_quadrant.values():
        q["share_of_employment"] = round(q["employment"] / total, 4)

    high = [r for r in rows if r["susceptibility"] >= 70]
    low = [r for r in rows if r["susceptibility"] < 50]
    unweighted = round(statistics.fmean(r["susceptibility"] for r in rows), 1)
    weighted = wmean("susceptibility")
    return {
        "soc_codes": len(rows),
        "total_employment": total,
        "employment_weighted_susceptibility": weighted,
        "unweighted_susceptibility": unweighted,
        # If these differ, headcount is concentrated in one end of the
        # distribution and an unweighted average misrepresents the workforce.
        "weighting_shifts_result_by": round(weighted - unweighted, 1),
        "employment_weighted_exposure": wmean("exposure"),
        "employment_weighted_anchoring": wmean("anchoring"),
        "workers_in_high_susceptibility_occupations": sum(r["total_employment"] for r in high),
        "share_workers_high_susceptibility": round(
            sum(r["total_employment"] for r in high) / total, 4),
        "workers_in_low_susceptibility_occupations": sum(r["total_employment"] for r in low),
        "annual_wage_bill_usd": sum(r["wage_bill_usd"] or 0 for r in rows),
        "by_quadrant": by_quadrant,
    }
