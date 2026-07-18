"""Shared fixtures for safety tests."""

from __future__ import annotations

import socket

import pytest


class NetworkDenied(RuntimeError):
    """Raised when a test blocks outbound network access."""


@pytest.fixture
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_connect(self: socket.socket, address: object) -> None:
        raise NetworkDenied(f"network disabled: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
