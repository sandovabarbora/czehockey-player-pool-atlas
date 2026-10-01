"""Question 2: when did it break? A change-point model on the Czech NHL series 1995/96-2025/26,
compared with Finland and Sweden.

Ported from the football atlas's `src/series_model.py` (Model 1 there): a local level with
step changes in the level.

    n_t ~ Poisson(lambda_t),  log lambda_t = mu_t + sum_k delta_k * 1[t >= tau_k]
    mu_t = mu_{t-1} + eps_t,  eps_t ~ Normal(0, sigma),  sigma ~ HalfNormal(0.2)
    delta_k ~ Normal(0, 1),   (tau_1 < tau_2) uniform over ordered pairs, each at least
    TAU_MARGIN seasons from the ends and from each other.

`n_t` is the number of the nation's players with at least the pro-rated games threshold in
the season (the same count as `q1_per_million`'s NHL series). The break seasons are
discrete, so they are marginalised out of the sampled model with a log-sum-exp over every
candidate pair, and their posterior is recovered afterwards per draw (softmax over the
candidates, averaged over draws), as in the football model.

Two differences from the football version:

- 2004/05 was not played. It stays in the time index (the level keeps walking through it)
  but contributes no likelihood (`mask`).
- No forecast and no backtest: the spec (§1) rules out predictions.

Each step is reported with its most probable seasons, its size as a factor and the
probability that it lowers the level. The report's "break" is the later step that lowers
the level (`fall`); when neither step lowers it, `fall` is null.

    python -m src.analysis.q2_break_model   -> outputs/q2_break_model.json
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
from scipy.special import gammaln

from src import config
from src.analysis import common, linking, q1_per_million

LOG = logging.getLogger(__name__)

TAU_MARGIN = 3
N_BREAKS = 2
DRAWS = 1000
TUNE = 1000
CHAINS = 4
CONTRAST = ("FIN", "SWE")
TARGET_ACCEPT = 0.99
# stage 2 of design/break-convergence-protocol.md: only for a fit that fails the rule,
# twice the tuning and draws (target_accept has no room left above 0.99)
STAGE2 = {"draws": 2000, "tune": 2000}


# =====================================================================================
# Data and grids
# =====================================================================================


def series_from_counts(n: list[int | None]) -> tuple[np.ndarray, np.ndarray]:
    """(y, mask): y as float64 with 0 where missing, mask True where observed."""
    mask = np.array([v is not None for v in n])
    y = np.array([0.0 if v is None else float(v) for v in n])
    return y, mask


def tau_grid_for(t: int, margin: int = TAU_MARGIN) -> np.ndarray:
    if t < 2 * margin + 1:
        raise ValueError(f"series too short ({t} seasons) for a margin of {margin} on each side")
    return np.arange(margin, t - margin + 1)


def tau_pairs_for(t: int, margin: int = TAU_MARGIN) -> np.ndarray:
    g = tau_grid_for(t, margin)
    pairs = [(a, b) for a in g for b in g if b - a >= margin]
    if not pairs:
        raise ValueError(f"series too short ({t} seasons) for two breaks with a margin of {margin}")
    return np.array(pairs, dtype=int)


def _step_matrix(t: int, tau_grid: np.ndarray) -> np.ndarray:
    """(T, n_candidates, n_breaks): season t is at or after the k-th break of candidate c."""
    grid = tau_grid.reshape(len(tau_grid), -1)
    return (np.arange(t)[:, None, None] >= grid[None, :, :]).astype("float64")


def _mu0_prior(y: np.ndarray, mask: np.ndarray) -> float:
    return float(np.log(max(float(y[mask].mean()), 1.0)))


# =====================================================================================
# Model
# =====================================================================================


def fit_change_point(
    y: np.ndarray,
    mask: np.ndarray,
    *,
    tau_grid: np.ndarray | None = None,
    n_breaks: int = N_BREAKS,
    draws: int = DRAWS,
    tune: int = TUNE,
    chains: int = CHAINS,
    target_accept: float = TARGET_ACCEPT,
    seed: int | None = None,
):
    """Fit the local level with marginalised change points. Returns (idata, tau_grid)."""
    import pymc as pm
    import pytensor.tensor as pt

    seed = config.RANDOM_SEED if seed is None else seed
    t = len(y)
    if tau_grid is None:
        tau_grid = tau_grid_for(t) if n_breaks == 1 else tau_pairs_for(t)
    step = _step_matrix(t, tau_grid)
    n_breaks = step.shape[2]
    log_prior_tau = -np.log(len(tau_grid))
    w = mask.astype("float64")[:, None]

    with pm.Model():
        mu0 = pm.Normal("mu0", mu=_mu0_prior(y, mask), sigma=1.0)
        sigma = pm.HalfNormal("sigma", 0.2)
        z_eps = pm.Normal("z_eps", 0.0, 1.0, shape=t - 1)
        eps = pm.Deterministic("eps", z_eps * sigma)
        mu_base = pm.Deterministic("mu_base", mu0 + pt.concatenate([[0.0], pt.cumsum(eps)]))
        if n_breaks > 1:
            delta = pm.Normal("delta", 0.0, 1.0, shape=n_breaks)
            steps = pt.tensordot(pt.as_tensor(step), delta, axes=[[2], [0]])
        else:
            delta = pm.Normal("delta", 0.0, 1.0)
            steps = delta * step[:, :, 0]
        mu_tau = mu_base[:, None] + steps
        logp = pm.logp(pm.Poisson.dist(mu=pm.math.exp(mu_tau)), y[:, None])
        logp_tau = (logp * w).sum(axis=0)
        pm.Potential("y_marginal", pm.math.logsumexp(logp_tau + log_prior_tau))
        idata = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            target_accept=target_accept,
            random_seed=seed,
            progressbar=False,
            cores=1,
        )
    return idata, tau_grid


def tau_log_likelihoods(
    y: np.ndarray, mask: np.ndarray, mu_base: np.ndarray, delta: np.ndarray, tau_grid: np.ndarray
) -> np.ndarray:
    """(n_draws, n_candidates) masked Poisson log-likelihood of y under each candidate."""
    t = mu_base.shape[1]
    step = _step_matrix(t, tau_grid)
    delta = np.asarray(delta).reshape(mu_base.shape[0], -1)
    mu_tau = mu_base[:, :, None] + np.einsum("tcb,db->dtc", step, delta)
    lam = np.exp(mu_tau)
    logp = y[None, :, None] * mu_tau - lam - gammaln(y[None, :, None] + 1.0)
    return (logp * mask[None, :, None]).sum(axis=1)


def _draws(idata, name: str) -> np.ndarray:
    v = idata.posterior[name].values
    return v.reshape(-1, *v.shape[2:])


def tau_posterior(idata, y: np.ndarray, mask: np.ndarray, tau_grid: np.ndarray) -> np.ndarray:
    mu_base = _draws(idata, "mu_base")
    delta = _draws(idata, "delta")
    ll = tau_log_likelihoods(y, mask, mu_base, delta, tau_grid)
    ll -= ll.max(axis=1, keepdims=True)
    wts = np.exp(ll)
    wts /= wts.sum(axis=1, keepdims=True)
    return wts.mean(axis=0)


def marginal_over_breaks(tau_grid: np.ndarray, probs: np.ndarray, t: int) -> list[np.ndarray]:
    grid = tau_grid.reshape(len(tau_grid), -1)
    out = []
    for k in range(grid.shape[1]):
        m = np.zeros(t)
        np.add.at(m, grid[:, k], probs)
        out.append(m)
    return out


def top_tau(
    idx: np.ndarray, probs: np.ndarray, labels: list[str], n: int = 3
) -> list[dict[str, Any]]:
    order = np.argsort(-probs, kind="stable")[:n]
    return [{"season": labels[int(idx[i])], "prob": float(probs[i])} for i in order]


def hdi(samples: np.ndarray, prob: float = 0.9) -> tuple[float, float]:
    s = np.sort(np.asarray(samples))
    n = len(s)
    n_in = max(int(np.floor(prob * n)), 1)
    n_out = n - n_in
    if n_out <= 0:
        return float(s[0]), float(s[-1])
    widths = s[n_in:] - s[:n_out]
    lo = int(np.argmin(widths))
    return float(s[lo]), float(s[lo + n_in])


def _factor(d: np.ndarray) -> dict[str, float]:
    f = np.exp(d)
    lo, hi = hdi(f, 0.9)
    return {"median": float(np.median(f)), "lo": lo, "hi": hi}


def _block(k: int, m: np.ndarray, d: np.ndarray, modal: int, labels: list[str]) -> dict[str, Any]:
    idx = np.arange(len(m))
    return {
        "order": k + 1,
        "top": top_tau(idx, m, labels),
        "delta_factor": _factor(d),
        "direction": "down" if float(np.median(d)) < 0 else "up",
        "p_down": float((d < 0).mean()),
        "modal": {"season": labels[modal], "prob": float(m[modal])},
        "marginal": [float(v) for v in m],
    }


def break_summary(
    idata, y: np.ndarray, mask: np.ndarray, tau_grid: np.ndarray, labels: list[str]
) -> dict[str, Any]:
    """The step(s): for each, the most probable seasons, the modal season, the step as a
    factor exp(delta) with its 90% HDI, and the posterior probability that it lowers the
    level. `fall` indexes the step the report calls the break: the later step that lowers
    the level, or None when neither does."""
    probs = tau_posterior(idata, y, mask, tau_grid)
    delta = _draws(idata, "delta")
    sigma = _draws(idata, "sigma").reshape(-1)
    delta = delta.reshape(len(sigma), -1)
    marg = marginal_over_breaks(tau_grid, probs, len(y))
    modal = np.atleast_1d(tau_grid[int(np.argmax(probs))])
    steps = [_block(k, m, delta[:, k], int(modal[k]), labels) for k, m in enumerate(marg)]
    falls = [k for k, b in enumerate(steps) if b["direction"] == "down"]
    grid = tau_grid.reshape(len(tau_grid), -1)
    pair_top = np.argsort(-probs, kind="stable")[:3]
    return {
        "n_breaks": len(steps),
        "steps": steps,
        "fall": falls[-1] if falls else None,
        "top_candidates": [
            {"seasons": [labels[int(v)] for v in grid[i]], "prob": float(probs[i])}
            for i in pair_top
        ],
        "sigma": float(np.median(sigma)),
    }


def fitted_level(idata, mode_tau: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Median and 90% band of the fitted level at the most probable break pair (a plotting
    aid; the break posterior itself is in `break_summary`)."""
    mu_base = _draws(idata, "mu_base")
    delta = _draws(idata, "delta").reshape(mu_base.shape[0], -1)
    taus = np.atleast_1d(np.asarray(mode_tau))
    step = (np.arange(mu_base.shape[1])[:, None] >= taus[None, :]).astype("float64")
    level = np.exp(mu_base + delta @ step.T)
    return (
        np.median(level, axis=0),
        np.quantile(level, 0.05, axis=0),
        np.quantile(level, 0.95, axis=0),
    )


def diagnostics(idata) -> dict[str, Any]:
    import arviz as az

    summ = az.summary(idata, var_names=["mu0", "sigma", "delta", "z_eps"], kind="diagnostics")
    d = {
        "max_rhat": float(summ["r_hat"].astype(float).max()),
        "min_ess_bulk": float(summ["ess_bulk"].astype(float).min()),
        "min_ess_tail": float(summ["ess_tail"].astype(float).min()),
        "n_divergences": int(np.asarray(idata["sample_stats"]["diverging"]).sum()),
    }
    # the convergence rule of design/break-convergence-protocol.md
    d["pass"] = (d["max_rhat"] <= 1.01 and d["min_ess_bulk"] >= 400 and d["min_ess_tail"] >= 400
                 and d["n_divergences"] == 0)
    return d


def analyse(n: list[int | None], labels: list[str], seed: int, **fit_kw) -> dict[str, Any]:
    y, mask = series_from_counts(n)
    t0 = time.time()
    for stage, kw in ((1, fit_kw), (2, {**fit_kw, **STAGE2})):
        idata, grid = fit_change_point(y, mask, seed=seed, **kw)
        diag = {**diagnostics(idata), "stage": stage}
        LOG.info("fit stage %d: %.1f s, %s", stage, time.time() - t0, diag)
        if diag["pass"]:
            break
    summary = break_summary(idata, y, mask, grid, labels)
    probs = tau_posterior(idata, y, mask, grid)
    mode = tuple(int(v) for v in np.atleast_1d(grid[int(np.argmax(probs))]))
    med, lo, hi = fitted_level(idata, mode)
    peak = int(np.argmax(med))
    return {
        "n": n,
        "break": summary,
        "fitted": {
            "at_pair": [labels[i] for i in mode],
            "median": med.tolist(),
            "lo": lo.tolist(),
            "hi": hi.tolist(),
            "peak": {"season": labels[peak], "level": float(med[peak])},
            "latest": {"season": labels[-1], "level": float(med[-1])},
            "latest_to_peak": float(med[-1] / med[peak]),
        },
        "diagnostics": diag,
    }


def run(lk: linking.Linked, **fit_kw) -> dict[str, Any]:
    tab = q1_per_million.counts(lk.stints, common.RUNG_1, common.FIRST_SEASON, common.LAST_SEASON)
    labels = [common.season_label(s) for s in tab.index]
    nations: dict[str, Any] = {}
    for i, code in enumerate((common.HOME, *CONTRAST)):
        n = [None if s in common.LOCKOUT_SEASONS else int(tab.at[s, code]) for s in tab.index]
        LOG.info("fitting %s", code)
        nations[code] = analyse(n, labels, seed=config.RANDOM_SEED + i, **fit_kw)
    return {
        "definitions": {
            "series": "players with at least the pro-rated games threshold (q1_per_million.nhl_series)",
            "model": "Poisson local level (Gaussian random walk on the log level) with two step "
            "changes, break seasons marginalised; ported from the football atlas series model",
            "priors": {
                "sigma": "HalfNormal(0.2)",
                "delta": "Normal(0, 1)",
                "mu0": "Normal(log mean, 1)",
                "breaks": f"uniform over ordered pairs, >= {TAU_MARGIN} seasons from the ends and apart",
            },
            "missing": "2004/05 (lockout) is in the time index with no likelihood",
            "sampler": {
                "draws": fit_kw.get("draws", DRAWS),
                "tune": fit_kw.get("tune", TUNE),
                "chains": fit_kw.get("chains", CHAINS),
                "seed": config.RANDOM_SEED,
            },
            "delta_factor": "exp(delta): the level after the step divided by the level before; median and 90% HDI",
        },
        "seasons": labels,
        "nations": nations,
    }


def main() -> None:
    out = run(linking.linked())
    path = common.write_output("q2_break_model.json", out, linking.SNAPSHOT_FILES)
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
