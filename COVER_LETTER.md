# Cover letter — Hnilička

**Předmět:** Strukturální benchmark českého fondu vs Finsko / Švédsko — návrh metodiky pro 4letý cyklus

**Komu:** milan.hnilicka@cesky-hokej.cz (ověř adresu na cesky-hokej.cz)
**CC:** žádné v prvním mailu (Morkesovi posíláme samostatný peer email 24h později)
**Kdy poslat:** Úterý nebo středa, 9:00-11:00 Prague time

---

## Verze A — vede s headline číslem (doporučená)

Vážený pane Hniličko,

jmenuji se Barbora Šandová, pracuji jako Data & Cloud Engineer ve společnosti
Alma Career. Posledních několik týdnů jsem ve volném čase vybudovala otevřenou
analytickou pipeline pro mapování a benchmarking českého hokejového fondu.

V příloženém reportu najdete strukturální srovnání **české NHL kohorty vs Finsko,
Švédsko, Slovensko, Kanada a USA** napříč věkovými skupinami. Tři čísla, která
v jednom místě (po mé znalosti) nemáte:

- **Per-capita hustota NHL hráčů:** ČR 1.38 / milion. Slovensko 1.67. Finsko 6.07.
  Švédsko 7.17. Po normalizaci na populaci je český fond v NHL šestý ze šesti
  porovnávaných zemí — za Slovenskem, čtyřikrát méně hustý než Finsko.

- **Junior pipeline (U22 forwards v NHL):** ČR 1 hráč (Kulich). Finsko 3.
  Švédsko 7. Kanada 22. Cohort budoucích reprezentantů je strukturálně tenký.

- **Defenzivní pipeline napříč všemi věkovými skupinami:** ČR 4 obránci v NHL
  celkem (z toho U22: 0, 23-25: 1, 26-29: 1, 30+: 1). Finsko: 14. Švédsko: 30.

Současný 26-29 cohort útočníků (Pastrňák, Nečas, Zacha, Hertl) drží mediánovou
produkci 1.06 P/GP — to je sám o sobě světová špička. Jen je 4 hráče hluboký.
Jakákoli jediná absence v tomto cohortu otevírá gap, který za ním nikdo
strukturálně nestojí.

**Toto není výběrové doporučení.** Cílem je dodat metodologii, kterou interní
tým může aplikovat na vaši rozšířenou datovou základnu (videoanalytika,
kondiční testy, scoutingové zprávy). Vidím tři možné vrstvy spolupráce:

1. **Bezplatná konzultace** + walkthrough metodiky (cca 1h, žádný závazek)
2. **Pilotní projekt** — aplikace přístupu na vaše interní data, výsledek je
   cohort dashboard pro long-term plánování v rámci 4letého cyklu
3. **Průběžná spolupráce** — measurement infrastructure pro fond reprezentace,
   včetně rozšíření o AHL, junior leagues, a peer-country tracking

Veřejný report: **https://hockey.datasimply.eu**
Repozitář: github.com/sandovabarbora/czehockey-player-pool-atlas
Plná metodika včetně sensitivity analysis a omezení dat: viz Limitations sekce reportu.

Pokud by Vás nebo pana Morkese metodika zaujala, ráda se ozvu. Děkuji za Váš čas
a přeji reprezentaci úspěšný start nového cyklu.

S úctou,
Barbora Šandová
Data & Cloud Engineer, Alma Career
+420 [telefon]
barbora@datasimply.eu
linkedin.com/in/barborasandova

---

## Verze B — kratší (pro mail-fatigued čtenáře)

Vážený pane Hniličko,

jmenuji se Barbora Šandová, Data & Cloud Engineer (Alma Career). V přiloženém
reportu najdete strukturální benchmark českého NHL fondu vs Finsko, Švédsko a
další peer-země.

**Klíčové číslo:** Česká per-capita hustota NHL hráčů je 1.38/milion — proti
Finsku (6.07), Švédsku (7.17), a dokonce Slovensku (1.67). Detailní cohort
breakdown ukazuje že problém není v top tieru (Pastrňák+Nečas+Zacha+Hertl drží
1.06 P/GP medián v 26-29 cohorte) ale v pipeline pod ně — U22 forwards: 1 hráč,
defensemen U22: 0.

Toto není výběrové doporučení; je to měřitelný strukturální stav, který interní
tým může používat pro plánování v rámci 4letého cyklu. Vidím tři vrstvy spolupráce:
volný walkthrough, pilotní projekt na vaše interní data, nebo průběžná
infrastructure spolupráce.

Repo + report: **https://hockey.datasimply.eu**
PDF reportu přiloženo (9 stran, česky).

Děkuji za Váš čas.

S úctou,
Barbora Šandová
barbora@datasimply.eu · +420 [telefon] · linkedin.com/in/barborasandova

---

## Peer email Morkesovi (24h po Hniličkovi)

**Předmět:** Methodology peer-check — strukturální benchmark Czech NHL pool vs peers

Zdravím Jane,

paralelně k mailu na pana Hniličku Vám posílám peer-level zkrácenou verzi.

Postavila jsem open pipeline integrující 5 zdrojů (NHL API, MoneyPuck, Liiga,
hokej.cz, IIHF přes Wikipedia) přes manuální crosswalk + Bayesovský shrinkage.
Hlavní deliverable, který by Vás možná zajímal nejvíc: **mezinárodní cohort
benchmark českého NHL fondu** vs FIN/SWE/SVK/CAN/USA, agregovaný po věkových
skupinách a pozicích. Headline: ČR 1.38 NHL hráčů per milion, Finsko 6.07.

Plus integrovaný Atlas 385 Czech-eligible hráčů, trajectory analýza, ±20%
sensitivity na ligové násobičky, a Bayesian shrinkage na malé vzorky.

Methodology, kód, parquets: https://github.com/sandovabarbora/czehockey-player-pool-atlas
Hlavní benchmark report: hockey.datasimply.eu/intl_cohort_summary.md

Kdyby měla peer perspective: jakou další zemi/věkovou skupinu byste přidal? Co
byste viděl jako nejvážnější metodologickou slabinu?

Hezký den,
Barbora

---

## Důležité notes před odesláním

- [ ] **Aktualizovat report HTML** s sekcí International Cohort Benchmark
  (`make pages` po update render.py — chci to mít v reportu, ne jen jako
  separátní markdown).
- [ ] **Veřejně publikovat repo** — již hotovo na github.com/sandovabarbora/czehockey-player-pool-atlas
- [ ] **Hostuj report** na hockey.datasimply.eu — již setup, jen čeká na HTTPS cert
- [ ] **Ověř e-mail Hniličky** — buď přes web reprezentace nebo LinkedIn
- [ ] **Telefonní číslo** doplň před odesláním (placeholder `[telefon]`)
- [ ] **Žádný follow-up před 14 dny.** Den 14: krátký zdvořilý reminder.
  Den 28: stop. Žádný 3. mail.
- [ ] **Neposílej současně klubům** (Sparta, Slavia, Třinec). Federační vztahy
  jsou ochranné, paralelní outreach = výpadek důvěry.

---

## Co dělat když odpovědí "není zájem" / "děkujeme"

Repo zůstává veřejné. Hodnota tvého úsilí nezávisí na tom jestli tato konkrétní
Federace odpoví. International cohort benchmark je publikovatelná analýza pro:

- LinkedIn / X post (data story o stavu českého hokeje)
- Hokejové média (Hokej.cz, iSport — datově-vědecký pohled na Czech NHL pool)
- Slovenský hokejový svaz (stejný strukturální problém, menší ego)
- Mezinárodní oslovení (Fin/Swede federations mohou ocenit metodiku)

Cover letter je adresován Hniličkovi protože je to nejnáročnější publikum.
Pokud neodpoví, není to signál že práce je špatná — je to signál že tato
konkrétní vrstva federace má jiné priority.

---

## Připravená reakce na možné odpovědi

**"Děkuji, není zájem."**
→ "Děkuji za odpověď. Repo zůstává veřejné, pokud by se situace změnila."
   Nic víc. Move on with grace.

**"Tato čísla jsou ale známá / nepřekvapivá."**
→ "Souhlasím že obecný směr je znám. Konkrétní cohort breakdown a per-capita
   normalizace mi přijde jako agregace která ve specifické formě zatím nikde
   nebyla publikována. Pokud máte interní materiály které jdou hlouběji, rád
   bych viděl porovnání metodik."

**"Dejte to Morkesovi přímo."**
→ "Děkuji za přeposlání. Janovi posílám detaily zvlášť." A pošli peer email
  okamžitě (ne 24h později — Hnilička už dal svolení).

**"Zní to zajímavě, kdy se sejdeme?"**
→ "Děkuji za zájem. Mám obvykle volno [konkrétní dny]. Vyhovuje Vám přímo
  v Praze, nebo přes Google Meet?" Nabídni 2-3 termíny.

**"Co konkrétně byste mohla pro nás dělat?"**
→ Použij 3-tier framework v cover letteru. Nejprve free consult (1h walkthrough),
   pak podle zájmu pilot project. Detail v FIRST_CALL_PREP.md.
