"""Reproducible price-path simulation for holding-period stress tests."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray


class GeometricBrownianMotionSimulator:
    """Generate GBM paths using annualized drift and volatility.

    GBM is a baseline stress model, not a claim that sneaker returns are
    continuous or normally distributed. Restocks and release events should be
    tested separately as explicit shocks.
    """

    def __init__(
        self,
        mu: float = 0.0,
        sigma: float = 0.2,
        periods_per_year: int = 365,
        seed: int | None = None,
    ) -> None:
        if not math.isfinite(mu):
            raise ValueError("mu must be finite")
        if not math.isfinite(sigma) or sigma < 0:
            raise ValueError("sigma must be finite and non-negative")
        if periods_per_year <= 0:
            raise ValueError("periods_per_year must be positive")
        self.mu = mu
        self.sigma = sigma
        self.periods_per_year = periods_per_year
        self._rng = np.random.default_rng(seed)

    def generate_paths(
        self,
        initial_price: float,
        num_periods: int = 14,
        num_paths: int = 1_000,
    ) -> NDArray[np.float64]:
        if not math.isfinite(initial_price) or initial_price <= 0:
            raise ValueError("initial_price must be finite and positive")
        if num_periods < 0:
            raise ValueError("num_periods cannot be negative")
        if num_paths <= 0:
            raise ValueError("num_paths must be positive")

        dt = 1.0 / self.periods_per_year
        shocks = self._rng.standard_normal((num_periods, num_paths))
        log_returns = (
            (self.mu - 0.5 * self.sigma**2) * dt
            + self.sigma * math.sqrt(dt) * shocks
        )
        cumulative = np.vstack(
            [np.zeros((1, num_paths)), np.cumsum(log_returns, axis=0)]
        )
        return initial_price * np.exp(cumulative)

    @staticmethod
    def apply_event_shock(
        paths: NDArray[np.float64],
        *,
        at_period: int,
        price_change: float,
    ) -> NDArray[np.float64]:
        """Return a copy with a discrete restock/hype shock applied onward."""
        if paths.ndim != 2 or paths.shape[0] == 0:
            raise ValueError("paths must be a non-empty 2D array")
        if not 0 <= at_period < paths.shape[0]:
            raise ValueError("at_period is outside the path horizon")
        if not math.isfinite(price_change) or price_change <= -1:
            raise ValueError("price_change must be finite and greater than -1")

        shocked = paths.copy()
        shocked[at_period:] *= 1 + price_change
        return shocked
