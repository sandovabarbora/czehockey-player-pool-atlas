```markdown
# Filip Chytil (útočník, 1999)

## Statistický profil
Chytil je v sezóně 2025-26 zařazen do style clusteru C1 (Mladí prospekti / doplnění) a quality clusteru C4 (EU mladá / depth), s PCA souřadnicemi style (-0.18, -0.09) a quality (1.46, -0.08) — vysoká hodnota PC1 v quality projekci odráží NHL násobičku (1.00) aplikovanou na produkci. Po Bayesovském shrinkage (K=10) činí P/GP 0.291 (raw 0.250), G/GP 0.225 a A/GP 0.068; cross-league quality z-score P/GP +0.834 ho řadí výrazně nad korpusový průměr.

## Trajektorie
Trajektorie nedostupná — single-season data v Atlasu (pouze 2025-26, GP=12). Vzorek 12 zápasů je pod prahem pro robustní Δ-analýzu, proto i shrunk hodnoty zůstávají blízko prior (zejména A/GP, kde raw 0.000 → shrunk 0.068 je tažen K=10 fantomovým zápasům).

## Reprezentační kontext
Eligibility flag = yes, ale IIHF účast v dataset window (MS 2024/2025) = 0 turnajů. V Czech NT pool tedy figuruje jako eligible NHL útočník bez aktuální reprezentační stopy v integrovaných datech.

## Srovnatelné profily (in-corpus)
Tři nejbližší profily v style clusteru C1: Theodor Pištěk (extraliga, P/GP quality 0.103, distance 0.155), Miloš Roman (extraliga, 0.099, 0.325) a Jakub Pour (extraliga, 0.122, 0.47). Blízkost ve style mapě je dána strukturou per-game profilu bez ligové násobičky; v quality projekci se Chytil díky NHL faktoru od těchto extraligových profilů výrazně oddaluje.

## Caveats
Sample size GP=12 je malý — shrinkage prior dominuje zejména u A/GP (raw 0.000), takže shrunk P/GP 0.291 nese široký posterior interval a interpretace cross-league z-score +0.834 je tomu úměrná. Zároveň chybí multi-season data pro NHL historii v tomto datasetu (zdroj pouze 'nhl', single season), takže není možné posoudit konzistenci profilu, a nulová IIHF účast omezuje cross-context kontrolu.
```