"""AST helpers for offline boundary audits."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "sneaker_market_maker"
RESEARCH_ROOT = PACKAGE_ROOT / "research"

FORBIDDEN_HTTP_CLIENTS = frozenset({"requests", "aiohttp", "httpx", "urllib3", "http.client"})
MARKETPLACE_SDKS = frozenset({"stockx", "goat", "alias"})
MODEL_LOADING_PARTS = ("iql", "pfhedge", "policies")

ALLOWED_NETWORK_MODULE_PREFIXES = (
    "sneaker_market_maker.api.",
    "sneaker_market_maker.persistence.",
)
ALLOWED_NETWORK_IMPORT_ROOTS = frozenset(
    {
        "fastapi",
        "uvicorn",
        "starlette",
        "websockets",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
    }
)
NETWORK_IMPORT_ROOTS = frozenset(
    {
        *ALLOWED_NETWORK_IMPORT_ROOTS,
        "requests",
        "aiohttp",
        "httpx",
        "urllib3",
        "http",
        "socket",
        "ftplib",
        "smtplib",
    }
)

FORBIDDEN_SUBSTRINGS = (
    "cloudflare",
    "captcha",
    "tls fingerprint",
    "tls_fingerprint",
    "proxy rotation",
    "proxy_rotation",
    "rotate_proxy",
    "stockx.com",
    "goat.com",
    "alias.com",
)
CREDENTIAL_ENV_MARKERS = (
    "STOCKX",
    "GOAT",
    "ALIAS",
    "API_KEY",
    "API_SECRET",
    "CLIENT_SECRET",
    "ACCESS_TOKEN",
)
EXECUTION_ADAPTER_MODULES = frozenset(
    {
        "sneaker_market_maker.core",
        "sneaker_market_maker.pipeline",
        "sneaker_market_maker.simulation",
        "sneaker_market_maker.execution",
        "sneaker_market_maker.research.adapters",
    }
)
FORBIDDEN_EXECUTION_CALLS = frozenset(
    {
        "submit_order",
        "place_order",
        "execute_order",
        "send_order",
        "execute_live",
        "execute_paper",
    }
)
UNSAFE_CODE_CALLS = frozenset({"eval", "exec", "compile", "__import__"})


def iter_python_modules(root: Path = PACKAGE_ROOT) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    )


def module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT.parent)
    parts = list(relative.parts)
    parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def forbidden_imports(tree: ast.AST, forbidden: frozenset[str]) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in forbidden or alias.name in forbidden:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in forbidden or node.module in forbidden:
                found.append(node.module)
    return found


def is_model_loading_module(path: Path) -> bool:
    parts = path.relative_to(PACKAGE_ROOT).parts
    return len(parts) >= 2 and parts[0] == "research" and parts[1] in MODEL_LOADING_PARTS


def has_pickle_load(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "load":
            value = func.value
            if isinstance(value, ast.Name) and value.id == "pickle":
                return True
            if isinstance(value, ast.Attribute) and value.attr == "pickle":
                return True
    return False


def has_torch_load(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "load":
            value = func.value
            if isinstance(value, ast.Name) and value.id == "torch":
                return True
            if isinstance(value, ast.Attribute) and value.attr == "load":
                return True
    return False


def has_subprocess_usage(tree: ast.AST) -> bool:
    if "subprocess" in import_roots(tree):
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"Popen", "run", "call"}:
            value = func.value
            if isinstance(value, ast.Name) and value.id == "subprocess":
                return True
    return False


def _env_key(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def credential_env_usages(tree: ast.AST) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "getenv":
                if isinstance(func.value, ast.Name) and func.value.id == "os":
                    key = _env_key(node.args[0]) if node.args else None
                    if key and any(marker in key.upper() for marker in CREDENTIAL_ENV_MARKERS):
                        violations.append(key)
            elif isinstance(func, ast.Attribute) and func.attr == "get":
                value = func.value
                if (
                    isinstance(value, ast.Attribute)
                    and value.attr == "environ"
                    and isinstance(value.value, ast.Name)
                    and value.value.id == "os"
                ):
                    key = _env_key(node.args[0]) if node.args else None
                    if key and any(marker in key.upper() for marker in CREDENTIAL_ENV_MARKERS):
                        violations.append(key)
        elif isinstance(node, ast.Subscript):
            value = node.value
            if (
                isinstance(value, ast.Attribute)
                and value.attr == "environ"
                and isinstance(value.value, ast.Name)
                and value.value.id == "os"
            ):
                key = _env_key(node.slice)
                if key and any(marker in key.upper() for marker in CREDENTIAL_ENV_MARKERS):
                    violations.append(key)
    return violations


def execution_call_names(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_EXECUTION_CALLS:
                found.append(node.func.attr)
    return found


def unsafe_code_calls(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in UNSAFE_CODE_CALLS:
                found.append(node.func.id)
    return found


def serving_execution_imports(path: Path, tree: ast.AST) -> list[str]:
    if "serving" not in path.parts:
        return []
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in EXECUTION_ADAPTER_MODULES or any(
                    alias.name.startswith(f"{module}.") for module in EXECUTION_ADAPTER_MODULES
                ):
                    violations.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module in EXECUTION_ADAPTER_MODULES or any(
                node.module.startswith(f"{module}.") for module in EXECUTION_ADAPTER_MODULES
            ):
                violations.append(node.module)
    return violations


def forbidden_substrings_in_source(path: Path) -> list[str]:
    text = path.read_text().casefold()
    return [marker for marker in FORBIDDEN_SUBSTRINGS if marker in text]


def network_capable_modules() -> tuple[str, ...]:
    capable: set[str] = set()
    for path in iter_python_modules():
        roots = import_roots(parse(path)) & NETWORK_IMPORT_ROOTS
        if roots:
            capable.add(module_name(path))
    return tuple(sorted(capable))


def disallowed_network_modules() -> list[str]:
    disallowed: list[str] = []
    for path in iter_python_modules():
        name = module_name(path)
        roots = import_roots(parse(path)) & NETWORK_IMPORT_ROOTS
        if not roots:
            continue
        if any(name.startswith(prefix) for prefix in ALLOWED_NETWORK_MODULE_PREFIXES):
            unexpected = roots - ALLOWED_NETWORK_IMPORT_ROOTS
            if unexpected:
                disallowed.append(f"{name} imports disallowed network roots: {sorted(unexpected)}")
            continue
        disallowed.append(name)
    return disallowed
