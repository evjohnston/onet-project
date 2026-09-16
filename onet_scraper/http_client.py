"""A deliberately boring HTTP client: polite, cached, retrying, resumable.

Every network read in this project goes through :class:`PoliteClient`, so a re-run
after a crash costs nothing and a full rebuild can be done entirely offline from the
on-disk cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Raised when a URL could not be retrieved after exhausting retries."""


@dataclass
class Fetched:
    url: str
    content: bytes
    from_cache: bool
    fetched_at: str
    status: int = 200

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


class _RateLimiter:
    """Shared token spacing so N worker threads still hit the site politely."""

    def __init__(self, per_second: float):
        self._min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            sleep_for = max(0.0, self._next_at - now)
            # Jitter keeps concurrent workers from lock-stepping into bursts.
            self._next_at = max(now, self._next_at) + self._min_interval * random.uniform(0.9, 1.2)
        if sleep_for:
            time.sleep(sleep_for)


class PoliteClient:
    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        *,
        rate: float = 1.5,
        timeout: float = 30.0,
        max_retries: int = 5,
        cache_ttl_days: float = 7.0,
        refresh: bool = False,
        offline: bool = False,
        obey_robots: bool = True,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl_days * 86400 if cache_ttl_days else None
        self.refresh = refresh
        self.offline = offline
        self.obey_robots = obey_robots

        self._limiter = _RateLimiter(rate)
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._robots_lock = threading.Lock()
        self._local = threading.local()
        self._user_agent = user_agent
        self.stats = {"hits": 0, "misses": 0, "retries": 0}
        self._stats_lock = threading.Lock()

    # -- session ---------------------------------------------------------------
    @property
    def session(self) -> requests.Session:
        # One session per thread: requests.Session is not guaranteed thread-safe.
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers.update(
                {
                    "User-Agent": self._user_agent,
                    "Accept": "text/html,application/xhtml+xml,text/csv,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
            self._local.session = sess
        return sess

    # -- cache -----------------------------------------------------------------
    def _paths(self, url: str) -> tuple[Path, Path]:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        shard = self.cache_dir / digest[:2]
        shard.mkdir(parents=True, exist_ok=True)
        return shard / f"{digest}.body", shard / f"{digest}.json"

    def _read_cache(self, url: str) -> Fetched | None:
        body_path, meta_path = self._paths(url)
        if not (body_path.exists() and meta_path.exists()):
            return None
        try:
            meta = json.loads(meta_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if self.cache_ttl is not None and not self.offline:
            age = time.time() - meta.get("epoch", 0)
            if age > self.cache_ttl:
                return None
        return Fetched(
            url=url,
            content=body_path.read_bytes(),
            from_cache=True,
            fetched_at=meta.get("fetched_at", ""),
            status=meta.get("status", 200),
        )

    def _write_cache(self, url: str, content: bytes, status: int) -> str:
        body_path, meta_path = self._paths(url)
        fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        body_path.write_bytes(content)
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "status": status,
                    "fetched_at": fetched_at,
                    "epoch": time.time(),
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                },
                indent=2,
            )
        )
        return fetched_at

    # -- robots ----------------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        if not self.obey_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._robots_lock:
            if origin not in self._robots:
                # Fetch robots.txt through our own session so it carries the same
                # identifying User-Agent as every other request. RobotFileParser.read()
                # would use urllib's default UA instead; sites that gate on UA (BLS,
                # for one) answer that with a 403, which the parser then interprets
                # as "disallow everything" - blocking paths that are actually allowed.
                parser = urllib.robotparser.RobotFileParser()
                try:
                    resp = self.session.get(origin + "/robots.txt", timeout=self.timeout)
                    if resp.status_code in (401, 403):
                        log.warning("%s refused robots.txt (HTTP %d) even with our "
                                    "User-Agent; treating the site as disallowed",
                                    origin, resp.status_code)
                        parser.disallow_all = True
                    elif resp.status_code >= 400:
                        parser.allow_all = True   # no robots.txt published
                    else:
                        parser.parse(resp.text.splitlines())
                except requests.RequestException as exc:  # hiccup: fail open, but say so
                    log.warning("could not read robots.txt for %s (%s); proceeding", origin, exc)
                    parser = None
                self._robots[origin] = parser
            parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(self._user_agent, url)

    # -- fetch -----------------------------------------------------------------
    def get(self, url: str) -> Fetched:
        if not self.refresh:
            cached = self._read_cache(url)
            if cached is not None:
                with self._stats_lock:
                    self.stats["hits"] += 1
                log.debug("cache hit %s", url)
                return cached

        if self.offline:
            raise FetchError(f"offline mode and no cached copy of {url}")

        if not self._allowed(url):
            raise FetchError(f"robots.txt disallows {url}")

        last_error: Exception | str = "unknown"
        for attempt in range(1, self.max_retries + 1):
            self._limiter.wait()
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                log.warning("attempt %d/%d failed for %s: %s", attempt, self.max_retries, url, exc)
            else:
                if resp.status_code == 200:
                    with self._stats_lock:
                        self.stats["misses"] += 1
                    fetched_at = self._write_cache(url, resp.content, resp.status_code)
                    return Fetched(url, resp.content, False, fetched_at, resp.status_code)
                if resp.status_code == 404:
                    raise FetchError(f"404 Not Found: {url}")
                if resp.status_code not in RETRY_STATUS:
                    raise FetchError(f"HTTP {resp.status_code} for {url}")
                last_error = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        time.sleep(min(60.0, float(retry_after)))
                    except ValueError:
                        pass
                log.warning("attempt %d/%d got %s for %s", attempt, self.max_retries, last_error, url)

            if attempt < self.max_retries:
                with self._stats_lock:
                    self.stats["retries"] += 1
                backoff = min(60.0, 1.5 * (2 ** (attempt - 1))) * random.uniform(0.8, 1.3)
                time.sleep(backoff)

        raise FetchError(f"giving up on {url} after {self.max_retries} attempts: {last_error}")
