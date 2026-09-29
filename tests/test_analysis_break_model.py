"""The change-point model (q2): the grids, the masked likelihood, and one short fit that
recovers a planted step."""

from __future__ import annotations

import numpy as np
import pytest

from src.analysis import q2_break_model as bm


def test_series_from_counts_masks_missing_season() -> None:
    y, mask = bm.series_from_counts([3, None, 5])
    assert y.tolist() == [3.0, 0.0, 5.0]
    assert mask.tolist() == [True, False, True]


def test_tau_grids() -> None:
    assert bm.tau_grid_for(10).tolist() == [3, 4, 5, 6, 7]
    pairs = bm.tau_pairs_for(12)
    assert all(b - a >= bm.TAU_MARGIN for a, b in pairs)
    assert pairs.min() >= bm.TAU_MARGIN and pairs.max() <= 12 - bm.TAU_MARGIN
    with pytest.raises(ValueError):
        bm.tau_grid_for(6)


def test_masked_season_does_not_enter_the_likelihood() -> None:
    t = 10
    grid = bm.tau_grid_for(t)
    mu = np.log(np.full((2, t), 20.0))
    delta = np.array([-0.5, -0.5])
    y, mask = bm.series_from_counts([20] * 4 + [None] + [12] * 5)
    ll = bm.tau_log_likelihoods(y, mask, mu, delta, grid)
    y2 = y.copy()
    y2[4] = 999.0  # whatever sits in the masked slot is ignored
    assert np.allclose(ll, bm.tau_log_likelihoods(y2, mask, mu, delta, grid))
    # the step placed at index 4 or 5 fits the drop at index 5 best (index 4 is unobserved)
    assert set(grid[np.argsort(-ll[0])[:2]]) == {4, 5}


def test_marginal_over_breaks_sums_to_one() -> None:
    grid = bm.tau_pairs_for(14)
    probs = np.full(len(grid), 1 / len(grid))
    for m in bm.marginal_over_breaks(grid, probs, 14):
        assert m.sum() == pytest.approx(1.0)


def test_hdi_covers_the_bulk() -> None:
    lo, hi = bm.hdi(np.random.default_rng(0).normal(0, 1, 20000), 0.9)
    assert lo == pytest.approx(-1.645, abs=0.05) and hi == pytest.approx(1.645, abs=0.05)


def test_fit_recovers_a_planted_fall() -> None:
    rng = np.random.default_rng(1)
    n = [int(v) for v in rng.poisson(60, 10)] + [int(v) for v in rng.poisson(25, 10)]
    n[3] = None
    labels = [f"{2000 + i}/{(i + 1) % 100:02d}" for i in range(20)]
    out = bm.analyse(n, labels, seed=1, n_breaks=1, draws=300, tune=300, chains=2)
    brk = out["break"]
    assert brk["steps"][0]["direction"] == "down"
    assert brk["steps"][0]["top"][0]["season"] == labels[10]
    assert brk["steps"][0]["delta_factor"]["hi"] < 0.7
