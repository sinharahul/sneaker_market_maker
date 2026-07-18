"""Paper Ops Strategy Mode + Inference Latency Budget controls."""

from __future__ import annotations

from dataclasses import dataclass, field

from sneaker_market_maker.paper.inference import InferenceLatencyBudget
from sneaker_market_maker.paper.strategy_mode import (
    QualificationError,
    StrategyMode,
    StrategyModeMachine,
)
from sneaker_market_maker.research.registry.service import RegistryState


@dataclass
class PaperModeControls:
    """Session-held mode, budget, and bound registry model for qualification."""

    machine: StrategyModeMachine = field(default_factory=StrategyModeMachine)
    budget: InferenceLatencyBudget = field(default_factory=InferenceLatencyBudget)
    model_id: str | None = None
    registry_state: RegistryState | None = None

    def bind_active_model(self, *, model_id: str, registry_state: RegistryState) -> None:
        self.model_id = model_id
        self.registry_state = registry_state

    def set_mode(self, mode: StrategyMode) -> tuple[bool, dict[str, object]]:
        """Apply mode when qualified. Raises QualificationError without mutation."""

        changed = self.machine.set_mode(mode, registry_state=self.registry_state)
        return changed, {
            "mode": self.machine.mode.value,
            "changed": changed,
            "registry_model_id": self.model_id,
            "registry_state": (
                None if self.registry_state is None else self.registry_state.value
            ),
        }

    def rejection_payload(self, mode: StrategyMode, error: QualificationError) -> dict[str, object]:
        return {
            "mode": mode.value,
            "code": error.code,
            "registry_state": (
                None if self.registry_state is None else self.registry_state.value
            ),
        }

    def set_budget(self, limit_ms: int) -> dict[str, object]:
        """Pin latency budget. Raises InferenceError without mutation on invalid."""

        self.budget = InferenceLatencyBudget(limit_ms=limit_ms)
        return {"limit_ms": self.budget.limit_ms}
