# Q2 break model: convergence protocol (1 October 2026)

Written and committed before any new estimate was looked at. It applies to this atlas the rule used in the football
atlas (`czefootball-player-pool-atlas/design/edition-refit-protocol.md`).

**Why.** The published fits run at 4 chains, 1000 tuning steps, 1000 draws and target_accept 0.99. Finland's fit has
one divergent transition. The diagnostics leave out `z_eps`, the non-centred innovations of the random walk.

**Model.** Unchanged: `q2_break_model.fit_change_point`, with the same priors, seeds and break grid.

**Sampler.**

- **Stage 1** (every fit): the published settings.
- **Stage 2** (only a fit that fails the rule in stage 1): 2000 tuning steps and 2000 draws, everything else the
  same. target_accept is already 0.99, so the step size has no room left; nothing else is changed to reach
  convergence.

**Convergence rule.** Checked on `mu0`, `sigma`, `delta` and `z_eps`. All of the following must hold:

- max R-hat ≤ 1.01;
- bulk and tail ESS ≥ 400;
- zero divergent transitions.

**Reporting.**

- `q2_break_model.json` records each nation's diagnostics, the stage used, and pass or fail.
- The Q2 page states the rule and gives each nation's diagnostics.
- A nation whose fit still fails after stage 2 has no dated steps on any page or chart, and the page says so.
- If the Czech fit failed, the summary, the facts strip and the Q2 page would date no Czech step either.
- Every dated step that changes is logged in the change log as old → new.
