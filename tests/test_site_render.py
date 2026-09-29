"""The site render (src/web): pages built from outputs/, numbers from the outputs, no old material."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from src import config
from src.web import charts, context, fmt
from src.web.render import render

DOCS = config.ROOT_DIR / "docs"
QPAGES = tuple(f"q/{slug}/index.html" for slug in ("per-head", "break", "cohorts", "youth", "abroad", "national-team", "goalkeepers"))
PAGES = ("index.html", *QPAGES, "this-autumn/index.html", "methodology/index.html", "players/index.html")


def _all(site: Path) -> str:
    return "\n".join((site / rel).read_text(encoding="utf-8") for rel in PAGES)


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("site")
    render(out, build_date="2026-09-29")
    return out


@pytest.fixture(scope="module")
def outputs() -> dict:
    return context.load_outputs()


def test_fmt() -> None:
    assert [fmt.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd",
    ]
    assert fmt.pct(0.143) == "14.3\u00a0%" and fmt.pct0(0.3042) == "30\u00a0%"
    assert fmt.num(17991) == "17\u00a0991" and fmt.signed(-0.31) == "\u22120.3" and fmt.signed(1.06) == "+1.1"
    assert fmt.f2(-0.5) == "\u22120.50"
    assert fmt.f2(1.8322) == "1.83"
    assert fmt.times(0.831) == "×0.83"
    assert fmt.ratio_words(0.98) == "at" and fmt.ratio_words(0.87) == "below" and fmt.ratio_words(1.4) == "above"


def test_pages_and_assets_written(site: Path) -> None:
    for rel in (*PAGES, "atlas/index.html", "charts/report.json", "players/pool.json",
                "style.css", "modern.css", "charts.js", "atlas.app.js"):
        assert (site / rel).stat().st_size > 0, rel
    assert not (site / "CNAME").exists(), "the render must not write CNAME"
    assert (DOCS / "CNAME").read_text().strip() == "hockey.bsandova.com"


def test_report_structure(site: Path) -> None:
    home = (site / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en"' in home and 'id="take"' in home
    assert "img/hockey.jpg" in home and "U.S. Air Force Academy" in home
    assert home.count('class="nx-take-link"') == 7
    for part in ('class="facts"', 'class="tldr"', 'class="meta-block', 'id="question"', 'id="cite"', 'id="references"', 'id="changes"'):
        assert part in home, part
    assert "Research · Czech hockey atlas" in home and "exploratory; not pre-registered" in home
    assert "29 September 2026" in home[home.index('id="changes"'):]
    for i, rel in enumerate(QPAGES, 1):
        page = (site / rel).read_text(encoding="utf-8")
        assert f'id="q{i}"' in page, rel
        for part in ("Figure 1.", "How to read it", "Evidence", "What this means", "What this does not show", 'class="page-meta'):
            assert part in page, (rel, part)
        assert "<h1" in page and "?</h1>" not in page, rel
    meth = (site / "methodology/index.html").read_text(encoding="utf-8")
    for anchor in ("scope", "nationality", "exclusions", "methodology", "data-sources", "linking", "limitations", "reproducibility", "references", "changes"):
        assert f'id="{anchor}"' in meth, anchor
    for excluded in ("KHL", "AHL", "Slovak Extraliga", "Elite Prospects"):
        assert excluded in meth
    js = (site / "charts.js").read_text(encoding="utf-8")
    for name in re.findall(r'data-chart="([^"]+)"', _all(site)):
        assert f"'{name}'" in js, f"no chart function for {name}"


def test_navigation_and_old_links(site: Path) -> None:
    """Every page has the same top bar; old one-page anchors and /atlas/ still lead somewhere."""
    for rel in PAGES:
        html = (site / rel).read_text(encoding="utf-8")
        for label in ("Summary", "Questions", "Methodology", "Players"):
            assert f">{label}<" in html, (rel, label)
        assert html.count('class="nav-q-list"') == 1
    home = (site / "index.html").read_text(encoding="utf-8")
    for old, new in (("q1", "q/per-head/"), ("q7", "q/goalkeepers/"), ("methodology", "methodology/#methodology"),
                     ("nationality", "methodology/#nationality"), ("autumn", "this-autumn/")):
        assert f'"{old}": "{new}"' in home, old
    redirect = (site / "atlas/index.html").read_text(encoding="utf-8")
    assert 'url=../players/' in redirect and not (site / "atlas/pool.json").exists()
    # every relative link on every page points at a page or file the render wrote
    for rel in PAGES:
        base = (site / rel).parent
        for href in re.findall(r'href="([^"]*)"', (site / rel).read_text(encoding="utf-8")):
            path = href.split("#")[0].split("?")[0]
            if ":" in href or not path or "img/" in path:
                continue
            target = (base / path).resolve()
            assert target.is_file() or (target / "index.html").is_file(), (rel, href)


def test_no_withdrawn_material(site: Path) -> None:
    for rel in PAGES:
        text = re.sub(r"<[^>]+>", " ", (site / rel).read_text(encoding="utf-8"))
        text = text.replace("the AI layer and the video proof of concept of the earlier version are withdrawn", "")
        for word in ("YOLO", "multimodal", "LLM", "Claude", "video", " AI ", "UMAP", "cluster"):
            assert word not in text, (rel, word)


def test_numbers_come_from_outputs(site: Path, outputs: dict) -> None:
    html = _all(site)
    head = outputs["q1_per_million"]["headline"]
    home = head["home"]
    assert f"{home['nhl_per_million']:.2f}" in html
    assert f"{head['peer_median']['nhl_per_million']:.2f}" in html
    peak = outputs["q1_per_million"]["nhl_home_peak"]
    assert f"{peak['n']} players in {peak['season']}" in html
    fall = next(s for s in outputs["q2_break_model"]["nations"]["CZE"]["break"]["steps"] if s["direction"] == "down")
    assert fall["modal"]["season"] in html
    q4 = outputs["q4_youth_ice_time"]["leagues"]
    assert fmt.pct(q4["Liiga"]["summary"]["mean_u21_games_share"]) in html
    assert fmt.num(outputs["linking"]["persons"]) in html
    atlas = (site / "players/index.html").read_text(encoding="utf-8")
    assert f"{outputs['pool']['counts']['players']} players" in atlas


def test_chart_data_matches_outputs(site: Path, outputs: dict) -> None:
    rep = json.loads((site / "charts/report.json").read_text(encoding="utf-8"))
    assert rep["q1"]["nhl_series"]["nations"]["CZE"]["n"] == outputs["q1_per_million"]["nhl_series"]["nations"]["CZE"]["n"]
    assert len(rep["q3"]["rows"]) == 12
    pool = json.loads((site / "players/pool.json").read_text(encoding="utf-8"))
    assert len(pool["players"]) == outputs["pool"]["counts"]["players"]
    for season, by in pool["by_season_rung"].items():
        assert sum(by.values()) == outputs["pool"]["counts"]["seasons"][season]


def test_published_site_is_current(site: Path) -> None:
    """docs/ must be re-rendered after outputs/ or the templates change (`make pages`)."""
    for rel in ("charts/report.json", "players/pool.json", "charts.js", "atlas.app.js", "modern.css", "atlas/index.html"):
        assert (DOCS / rel).read_bytes() == (site / rel).read_bytes(), f"docs/{rel} is stale: run `make pages`"
    strip = lambda s: re.sub(r"Built \d{1,2} \w+ \d{4}", "", s)  # noqa: E731
    for rel in PAGES:
        assert strip((DOCS / rel).read_text(encoding="utf-8")) == strip((site / rel).read_text(encoding="utf-8")), f"docs/{rel} is stale"


def test_words_follow_numbers(outputs: dict) -> None:
    """A sentence's direction is chosen from its number, so flipping the number flips the word."""
    o = copy.deepcopy(outputs)
    q1 = o["q1_per_million"]
    q1["headline"]["home"]["nhl_per_million"] = q1["headline"]["peer_median"]["nhl_per_million"] / 2
    assert context._q1(q1)["nhl_vs_median_word"] == "below"
    q2 = o["q2_break_model"]
    for s in q2["nations"]["CZE"]["break"]["steps"]:
        s["direction"] = "up"
    assert context._q2(q2)["CZE"]["fall"] is None


def test_pool_data_rows(outputs: dict) -> None:
    data = charts.pool_data(outputs["pool"])
    p = data["players"][0]
    assert set(p) == {"id", "n", "b", "bd", "p", "nb", "r", "l", "g", "s"}
    assert all(len(row) == len(data["fields"]) for row in p["s"])


def test_autumn_section(site: Path, outputs: dict) -> None:
    """This autumn: the as-of line, only confirmed news, footnoted, the captain's numbers from outputs/."""
    html = (site / "this-autumn/index.html").read_text(encoding="utf-8")
    assert 'id="autumn"' in html
    sec = html[html.index('id="autumn"'):]
    sec = sec[: sec.index("</section>")]
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sec))
    assert "Atlas data as of 29 September 2026; news as of 29 September 2026" in text
    assert "Note · Czech hockey atlas" in text and "n.d.)" not in text  # every source carries its date
    news = config.news()
    assert news is not None
    for s in news["sources"]:
        assert s["url"] in sec, s["key"]
    assert len(re.findall(r'<li id="autumn-src-\d+"', sec)) == len(news["sources"])
    for n in set(re.findall(r'href="#autumn-src-(\d+)"', sec)):
        assert f'id="autumn-src-{n}"' in sec
    # the Bruins captaincy is a club role; the unconfirmed items stay out
    assert "not a national-team role" in text
    for word in ("Červenka", "alternate captain", "Brno", "Plzeň"):
        assert word not in text, word
    pid = news["captain"]["person_id"]
    player = next(p for p in outputs["pool"]["players"] if p["person_id"] == pid)
    last = player["seasons"][-1]
    row = next(r for r in outputs["q5_abroad"]["players"] if r["person_id"] == pid and r["season"] == last["season"])
    assert f"NHL games, {last['season']} {int(last['games'])}" in text
    assert f"Points {int(last['points'])}" in text
    assert fmt.mmss(last["toi_per_game_s"]) in text and fmt.mmss(row["median_toi_per_game_s"]) in text
    assert fmt.f2(row["median_points_per_game"]) in text
    assert 'href="../q/national-team/"' in sec


def test_mmss() -> None:
    assert fmt.mmss(1239.3) == "20:39" and fmt.mmss(875.69) == "14:36" and fmt.mmss(59.6) == "1:00"


def test_references_resolve(site: Path) -> None:
    """Every citation on every page resolves to a numbered reference, and every reference is cited."""
    from src.web import references

    cited: set[int] = set()
    for rel in PAGES:
        html = (site / rel).read_text(encoding="utf-8")
        for n in re.findall(r'href="[^"]*#ref-(\d+)"', html):
            cited.add(int(n))
    listed = {r["n"] for r in references.listing()}
    assert cited == listed
    meth = (site / "methodology/index.html").read_text(encoding="utf-8")
    for n in listed:
        assert f'id="ref-{n}"' in meth


def test_intervals_match_point_values(outputs: dict) -> None:
    """The bootstrap module reproduces the point values the question outputs report."""
    iv = outputs["intervals"]
    for lg in ("NHL", "Liiga", "SHL"):
        s = outputs["q5_abroad"]["summary"][lg]["CZE"]
        assert iv["q5"][lg]["toi"]["median"] == pytest.approx(s["median_toi_ratio"])
        assert iv["q5"][lg]["ppg"]["median"] == pytest.approx(s["median_ppg_ratio"])
        assert iv["q5"][lg]["toi"]["lo"] <= iv["q5"][lg]["toi"]["median"] <= iv["q5"][lg]["toi"]["hi"]
    for lg in ("Extraliga", "Liiga", "SHL"):
        assert iv["q4"]["leagues"][lg]["games"]["mean"] == pytest.approx(
            outputs["q4_youth_ice_time"]["leagues"][lg]["summary"]["mean_u21_games_share"], abs=1e-5)
    assert iv["q6"]["all"]["shares"]["1"] == pytest.approx(outputs["q6_national_team"]["mean_shares"]["CZE"]["1"], abs=1e-5)
    for lg, v in iv["q7"].items():
        if v:
            assert v["median"] == pytest.approx(outputs["q7_goalkeepers"]["abroad"]["summary"][lg]["median_save_pct_minus_median"], abs=1e-5)
    for lg, v in iv["q7_youth"].items():
        assert v["mean"] == pytest.approx(outputs["q7_goalkeepers"]["youth"][lg]["mean_u24_games_share"], abs=1e-5)
        assert v["lo"] <= v["mean"] <= v["hi"]
    for lg in ("Liiga", "SHL"):
        s = outputs["q5_abroad"]["home_by_position"][lg]["F"]
        assert iv["q5_positions"][lg]["F"]["ppg"]["median"] == pytest.approx(s["median_ppg_ratio"], abs=1e-5)
    last = [r for r in iv["q3"]["u21_by_season"] if r["season"] == outputs["q3_cohort_gaps"]["definitions"]["season"]]
    top = next(c for c in outputs["q3_cohort_gaps"]["cells"] if c["position"] == "F" and c["age_band"] == "≤21")
    assert next(r for r in last if r["position"] == "F")["shortfall"] == pytest.approx(top["shortfall"])
