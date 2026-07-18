"""FastAPI application factory for local research + paper ops control planes."""

from __future__ import annotations

from collections.abc import Callable
from ipaddress import ip_address

from fastapi import Depends, FastAPI

from sneaker_market_maker.api.paper_events import create_paper_event_router
from sneaker_market_maker.api.paper_routes import PaperServices, create_paper_router
from sneaker_market_maker.api.research_events import create_event_router
from sneaker_market_maker.api.research_routes import ResearchServices, create_research_router

DEFAULT_BIND_HOST = "127.0.0.1"


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def create_app(
    services: ResearchServices,
    *,
    paper_services: PaperServices | None = None,
    bind_host: str = DEFAULT_BIND_HOST,
    authentication: Callable[..., object] | None = None,
) -> FastAPI:
    """Build an app whose infrastructure services are supplied by the caller."""

    if not _is_loopback(bind_host) and authentication is None:
        raise ValueError("external binding requires an authentication dependency")

    app = FastAPI(title="Sneaker Market Maker Research API")
    app.state.bind_host = bind_host
    dependencies = [Depends(authentication)] if authentication is not None else []
    app.include_router(create_event_router(services.event_service), dependencies=dependencies)
    app.include_router(create_research_router(services), dependencies=dependencies)
    if paper_services is not None:
        app.include_router(
            create_paper_event_router(paper_services.event_service),
            dependencies=dependencies,
        )
        app.include_router(create_paper_router(paper_services), dependencies=dependencies)
    return app


__all__ = ["DEFAULT_BIND_HOST", "create_app"]
