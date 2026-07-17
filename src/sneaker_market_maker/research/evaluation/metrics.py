"""Evaluation metrics and deterministic episode-block bootstrap intervals."""

from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections.abc import Mapping, Sequence

from sneaker_market_maker.research.ports import EpisodeEvaluation, MetricInterval

SIMULATOR_METRICS = (
    "net_return",
    "max_drawdown",
    "inventory_age",
    "stranded_inventory",
    "capital_utilization",
    "reservation_time",
    "turnover_rate",
    "cancel_rate",
    "fill_rate",
    "gate_rejection_rate",
)
RETURN_METRICS = (
    "net_return",
    "certainty_equivalent",
    "mean_return",
    "median_return",
    "var_95",
    "cvar_95",
    "worst_block",
)
REPORT_METRICS = (
    *RETURN_METRICS,
    *SIMULATOR_METRICS[1:],
    "support_coverage",
    "latency_ms",
    "numerical_failures",
    "seed_dispersion",
)


def _mean(values: Sequence[float]) -> float:
    return statistics.fmean(values)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _certainty_equivalent(values: Sequence[float]) -> float:
    exponentials = [math.exp(min(700.0, -value)) for value in values]
    return -math.log(_mean(exponentials))


def _seed_dispersion(rows: Sequence[EpisodeEvaluation]) -> float:
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(row.seed, []).append(row.metrics["net_return"])
    seed_returns = [_mean(values) for values in grouped.values()]
    return statistics.pstdev(seed_returns) if len(seed_returns) > 1 else 0.0


def _statistic(name: str, rows: Sequence[EpisodeEvaluation]) -> float:
    returns = [row.metrics["net_return"] for row in rows]
    if name in ("net_return", "mean_return"):
        return _mean(returns)
    if name == "certainty_equivalent":
        return _certainty_equivalent(returns)
    if name == "median_return":
        return statistics.median(returns)
    if name == "var_95":
        return _quantile(returns, 0.05)
    if name == "cvar_95":
        value_at_risk = _quantile(returns, 0.05)
        return _mean([value for value in returns if value <= value_at_risk])
    if name == "worst_block":
        return min(returns)
    if name == "support_coverage":
        return _mean([row.support_coverage for row in rows])
    if name == "latency_ms":
        return _mean([row.latency_ms for row in rows])
    if name == "numerical_failures":
        return float(sum(row.numerical_failures for row in rows))
    if name == "seed_dispersion":
        return _seed_dispersion(rows)
    return _mean([row.metrics[name] for row in rows])


def _validate(rows: Sequence[EpisodeEvaluation]) -> None:
    if not rows:
        raise ValueError("evaluation requires at least one episode")
    for row in rows:
        missing = set(SIMULATOR_METRICS) - row.metrics.keys()
        if missing:
            raise ValueError(f"simulator omitted metric: {sorted(missing)[0]}")


def metric_intervals(
    rows: Sequence[EpisodeEvaluation],
    *,
    confidence: float = 0.95,
    bootstrap_samples: int = 1_000,
) -> Mapping[str, MetricInterval]:
    """Aggregate outcomes with deterministic whole-episode resampling."""
    _validate(rows)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive")

    intervals: dict[str, MetricInterval] = {}
    alpha = (1.0 - confidence) / 2.0
    for name in REPORT_METRICS:
        seed = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big")
        rng = random.Random(seed)
        samples = [
            _statistic(name, [rows[rng.randrange(len(rows))] for _ in rows])
            for _ in range(bootstrap_samples)
        ]
        point = _statistic(name, rows)
        lower = min(point, _quantile(samples, alpha))
        upper = max(point, _quantile(samples, 1.0 - alpha))
        intervals[name] = MetricInterval(point, lower, upper, confidence)
    return intervals


def seed_results(
    rows: Sequence[EpisodeEvaluation],
) -> Mapping[int, Mapping[str, float]]:
    grouped: dict[int, list[EpisodeEvaluation]] = {}
    for row in rows:
        grouped.setdefault(row.seed, []).append(row)
    return {
        seed: {name: _statistic(name, seed_rows) for name in REPORT_METRICS}
        for seed, seed_rows in grouped.items()
    }


__all__ = ["REPORT_METRICS", "metric_intervals", "seed_results"]
