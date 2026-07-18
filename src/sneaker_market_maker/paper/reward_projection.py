"""Fee-once RewardRecord projection from paper accounting (R1-02)."""

from __future__ import annotations

from sneaker_market_maker.paper.capital import INITIAL_PAPER_CAPITAL
from sneaker_market_maker.paper.errors import PaperError
from sneaker_market_maker.research.contracts.transition import RewardRecord
from sneaker_market_maker.research.rewards.builder import (
    AccountingProjection,
    PenaltyStatistics,
    RewardBuilder,
    RewardConfig,
)
from decimal import Decimal

ZERO = Decimal("0")

ZERO_PENALTIES = PenaltyStatistics(
    age=ZERO,
    capital=ZERO,
    turnover=ZERO,
    drawdown=ZERO,
    stale=ZERO,
    liquidation=ZERO,
)


def default_paper_reward_config() -> RewardConfig:
    return RewardConfig(
        version="paper-reward-v1",
        initial_nav=INITIAL_PAPER_CAPITAL,
        lambda_age=ZERO,
        lambda_capital=ZERO,
        lambda_turnover=ZERO,
        lambda_drawdown=ZERO,
        lambda_stale=ZERO,
        lambda_terminal=ZERO,
        tolerance=Decimal("0.0001"),
    )


def project_paper_reward(
    *,
    before: AccountingProjection,
    after: AccountingProjection,
    terminal: bool = False,
    penalties: PenaltyStatistics | None = None,
    config: RewardConfig | None = None,
) -> RewardRecord:
    """Project fee-once reward or raise PaperError to quarantine incomplete accounting."""

    builder = RewardBuilder(config or default_paper_reward_config())
    try:
        return builder.build(
            before,
            after,
            penalties if penalties is not None else ZERO_PENALTIES,
            terminal,
        )
    except (ValueError, TypeError) as error:
        raise PaperError("reward_quarantine", f"quarantine: {error}") from error
