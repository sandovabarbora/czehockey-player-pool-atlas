```markdown
# Tomáš Hertl (F, 1993)

## Statistický profil
Style cluster C0 (Top-six skórující), quality cluster C3 (EU veteráni); PCA style (2.45, -0.55), quality (4.47, -0.44) ho řadí daleko na produkční ose. Quality-adjusted P/GP 0.667 (G/GP 0.282, A/GP 0.386) na vzorku 82 GP odpovídá cross-league z-score +3.21 — třetí nejvyšší pásmo v celém korpusu. PIM/GP 0.458 indikuje umírněnou fyzickou stopu nepřevyšující průměr top-six profilu.

## Trajektorie
Mezi 2024-25 a 2025-26 P/GP 0.776 → 0.667 (Δ -0.109) při růstu GP 73 → 82, tedy plný sezónní vzorek proti částečnému. Směr klesající, ale absolutní úroveň zůstává v horní decilu NHL forwards v korpusu. Hráči v cluster C0 ve věku 32 let typicky vstupují do plateau/decline fáze produkční křivky.

## Reprezentační kontext
IIHF účast v datasetu 0 turnajů (eligibility flag yes přiřazena přes birth_country, nikoli MS 2024/2025 účast). Profil odpovídá top-end produkčnímu pásmu mezi Czech-eligible NHL útočníky v korpusu.

## Srovnatelné profily (in-corpus)
Tři nejbližší ve style projekci: Michael Gabriel Vukojevic (extraliga, dist. 0.312), Petr Kodytek (liiga, dist. 0.354), Filip Chlapík (extraliga, dist. 0.583). Style cluster je liga-agnostický — proto v sousedství figurují EU hráči se shodným profilovým tvarem (vyšší A-share, mírná fyzicalita), ale řádově nižším quality-adjusted výstupem.

## Caveats
Datový zdroj výhradně NHL; chybí shots/GP konzistentně napříč ligami, takže feature vektor je dominantně driven G/A/PIM. Style-cluster sousedi mají dramaticky nižší quality output — geometrická blízkost ve style mapě neimplikuje srovnatelnou úroveň hry, pouze podobný relativní profil v rámci vlastní ligy. Eligibility flag bez IIHF turnaje znamená, že reprezentační status je odvozen z birth_country, nikoli z recent NT účasti.
```