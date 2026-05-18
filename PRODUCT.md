# Product

## Register

product

## Users

**Primary:** Jan Morkes (analytik reprezentace ČR), Milan Hnilička (manažer A-týmu).
Both Czech, both read full report end-to-end as a single artifact, both work
in a small federation analytical setup where domain expertise dominates and
data tooling is sparse. Hnilička reads ~90s of exec summary; Morkes reads ~45min
of methodology. Audience is data-literate but not software engineers; comfortable
with terms like P/GP, percentile, multiplier, confidence band.

**Secondary:** Jiří Šlégr (GM), Martin Havlát (asistent GM), Radim Rulík (head
coach) — receive Hnilička-curated summary; rarely open the full report. Plekanec
+ Židlický (NHL veterans on coaching staff) may glance; treat them as harshest
technical/credibility audience.

**Tertiary:** Czech hockey ecosystem (analytics fans, media, agencies, other
federations) who may stumble on hockey.datasimply.eu via portfolio links.

## Product Purpose

Public-data structural benchmark of the Czech professional hockey pool that
exposes things hockey domain experts don't typically have systematically (e.g.
per-capita NHL density vs Finland/Sweden, U22 pipeline gaps by position). The
report is a **methodology showcase** that creates a consulting conversation
hook, NOT a roster recommendation or tactical analysis.

Success: Hnilička clicks through, doesn't bounce. Morkes finds the
methodology defensible enough to be interested in a peer conversation. At
minimum: leaves the audience with one quantified fact they didn't have before
(e.g. "1.38 NHL hráčů/M populace, šestí ze šesti porovnávaných zemí").

## Brand Personality

Sport-analytics seriózní: peer-to-peer, metodicky pečlivý, písemný. The
author writes from the position of a **hockey intelligence consultant** —
the emerging professional role that blends data science, video tracking,
and tactical reading of the game (closer to NHL "Hockey Ops Analyst" or
"Video Analytics Director" than to academic data scientist). This identity
should be felt across the report (operator voice, descriptive tactical reads
in cluster archetypes) but never overclaimed: tactical interpretation stays
strictly descriptive, never predictive or prescriptive.

The voice is closer to a consulting paper than a marketing landing. Calm,
authoritative through evidence (not bravado), each sentence load-bearing. The
report sounds like a senior analyst writing for another senior analyst, not
like a startup pitching enterprise software. Czech-first; English appears only
in code references and source links.

References that hit the right register:
- Stripe Atlas guides (technical authority without enterprise blandness)
- OECD economic outlooks (committed to method, generous with caveats)
- FT Visual Storytelling (data viz that respects the reader's attention)
- Pavel Barša essays in Respektu (Czech-language technical-meets-readable)

## Anti-references

Explicit don't-look-like-these patterns:

- **Generic AI/data dashboards.** Purple gradients on white/dark, glassmorphism
  cards, hero metric templates ("Big Number / Small Label / Sparkline"). The
  whole Mixpanel/Amplitude/Sisense visual vocabulary. Morkes would recognize
  this as boilerplate and discount the content instantly.
- **Marketing fluff sites.** Over-styled hero with big CTA, animated counters,
  testimonial carousels, gradient mesh backgrounds. Federation leadership
  reads this as "she's selling, not informing."
- **Powerpoint-style reports.** Centered titles on every page, bullet points
  carrying the analysis (not supporting prose), corporate stock chart styles.
  Wrong format for a deep methodology read.
- **Sport-fan aesthetics.** Team colors, flag iconography, national
  symbols, emoji, energetic typography. Federation is a professional
  institution, not a fan club.
- **Bilingual sloppiness.** Mid-paragraph language switches, untranslated
  English UI elements, English headers above Czech content. The report is
  Czech with consistent technical English vocabulary (P/GP, cluster, shrinkage)
  inline; never split-language structure.

## Design Principles

1. **Methodology over insight.** The report's value is the replicable method,
   not surprising discoveries. Layout should make the method legible (PCA
   loadings table, sensitivity rows, multiplier notes), not hide it behind
   pretty visuals. If a reader can't audit how a number was produced, the
   credibility is wasted.

2. **Peer-to-peer register.** No over-simplification, no marketing tone, no
   urgency cues (red badges, "NEW!" tags, exclamation marks). Reader is
   treated as analytical equal. Type weights and colors do the persuasion
   work; visual loudness does not.

3. **No predictions, no recommendations.** Stance discipline from the brief
   carries into design language: no leaderboards labeled "Top picks", no
   star ratings, no "recommended for selection" badges. Even color choices
   should avoid implying winners (no red-for-bad cells in cohort tables that
   could be read as a verdict — bad cells use empty cells or muted hues).

4. **Quantified uncertainty visible.** Sensitivity analysis, CI bands, ±20%
   perturbation tables, Bayesian shrinkage indicators — these are not
   afterthoughts in a Limitations section. Where they appear inline, they
   deserve typographic weight, not parenthetical demotion.

5. **Czech-first, English-for-code.** Body text, headlines, captions, table
   labels in Czech. English appears only in code blocks, repo URLs, source
   citations, and unavoidable technical terms (P/GP, cluster ID). Never
   English headers above Czech body text.

## Accessibility & Inclusion

- WCAG AA color contrast for body text + UI elements (background-foreground
  contrast ratio ≥ 4.5:1 for normal text, ≥ 3:1 for large text).
- Honor `prefers-reduced-motion` for any animation added (no animations
  required for current report; if added, respect this).
- Charts have data-table fallback or alt text describing the structural
  finding (e.g. "Heatmap showing Czech NHL pool is sixth of six
  countries per-capita, gap concentrated in U22 forwards and defensemen").
- Czech screen reader support: text is real Unicode (not rasterized images
  of Czech text). No `aria-label` shortcuts replacing readable text.
- Print stylesheet works for PDF generation (`@media print` rules in style.css
  already exist; verified via weasyprint).
