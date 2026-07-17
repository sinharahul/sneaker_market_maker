import numpy as np
import pytest

from sneaker_market_maker.simulation import GeometricBrownianMotionSimulator


def test_paths_include_initial_state_and_stay_positive() -> None:
    paths = GeometricBrownianMotionSimulator(seed=7).generate_paths(
        200, num_periods=5, num_paths=3
    )
    assert paths.shape == (6, 3)
    np.testing.assert_array_equal(paths[0], np.array([200.0, 200.0, 200.0]))
    assert np.all(paths > 0)


def test_seed_makes_first_simulation_reproducible() -> None:
    first = GeometricBrownianMotionSimulator(seed=42).generate_paths(100, 3, 2)
    second = GeometricBrownianMotionSimulator(seed=42).generate_paths(100, 3, 2)
    np.testing.assert_array_equal(first, second)


def test_zero_volatility_produces_deterministic_growth() -> None:
    paths = GeometricBrownianMotionSimulator(
        mu=0.365, sigma=0, periods_per_year=365, seed=1
    ).generate_paths(100, 2, 2)
    expected = 100 * np.exp(np.array([0.0, 0.001, 0.002]))
    np.testing.assert_allclose(paths[:, 0], expected)
    np.testing.assert_array_equal(paths[:, 0], paths[:, 1])


def test_event_shock_applies_only_from_selected_period() -> None:
    paths = np.full((4, 2), 100.0)
    shocked = GeometricBrownianMotionSimulator.apply_event_shock(
        paths, at_period=2, price_change=-0.25
    )
    np.testing.assert_array_equal(shocked[:2], paths[:2])
    np.testing.assert_array_equal(shocked[2:], np.full((2, 2), 75.0))
    np.testing.assert_array_equal(paths, np.full((4, 2), 100.0))


@pytest.mark.parametrize(
    ("price", "periods", "paths"),
    [(0, 1, 1), (100, -1, 1), (100, 1, 0)],
)
def test_invalid_generation_arguments_raise(
    price: float, periods: int, paths: int
) -> None:
    with pytest.raises(ValueError):
        GeometricBrownianMotionSimulator().generate_paths(price, periods, paths)


@pytest.mark.parametrize("price_change", [-1, -2, float("nan")])
def test_invalid_shocks_raise(price_change: float) -> None:
    with pytest.raises(ValueError):
        GeometricBrownianMotionSimulator.apply_event_shock(
            np.ones((2, 2)), at_period=1, price_change=price_change
        )
