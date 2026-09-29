"""PoliteClient: throttling, cache, robots.txt. No network."""

from __future__ import annotations

import pytest

from src.fetch._http import USER_AGENT, PoliteClient, RobotsDisallowedError


class FakeResponse:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError("unexpected error status in test")


class FakeSession:
    def __init__(self, robots: str | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []
        self.robots = robots

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResponse(self.robots or "", 200 if self.robots is not None else 404)
        return FakeResponse('{"ok": true}')


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def make(tmp_path, robots=None):
    clock = FakeClock()
    session = FakeSession(robots)
    client = PoliteClient(tmp_path, session=session, clock=clock.now, sleep=clock.sleep)
    return client, session, clock


def test_rejects_interval_below_one_second(tmp_path):
    with pytest.raises(ValueError):
        PoliteClient(tmp_path, min_interval=0.5)


def test_sets_user_agent(tmp_path):
    client, session, _ = make(tmp_path)
    assert session.headers["User-Agent"] == USER_AGENT


def test_waits_at_least_one_second_between_requests(tmp_path):
    client, session, clock = make(tmp_path)
    client.get_json("https://x.test/a", "a.json")
    client.get_json("https://x.test/b", "b.json")
    # robots.txt, a, b: two waits of a full second each (the fake clock does not advance otherwise)
    assert clock.slept == [1.0, 1.0]
    assert client.network_calls == 3


def test_cached_key_is_served_from_disk(tmp_path):
    client, session, _ = make(tmp_path)
    assert client.get_json("https://x.test/a", "sub/a.json") == {"ok": True}
    n = len(session.calls)
    assert client.get_json("https://x.test/a", "sub/a.json") == {"ok": True}
    assert len(session.calls) == n
    assert (tmp_path / "sub" / "a.json").exists()


def test_robots_disallow_is_honoured(tmp_path):
    client, session, _ = make(tmp_path, robots="User-agent: *\nDisallow: /private/\n")
    with pytest.raises(RobotsDisallowedError):
        client.get_text("https://x.test/private/p", "p.txt")
    assert client.get_text("https://x.test/public/p", "q.txt")
    assert session.calls.count("https://x.test/robots.txt") == 1
