"""The "what to take from it" block: the report's conclusions, written from
its own numbers at build time and placed first, the way the football atlas
does it (site/takeaways.py there).

The hockey pipeline's processed tables are not kept in the repository, so
the statements are read back from the rendered page itself -- the
per-capita rows, the two cohort tables and the cluster blocks are all
structured markup with the numbers in them. A re-render therefore moves the
statements with the data, and nothing here is typed by hand.

Inserted by site/insert_takeaways.py at the end of the build. The site is
English only since 2026-09-22; the Czech strings below stay because the
content source is still the Czech render and a Czech edition would need
nothing but a second call.
"""

from __future__ import annotations

import html
import re

CS = {
    "kicker": "Co si z toho odnést",
    "per_capita": "Na hlavu je český pool {rank} z {n}: {cze} hráče NHL na milion obyvatel; nejvíc jich má {top} ({top_v}).",
    "per_capita_body": "{slovakia}Pořadí na milion obyvatel: {lead}.",
    "cohorts": "Kde je pool tenký: {thin}.",
    "cohorts_body": "V každé kohortě je počet hráčů to první, co chybí; medián produkce je až druhá otázka. {elite}",
    "clusters": "Útočníci se dělí na {n} archetypy a dva z nich nesou skoro všechno: {top2}.",
    "clusters_body": "{detail} Z {total} mapovaných útočníků jich {wc} hrálo mistrovství světa — napříč archetypy, ne v jednom.",
    "limits": "Co to neříká: nic o výběru, nic o formě, nic o budoucnosti.",
    "limits_body": "Mapa je popis toho, co v datech je: kdo kde hraje, s jakou produkcí a v jakém profilu. Není to doporučení nominace ani předpověď; ligové multiplikátory jsou subjektivní a citlivostní analýza (±20 %) je v metodologii.",
}
EN = {
    "kicker": "What to take from it",
    "per_capita": "Per head the Czech pool ranks {rank} of {n}: {cze} NHL players per million inhabitants against {top_v} for {top}.",
    "per_capita_body": "{slovakia}Per million inhabitants: {lead}.",
    "cohorts": "Where the pool is thin: {thin}.",
    "cohorts_body": "In every cohort the count is what is missing first; the median production is the second question. {elite}",
    "clusters": "The forwards split into {n} archetypes and two of them carry almost all of it: {top2}.",
    "clusters_body": "{detail} Of the {total} mapped forwards, {wc} played at a World Championship — spread across the archetypes, not held in one.",
    "limits": "What it does not say: nothing about selection, form, or the future.",
    "limits_body": "The map describes what is in the data: who plays where, with what production and in what profile. It is not a roster recommendation and not a forecast; the league multipliers are subjective and a ±20 % sensitivity analysis is in the methodology.",
}


def _ordinal(n: int, lang: str) -> str:
    if lang != "en":
        return f"{n}."
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def parse(page: str) -> dict:
    """Every number the statements need, read from the built page."""
    capita = [
        {"value": float(v), "code": c, "name": _clean(n)}
        for v, c, n in re.findall(
            r'<div class="capita-row"[^>]*style="--value: ([\d.]+);[^"]*">\s*<div class="capita-country">\s*'
            r'<span class="capita-code">([A-Z]{3})</span>\s*([^<]+)', page)
    ]
    cohorts = []
    for table in re.findall(r'<table class="cohort-table"[^>]*>(.*?)</table>', page, re.S):
        head = [_clean(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", table, re.S)]
        rows = []
        for tr in re.findall(r"<tr>(.*?)</tr>", table, re.S)[1:]:
            cells = [_clean(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if not cells:
                continue
            parsed = []
            for c in cells[1:]:
                m = re.match(r"(\d+)\s+([\d.,]+)", c)
                parsed.append({"n": int(m.group(1)), "median": float(m.group(2).replace(",", "."))} if m else None)
            rows.append({"cohort": cells[0], "by_country": dict(zip(head[1:], parsed))})
        cohorts.append({"countries": head[1:], "rows": rows})
    # the cluster blocks come in two runs, forwards then defensemen; the
    # headings between them say which is which
    splits = [m.start() for m in re.finditer(r'<h[23][^>]*>[^<]*?(?:forwards|útočníc|defensem|obránc)[^<]*?</h[23]>', page, re.I)]
    clusters = []
    for m in re.finditer(r'<details class="cluster">(.*?)</summary>', page, re.S):
        block = m.group(1)
        group = sum(1 for s_ in splits if s_ < m.start())
        name = re.search(r'class="cluster-name">([^<]*)|<span>\s*([^<\n]+?)\s*<span class="cluster-meta-inline"', block)
        meta = re.search(r'class="cluster-meta-inline">(.*?)</span>', block, re.S)
        if not (name and meta):
            continue
        mm = re.search(r"(\d+)\s*(?:players|hráč\w*)\s*·\s*(?:WC pool|MS pool)\s*(\d+)", _clean(meta.group(1)), re.I)
        clusters.append({"name": _clean(name.group(1) or name.group(2)), "group": group,
                         "n": int(mm.group(1)) if mm else None, "wc": int(mm.group(2)) if mm else None})
    return {"capita": capita, "cohorts": cohorts, "clusters": clusters}


def statements(data: dict, lang: str = "en") -> list[dict]:
    T = EN if lang == "en" else CS
    out: list[dict] = []
    num = (lambda v, d=2: f"{v:.{d}f}") if lang == "en" else (lambda v, d=2: f"{v:.{d}f}".replace(".", ","))
    home_col = "CZE" if lang == "en" else "ČR"
    cap = data["capita"]
    if cap:
        cze = next((r for r in cap if r["code"] == "CZE"), None)
        if cze:
            ordered = sorted(cap, key=lambda r: -r["value"])
            rank = ordered.index(cze) + 1
            top = ordered[0]
            above = [r for r in ordered if r["value"] > cze["value"]]
            smaller = [r for r in above if r["code"] == "SVK"]
            lead = ", ".join(f"{r['name']} {num(r['value'])}" for r in ordered)
            slovakia = ("Slovakia is ahead of it with half the population. " if lang == "en" else
                        "Slovensko je před ním s polovičním počtem obyvatel. ") if smaller else ""
            out.append({"head": T["per_capita"].format(rank=_ordinal(rank, lang), n=len(cap), cze=num(cze["value"]),
                                                       top=top["name"], top_v=num(top["value"])),
                        "body": T["per_capita_body"].format(slovakia=slovakia, lead=lead)})
    if data["cohorts"]:
        fw = data["cohorts"][0]
        peers = [c for c in fw["countries"] if c != home_col]
        thin, elite = [], ""
        for row in fw["rows"]:
            cze = row["by_country"].get(home_col)
            others = [row["by_country"].get(p) for p in peers]
            others = [o for o in others if o]
            if not cze or not others:
                continue
            best = max(others, key=lambda o: o["n"])
            if cze["n"] <= 2 and best["n"] >= cze["n"] * 3:
                name = [p for p in peers if row["by_country"].get(p) is best][0]
                thin.append(f"{row['cohort']} {cze['n']} ({name} {best['n']})")
            if cze["median"] >= max(o["median"] for o in others):
                elite = (f"In {row['cohort']} the {cze['n']} Czech forwards have the highest median production of any peer "
                         f"({num(cze['median'])} points per game) — the top is fine, the queue behind it is not."
                         if lang == "en" else
                         f"V kohortě {row['cohort']} drží český pool nejvyšší medián produkce ze všech (útočníků: {cze['n']}) "
                         f"— {num(cze['median'])} bodu na zápas; špička drží, fronta za ní ne.")
        if thin:
            out.append({"head": T["cohorts"].format(thin="; ".join(thin)), "body": T["cohorts_body"].format(elite=elite)})
    cl = [c for c in data["clusters"] if c["n"]]
    if cl:
        # the forwards' own run of clusters: the first group that has any
        first = min(c["group"] for c in cl)
        seen, uniq = set(), []
        for c in cl:
            if c["group"] != first or c["name"] in seen:
                continue
            seen.add(c["name"])
            uniq.append(c)
        top2 = sorted(uniq, key=lambda c: -c["n"])[:2]
        total = sum(c["n"] for c in uniq)
        wc = sum(c["wc"] or 0 for c in uniq)
        detail = ("; ".join(f"{c['name']} {c['n']}" for c in sorted(uniq, key=lambda c: -c['n'])) + ".")
        out.append({"head": T["clusters"].format(n=len(uniq), top2=" and ".join(f"{c['name']} ({c['n']})" for c in top2) if lang == "en"
                                                 else " a ".join(f"{c['name']} ({c['n']})" for c in top2)),
                    "body": T["clusters_body"].format(detail=detail, wc=wc, total=total)})
    out.append({"head": T["limits"], "body": T["limits_body"]})
    return out


def render(page: str, lang: str = "en") -> str:
    """The block's HTML for a built page, or "" when the numbers are absent."""
    items = statements(parse(page), lang)
    if not items:
        return ""
    T = EN if lang == "en" else CS
    body = "".join(
        f'<div class="nx-take"><p class="nx-take-n">{i + 1}</p><div>'
        f'<p class="nx-take-head">{html.escape(it["head"])}</p>'
        f'<p class="nx-take-body">{html.escape(it["body"])}</p></div></div>'
        for i, it in enumerate(items))
    return (f'<section class="take" id="take">\n  <div class="container">\n'
            f'    <p class="masthead-kicker">{T["kicker"]}</p>\n{body}\n  </div>\n</section>\n')
