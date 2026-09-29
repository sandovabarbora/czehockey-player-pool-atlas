"""Polite, cached HTTP for the fetchers.

Every fetcher goes through `PoliteClient`:

- robots.txt is read once per host and honoured (a missing robots.txt, 404,
  means no restriction);
- at least `min_interval` seconds (default 1 s) pass between two requests to
  the network, whatever the host;
- each raw response body is cached under data/raw/<source>/<key>; a cached key
  is served from disk and never refetched unless `refresh=True`.

The cache is gitignored; the processed tables built from it are what the repo
commits (data/snapshot/).
"""

from __future__ import annotations

import json
import logging
import time
import urllib.robotparser
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

LOG = logging.getLogger(__name__)

USER_AGENT = "czehockey-player-pool-atlas/1.0 (hello@bsandova.com)"


class RobotsDisallowedError(RuntimeError):
    """The host's robots.txt forbids the URL for our user agent."""


class PoliteClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        min_interval: float = 1.0,
        session: requests.Session | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        check_robots: bool = True,
    ) -> None:
        if min_interval < 1.0:
            raise ValueError("min_interval below 1 s is not polite")
        self.cache_dir = cache_dir
        self.min_interval = min_interval
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers["User-Agent"] = USER_AGENT
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._check_robots = check_robots
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.network_calls = 0

    # -- throttling and robots ------------------------------------------------

    def _wait(self) -> None:
        if self._last is not None:
            gap = self._clock() - self._last
            if gap < self.min_interval:
                self._sleep(self.min_interval - gap)
        self._last = self._clock()

    def _allowed(self, url: str) -> bool:
        if not self._check_robots:
            return True
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            self._wait()
            self.network_calls += 1
            resp = self.session.get(f"{host}/robots.txt", timeout=20)
            if resp.status_code >= 400:
                self._robots[host] = None  # no robots.txt: no restriction
            else:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(resp.text.splitlines())
                self._robots[host] = rp
        rp = self._robots[host]
        return rp is None or rp.can_fetch(USER_AGENT, url)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _get(self, url: str, params: dict[str, Any] | None) -> requests.Response:
        self._wait()
        self.network_calls += 1
        resp = self.session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp

    # -- public ---------------------------------------------------------------

    def get_text(
        self,
        url: str,
        key: str,
        *,
        params: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> str:
        """Return the body of `url`, from data/raw/<source>/<key> when cached."""
        path = self.cache_dir / key
        if path.exists() and not refresh:
            return path.read_text(encoding="utf-8")
        if not self._allowed(url):
            raise RobotsDisallowedError(url)
        body = self._get(url, params).text
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        LOG.debug("cached %s -> %s", url, path)
        return body

    def get_json(self, url: str, key: str, **kwargs: Any) -> Any:
        return json.loads(self.get_text(url, key, **kwargs))
