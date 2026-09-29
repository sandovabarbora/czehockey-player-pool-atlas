"""Number formatting for the page text: one place, so every figure reads the same way."""

from __future__ import annotations

_ORD = {1: "st", 2: "nd", 3: "rd"}


def f1(x: float | None) -> str:
    return "–" if x is None else f"{x:.1f}"


def f2(x: float | None) -> str:
    return "–" if x is None else f"{x:.2f}"


def pct(share: float | None, digits: int = 1) -> str:
    """0.0795 -> '7.9%'."""
    return "–" if share is None else f"{share * 100:.{digits}f}%"


def pct0(share: float | None) -> str:
    return pct(share, 0)


def num(n: float | int | None) -> str:
    """1234 -> '1,234'."""
    return "–" if n is None else f"{round(n):,}"


def ordinal(n: int) -> str:
    """1 -> '1st', 12 -> '12th', 23 -> '23rd'."""
    suffix = "th" if 10 <= n % 100 <= 20 else _ORD.get(n % 10, "th")
    return f"{n}{suffix}"


def times(x: float | None) -> str:
    """0.831 -> '×0.83'."""
    return "–" if x is None else f"×{x:.2f}"


def ratio_words(x: float | None, tol: float = 0.03) -> str:
    """How a ratio to the median reads: 'above', 'below' or 'at'."""
    if x is None:
        return "not measured"
    if x > 1 + tol:
        return "above"
    if x < 1 - tol:
        return "below"
    return "at"


def mmss(seconds: float | None) -> str:
    """1239.3 -> '20:39' (minutes:seconds, as ice time is written)."""
    if seconds is None:
        return "–"
    m, s = divmod(round(seconds), 60)
    return f"{m}:{s:02d}"


def long_date(d: object) -> str:
    """date(2026, 9, 29) -> '29 September 2026'."""
    return f"{d.day} {d:%B} {d.year}"  # type: ignore[attr-defined]
