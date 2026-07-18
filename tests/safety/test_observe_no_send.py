"""L1 safety: observe package must not grow an order-send client."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.safety.audit_helpers import (
    FORBIDDEN_HTTP_CLIENTS,
    MARKETPLACE_SDKS,
    execution_call_names,
    forbidden_imports,
    iter_python_modules,
    module_name,
    parse,
)

OBSERVE_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "sneaker_market_maker"
    / "observe"
)


@pytest.mark.parametrize("path", iter_python_modules(OBSERVE_ROOT), ids=module_name)
def test_observe_rejects_http_and_marketplace_sdks(path: Path) -> None:
    tree = parse(path)
    forbidden = forbidden_imports(tree, FORBIDDEN_HTTP_CLIENTS | MARKETPLACE_SDKS)
    assert forbidden == [], f"{path} imports forbidden clients/SDKs: {forbidden}"


@pytest.mark.parametrize("path", iter_python_modules(OBSERVE_ROOT), ids=module_name)
def test_observe_rejects_order_send_methods(path: Path) -> None:
    calls = execution_call_names(parse(path))
    assert calls == [], f"{path} invokes forbidden execution methods: {calls}"


def test_observe_package_exists_and_is_nonempty() -> None:
    modules = list(iter_python_modules(OBSERVE_ROOT))
    assert modules, "observe package missing — L1 port not present"
