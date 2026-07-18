"""FastAPI application factory for the local research control plane."""

from __future__ import annotations

from collections.abc import Callable
from ipaddress import ip_address

from fastapi import Depends, FastAPI

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
    return app


__all__ = ["DEFAULT_BIND_HOST", "create_app"]
