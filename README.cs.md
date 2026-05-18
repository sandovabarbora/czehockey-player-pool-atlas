# Český hokej — Atlas fondu hráčů

Pozičně normalizovaná dvourozměrná mapa cca 140–200 hokejistů s českou
mezinárodní způsobilostí, působících v NHL, AHL, Liize, SHL, švýcarské NL, české
Extralize a české 1. lize.

**Jedná se o ukázku metodologie, nikoli o výběrové doporučení.** Cílem je
replikovatelný způsob mapování fondu hráčů jako plánovacího nástroje v rámci
víceletého reprezentačního cyklu. Není to návrh sestavy a nekomentuje výsledky
turnajů, sestavování útoků ani konkrétní trenérská rozhodnutí.

Anglickou verzi tohoto dokumentu najdete v [`README.md`](README.md).

---

## Co projekt produkuje

Dvě mapové projekce vedle sebe:

1. **Style mapa** — pozičně normalizované z-skóre per-60 metrik, bez násobiček
   kvality lig. Hráči jsou seskupeni podle herního profilu nezávisle na ligové síle.
2. **Kvalitou upravená mapa** — stejné featury, ale s aplikovanými násobičkami
   kvality lig na produkční metriky. Hráči z různých lig se stávají přímo
   porovnatelnými na jedné kvalitativní ose. Násobičky jsou subjektivní volbou;
   přiložena je citlivostní analýza (perturbace ±20 %).

Dále:

- **Trajektorie** — meziroční změna (2024/25 → 2025/26), zobrazená pouze pro hráče
  s dostatečným vzorkem v obou sezónách.
- **Klastry archetypů** — KMeans s K vybraným na základě silhouette score, popisky
  archetypů jsou aplikovány post-hoc po inspekci.
- **Mini sekce brankářů** — samostatná malá tabulka; brankářská analytika je
  pro hlavní mapu příliš kontextově závislá.
- **Sekce omezení** — explicitní, povinná, v české verzi reportu.

## Datové zdroje

Viz `README.md` pro detailní tabulku. Klíčové vyloučení: **KHL je z analýzy
vyloučena** ze dvou důvodů: politické sankce ovlivňující dostupnost ruských
datových zdrojů a kvalita dat. Vyloučení je zdokumentováno v sekci omezení reportu.

## Metodika — klíčové volby

- **Pozičně specifické featury.** Útočníci, obránci a brankáři mají oddělené
  feature vektory (10D pro útočníky/obránce, 6D pro brankáře). Žádná smíšená
  projekce.
- **Násobičky kvality lig jsou subjektivní.** Citlivostní notebook ukazuje, jak
  se mapa mění při změně násobiček o ±20 %. Hodnoty jsou v `config/league_quality.yaml`
  s citacemi zdrojů.
- **Počet klastrů K je data-driven.** Výběr na základě silhouette score a elbow
  metody pro K ∈ {4..8} u útočníků a {3..6} u obránců. Popisky archetypů jsou
  post-hoc.
- **Žádné xG v cross-league feature vektoru.** Veřejné xG modely pro Liigu / SHL /
  NL / Extraligu neexistují. xG je zobrazeno pouze pro NHL/AHL hráče v tooltipech
  a technické sekci; není imputováno.
- **Minimální vzorek pro trajektorii.** Hráči musí mít ≥ 30 zápasů v obou sezónách,
  aby se objevili v trajektoriální analýze.

## Co tento projekt není

- Není to výběrové doporučení.
- Není to kritika trenérů, sestavení útoků ani konkrétních turnajových výsledků.
- Není to nástroj pro hodnocení brankářů nad rámec agregovaných statistik.
- Nepoužívá žádná interní scoutingová, video, kondiční ani tracking data.
- Nezahrnuje hráče z KHL.

## Licence

MIT. Viz [LICENSE](LICENSE).

## Kontakt

Barbora Šandová · barbora@datasimply.eu · [linkedin.com/in/barborasandova](https://linkedin.com/in/barborasandova)
