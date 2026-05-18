# První hovor s Morkesem — příprava

Pokud první meeting přijde, Morkes je peer-level analytik. Bude tě testovat
technicky během prvních 10 minut. Pokud projdeš, pravděpodobně zavolá Hniličku
nebo přidá Šlégra/Havláta na další meeting. Pokud neprojdeš, je to konec.

**Cíl prvního hovoru:** Ne prodávat. Demonstrovat technickou kompetenci +
porozumět jejich workflow.

**Délka:** Plánuj na 30-45 min. Pokud Morkes prodlouží na 60+, je to dobrý
signál (zajímá ho hlubší diskuze).

---

## Pravděpodobné Morkesovy otázky + tvé odpovědi

### Technické

**Q: "Proč zrovna tyhle ligové násobičky? Odkud máš ty hodnoty?"**

> Subjektivní aproximace inspirované publicly available NHL-equivalency
> analýzami (Sznajder, hockeyviz.com). Vědomě je v reportu označuju jako
> subjektivní. Klíčové je že sensitivity analysis ukazuje že top-10 ranking
> je vůči ±20% perturbacím robustní — žádný scénář nezpůsobí churn větší
> než 1 hráč. NHL elita (Pastrňák, Nečas, Zacha, Hertl) je v top čtyřce
> ve všech sedmi scénářích včetně všechny -20% / všechny +20%. Multipliery
> jsou tedy v praxi spíš kalibrační než určující.

**Q: "Co s xG? Proč ne pro EU hráče?"**

> xG modely jsou veřejně dostupné jen pro NHL (přes MoneyPuck). Pro Liigu,
> Extraligu, Swiss NL veřejný xG model neexistuje. Místo imputace (která
> by vytvořila phantom signal — to jsem rejectla už ve fázi designu) je
> xG vyloučeno z cross-league projekce, ale máte ho jako enrichment tooltip
> pro NHL hráče v technické sekci. Kdybyste měli interně agreement s nějakým
> tracking providerem pro EU ligy, tohle by se mohlo přepnout.

**Q: "Jak řešíte brankáře?"**

> Brankáři jsou vyloučeni z hlavní mapy, mají vlastní mini-sekci s šesti
> position-specific metrikami (GP, SV%, SV% short-handed, GSAx, věk, liga).
> Brankářská analytika je extrémně kontext-závislá (kvalita defenzivy před
> brankářem, schéma hry, ledové podmínky). Veřejná data tady poskytují
> spíš orientační hodnoty než plnohodnotnou projekci. V této verzi reportu
> je goalie sekce minimální — můžete rozšířit pokud byste měli interní
> tracking dat.

**Q: "Proč chybí AHL? Tam je nezanedbatelný počet českých prospektů."**

> Záměrný scope-cut pro v1. AHL skater coverage je technicky řešitelná
> (theahl.com je SSR'd), ale chybí mi advanced metriky srovnatelné s tím
> co MoneyPuck poskytuje pro NHL. V další iteraci dáme AHL jako vlastní
> ligu s vlastním multiplierem. Pro tuhle verzi je v Limitations sekci
> jako known gap.

**Q: "Proč není SHL nebo Swiss NL?"**

> Oba weby jsou plně JavaScript-rendered SPA bez veřejně přístupného API
> a se silnou bot-detekcí na Cloudflare úrovni. Pokusila jsem se přes
> Playwright headless browser, ale data se nahrává jen po deeper UI
> interakcích (dropdowny, taby) které nelze automatizovat robustně.
> Implementační čas vs return = nevýhodný pro v1. Máme od vás listy
> aktivních českých hráčů v SHL/NL? Pokud ano, manuální seed list + per-player
> scraping by mohl fungovat — jednodušší než scrapovat celé ligy.

**Q: "Jak řešíš mid-season trades?"**

> Pro NHL hráče aggregujeme stats přes všechny týmy v sezoně (Nečas
> CAR+COL → spočítáno jako jeden hráč). Mid-season trade napříč ligami
> (např. Mazura Brno → Kuopio = Extraliga → Liiga) crosswalk dedupuje
> přes (name + birthdate) match. Trade napříč ligami zachycen jako
> jeden kanonický hráč s rows v obou ligách. V trajektoriální analýze
> bereme aggregát.

**Q: "Bayesovský shrinkage — proč K=10?"**

> Hyperparametr odvozený empiricky. K=10 znamená že hráč s GP=10 má
> 50/50 mix svých dat a cohort medianu. S NHL hráči (typicky 60+ GP) je
> shrinkage minimální (~10% pull). S EU juniory (3-5 GP) je dominantní
> cohort prior (~70% pull). Hyperparametr je možné sweepnout — vyšší K
> = více konzervativní (silnější regression to mean), nižší K = více
> respektuje malé vzorky. K=10 je defaultní volba; testovali jsme
> K∈{5,10,20} a top-10 ranking byl stabilní.

**Q: "Cluster count = 4 pro útočníky? Brief měl 6."**

> Brief byl můj draft. Při implementaci jsem K vybírala přes silhouette
> score na K∈{4..8}. Best K = 4 (silhouette 0.307). K=6 dostalo nižší
> skóre (0.291). Vzhledem k tomu že máme 4D feature vektor po dropnutí
> shots a xG, K=4 dává čistší separaci. K=5/6/7/8 produkují buď
> sub-clusters s podobnou centroidu nebo singleton clusters. Když budete
> mít interně bohatší feature vektor (zone entries, defensive shifts,
> atd.), vyšší K bude pravděpodobně lépe oddělitelné.

### Strategické

**Q: "Co byste pro nás konkrétně dělala?"**

> Tři vrstvy spolupráce, podle vašeho zájmu:
>
> **1. Volný walkthrough metodologie** (1h, zdarma) — projdu pipeline,
>    odpovídám na technické otázky, identifikujeme váš workflow + bolesti.
>    Žádný závazek.
>
> **2. Pilotní projekt** (2-4 týdny, fixed price) — integrujeme váš interní
>    scouting / kondiční / video tracking data s touto pipeline. Vznikne
>    web-deployed dashboard pro long-term cohort tracking přes 4-letý cyklus.
>    Konkrétní příklady:
>    - "Pre-camp cohort baseline" — pro každý nominační kemp comparison
>      hráče vs jeho vlastní baseline + cohort median
>    - "Cross-league player tracking" — integrate váš roster history se
>      současnou pipeline, výsledek = dashboard "kde je Czech pool po
>      věkových skupinách"
>    - "Internal scouting unification" — vezmu scouting Excely + kondiční
>      testy + Atlas → jednotný pipeline s privacy ochranami (sloupcové
>      prefixy `internal_*`)
>
> **3. Průběžná spolupráce** (10-20 h/měsíc, retainer) — maintenance +
>    nová rozšíření. Phase 2 (Opponent Style Atlas — mapa stylů soupeřů)
>    je natural follow-up zde.

**Q: "Pracujete na full-time? Můžete vůbec nabídnout konzistentní hodiny?"**

> Pracuju jako Data Engineer pro Alma Career. Tuhle práci dělám ve volném
> čase. Pro pilot project umím vyhradit konkrétní dvoutýdenní okno s
> fixed price; pro průběžnou spolupráci 10-20 h/měsíc po práci a o
> víkendech. Pokud byste potřebovali víc, museli bychom se bavit jinak.

**Q: "Máte nějaké reference v hokeji?"**

> Tohle je můj první hokejový projekt. Reference mám v adjacent domain —
> Sparta European Context analysis (basketbal), strategický mapping
> Czech tech ecosystem. Vše veřejně na GitHubu. Ale honest: hokej je
> nový. Proto první nabídka je free walkthrough — nejde mi o smlouvu
> na hodiny ale o demonstraci hodnoty.

**Q: "Kolik to bude stát?"**

> Free consult zdarma. Pilot project — záleží na scope. Typicky 40-80 h
> práce, fixed price podle dohody. Sazba je niž šeš tržní pro federation
> non-profit. Můžu nabídnout splátkový pricing pokud rozpočet je
> omezený. Pro průběžnou spolupráci by to bylo retainer 1k-3k Kč/měsíc
> (záleží na hours). Specific čísla po pochopení scope.

### Záludné

**Q: "Tohle vypadá AI-generated. Děláš to sama?"**

> Pipeline je můj kód, methodology je moje rozhodnutí. Použila jsem
> AI nástroje (Claude Code) jako pair programmer — stejně jako bych
> použila Stack Overflow nebo IDE autocomplete. Všechno je veřejně na
> GitHubu (commits, tests, decisions doc), můžete to projít. Žádné
> AI-generated metodologické rozhodnutí; to vždycky moje (např. odmítnutí
> xG imputation byl výsledek peer-review konverzce, ne suggestion modelu).

**Q: "Můžu vás vyzkoušet — co kdybyste nám udělala A/B test bez kontextu?"**

> Můžu to udělat, ale upřímně — bez kontextu (vaše workflow, vaše data,
> váš research question) bych pravděpodobně postavila něco z mého úhlu
> pohledu, ne vašeho. Lepší formát je: zadejte konkrétní otázku co vás
> reálně zajímá, dejte mi 1-2 týdny + access k veřejným zdrojům, a já
> Vám vrátím odpověď + co bych potřebovala k lepší odpovědi (typicky
> internal data).

**Q: "Co když uděláš špatnou prognózu nebo doporučení?"**

> Ten risk si neuriňujem protože v reportu nejsou predikce ani doporučení
> hráčů. Jsou tam pozorování ("hráči v cluster X se obvykle...") a popisné
> trajektorie ("Hertl má klesající Δ"). Žádný hráč není označen jako
> "měl by být v reprezentaci" nebo "měl by být vyřazen". Toto je doménou
> Vás a trenérského štábu — moje data Vám maximálně dají hypotézu pro
> vnitřní validaci. Pokud někdo požádá o predikci, řeknu že to není
> co tahle metodologie nabízí.

---

## Co se ZEPTAT Morkese (priority order)

Nejdřív poslouchat, pak ptát. Cíl: pochopit jejich svět, ne prodávat tvoje.

1. **"Jaké data máte dnes nejvíc nepřístupné? PDF? Excel? Vlastní DB?
   Vendor SaaS?"** — odhalí kde leží jejich data engineering bolest.

2. **"Kdo dnes dělá pre-camp cohort comparisons? Jakou tooling používá?"** —
   identifies the workflow gap.

3. **"Co by Vám osobně pomohlo nejvíc kdyby existovalo?"** — Morkesova
   konkrétní bolest, ne strategická vize.

4. **"Máte interně cross-league tracking pro česky způsobilé hráče?
   Jak ho dnes řešíte?"** — checks if my Atlas is novel or duplicates
   their internal tools.

5. **"Jaký je váš research-question příští 6 měsíců? Nějaký specific
   topic kde byste potřebovali víc dat?"** — finds the pilot project shape.

6. **"S kým spolupracujete na video analytics? Tracking?"** — landscape
   check; možná i kontakty pro budoucí projekty.

7. **"Jaké jsou Vaše plány pro ZOH 2030 cyklus z hlediska analytics
   infrastructure?"** — long-term horizon question; signal pro
   potential retainer.

---

## Co NEdělat během prvního hovoru

- **Nedrtit:** Pokud Morkes položí krátkou otázku, dej krátkou odpověď.
  Špatný signál = mluvíš 5 min za sebou bez pauzy.
- **Nepředstírat hokejovou expertízu:** Nikdy "myslím že by Pastrňák měl..."
  nebo "rozumím že Rulík chce...". Tvoje role = methodology.
- **Neporovnávat se s pražákem:** Morkes je Tvůj peer ne podřízený. Vyhni
  se "tady jsem chytřejší než vy" tone.
- **Nepředkládat pricing pokud se nezeptá:** Free consult je první krok.
  Pricing teprve po identifikaci scope.
- **Neslíbit timeline kterou neumíš dodržet:** "Týden" = víkend + 5 večerů.
  Realisticky 2 týdny minimum pro cokoli nontriviální.
- **Nesdílet wishlist o NHL kariéře:** Tohle je business call, ne fanouškovský
  setkání. Pokud Morkes začne hovor o vlastní hokejové vášni, polož krátkou
  odpověď a vrať se k tématu.

---

## Po hovoru

Bez ohledu na výsledek:

1. **Do 24h pošli thank-you email** s 2-3 konkrétními take-aways z hovoru.
   Demonstruje že jsi poslouchala.
2. **Pokud byl pozitivní:** navrhni konkrétní follow-up termín do týdne
   (pilot project scope discussion, technical deep-dive, atd.).
3. **Pokud byl neutrální:** "Děkuji za čas. Repo zůstává veřejné. Pokud
   se situace změní, jsem k dispozici." Žádný push.
4. **Pokud byl negativní:** Lekce. Co bys udělala jinak? Zapiš do
   `decisions.md` pro příští pokus.
