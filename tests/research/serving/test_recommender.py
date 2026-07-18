import json
from dataclasses import asdict, replace
from uuid import UUID

import pytest

from sneaker_market_maker.research.contracts.action import (
    ActionBounds,
    ActionCategory,
    ActionMask,
    HybridAction,
    RawHybridAction,
)
from sneaker_market_maker.research.registry.service import RegistryState
from sneaker_market_maker.research.serving.recommender import (
    GateResult,
    RecommendationRecord,
    RecommendationRequest,
    RecommendationService,
)

DETERMINISTIC = HybridAction(ActionCategory.NO_OP, 0.0, 0, 0)
RAW_QUOTE = RawHybridAction(ActionCategory.QUOTE, 1.4, -4.6, 2.6)
BOUNDS = ActionBounds(-3, 3, -4, 2)
MASK = ActionMask(True, True, True)
GATE_NAMES = ("schema", "fees", "capital", "liquidity", "inventory", "exposure")


class Gates:
    def __init__(self, result: GateResult | None = None, clock: "Clock | None" = None) -> None:
        self.result = result or GateResult(True, (("risk", True),))
        self.clock = clock
        self.calls: list[tuple[HybridAction, object]] = []

    def evaluate(self, action: HybridAction, risk_state: object) -> GateResult:
        self.calls.append((action, risk_state))
        if self.clock is not None:
            self.clock.value += 1.0
        return self.result


class Store:
    def __init__(self) -> None:
        self.records: list[RecommendationRecord] = []

    def save(self, record: RecommendationRecord) -> None:
        self.records.append(record)


class Clock:
    value = 0.0

    def __call__(self) -> float:
        return self.value


def request(**overrides: object) -> RecommendationRequest:
    values: dict[str, object] = {
        "request_id": UUID(int=20),
        "deterministic_action": DETERMINISTIC,
        "pfhedge_action": RAW_QUOTE,
        "iql_action": RAW_QUOTE,
        "selected_model_action": RAW_QUOTE,
        "bounds": BOUNDS,
        "mask": MASK,
        "risk_state": {"deterministic_approved": True},
        "registry_state": RegistryState.SHADOW,
        "support_ok": True,
        "healthy": True,
        "drifted": False,
        "lineage_compatible": True,
    }
    values.update(overrides)
    return RecommendationRequest(**values)  # type: ignore[arg-type]


def service(
    gates: Gates | None = None,
    store: Store | None = None,
    *,
    clock: Clock | None = None,
    timeout_seconds: float = 0.5,
) -> RecommendationService:
    return RecommendationService(
        gates or Gates(),
        store or Store(),
        clock=clock or Clock(),
        timeout_seconds=timeout_seconds,
    )


def test_shadow_canonicalizes_rounds_clamps_but_never_changes_final_action() -> None:
    gates = Gates()

    record = service(gates).recommend(request())

    assert record.request_id == UUID(int=20)
    assert record.canonical_action == HybridAction(ActionCategory.QUOTE, 1.0, -3, 2)
    assert gates.calls == [(record.canonical_action, {"deterministic_approved": True})]
    assert record.final_action == DETERMINISTIC
    assert record.fallback_reason is None


@pytest.mark.parametrize(
    ("raw_action", "mask", "message"),
    [
        (
            RawHybridAction("QUOTE", 0.5, 0.0, 0.0),  # type: ignore[arg-type]
            MASK,
            "schema",
        ),
        (RawHybridAction(ActionCategory.QUOTE, float("nan"), 0.0, 0.0), MASK, "finite"),
        (RAW_QUOTE, ActionMask(True, False, True), "masked"),
    ],
)
def test_invalid_model_output_fails_closed(
    raw_action: RawHybridAction,
    mask: ActionMask,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        service().recommend(request(selected_model_action=raw_action, mask=mask))


def test_inactive_action_is_canonicalized_to_neutral_values() -> None:
    raw = RawHybridAction(ActionCategory.CANCEL, float("nan"), float("inf"), 4.0)
    record = service().recommend(request(selected_model_action=raw))
    assert record.canonical_action == HybridAction(ActionCategory.CANCEL, 0.0, 0, 0)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"support_ok": False}, "weak_support"),
        ({"drifted": True}, "drift"),
        ({"lineage_compatible": False}, "incompatible_lineage"),
        ({"selected_model_action": None}, "missing_artifact"),
        ({"healthy": False}, "unhealthy_service"),
    ],
)
def test_runtime_preconditions_fail_closed_with_stable_reason(
    overrides: dict[str, object],
    reason: str,
) -> None:
    item = request(registry_state=RegistryState.ADVISORY_APPROVED, **overrides)
    record = service().recommend(item)
    assert record.final_action == DETERMINISTIC
    assert record.fallback_reason == reason


def test_gate_timeout_uses_injected_clock_and_fails_closed() -> None:
    clock = Clock()
    gates = Gates(clock=clock)
    record = service(gates, clock=clock).recommend(
        request(registry_state=RegistryState.ADVISORY_APPROVED)
    )
    assert record.final_action == DETERMINISTIC
    assert record.gate_results[-1] == ("timeout", False)
    assert record.fallback_reason == "timeout"


def test_gate_timeout_fails_closed_at_exact_deadline() -> None:
    clock = Clock()
    gates = Gates(clock=clock)
    record = service(gates, clock=clock, timeout_seconds=1.0).recommend(
        request(registry_state=RegistryState.ADVISORY_APPROVED)
    )
    assert record.final_action == DETERMINISTIC
    assert record.gate_results[-1] == ("timeout", False)
    assert record.fallback_reason == "timeout"


@pytest.mark.parametrize("failed_gate", GATE_NAMES)
def test_each_gate_failure_has_a_stable_reason(failed_gate: str) -> None:
    results = tuple((name, name != failed_gate) for name in GATE_NAMES)
    gates = Gates(GateResult(False, results))
    record = service(gates).recommend(request(registry_state=RegistryState.ADVISORY_APPROVED))
    assert record.final_action == DETERMINISTIC
    assert record.gate_results == results
    assert record.fallback_reason == f"gate_failed:{failed_gate}"


def test_advisory_cannot_reverse_deterministic_rejection() -> None:
    gates = Gates(GateResult(False, (("deterministic_approved", False),)))
    record = service(gates).recommend(
        request(
            registry_state=RegistryState.ADVISORY_APPROVED,
            risk_state={"deterministic_approved": False},
        )
    )
    assert record.final_action == DETERMINISTIC
    assert record.fallback_reason == "gate_failed:deterministic_approved"


def test_approved_advisory_uses_candidate_only_when_all_checks_pass() -> None:
    record = service().recommend(request(registry_state=RegistryState.ADVISORY_APPROVED))
    assert record.final_action == record.canonical_action
    assert record.fallback_reason is None


def _paper_bytes(actions: list[HybridAction]) -> bytes:
    commands = [
        {
            **asdict(action),
            "category": action.category.value,
        }
        for action in actions
    ]
    return json.dumps(commands, sort_keys=True, separators=(",", ":")).encode()


def test_shadow_persists_comparisons_without_changing_full_paper_command_stream() -> None:
    deterministic_commands = [
        DETERMINISTIC,
        HybridAction(ActionCategory.CANCEL, 0.0, 0, 0),
    ]
    shadow_requests = [
        request(deterministic_action=deterministic_commands[0]),
        replace(
            request(),
            request_id=UUID(int=21),
            deterministic_action=deterministic_commands[1],
        ),
    ]
    shadow_store = Store()
    shadow_service = service(store=shadow_store)
    shadow_records = [shadow_service.recommend(item) for item in shadow_requests]

    deterministic_bytes = _paper_bytes(deterministic_commands)
    shadow_bytes = _paper_bytes([record.final_action for record in shadow_records])
    assert deterministic_bytes == shadow_bytes
    assert len(shadow_store.records) == 2
    assert all(record.canonical_action is not None for record in shadow_store.records)
    assert all(record.pfhedge_action == RAW_QUOTE for record in shadow_store.records)
    assert all(record.iql_action == RAW_QUOTE for record in shadow_store.records)
