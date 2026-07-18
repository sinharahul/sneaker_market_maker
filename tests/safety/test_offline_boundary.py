"""Static AST audits for the offline research boundary."""

from __future__ import annotations

import pytest

from tests.safety.audit_helpers import (
    ALLOWED_NETWORK_MODULE_PREFIXES,
    EXECUTION_ADAPTER_MODULES,
    FORBIDDEN_HTTP_CLIENTS,
    FORBIDDEN_SUBSTRINGS,
    MARKETPLACE_SDKS,
    PACKAGE_ROOT,
    RESEARCH_ROOT,
    credential_env_usages,
    disallowed_network_modules,
    execution_call_names,
    forbidden_imports,
    forbidden_substrings_in_source,
    has_pickle_load,
    has_subprocess_usage,
    has_torch_load,
    is_model_loading_module,
    iter_python_modules,
    module_name,
    network_capable_modules,
    parse,
    serving_execution_imports,
    unsafe_code_calls,
)


def test_network_capable_modules_match_allowlist() -> None:
    capable = network_capable_modules()
    allowed = {
        name
        for name in capable
        if any(name.startswith(prefix) for prefix in ALLOWED_NETWORK_MODULE_PREFIXES)
    }
    assert set(capable) == allowed, (
        "reviewed network-capable backend modules must match the narrow allowlist; "
        f"found {capable}, allowed {sorted(allowed)}"
    )
    assert disallowed_network_modules() == []


@pytest.mark.parametrize("path", iter_python_modules(), ids=module_name)
def test_rejects_forbidden_http_and_marketplace_imports(path) -> None:
    tree = parse(path)
    forbidden = forbidden_imports(tree, FORBIDDEN_HTTP_CLIENTS | MARKETPLACE_SDKS)
    assert forbidden == [], f"{path} imports forbidden clients/SDKs: {forbidden}"


@pytest.mark.parametrize("path", iter_python_modules(RESEARCH_ROOT), ids=module_name)
def test_rejects_anti_bot_and_marketplace_host_terms(path) -> None:
    matches = forbidden_substrings_in_source(path)
    assert matches == [], f"{path} contains forbidden terms: {matches}"


@pytest.mark.parametrize("path", iter_python_modules(RESEARCH_ROOT), ids=module_name)
def test_rejects_credential_environment_names(path) -> None:
    violations = credential_env_usages(parse(path))
    assert violations == [], f"{path} reads credential env names: {violations}"


@pytest.mark.parametrize("path", iter_python_modules(RESEARCH_ROOT), ids=module_name)
def test_rejects_execution_methods(path) -> None:
    calls = execution_call_names(parse(path))
    assert calls == [], f"{path} invokes forbidden execution methods: {calls}"


@pytest.mark.parametrize("path", iter_python_modules(RESEARCH_ROOT), ids=module_name)
def test_rejects_unguarded_pickle_load(path) -> None:
    tree = parse(path)
    assert not has_pickle_load(tree), f"{path} uses pickle.load"


@pytest.mark.parametrize(
    "path",
    [path for path in iter_python_modules() if is_model_loading_module(path)],
    ids=module_name,
)
def test_model_loading_rejects_subprocess_and_torch_load(path) -> None:
    tree = parse(path)
    assert not has_subprocess_usage(tree), f"{path} uses subprocess during model loading"
    assert not has_torch_load(tree), f"{path} uses torch.load during model loading"
    assert unsafe_code_calls(tree) == [], f"{path} executes model-provided code paths"


@pytest.mark.parametrize("path", iter_python_modules(RESEARCH_ROOT / "serving"), ids=module_name)
def test_serving_has_no_execution_adapter_dependencies(path) -> None:
    tree = parse(path)
    imports = serving_execution_imports(path, tree)
    assert imports == [], (
        f"{path} depends on paper/live execution adapters: {imports}; "
        f"forbidden modules: {sorted(EXECUTION_ADAPTER_MODULES)}"
    )


def test_allowlist_rejects_marketplace_hosts_and_model_code_terms() -> None:
    joined = "\n".join(path.read_text() for path in iter_python_modules(PACKAGE_ROOT))
    lowered = joined.casefold()
    for marker in FORBIDDEN_SUBSTRINGS:
        assert marker not in lowered, f"backend contains forbidden marker {marker!r}"
