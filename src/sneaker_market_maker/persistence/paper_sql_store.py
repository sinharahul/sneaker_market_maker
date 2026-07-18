"""PostgreSQL Authoritative Store for Continuous Paper Market-Maker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session, sessionmaker

from sneaker_market_maker.paper.capital import PaperCapital
from sneaker_market_maker.paper.intents import Side
from sneaker_market_maker.paper.inventory import LotState
from sneaker_market_maker.paper.orders import OrderStatus
from sneaker_market_maker.persistence.paper_models import (
    PaperAuditEvent,
    PaperBookSnapshot,
    PersistedFill,
    PersistedLot,
    PersistedOrder,
    json_safe,
    money,
)
from sneaker_market_maker.persistence.paper_tables import (
    paper_audit_events,
    paper_capital,
    paper_fills,
    paper_lots,
    paper_orders,
    paper_runs,
)


class SqlAlchemyPaperStore:
    """PostgreSQL Authoritative Store for the paper book and append-only audit."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create_run(
        self,
        *,
        dataset_id: str,
        dataset_version: str,
        checksum_sha256: str,
        seed: int,
        status: str = "loaded",
    ) -> UUID:
        run_id = uuid4()
        with self._factory() as session:
            session.execute(
                insert(paper_runs).values(
                    id=run_id,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    checksum_sha256=checksum_sha256,
                    seed=seed,
                    status=status,
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        return run_id

    def save_book(self, snapshot: PaperBookSnapshot) -> None:
        now = datetime.now(timezone.utc)
        with self._factory() as session:
            session.execute(delete(paper_fills).where(paper_fills.c.run_id == snapshot.run_id))
            session.execute(delete(paper_lots).where(paper_lots.c.run_id == snapshot.run_id))
            session.execute(delete(paper_orders).where(paper_orders.c.run_id == snapshot.run_id))
            session.execute(
                delete(paper_capital).where(paper_capital.c.run_id == snapshot.run_id)
            )
            session.execute(
                insert(paper_capital).values(
                    run_id=snapshot.run_id,
                    initial=snapshot.capital.initial,
                    cash=snapshot.capital.cash,
                    reserved_buy_principal=snapshot.capital.reserved_buy_principal,
                    updated_at=now,
                )
            )
            for order in snapshot.orders:
                session.execute(
                    insert(paper_orders).values(
                        id=order.order_id,
                        run_id=snapshot.run_id,
                        side=order.side.value,
                        price=order.price,
                        quantity=order.quantity,
                        status=order.status.value,
                        product_family=order.product_family,
                        style_code=order.style_code,
                        shoe_size=order.shoe_size,
                        principal=order.principal,
                        replaced_order_id=order.replaced_order_id,
                    )
                )
            for fill in snapshot.fills:
                session.execute(
                    insert(paper_fills).values(
                        id=fill.fill_id,
                        run_id=snapshot.run_id,
                        order_id=fill.order_id,
                        side=fill.side.value,
                        quantity=fill.quantity,
                        quoted_price=fill.quoted_price,
                        execution_price=fill.execution_price,
                        slippage=fill.slippage,
                        fee_schedule_version=fill.fee_schedule_version,
                        slippage_version=fill.slippage_version,
                        total_fees=fill.total_fees,
                        source_event_id=fill.source_event_id,
                        product_family=fill.product_family,
                        style_code=fill.style_code,
                        shoe_size=fill.shoe_size,
                        simulation_time=fill.simulation_time,
                    )
                )
            for lot in snapshot.lots:
                session.execute(
                    insert(paper_lots).values(
                        id=lot.lot_id,
                        run_id=snapshot.run_id,
                        product_family=lot.product_family,
                        style_code=lot.style_code,
                        shoe_size=lot.shoe_size,
                        landed_cost=lot.landed_cost,
                        state=lot.state.value,
                        source_fill_id=lot.source_fill_id,
                        created_at=lot.created_at,
                    )
                )
            session.commit()

    def load_book(self, run_id: UUID) -> PaperBookSnapshot | None:
        with self._factory() as session:
            capital_row = (
                session.execute(select(paper_capital).where(paper_capital.c.run_id == run_id))
                .mappings()
                .first()
            )
            if capital_row is None:
                return None
            orders = tuple(
                PersistedOrder(
                    order_id=row["id"],
                    side=Side(row["side"]),
                    price=money(row["price"]),
                    quantity=int(row["quantity"]),
                    status=OrderStatus(row["status"]),
                    product_family=row["product_family"],
                    style_code=row["style_code"],
                    shoe_size=money(row["shoe_size"]),
                    principal=money(row["principal"]),
                    replaced_order_id=row["replaced_order_id"],
                )
                for row in session.execute(
                    select(paper_orders).where(paper_orders.c.run_id == run_id)
                ).mappings()
            )
            fills = tuple(
                PersistedFill(
                    fill_id=row["id"],
                    order_id=row["order_id"],
                    side=Side(row["side"]),
                    quantity=int(row["quantity"]),
                    quoted_price=money(row["quoted_price"]),
                    execution_price=money(row["execution_price"]),
                    slippage=money(row["slippage"]),
                    fee_schedule_version=row["fee_schedule_version"],
                    slippage_version=row["slippage_version"],
                    total_fees=money(row["total_fees"]),
                    source_event_id=row["source_event_id"],
                    product_family=row["product_family"],
                    style_code=row["style_code"],
                    shoe_size=money(row["shoe_size"]),
                    simulation_time=row["simulation_time"],
                )
                for row in session.execute(
                    select(paper_fills).where(paper_fills.c.run_id == run_id)
                ).mappings()
            )
            lots = tuple(
                PersistedLot(
                    lot_id=row["id"],
                    product_family=row["product_family"],
                    style_code=row["style_code"],
                    shoe_size=money(row["shoe_size"]),
                    landed_cost=money(row["landed_cost"]),
                    state=LotState(row["state"]),
                    source_fill_id=row["source_fill_id"],
                    created_at=row["created_at"],
                )
                for row in session.execute(
                    select(paper_lots).where(paper_lots.c.run_id == run_id)
                ).mappings()
            )
            return PaperBookSnapshot(
                run_id=run_id,
                capital=PaperCapital(
                    initial=money(capital_row["initial"]),
                    cash=money(capital_row["cash"]),
                    reserved_buy_principal=money(capital_row["reserved_buy_principal"]),
                ),
                orders=orders,
                fills=fills,
                lots=lots,
            )

    def append_audit(
        self,
        run_id: UUID,
        event_type: str,
        payload: dict[str, Any],
    ) -> int:
        with self._factory() as session:
            current = session.execute(
                select(func.coalesce(func.max(paper_audit_events.c.sequence), 0)).where(
                    paper_audit_events.c.run_id == run_id
                )
            ).scalar_one()
            sequence = int(current) + 1
            session.execute(
                insert(paper_audit_events).values(
                    id=uuid4(),
                    run_id=run_id,
                    sequence=sequence,
                    event_type=event_type,
                    payload=json_safe(payload),
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        return sequence

    def list_audit(
        self, run_id: UUID, *, after_sequence: int = 0
    ) -> tuple[PaperAuditEvent, ...]:
        with self._factory() as session:
            rows = session.execute(
                select(paper_audit_events)
                .where(paper_audit_events.c.run_id == run_id)
                .where(paper_audit_events.c.sequence > after_sequence)
                .order_by(paper_audit_events.c.sequence)
            ).mappings()
            return tuple(
                PaperAuditEvent(
                    sequence=int(row["sequence"]),
                    event_type=row["event_type"],
                    payload=dict(row["payload"]),
                    created_at=row["created_at"],
                )
                for row in rows
            )
