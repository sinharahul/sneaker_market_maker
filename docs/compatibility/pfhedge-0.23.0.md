# PFHedge 0.23.0 compatibility

Validated on macOS 26.4 (Darwin 25.4.0, arm64) with CPython 3.10–3.12.

## Linux evidence waiver

Dated **2026-07-17**: Linux matrix evidence is explicitly waived for Task 1.
macOS Python 3.10–3.12 governs this task. This document does **not** claim that
Linux installs or tests passed.

## Pre-install failure evidence

On 2026-07-17 a temporary clean CPython 3.10.20 environment was created without
PFHedge (pytest, pytest-cov, and torch only) and the compatibility test was run:

```text
TMP=$(mktemp -d)
/opt/homebrew/bin/python3.10 -m venv "$TMP/venv"
"$TMP/venv/bin/python" -m pip install pytest==8.3.3 pytest-cov==5.0.0 torch==2.2.2
PYTHONPATH=src "$TMP/venv/bin/python" -m pytest \
  tests/compatibility/test_pfhedge_public_api.py -q -m integration
```

Exact failure excerpt:

```text
tests/compatibility/test_pfhedge_public_api.py:5: in <module>
    from pfhedge.nn import EntropicRiskMeasure
E   ModuleNotFoundError: No module named 'pfhedge'
ERROR tests/compatibility/test_pfhedge_public_api.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 warning, 1 error in 4.66s
```

## Matrix (macOS)

| Runtime | Clean environment | Install | Public API test (`-m integration`) | Dependency check | Result |
| --- | --- | --- | --- | --- | --- |
| CPython 3.10.20 | `python -m venv .matrix/3.10` | PASS | `1 passed` | `No broken requirements found.` | PASS |
| CPython 3.11.4 | `python -m venv .matrix/3.11` | PASS | `1 passed` | `No broken requirements found.` | PASS |
| CPython 3.12.4 | `python -m venv .matrix/3.12` | PASS | `1 passed` | `No broken requirements found.` | PASS |

Each macOS row was recreated from scratch and run with the corresponding interpreter:

```text
python -m venv .matrix/<version>
.matrix/<version>/bin/python -m pip install -r requirements.txt
.matrix/<version>/bin/python -m pytest \
  tests/compatibility/test_pfhedge_public_api.py -q -m integration
.matrix/<version>/bin/python -m pip check
```

The compatibility test is marked `@pytest.mark.integration` and exercises the
documented public `pfhedge.nn.EntropicRiskMeasure(a: float = 1.0)` API,
including its public `target` argument and reduction across the first input
dimension.

## Direct package versions

All three macOS rows resolved the same direct package versions:

```text
numpy==1.26.4
torch==2.2.2
pfhedge==0.23.0
tqdm==4.66.5
safetensors==0.4.5
fastapi==0.115.0
uvicorn==0.30.6
pydantic==2.9.2
sqlalchemy==2.0.35
alembic==1.13.3
psycopg==3.2.3
httpx==0.27.2
pytest==8.3.3
pytest-cov==5.0.0
hypothesis==6.115.0
ruff==0.6.9
```

`uvicorn[standard]` and `psycopg[binary]` are the pinned requirement forms;
installed distribution metadata reports their base distribution names.

## Task 26 acceptance re-run (2026-07-17)

Re-validated on branch `feature/deep-bellman-pfhedge` at
`cbfe839643432c1a88c1cc6805cb36c668ae3e83` with CPython 3.12.4:

```text
.venv/bin/python -m pytest tests/compatibility/test_pfhedge_public_api.py \
  -q -m integration --import-mode=importlib
```

Result: `1 passed in 1.37s`. Full acceptance evidence is recorded in
`docs/research/acceptance-checklist.md` (AC-06, AC-14).
