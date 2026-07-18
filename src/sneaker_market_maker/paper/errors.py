"""Shared paper-domain boundary errors."""

from __future__ import annotations


class PaperError(ValueError):
    """Fail-closed paper boundary error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
