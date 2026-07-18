"""Local demo API serves Swagger and research comparison fixtures."""

from fastapi.testclient import TestClient

from sneaker_market_maker.api.local_demo import app


def test_swagger_docs_are_available() -> None:
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.casefold() or "openapi" in response.text.casefold()


def test_openapi_schema_lists_research_routes() -> None:
    client = TestClient(app)
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/research/comparisons" in paths or any(
        path.startswith("/api/research/") for path in paths
    )
    assert schema["info"]["title"].startswith("Sneaker Market Maker")


def test_comparisons_fixture_matches_research_page_shape() -> None:
    client = TestClient(app)
    payload = client.get("/api/research/comparisons").json()
    assert "assumptions" in payload
    assert "tracks" in payload
    assert "registry" in payload
    assert "trace" in payload
    assert payload["registry"]["state"] == "shadow"
