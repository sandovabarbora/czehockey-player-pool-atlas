"""Wikipedia roster fetcher: parsers on trimmed saved articles (no network) and the snapshot contract."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from bs4 import BeautifulSoup

from src import config, snapshot
from src.fetch import rosters
from src.nations import ISO3


def page(fixtures_dir, name: str) -> str:
    return (fixtures_dir / "rosters" / name).read_text(encoding="utf-8")


def test_events_cover_2010_to_2026_without_2020():
    ev = rosters.events()
    wc = [e["year"] for e in ev if e["event"] == "WC"]
    og = [e["year"] for e in ev if e["event"] == "OG"]
    assert wc == [y for y in range(2010, 2027) if y != 2020]
    assert og == [2010, 2014, 2018, 2022, 2026]
    assert ev[0]["title"] == "Ice hockey at the 2010 Winter Olympics – Men's team rosters"


def test_page_url_is_an_article_url_not_the_api():
    url = rosters.page_url("Ice hockey at the 2014 Winter Olympics – Men's team rosters")
    assert url.startswith("https://en.wikipedia.org/wiki/Ice_hockey_at_the_2014_")
    assert "/w/" not in url and "api.php" not in url


def test_page_meta(fixtures_dir):
    meta = rosters.page_meta(page(fixtures_dir, "og_2014.html"))
    assert meta == {
        "title": "Ice hockey at the 2014 Winter Olympics – Men's team rosters",
        "revid": 1366321849,
    }
    with pytest.raises(ValueError):
        rosters.page_meta("<html></html>")


def test_parse_2010_page_without_birth_dates(fixtures_dir):
    df = rosters.parse_page(page(fixtures_dir, "wc_2010.html"))
    assert df.groupby("team").size().to_dict() == {"Czech Republic": 25, "Germany": 25}
    assert df["birth_date"].isna().all()
    assert df["wiki_title"].notna().all() and df["club"].notna().all()
    # goaltender tables have no position column: the "Goaltenders" sub-heading gives G
    assert df.groupby("team")["position"].apply(lambda s: (s == "G").sum()).ge(2).all()
    assert set(df["position"]) == {"G", "D", "F"}
    jagr = df[df["player"] == "Jaromír Jágr"].iloc[0]
    assert jagr["club"] == "Avangard Omsk" and jagr["team"] == "Czech Republic"


def test_parse_2025_page(fixtures_dir):
    df = rosters.parse_page(page(fixtures_dir, "wc_2025.html"))
    assert set(df["team"]) == {"Czechia", "Austria"}
    assert df["birth_date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()
    assert set(df["captaincy"].dropna()) == {"C", "A"}
    assert (df["captaincy"] == "C").sum() == 2
    # red links (no article) keep the name but no title
    red = df[df["player"] == "Jáchym Kondelík"].iloc[0]
    assert pd.isna(red["wiki_title"])
    assert not df["player"].str.contains("–").any()


def test_parse_olympic_page_with_club_league(fixtures_dir):
    df = rosters.parse_page(page(fixtures_dir, "og_2014.html"))
    kovar = df[df["player"] == "Jakub Kovář"].iloc[0]
    assert kovar["birth_date"] == "1988-07-19"
    assert kovar["club"] == "Avtomobilist Yekaterinburg"
    assert kovar["club_country"] == "Russia"
    assert kovar["club_league"] == "Kontinental Hockey League"
    assert kovar["position"] == "G"


@pytest.mark.parametrize(
    ("html", "iso"),
    [
        (
            '<td><span style="display:none"> (<span class="bday">1991-07-13</span>)</span>13 July 1991</td>',
            "1991-07-13",
        ),
        (
            '<td><span data-sort-value="000000001984-11-21-0000">21 November 1984</span></td>',
            "1984-11-21",
        ),
        ("<td>November 21, 1984 (aged 29)</td>", "1984-11-21"),
        ("<td>21 November 1984</td>", "1984-11-21"),
        ("<td>unknown</td>", None),
    ],
)
def test_parse_birth_date(html, iso):
    cell = BeautifulSoup(html, "lxml").find("td")
    assert rosters.parse_birth_date(cell) == iso


def test_wiki_title_skips_red_and_external_links():
    def a(html):
        return BeautifulSoup(html, "lxml").find("a")

    assert (
        rosters.wiki_title(
            a('<a href="https://en.wikipedia.org/wiki/Petr_%C4%8C%C3%A1slava">x</a>')
        )
        == "Petr Čáslava"
    )
    assert rosters.wiki_title(a('<a href="./Roman_%C4%8Cervenka">x</a>')) == "Roman Červenka"
    assert (
        rosters.wiki_title(a('<a class="new" href="/wiki/X?action=edit&redlink=1">x</a>')) is None
    )
    assert rosters.wiki_title(a('<a href="https://example.org/">x</a>')) is None


def test_article_birth_date(fixtures_dir):
    assert rosters.article_birth_date(page(fixtures_dir, "player_article.html")) == "1982-05-16"
    assert rosters.article_birth_date("<html><body><p>no infobox</p></body></html>") is None


class FixtureClient:
    """Serves the 2010 World Championship page and one player article; the 2010 Olympic page is missing."""

    def __init__(self, fixtures_dir, cache_dir):
        self.dir = fixtures_dir / "rosters"
        self.cache_dir = cache_dir
        self.network_calls = 0
        self.player_requests = 0

    def get_text(self, url, key, params=None):
        if key == "pages/WC_2010.html":
            text = (self.dir / "wc_2010.html").read_text(encoding="utf-8")
        elif key.startswith("players/"):
            self.player_requests += 1
            text = (self.dir / "player_article.html").read_text(encoding="utf-8")
        else:
            raise RuntimeError(f"404 {url}")
        path = self.cache_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return text


def test_run_fills_birth_dates_for_compared_nations(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshot")
    client = FixtureClient(fixtures_dir, tmp_path / "cache")
    written = rosters.run(2010, 2010, client=client)
    assert {p.name for p in written} == {
        rosters.OUT_ROSTERS,
        rosters.OUT_SOURCES,
        rosters.OUT_COVERAGE,
    }
    df = pd.read_parquet(tmp_path / "snapshot" / rosters.OUT_ROSTERS)
    assert list(df.columns) == rosters.COLUMNS
    assert set(df["team_iso3"]) == {"CZE", "DEU"}
    assert (df["birth_date_source"] == "wikipedia_article").all()
    assert client.player_requests == df["wiki_title"].nunique()
    src = json.loads((tmp_path / "snapshot" / rosters.OUT_SOURCES).read_text())
    assert src["license"] == "CC BY-SA 4.0"
    (pg,) = src["pages"]
    assert pg["revid"] == 1312817550 and pg["url"].startswith(
        "https://en.wikipedia.org/wiki/2010_IIHF"
    )
    assert src["player_articles"] and all(p["revid"] for p in src["player_articles"])
    cov = json.loads((tmp_path / "snapshot" / rosters.OUT_COVERAGE).read_text())
    assert cov["missing_pages"] == ["Ice hockey at the 2010 Winter Olympics – Men's team rosters"]
    assert snapshot.verify(tmp_path / "snapshot") == []


# -- contract on the committed snapshot --------------------------------------------------


@pytest.fixture(scope="module")
def roster() -> pd.DataFrame:
    path = snapshot.SNAPSHOT_DIR / rosters.OUT_ROSTERS
    if not path.exists():
        pytest.skip("rosters not in the snapshot yet")
    return pd.read_parquet(path)


def test_snapshot_columns_and_events(roster):
    assert list(roster.columns) == rosters.COLUMNS
    got = sorted(set(zip(roster["event"], roster["year"].astype(int), strict=True)))
    want = sorted((e["event"], e["year"]) for e in rosters.events())
    assert got == want


def test_snapshot_rows_per_event(roster):
    per = roster.groupby(["event", "year"]).agg(
        teams=("team", "nunique"), players=("player", "size")
    )
    wc = per.loc["WC"]
    assert (wc["teams"] == 16).all(), wc.to_dict()
    assert wc["players"].between(370, 460).all(), wc.to_dict()
    og = per.loc["OG"]
    assert (og["teams"] == 12).all() and og["players"].between(250, 320).all(), og.to_dict()


def test_snapshot_compared_nations(roster):
    ours = roster[roster["team_iso3"].isin(ISO3)]
    per = ours.groupby(["event", "year", "team_iso3"]).size()
    assert per.between(20, 30).all(), per[~per.between(20, 30)].to_dict()
    czech = ours[ours["team_iso3"] == "CZE"]
    assert len(czech.groupby(["event", "year"])) == len(rosters.events())
    assert czech["birth_date"].notna().mean() >= 0.97
    assert ours["birth_date"].notna().mean() >= 0.95
    assert ours["club"].notna().mean() >= 0.99
    assert ours["position"].isin(["G", "D", "F"]).mean() >= 0.99


def test_snapshot_one_row_per_player_and_event(roster):
    key = roster.assign(k=roster["wiki_title"].fillna(roster["player"]))
    assert not key.duplicated(["event", "year", "team", "k"]).any()
    assert roster["birth_date"].dropna().str.fullmatch(r"\d{4}-\d{2}-\d{2}").all()


def test_snapshot_sources_carry_attribution():
    path = snapshot.SNAPSHOT_DIR / rosters.OUT_SOURCES
    if not path.exists():
        pytest.skip("sources not in the snapshot yet")
    src = json.loads(path.read_text())
    assert src["license"] == "CC BY-SA 4.0" and src["license_url"].startswith(
        "https://creativecommons.org/"
    )
    assert len(src["pages"]) == len(rosters.events())
    for p in src["pages"] + src["player_articles"]:
        assert (
            p["revid"] and p["url"].startswith("https://en.wikipedia.org/wiki/") and p["retrieved"]
        )
