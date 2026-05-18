# Cover letter — Hnilička

**Předmět:** Mapování fondu Čechy hokejistů ve světových ligách — metodologický nástroj

**Komu:** milan.hnilicka@cesky-hokej.cz (ověř konkrétní adresu na cesky-hokej.cz)
**CC:** žádné v prvním mailu (Morkesovi posíláme samostatný peer email 24h později)

**Kdy poslat:** Úterý nebo středa, 9:00-11:00 Prague time. Vyhnout se ±48h od jakéhokoli zápasu reprezentace.

---

## Verze A — formální, jednoduchá

Vážený pane Hniličko,

jmenuji se Barbora Šandová, pracuji jako Data & Cloud Engineer ve společnosti Alma Career. Posledních několik týdnů jsem ve volném čase budovala metodologický nástroj pro mapování fondu českých hokejistů v profesionálních ligách.

Vznikl z toho otevřený dataset a interaktivní report — pozičně normalizovaný atlas **385 kanonických hráčů** napříč NHL, Tipsport Extraligou, Liigou a IIHF turnaji. Hráči jsou segmentováni podle herního profilu, mezi-ligové srovnatelnosti produkce a meziroční trajektorie výkonu. Reprezentační pool MS 2024 a MS 2025 (42 aktivních hráčů v mapovaném souboru) je vizuálně zvýrazněn.

**Cílem není předkládat výběrové doporučení** — to nejlépe ví Váš tým a trenérský štáb — ale ukázat replikovatelnou metodu, kterou je možné průběžně aplikovat na fond hráčů v rámci čtyřletého olympijského cyklu. Práce stojí výhradně na veřejně dostupných zdrojích; metodologie obsahuje sensitivity analýzu ukazující robustnost vůči subjektivním ligovým násobičkám (top-10 ranking se nemění pro ±20 % perturbace).

Pokud by Vás nebo pana Morkese metodologie zaujala, ráda bych ji představila na krátkém hovoru. Z případné spolupráce bych viděla tři vrstvy:

1. Bezplatná konzultace + walkthrough metody (cca 1h)
2. Pilotní projekt — aplikace přístupu na vaši rozšířenou interní datovou základnu (videoanalytika, kondiční testy, scoutingové zprávy)
3. Průběžná spolupráce — long-term cohort tracking infrastructure pro fond reprezentace

Veřejný výstup: **https://github.com/barborasandova/czehockey-player-pool-atlas**
Připojuji PDF reportu (9 stran, česky).

Děkuji za Váš čas. Přeji reprezentaci úspěšný start nového cyklu.

S úctou,
Barbora Šandová
Data & Cloud Engineer, Alma Career
+420 [telefon]
barbora@datasimply.eu
linkedin.com/in/barborasandova

---

## Verze B — kratší, přímější

Vážený pane Hniličko,

jmenuji se Barbora Šandová, jsem Data & Cloud Engineer (Alma Career). V přiloženém reportu najdete metodologický nástroj — pozičně normalizovaný atlas **385 českých hráčů** z NHL, Extraligy, Liigy + IIHF turnajů, segmentovaný podle herního profilu a meziroční trajektorie.

Není to výběrové doporučení (to ví Váš tým lépe), ale ukázka replikovatelné metody. Veřejně dostupná data, MIT licence, sensitivity analýza top-10 ranking stabilní vůči ±20 % perturbacím.

Pokud by Vás nebo pana Morkese zaujalo, ráda bych se ozvala. Vidím tři možné vrstvy spolupráce — bezplatná konzultace, pilotní projekt s vaší interní datovou základnou, nebo průběžná spolupráce na fondu reprezentace.

Repo: github.com/barborasandova/czehockey-player-pool-atlas
PDF: 9 stran, přiloženo.

Děkuji za Váš čas.

S úctou,
Barbora Šandová
barbora@datasimply.eu · +420 [telefon] · linkedin.com/in/barborasandova

---

## Peer email Morkesovi (24h po Hniličkovi)

**Předmět:** Methodology peer-check — atlas fondu Čechy hráčů

Zdravím Jane,

paralelně k mailu na pana Hniličku Vám posílám peer-level zkrácenou verzi.

Postavila jsem otevřenou pipeline integrující 5 zdrojů (NHL API, MoneyPuck, Liiga, hokej.cz, IIHF přes Wikipedia rosters) přes manuální crosswalk + Bayesovský shrinkage (K=10) pro malé vzorky. Cross-league projekce přes PCA + UMAP, KMeans s data-driven K (silhouette score, ne preconceived archetypes). Ligové násobičky s explicitní sensitivity analýzou (±20% perturbace, top-10 churn 0-1).

Metodologie, kód a sensitivity analýza: https://github.com/barborasandova/czehockey-player-pool-atlas

Kdyby měla peer perspective: jaké slabiny byste viděl jako první?

Hezký den,
Barbora

---

## Důležité notes před odesláním

- [ ] **Veřejně publikuj GitHub repo** než pošleš mail. README.cs.md musí být finální. LICENSE = MIT.
- [ ] **Hostuj report** na `hockey.datasimply.eu` nebo přes GitHub Pages.
  Pokud jen přiložíš PDF jako attachment, repo URL musí fungovat (= veřejné).
- [ ] **Ověř e-mail Hniličky** — buď přes web reprezentace nebo LinkedIn. Pokud
  není veřejně, zkus přes hlavního kontakt na cesky-hokej.cz a požádej
  o přeposlání.
- [ ] **Telefonní číslo** doplň před odesláním (placeholder `[telefon]`).
- [ ] **Žádný follow-up před 14 dny.** Den 14: krátký zdvořilý reminder.
  Den 28: stop. Žádný 3. mail.
- [ ] **Neposílej současně klubům** (Sparta, Slavia, Třinec). Federace
  vztahy jsou ochranné, paralelní outreach = výpadek důvěry.

---

## Připravená reakce na možné odpovědi

**"Děkuji, není zájem."**
→ Odpověz: "Děkuji za odpověď. Repo zůstává veřejné, pokud by se situace
  změnila." Nic víc. Move on with grace.

**"Dejte to Morkesovi přímo."**
→ "Děkuji za přeposlání. Janovi posílám detaily zvlášť." A pošli peer email
  okamžitě (ne 24h později — Hnilička už dal svolení).

**"Zní to zajímavě, kdy se sejdeme?"**
→ "Děkuji za zájem. Mám obvykle volno [konkrétní dny]. Vyhovuje Vám
  přímo v Praze, nebo přes Google Meet?" Nabídni 2-3 termíny.

**"Co konkrétně byste mohla pro nás dělat?"**
→ Použij 3-tier framework. Nejprve free consult (1h walkthrough), pak
  podle zájmu pilot project. Detail v Q&A dokumentu.
