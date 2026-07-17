# PFHedge 0.23.0 compatibility

Validated on macOS 26.4 (Darwin 25.4.0, arm64). The pinned boundary is intended
for macOS and Linux; no Linux runner was available for this local validation.

## Matrix

| Runtime | Clean environment | Install | Public API test | Dependency check | Result |
| --- | --- | --- | --- | --- | --- |
| CPython 3.10.20 | `python -m venv .matrix/3.10` | PASS | `1 passed` | `No broken requirements found.` | PASS |
| CPython 3.11.4 | `python -m venv .matrix/3.11` | PASS | `1 passed` | `No broken requirements found.` | PASS |
| CPython 3.12.4 | `python -m venv .matrix/3.12` | PASS | `1 passed` | `No broken requirements found.` | PASS |

Each row was recreated from scratch and run with the corresponding interpreter:

```text
python -m venv .matrix/<version>
.matrix/<version>/bin/python -m pip install -r requirements.txt
.matrix/<version>/bin/python -m pytest tests/compatibility/test_pfhedge_public_api.py -q
.matrix/<version>/bin/python -m pip check
```

The compatibility test exercises the documented public
`pfhedge.nn.EntropicRiskMeasure(a: float = 1.0)` API, including its public
`target` argument and reduction across the first input dimension.

## Direct package versions

All three rows resolved the same direct package versions:

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
