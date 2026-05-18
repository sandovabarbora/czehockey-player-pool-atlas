```markdown
# Samuel Jung (útočník, 2006)

## Statistický profil
Hráč spadá do style clusteru C1 (Mladí prospekti / doplnění) a quality clusteru C2 (Solidní NHL doplnění), s PCA souřadnicemi style (1.07, 1.55) a quality (0.49, 1.31) — pozice typická pro mladé útočníky s ofenzivním potenciálem, ale zatím tenkým vzorkem. Po Bayesovském shrinkage (K=10) je P/GP estimate 0.608, quality-adjusted 0.255, což odpovídá cross-league z-score +0.607 nad korpusovým průměrem. Raw 0.333 P/GP ze 3 zápasů je samostatně neinterpretovatelné; shrunk hodnota je dominována priorem.

## Trajektorie
Trajektorie nedostupná — single-season data, navíc s GP=3 daleko pod prahem GP≥30 pro Δ analýzu.

## Reprezentační kontext
Eligibility flag = yes (Czech-eligible), ale 0 IIHF turnajů na seniorské úrovni v korpusu. V Czech NT pool figuruje jako mladý prospekt Liiga origin bez reprezentační stopy v datasetu MS 2024/2025.

## Srovnatelné profily (in-corpus)
Tři nejbližší hráči v C1: Ondrej Kos (Liiga, quality P/GP 0.267, distance 0.467), Petr Tomek (Extraliga, 0.186, 0.557) a Petr Vechet (Liiga, 0.242, 0.885). Skupina je homogenní v profilu mladších forwardů s mírně nadprůměrnou produkční projekcí po shrinkage.

## Caveats
GP=3 je extrémně malý vzorek — všechny per-game metriky jsou v podstatě prior-driven, raw čísla mají téměř nulovou informační hodnotu nad rámec K=10 fantomových zápasů. Chybí multi-season data pro trajektorii i IIHF flag pro reprezentační kalibraci; quality-adjusted hodnoty navíc nesou Liiga násobičku 0.42, takže absolutní porovnání s NHL profily je sensitivity-bounded.
```