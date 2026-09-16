"""Parser contract tests.

Fixtures reproduce O*NET's real markup (attribute names, nesting, the collapsed
rows and the "N displayed" counter) in miniature, so a change in the live site's
structure fails here rather than silently emptying a column.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from onet_scraper.parse import (  # noqa: E402
    ParseError,
    parse_dwas,
    parse_occupation,
    parse_stem_index,
    parse_tasks,
    soup_of,
)

INDEX_HTML = """
<html><body>
<h2 id="f1">Technologists and Technicians &mdash; Computer and Mathematical</h2>
<table class="table tablesorter">
  <thead><tr><th>Code</th><th>Occupation</th><th>Occupation Types</th></tr></thead>
  <tbody>
    <tr>
      <td data-title="Code">15-2011.00</td>
      <td data-title="Occupation">
        <a href="https://www.onetonline.org/link/summary/15-2011.00">Actuaries</a>
        <a href="/help/bright/15-2011.00"><i class="fakd fa-bright-outlook bright-outlook-icon"></i>
        <small>Bright Outlook</small></a>
      </td>
      <td data-title="Occupation Types">Research, Development, Design, and Practitioners</td>
    </tr>
    <tr>
      <td data-title="Code">17-2051.00</td>
      <td data-title="Occupation"><a href="/link/summary/17-2051.00">Civil Engineers</a></td>
      <td data-title="Occupation Types">Managerial</td>
    </tr>
    <tr><td data-title="Code">&nbsp;</td><td data-title="Occupation">spacer</td></tr>
  </tbody>
</table>
</body></html>
"""

DETAILS_HTML = """
<html><body>
<div id="content">
  <h1><span class="main">Actuaries</span>
      <span class="sub"><div>15-2011.00</div>
      <a>Bright Outlook</a><a>Updated 2026</a></span></h1>
  <p>Analyze statistical data and construct probability tables.</p>
  <p><b>Sample of reported job titles:</b> Actuarial Analyst, Consulting Actuary, Health Actuary</p>

  <div id="Tasks" class="reportsection">
    <h2 class="report">Tasks</h2>
    <div><button>10 of All 2 displayed</button></div>
    <table class="table tablesorter">
      <thead><tr><th>Importance</th><th>Category</th><th>Task</th></tr></thead>
      <tbody>
        <tr>
          <td data-title="Importance" data-text="94"><span>94</span></td>
          <td data-title="Category">Core</td>
          <td data-title="Task" data-text="Analyze data to determine premium rates.">
            <div class="order-2">Analyze data to determine premium rates.</div>
            <a href="/link/moreinfo/task/24015?r=details&amp;j=15-2011.00">more</a>
          </td>
        </tr>
        <tr class="long_Tasks collapse">
          <td data-title="Importance" data-text="67"><span>67</span></td>
          <td data-title="Category">Supplemental</td>
          <td data-title="Task" data-text="Construct probability tables.">
            <div class="order-2">Construct probability tables.</div>
            <a href="/link/moreinfo/task/24016?r=details">more</a>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div id="DetailedWorkActivities" class="reportsection">
    <h2 class="report">Detailed Work Activities</h2>
    <div><button>10 of All 2 displayed</button></div>
    <ul class="list-unstyled m-0">
      <li><div class="d-flex"><div class="order-2">Manage financial activities of the organization.</div>
        <a href="/link/moreinfo/dwa/4.A.4.b.4.h.6?r=details">more</a></div></li>
      <li><div class="d-flex"><div class="order-2">Analyze data to inform operational decisions.</div>
        <a href="/link/moreinfo/dwa/4.A.2.a.4.g.12?r=details">more</a></div></li>
    </ul>
  </div>

  <div id="JobZone" class="reportsection">
    <table><tr><td>Title</td><td>Job Zone Four: Considerable Preparation Needed</td></tr></table>
  </div>
</div>
</body></html>
"""

# Occupations with no incumbent ratings render Tasks as a <ul>, not a table
# (e.g. 19-4044.00 Hydrologic Technicians). Same section id, different shape.
UNRATED_TASKS_HTML = """
<html><body><div id="content">
  <h1><span class="main">Hydrologic Technicians</span>
      <span class="sub"><div>19-4044.00</div></span></h1>
  <div id="Tasks" class="reportsection">
    <h2 class="report">Tasks</h2>
    <div><button>10 of All 2 displayed</button></div>
    <ul class="list-unstyled m-0">
      <li><div class="d-flex"><div class="order-2">Analyze ecological data about pollution.</div>
        <a href="/link/moreinfo/task/22292?r=details&amp;j=19-4044.00">more</a></div></li>
      <li><div class="d-flex"><div class="order-2">Answer technical questions from hydrologists.</div>
        <a href="/link/moreinfo/task/22293?r=details">more</a></div></li>
    </ul>
  </div>
</div></body></html>
"""


# Tasks O*NET has not yet rated show "Not available" with a negative data-text
# sort sentinel (-2). That is missing data, not a score of -2.
UNAVAILABLE_SCORE_HTML = DETAILS_HTML.replace(
    '''<td data-title="Importance" data-text="67"><span>67</span></td>
          <td data-title="Category">Supplemental</td>''',
    '''<td data-title="Importance" data-text="-2">Not available</td>
          <td data-title="Category">New</td>''',
)


class TestStemIndex(unittest.TestCase):
    def test_sections_rows_and_anchor(self):
        sections = parse_stem_index(INDEX_HTML)
        self.assertEqual(len(sections), 1)
        section = sections[0]
        self.assertEqual(section["anchor"], "f1")
        self.assertEqual(len(section["rows"]), 2, "the spacer row must be dropped")
        first = section["rows"][0]
        self.assertEqual(first["onet_soc_code"], "15-2011.00")
        self.assertEqual(first["title"], "Actuaries")
        self.assertTrue(first["bright_outlook"])
        self.assertFalse(section["rows"][1]["bright_outlook"])

    def test_missing_table_raises(self):
        with self.assertRaises(ParseError):
            parse_stem_index("<html><body><p>nothing here</p></body></html>")


class TestTasks(unittest.TestCase):
    def setUp(self):
        self.soup = soup_of(DETAILS_HTML)

    def test_collapsed_rows_are_included(self):
        tasks, declared = parse_tasks(self.soup)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(declared, 2, "must read the page's own row count for cross-checking")

    def test_fields(self):
        tasks, _ = parse_tasks(self.soup)
        self.assertEqual(tasks[0]["task_id"], 24015)
        self.assertEqual(tasks[0]["importance"], 94.0)
        self.assertEqual(tasks[0]["task_category"], "Core")
        self.assertEqual(tasks[0]["task"], "Analyze data to determine premium rates.")
        self.assertEqual(tasks[1]["task_category"], "Supplemental")
        self.assertIsNone(tasks[0]["relevance"])

    def test_column_order_is_irrelevant(self):
        swapped = DETAILS_HTML.replace(
            '<th>Importance</th><th>Category</th><th>Task</th>',
            '<th>Task</th><th>Category</th><th>Importance</th>',
        )
        tasks, _ = parse_tasks(soup_of(swapped))
        self.assertEqual(tasks[0]["importance"], 94.0)
        self.assertEqual(tasks[0]["task_id"], 24015)

    def test_missing_section_is_empty_not_fatal(self):
        tasks, declared = parse_tasks(soup_of("<html><body></body></html>"))
        self.assertEqual(tasks, [])
        self.assertIsNone(declared)


class TestDwas(unittest.TestCase):
    def test_ids_and_titles(self):
        dwas, declared = parse_dwas(soup_of(DETAILS_HTML))
        self.assertEqual(declared, 2)
        self.assertEqual(
            [d["dwa_id"] for d in dwas],
            ["4.A.4.b.4.h.6", "4.A.2.a.4.g.12"],
        )
        self.assertEqual(dwas[0]["dwa_title"], "Manage financial activities of the organization.")


class TestOccupation(unittest.TestCase):
    def test_full_record(self):
        record = parse_occupation(DETAILS_HTML, expected_code="15-2011.00")
        self.assertEqual(record["title"], "Actuaries")
        self.assertEqual(record["onet_soc_code"], "15-2011.00")
        self.assertEqual(record["updated_year"], 2026)
        self.assertTrue(record["bright_outlook"])
        self.assertEqual(record["job_zone"], 4)
        self.assertIn("probability tables", record["description"])
        self.assertEqual(record["reported_job_titles"][0], "Actuarial Analyst")
        self.assertEqual(record["counts"],
                         {"tasks_parsed": 2, "tasks_declared": 2,
                          "dwas_parsed": 2, "dwas_declared": 2})

    def test_wrong_code_raises(self):
        with self.assertRaises(ParseError):
            parse_occupation(DETAILS_HTML, expected_code="11-1011.00")


class TestUnratedTaskList(unittest.TestCase):
    """The list layout must yield the same records, minus the ratings."""

    def test_tasks_parsed_from_list(self):
        tasks, declared = parse_tasks(soup_of(UNRATED_TASKS_HTML))
        self.assertEqual(declared, 2)
        self.assertEqual(len(tasks), 2, "list-layout tasks must not be dropped")
        self.assertEqual(tasks[0]["task_id"], 22292)
        self.assertEqual(tasks[0]["task"], "Analyze ecological data about pollution.")
        self.assertIsNone(tasks[0]["importance"])
        self.assertIsNone(tasks[0]["task_category"])
        self.assertEqual(tasks[1]["display_rank"], 2)

    def test_counts_reconcile(self):
        record = parse_occupation(UNRATED_TASKS_HTML, expected_code="19-4044.00")
        counts = record["counts"]
        self.assertEqual(counts["tasks_parsed"], counts["tasks_declared"])


class TestUnavailableScores(unittest.TestCase):
    def test_sentinel_becomes_none(self):
        tasks, _ = parse_tasks(soup_of(UNAVAILABLE_SCORE_HTML))
        self.assertEqual(tasks[1]["task_category"], "New")
        self.assertIsNone(tasks[1]["importance"],
                          "the -2 sort sentinel must not leak in as a rating")
        self.assertEqual(tasks[0]["importance"], 94.0, "real scores still parse")


if __name__ == "__main__":
    unittest.main(verbosity=2)
