"""Configuration, constants and run settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

ONLINE_BASE = "https://www.onetonline.org"
CENTER_BASE = "https://www.onetcenter.org"

STEM_INDEX_URL = ONLINE_BASE + "/find/stem"
OCCUPATION_DETAILS_URL = ONLINE_BASE + "/link/details/{code}"

# O*NET OnLine's STEM filter values. Only the top-level ids are real pages: the
# sub-disciplines are anchored sections inside their parent page (?t=1#f1 ... #f4),
# so "1-2" is the section anchored at f2 on the ?t=1 page. "0" is the union of all.
TOP_LEVEL_CATEGORIES = ("0", "1", "2", "3", "4", "5")

STEM_CATEGORIES: dict[str, tuple[str, str | None]] = {
    "0": ("All STEM Occupations", None),
    "1": ("Research, Development, Design, and Practitioners", None),
    "1-1": ("Architecture and Engineering", "1"),
    "1-2": ("Computer and Mathematical", "1"),
    "1-3": ("Healthcare Practitioners and Technical", "1"),
    "1-4": ("Life, Physical, and Social Science", "1"),
    "2": ("Technologists and Technicians", None),
    "2-1": ("Architecture and Engineering", "2"),
    "2-2": ("Computer and Mathematical", "2"),
    "2-3": ("Healthcare Practitioners and Technical", "2"),
    "2-4": ("Life, Physical, and Social Science", "2"),
    "3": ("Postsecondary Teaching", None),
    "4": ("Managerial", None),
    "5": ("Sales", None),
}

# Bulk distribution of the O*NET database. The public website deliberately does not
# publish the task -> detailed-work-activity edge, so the authoritative crosswalk is
# pulled from these files. DB_RELEASE is resolved at runtime from the release index
# and only falls back to this pin if discovery fails.
DB_RELEASE_FALLBACK = "31_0"
DB_INDEX_URL = CENTER_BASE + "/database.html"
DB_FILE_URL = CENTER_BASE + "/dl_files/database/db_{release}_csv/{name}"

# Core bulk files are small and fast. task_ratings.csv is ~29 MB and holds the full
# Importance / Relevance / Frequency distributions; it is opt-in via --with-ratings.
BULK_FILES = (
    "tasks_to_dwas.csv",
    "task_statements.csv",
    "gwas_to_iwas_to_dwas.csv",
    "occupation_data.csv",
)
BULK_FILES_OPTIONAL = ("task_ratings.csv",)

# Descriptor files power the collaboration and automation-bottleneck indices.
# They are large (work_context.csv alone is ~40 MB) so the stage is opt-in.
DESCRIPTOR_FILES = (
    "work_context.csv",
    "abilities.csv",
    "work_activities.csv",
    "essential_skills.csv",
)
LINKAGE_FILES = ("emerging_tasks.csv", "related_occupations.csv")
AUGMENT_FILES = DESCRIPTOR_FILES + LINKAGE_FILES

# Composite indices, defined by O*NET element NAME rather than id: names are
# stable and readable, and a rename shows up as a warning instead of a silent
# zero. Each entry is (source file, scale id, [element names]).
INDEX_DEFINITIONS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # How much of the job is conducted with and through other people.
    "collaboration": ("work_context.csv", "CX", (
        "Contact With Others",
        "Work With or Contribute to a Work Group or Team",
        "Face-to-Face Discussions with Individuals and Within Teams",
        "Coordinate or Lead Others in Accomplishing Work Activities",
    )),
    # Accountability for other people - the bottleneck O*NET measures directly.
    "responsibility_for_others": ("work_context.csv", "CX", (
        "Health and Safety of Other Workers",
        "Work Outcomes and Results of Other Workers",
    )),
    # Frey & Osborne's three engineering bottlenecks to computerisation.
    "bottleneck_perception_manipulation": ("abilities.csv", "LV", (
        "Finger Dexterity",
        "Manual Dexterity",
        "Arm-Hand Steadiness",
    )),
    "bottleneck_creative_intelligence": ("abilities.csv", "LV", (
        "Originality",
        "Fluency of Ideas",
    )),
    "bottleneck_social_intelligence": ("work_activities.csv", "LV", (
        "Assisting and Caring for Others",
        "Establishing and Maintaining Interpersonal Relationships",
        "Resolving Conflicts and Negotiating with Others",
    )),
}

SOC_CODE_RE = r"\d{2}-\d{4}\.\d{2}"


def default_user_agent(contact: str | None = None) -> str:
    """Identify the crawler. Set ONET_CONTACT (or --contact) so O*NET can reach you."""
    contact = contact or os.environ.get("ONET_CONTACT", "")
    suffix = f"; {contact}" if contact else "; set ONET_CONTACT to identify yourself"
    return f"onet-job-taskings/{__version__} (+research dataset build{suffix})"


@dataclass
class Settings:
    data_dir: Path = Path("data")
    contact: str | None = None
    rate: float = 1.5           # requests per second, shared across worker threads
    workers: int = 4
    timeout: float = 30.0
    max_retries: int = 5
    cache_ttl_days: float = 7.0
    refresh: bool = False       # ignore cached copies, re-fetch and overwrite
    offline: bool = False       # serve only from cache; error on a miss
    obey_robots: bool = True
    limit: int | None = None    # cap occupations, for smoke tests
    use_bulk: bool = True
    with_ratings: bool = False
    with_descriptors: bool = False
    save_html: bool = False

    categories: tuple[str, ...] = field(default_factory=lambda: TOP_LEVEL_CATEGORIES)

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def out_dir(self) -> Path:
        return self.data_dir / "out"

    @property
    def html_dir(self) -> Path:
        return self.data_dir / "raw" / "html"

    @property
    def bulk_dir(self) -> Path:
        return self.data_dir / "raw" / "bulk"

    def ensure_dirs(self) -> None:
        for path in (self.cache_dir, self.raw_dir, self.out_dir, self.bulk_dir):
            path.mkdir(parents=True, exist_ok=True)
        if self.save_html:
            self.html_dir.mkdir(parents=True, exist_ok=True)

    @property
    def user_agent(self) -> str:
        return default_user_agent(self.contact)
