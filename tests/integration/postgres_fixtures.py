"""Postgres integration fixtures for research repository tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import delete

from alembic import command
from alembic.config import Config
from sneaker_market_maker.persistence.database import (
    create_database_engine,
    create_session_factory,
)
from sneaker_market_maker.persistence.paper_tables import (
    paper_audit_events,
    paper_capital,
    paper_fills,
    paper_lots,
    paper_orders,
    paper_runs,
)
from sneaker_market_maker.persistence.research_tables import (
    action_schemas,
    behavior_policies,
    decision_points,
    episode_manifests,
    mdp_state_schemas,
    offline_transitions,
    reward_schemas,
)

DATABASE_URL = os.getenv("DATABASE_URL", "")
ROOT = Path(__file__).parents[2]


def alembic_config() -> Config:
    config = Config(ROOT / "alembic.ini")
    config.set_main_option("script_location", str(ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def engine():
    database_engine = create_database_engine(DATABASE_URL)
    command.upgrade(alembic_config(), "head")
    yield database_engine
    database_engine.dispose()


@pytest.fixture()
def session_factory(engine):
    with engine.begin() as connection:
        for table in (
            offline_transitions,
            behavior_policies,
            decision_points,
            episode_manifests,
            reward_schemas,
            action_schemas,
            mdp_state_schemas,
            paper_audit_events,
            paper_fills,
            paper_lots,
            paper_orders,
            paper_capital,
            paper_runs,
        ):
            connection.execute(delete(table))
    return create_session_factory(engine)
