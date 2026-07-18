"""Strategy Mode quote authorship: advisory nudge and IQL-primary intents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sneaker_market_maker.paper.action_translator import (
    ActionTranslator,
    TranslatedKind,
    TranslatorError,
)
from sneaker_market_maker.paper.gate import GateDecision
from sneaker_market_maker.paper.inference import InferenceOutcome
from sneaker_market_maker.paper.intents import QuoteIntent
from sneaker_market_maker.paper.quote_engine import QuoteEngine
from sneaker_market_maker.paper.replay.loader import MarketReplayEvent
from sneaker_market_maker.paper.strategy_mode import StrategyMode
from sneaker_market_maker.research.contracts.action import ActionBounds, HybridAction

DEFAULT_TRANSLATOR = ActionTranslator(version="action-translator-v1", tick_size=Decimal("1.00"))
DEFAULT_BOUNDS = ActionBounds(bid_low=-5, bid_high=5, ask_low=-5, ask_high=5)


@dataclass(frozen=True)
class ModeTickResult:
    intents: tuple[tuple[QuoteIntent, GateDecision], ...]
    fallback_reason: str | None
    pause_for_iql: bool
    last_action_summary: dict[str, Any] | None


def _action_summary(action: HybridAction | None, *, source: str) -> dict[str, Any] | None:
    if action is None:
        return None
    return {
        "source": source,
        "category": action.category.value,
        "allocation": action.allocation,
        "bid_offset_ticks": action.bid_offset_ticks,
        "ask_offset_ticks": action.ask_offset_ticks,
    }


def apply_strategy_mode(
    *,
    mode: StrategyMode,
    quotes: QuoteEngine,
    event: MarketReplayEvent,
    simulation_time: datetime,
    inference: InferenceOutcome | None,
    translator: ActionTranslator = DEFAULT_TRANSLATOR,
    bounds: ActionBounds = DEFAULT_BOUNDS,
) -> ModeTickResult:
    """Map mode + inference into gated Quote Intents."""

    if mode is StrategyMode.DETERMINISTIC or inference is None:
        intents = quotes.on_market(event, simulation_time=simulation_time)
        return ModeTickResult(intents, None, False, None)

    if not inference.valid or inference.action is None:
        reason = inference.reason or "invalid_inference"
        if mode is StrategyMode.ADVISORY:
            intents = quotes.on_market(event, simulation_time=simulation_time)
            return ModeTickResult(intents, reason, False, None)
        return ModeTickResult((), reason, True, None)

    action = inference.action
    summary = _action_summary(action, source=mode.value)

    try:
        if mode is StrategyMode.ADVISORY:
            return _advisory(
                quotes=quotes,
                event=event,
                simulation_time=simulation_time,
                action=action,
                translator=translator,
                bounds=bounds,
                summary=summary,
            )
        return _iql_primary(
            quotes=quotes,
            event=event,
            simulation_time=simulation_time,
            action=action,
            translator=translator,
            bounds=bounds,
            summary=summary,
        )
    except TranslatorError as error:
        if mode is StrategyMode.ADVISORY:
            intents = quotes.on_market(event, simulation_time=simulation_time)
            return ModeTickResult(intents, error.code, False, summary)
        return ModeTickResult((), error.code, True, summary)


def _advisory(
    *,
    quotes: QuoteEngine,
    event: MarketReplayEvent,
    simulation_time: datetime,
    action: HybridAction,
    translator: ActionTranslator,
    bounds: ActionBounds,
    summary: dict[str, Any] | None,
) -> ModeTickResult:
    base_bid, base_ask = quotes.deterministic_desired(event)
    translated = translator.translate(
        action,
        highest_bid=base_bid,
        lowest_ask=base_ask if base_ask is not None else event.lowest_ask,
        bounds=bounds,
    )
    if translated.kind is TranslatedKind.NO_OP:
        intents = quotes.on_market(event, simulation_time=simulation_time)
        return ModeTickResult(intents, None, False, summary)
    if translated.kind is TranslatedKind.CANCEL:
        intents = quotes.cancel_all_actives(event, simulation_time=simulation_time)
        return ModeTickResult(intents, None, False, summary)
    assert translated.desired is not None
    ask = translated.desired.ask_price if base_ask is not None else None
    intents = quotes.on_market(
        event,
        simulation_time=simulation_time,
        desired_bid=translated.desired.bid_price,
        desired_ask=ask,
    )
    return ModeTickResult(intents, None, False, summary)


def _iql_primary(
    *,
    quotes: QuoteEngine,
    event: MarketReplayEvent,
    simulation_time: datetime,
    action: HybridAction,
    translator: ActionTranslator,
    bounds: ActionBounds,
    summary: dict[str, Any] | None,
) -> ModeTickResult:
    translated = translator.translate(
        action,
        highest_bid=event.highest_bid,
        lowest_ask=event.lowest_ask,
        bounds=bounds,
    )
    if translated.kind is TranslatedKind.NO_OP:
        return ModeTickResult((), None, False, summary)
    if translated.kind is TranslatedKind.CANCEL:
        intents = quotes.cancel_all_actives(event, simulation_time=simulation_time)
        return ModeTickResult(intents, None, False, summary)
    assert translated.desired is not None
    _base_bid, base_ask = quotes.deterministic_desired(event)
    ask = translated.desired.ask_price if base_ask is not None else None
    intents = quotes.on_market(
        event,
        simulation_time=simulation_time,
        desired_bid=translated.desired.bid_price,
        desired_ask=ask,
    )
    return ModeTickResult(intents, None, False, summary)
