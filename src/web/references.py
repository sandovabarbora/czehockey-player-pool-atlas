"""The atlas's references, numbered by first citation (summary first, then the question pages).

Each entry was checked on 29 September 2026: the journal articles against their DOI record
(api.crossref.org), the Wikipedia articles at the revision given. `cite(key)` gives the number;
the methodology page lists them all.
"""

from __future__ import annotations

ACCESSED = "29 September 2026"

REFERENCES: tuple[dict[str, str], ...] = (
    {
        "key": "cobley2009",
        "text": "Cobley, S., Baker, J., Wattie, N. and McKenna, J. (2009). Annual age-grouping and athlete development: "
        "a meta-analytical review of relative age effects in sport. Sports Medicine 39(3), 235–256.",
        "url": "https://doi.org/10.2165/00007256-200939030-00005",
    },
    {
        "key": "nolan2010",
        "text": "Nolan, J. E. and Howell, G. (2010). Hockey success and birth date: the relative age effect revisited. "
        "International Review for the Sociology of Sport 45(4), 507–512.",
        "url": "https://doi.org/10.1177/1012690210371560",
    },
    {
        "key": "barreiros2014",
        "text": "Barreiros, A., Côté, J. and Fonseca, A. M. (2014). From early to adult sport success: analysing athletes' "
        "progression in national squads. European Journal of Sport Science 14(S1), S178–S182.",
        "url": "https://doi.org/10.1080/17461391.2012.671368",
    },
    {
        "key": "gullich2022",
        "text": "Güllich, A., Macnamara, B. N. and Hambrick, D. Z. (2022). What makes a champion? Early multidisciplinary "
        "practice, not early specialization, predicts world-class performance. Perspectives on Psychological Science 17(1), 6–29.",
        "url": "https://doi.org/10.1177/1745691620974772",
    },
    {
        "key": "maguire1996",
        "text": "Maguire, J. (1996). Blade runners: Canadian migrants, ice hockey, and the global sports process. "
        "Journal of Sport and Social Issues 20(3), 335–360.",
        "url": "https://doi.org/10.1177/019372396020003007",
    },
    {
        "key": "debosscher2006",
        "text": "De Bosscher, V., De Knop, P., Van Bottenburg, M. and Shibli, S. (2006). A conceptual framework for analysing "
        "sports policy factors leading to international sporting success. European Sport Management Quarterly 6(2), 185–215.",
        "url": "https://doi.org/10.1080/16184740600955087",
    },
    {
        "key": "nhl_timeline",
        "text": "Wikipedia contributors (2026). Timeline of the National Hockey League, revision 1376655521 of 25 September 2026. "
        "English Wikipedia (CC BY-SA 4.0).",
        "url": "https://en.wikipedia.org/w/index.php?oldid=1376655521",
    },
    {
        "key": "khl",
        "text": "Wikipedia contributors (2026). Kontinental Hockey League, revision 1375949502 of 21 September 2026. "
        "English Wikipedia (CC BY-SA 4.0).",
        "url": "https://en.wikipedia.org/w/index.php?oldid=1375949502",
    },
    {
        "key": "og2018",
        "text": "Wikipedia contributors (2026). Ice hockey at the 2018 Winter Olympics – Men's tournament, revision 1349342664 "
        "of 16 April 2026. English Wikipedia (CC BY-SA 4.0).",
        "url": "https://en.wikipedia.org/w/index.php?oldid=1349342664",
    },
    {
        "key": "og2022",
        "text": "Wikipedia contributors (2026). Ice hockey at the 2022 Winter Olympics – Men's tournament, revision 1366326745 "
        "of 27 July 2026. English Wikipedia (CC BY-SA 4.0).",
        "url": "https://en.wikipedia.org/w/index.php?oldid=1366326745",
    },
)

NUMBER = {r["key"]: i + 1 for i, r in enumerate(REFERENCES)}


def cite(*keys: str) -> str:
    """'[1, 2]' for the given keys, in number order."""
    return "[" + ", ".join(str(n) for n in sorted(NUMBER[k] for k in keys)) + "]"


def listing() -> list[dict[str, str | int]]:
    return [{**r, "n": i + 1, "accessed": ACCESSED} for i, r in enumerate(REFERENCES)]
