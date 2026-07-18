"""Assemble research OfflineTransitions from paper-derived drafts (R1-03)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.research.contracts.action import HybridAction
from sneaker_market_maker.research.contracts.transition import (
    BehaviorPolicy,
    OfflineTransition,
    RewardRecord,
    StepEffects,
    TrainabilityError,
)
from sneaker_market_maker.research.episodes.events import DecisionPoint
from sneaker_market_maker.research.transitions.service import (
    TransitionAssembler,
    TransitionInput,
    TransitionLineage,
)

PAPER_STATE_SCHEMA = "paper-state-v1"
PAPER_ACTION_SCHEMA = "paper-action-v1"
PAPER_BEHAVIOR = BehaviorPolicy(
    version="paper-behavior-v1",
    collection_mode="deterministic",
    categorical_propensity=None,
    active_continuous_log_density=None,
    joint_log_propensity=None,
    deterministic=True,
    support_method="paper-gate",
    support_version="paper-support-v1",
    missingness_reason="paper_deterministic_gate_final",
)


@dataclass(frozen=True)
class PaperTransitionDraft:
    current: DecisionPoint
    next: DecisionPoint
    proposed_action: HybridAction
    post_gate_action: HybridAction
    reward: RewardRecord
    effects: StepEffects
    paper_run_id: UUID
    dataset_version: str
    random_seed: int


def assemble_paper_transition(draft: PaperTransitionDraft) -> OfflineTransition:
    """Assemble one OfflineTransition; quarantines incomplete rows fail-closed."""

    if draft.current.episode_id != draft.next.episode_id:
        raise PaperError("adjacent", "paper transitions require the same episode_id")
    if draft.next.index != draft.current.index + 1:
        raise PaperError("adjacent", "paper transitions require adjacent decision indices")

    lineage = TransitionLineage(
        state_schema_version=PAPER_STATE_SCHEMA,
        action_schema_version=PAPER_ACTION_SCHEMA,
        reward_schema_version=draft.reward.version,
        dataset_version=draft.dataset_version,
        scenario_version=f"paper-run:{draft.paper_run_id}",
        simulator_version="paper-ops-v1",
        gate_policy_version="deterministic-gate-v1",
        code_revision="paper-transition-bridge-v1",
        random_seed=draft.random_seed,
        provenance_label="historical",
    )
    transition_input = TransitionInput(
        current=draft.current,
        next=draft.next,
        proposed_action=draft.proposed_action,
        post_gate_action=draft.post_gate_action,
        behavior=PAPER_BEHAVIOR,
        reward=draft.reward,
        effects=draft.effects,
        lineage=lineage,
    )
    transition = TransitionAssembler().assemble(transition_input)
    try:
        transition.validate_trainable()
    except TrainabilityError as exc:
        return replace(
            transition,
            trainability_status="quarantined",
            non_trainable_reason=str(exc),
        )
    return transition
