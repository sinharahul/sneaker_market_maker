"""Executable smoke tests with outbound network denied."""

from __future__ import annotations

import pytest

from sneaker_market_maker.research.contracts.action import ActionCategory
from sneaker_market_maker.research.registry.service import RegistryState
from tests.safety.conftest import NetworkDenied
from tests.safety.network_fixtures import (
    build_episode,
    build_reward,
    register_candidate,
    run_demo,
    run_evaluation,
    run_iql_inference,
    run_pfhedge_inference,
    shadow_recommendation,
)

pytestmark = pytest.mark.usefixtures("deny_network")


def test_episode_construction_with_network_denied() -> None:
    episode = build_episode()
    assert len(episode.decisions) == 1
    assert episode.decisions[0].source_ids == ("book", "fill")


def test_reward_builder_with_network_denied() -> None:
    assert float(build_reward()) == pytest.approx(0.01)


def test_evaluation_harness_with_network_denied() -> None:
    assert run_evaluation() >= 0.0


def test_pfhedge_inference_with_network_denied() -> None:
    assert run_pfhedge_inference() == 3


def test_iql_inference_with_network_denied() -> None:
    assert run_iql_inference() == 2


def test_registry_with_network_denied() -> None:
    assert register_candidate() is RegistryState.CANDIDATE


def test_shadow_recommendation_with_network_denied() -> None:
    final_action = shadow_recommendation()
    assert final_action.category is ActionCategory.NO_OP


def test_demo_with_network_denied() -> None:
    beats = run_demo()
    assert beats[0] == "healthy_spread"
    assert beats[-1] == "risk_gate_rejection"
    assert len(beats) == 6


def test_network_denied_fixture_blocks_socket_connect() -> None:
    import socket

    with pytest.raises(NetworkDenied, match="network disabled"):
        socket.socket().connect(("127.0.0.1", 9))
