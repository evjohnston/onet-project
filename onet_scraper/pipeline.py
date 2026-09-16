"""The three fetch stages: STEM roster, occupation reports, bulk crosswalk."""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

from .config import (
    AUGMENT_FILES,
    BULK_FILES,
    BULK_FILES_OPTIONAL,
    DB_FILE_URL,
    DB_INDEX_URL,
    DB_RELEASE_FALLBACK,
    OCCUPATION_DETAILS_URL,
    STEM_CATEGORIES,
    STEM_INDEX_URL,
    TOP_LEVEL_CATEGORIES,
    Settings,
)
from .http_client import FetchError, PoliteClient
from .parse import ParseError, parse_occupation, parse_stem_index

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Stage 1: which occupations are STEM, and under which STEM categories          #
# --------------------------------------------------------------------------- #
def fetch_stem_index(client: PoliteClient, settings: Settings) -> dict[str, Any]:
    occupations: dict[str, dict[str, Any]] = {}
    memberships: set[tuple[str, str]] = set()
    per_category: dict[str, int] = {}

    for page_id in settings.categories:
        if page_id not in TOP_LEVEL_CATEGORIES:
            log.warning("%r is not a top-level STEM page id, skipping", page_id)
            continue
        url = f"{STEM_INDEX_URL}?t={page_id}"
        sections = parse_stem_index(client.get(url).text)

        for section in sections:
            anchor = section["anchor"]
            category = page_id if anchor is None else f"{page_id}-{anchor[1:]}"
            if category not in STEM_CATEGORIES:
                log.warning("page %s exposed unknown section %s (%s); recording it anyway",
                            page_id, anchor, section["heading"][:60])
                STEM_CATEGORIES[category] = (section["heading"], page_id)
            per_category[category] = len(section["rows"])
            log.info("STEM %-4s %-52s %3d occupations", category,
                     STEM_CATEGORIES[category][0][:52], len(section["rows"]))

            for row in section["rows"]:
                code = row["onet_soc_code"]
                existing = occupations.setdefault(code, dict(row))
                # The "All STEM" page carries the authoritative occupation-type label.
                if page_id == "0" or not existing.get("occupation_types"):
                    existing["occupation_types"] = row["occupation_types"]
                existing["bright_outlook"] = existing["bright_outlook"] or row["bright_outlook"]
                if category != "0":
                    memberships.add((code, category))
                    parent = STEM_CATEGORIES[category][1]
                    if parent:
                        memberships.add((code, parent))

    if not occupations:
        raise ParseError("STEM index produced no occupations")

    return {
        "occupations": [occupations[c] for c in sorted(occupations)],
        "memberships": sorted(memberships),
        "per_category_counts": per_category,
    }


# --------------------------------------------------------------------------- #
# Stage 2: the occupation detail reports (tasks + occupation-level DWAs)        #
# --------------------------------------------------------------------------- #
def _load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return records
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                log.warning("dropping corrupt checkpoint line in %s", path)
                continue
            records[record["onet_soc_code"]] = record
    return records


def fetch_occupations(
    client: PoliteClient,
    settings: Settings,
    codes: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    codes = list(dict.fromkeys(codes))
    if settings.limit:
        codes = codes[: settings.limit]

    checkpoint = settings.raw_dir / "occupations.jsonl"
    if settings.refresh and checkpoint.exists():
        checkpoint.unlink()
    done = _load_checkpoint(checkpoint)
    todo = [c for c in codes if c not in done]
    log.info("occupations: %d total, %d cached in checkpoint, %d to fetch",
             len(codes), len(codes) - len(todo), len(todo))

    failures: list[dict[str, str]] = []

    def work(code: str) -> dict[str, Any]:
        url = OCCUPATION_DETAILS_URL.format(code=code)
        page = client.get(url)
        record = parse_occupation(page.text, expected_code=code)
        record["source_url"] = url
        record["fetched_at"] = page.fetched_at
        record["source_sha256"] = page.sha256
        if settings.save_html:
            (settings.html_dir / f"{code}.html").write_text(page.text)
        return record

    if todo:
        with checkpoint.open("a") as sink, ThreadPoolExecutor(max_workers=settings.workers) as pool:
            futures = {pool.submit(work, code): code for code in todo}
            for finished, future in enumerate(as_completed(futures), start=1):
                code = futures[future]
                try:
                    record = future.result()
                except (FetchError, ParseError) as exc:
                    log.error("%s failed: %s", code, exc)
                    failures.append({"onet_soc_code": code, "error": str(exc)})
                    continue
                except Exception as exc:  # unexpected, but one page must not kill the run
                    log.exception("%s raised unexpectedly", code)
                    failures.append({"onet_soc_code": code, "error": repr(exc)})
                    continue
                done[code] = record
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                sink.flush()
                if finished % 25 == 0 or finished == len(todo):
                    log.info("  fetched %d/%d", finished, len(todo))

    (settings.raw_dir / "failures.json").write_text(json.dumps(failures, indent=2))
    ordered = [done[c] for c in codes if c in done]
    return ordered, failures


# --------------------------------------------------------------------------- #
# Stage 3: the bulk crosswalk that the website does not expose                  #
# --------------------------------------------------------------------------- #
def discover_db_release(client: PoliteClient) -> str:
    """Latest db_<major>_<minor>_csv release advertised on onetcenter.org."""
    try:
        page = client.get(DB_INDEX_URL)
    except FetchError as exc:
        log.warning("could not read the database index (%s); pinning %s",
                    exc, DB_RELEASE_FALLBACK)
        return DB_RELEASE_FALLBACK
    releases = set(re.findall(r"db_(\d+_\d+)_csv/", page.text))
    if not releases:
        log.warning("no release found on %s; pinning %s", DB_INDEX_URL, DB_RELEASE_FALLBACK)
        return DB_RELEASE_FALLBACK
    latest = max(releases, key=lambda r: tuple(int(p) for p in r.split("_")))
    log.info("O*NET database release: %s", latest.replace("_", "."))
    return latest


def fetch_bulk(client: PoliteClient, settings: Settings) -> dict[str, Any]:
    release = discover_db_release(client)
    tables: dict[str, list[dict[str, str]]] = {}
    provenance: dict[str, dict[str, str]] = {}

    wanted = BULK_FILES + (BULK_FILES_OPTIONAL if settings.with_ratings else ())
    for name in wanted:
        url = DB_FILE_URL.format(release=release, name=name)
        page = client.get(url)
        (settings.bulk_dir / name).write_bytes(page.content)
        rows = list(csv.DictReader(io.StringIO(page.text)))
        tables[name] = rows
        provenance[name] = {"url": url, "rows": str(len(rows)), "sha256": page.sha256}
        log.info("bulk %-28s %6d rows", name, len(rows))

    return {"release": release, "tables": tables, "provenance": provenance}


def write_manifest(settings: Settings, payload: dict[str, Any]) -> Path:
    payload = dict(payload)
    payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path = settings.out_dir / "manifest.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


# --------------------------------------------------------------------------- #
# Reloading persisted stage output, so stages can be run separately             #
# --------------------------------------------------------------------------- #
def save_index(settings: Settings, index: dict[str, Any]) -> Path:
    path = settings.raw_dir / "stem_index.json"
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False))
    return path


def load_index(settings: Settings) -> dict[str, Any]:
    path = settings.raw_dir / "stem_index.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run the fetch-stem stage first")
    index = json.loads(path.read_text())
    index["memberships"] = [tuple(m) for m in index["memberships"]]
    return index


def load_occupations(settings: Settings, codes: Iterable[str] | None = None) -> list[dict[str, Any]]:
    records = _load_checkpoint(settings.raw_dir / "occupations.jsonl")
    if codes is None:
        return [records[c] for c in sorted(records)]
    return [records[c] for c in codes if c in records]


def load_failures(settings: Settings) -> list[dict[str, str]]:
    path = settings.raw_dir / "failures.json"
    return json.loads(path.read_text()) if path.exists() else []


def save_bulk_meta(settings: Settings, bulk: dict[str, Any]) -> Path:
    path = settings.raw_dir / "bulk_meta.json"
    path.write_text(json.dumps(
        {"release": bulk["release"], "provenance": bulk["provenance"]}, indent=2))
    return path


def load_bulk(settings: Settings) -> dict[str, Any] | None:
    meta_path = settings.raw_dir / "bulk_meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    tables: dict[str, list[dict[str, str]]] = {}
    for name in meta["provenance"]:
        path = settings.bulk_dir / name
        if not path.exists():
            log.warning("bulk file %s listed in metadata but missing on disk", name)
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            tables[name] = list(csv.DictReader(handle))
    return {"release": meta["release"], "tables": tables, "provenance": meta["provenance"]}


# --------------------------------------------------------------------------- #
# Stage 3b: descriptor files behind the collaboration / bottleneck indices      #
# --------------------------------------------------------------------------- #
def fetch_augment(client: PoliteClient, settings: Settings) -> dict[str, Any]:
    release = discover_db_release(client)
    tables: dict[str, list[dict[str, str]]] = {}
    provenance: dict[str, dict[str, str]] = {}

    for name in AUGMENT_FILES:
        url = DB_FILE_URL.format(release=release, name=name)
        page = client.get(url)
        (settings.bulk_dir / name).write_bytes(page.content)
        rows = list(csv.DictReader(io.StringIO(page.text)))
        tables[name] = rows
        provenance[name] = {"url": url, "rows": str(len(rows)), "sha256": page.sha256}
        log.info("descriptor %-24s %7d rows", name, len(rows))

    path = settings.raw_dir / "augment_meta.json"
    path.write_text(json.dumps({"release": release, "provenance": provenance}, indent=2))
    return {"release": release, "tables": tables, "provenance": provenance}


def load_augment(settings: Settings) -> dict[str, Any] | None:
    meta_path = settings.raw_dir / "augment_meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    tables: dict[str, list[dict[str, str]]] = {}
    for name in meta["provenance"]:
        path = settings.bulk_dir / name
        if not path.exists():
            log.warning("descriptor file %s missing on disk", name)
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            tables[name] = list(csv.DictReader(handle))
    return {"release": meta["release"], "tables": tables, "provenance": meta["provenance"]}
