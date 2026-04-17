"""Shared statistical functions.

Single implementation used by both the viewer (live overlays) and
procedures (post-processing). Same data + same function = identical results.
"""

from __future__ import annotations

from scipy import stats as sp_stats

from plotting.elements import LinearFitResult


def linear_fit(x: list[float], y: list[float]) -> LinearFitResult:
    """Ordinary least-squares linear regression.

    Returns LinearFitResult with slope, intercept, and r_squared.
    Raises ValueError if fewer than 2 points are provided.
    """
    if len(x) < 2:
        raise ValueError(f"linear_fit requires at least 2 points, got {len(x)}")
    result = sp_stats.linregress(x, y)
    return LinearFitResult(
        slope=result.slope,
        intercept=result.intercept,
        r_squared=result.rvalue ** 2,
    )
