"""Tests for React SPA and asset serving in work_management_api."""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from aao.work_management_api import app


def test_workboard_ui_serves_html():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "html" in response.headers.get("content-type", "").lower()


def test_spa_client_routes_serve_html():
    client = TestClient(app)
    for route in ("/kanban", "/mandates", "/activity", "/organization"):
        response = client.get(route)
        assert response.status_code == 200
        assert "html" in response.headers.get("content-type", "").lower()


def test_api_routes_do_not_fallback_to_spa():
    client = TestClient(app)
    response = client.get("/v1/nonexistent-route-for-testing")
    assert response.status_code == 404
    assert "application/json" in response.headers.get("content-type", "").lower()


def test_path_traversal_in_assets_rejected():
    client = TestClient(app)
    response = client.get("/assets/../../etc/passwd")
    assert response.status_code in (400, 404)


def test_static_dir_override(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "index.html").write_text("<!doctype html><h1>Custom SPA</h1>", encoding="utf-8")
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        (assets_dir / "app.js").write_text("console.log('custom');", encoding="utf-8")

        monkeypatch.setenv("AAO_STATIC_DIR", str(tmp_path))

        client = TestClient(app)
        res_root = client.get("/")
        assert res_root.status_code == 200
        assert "Custom SPA" in res_root.text

        res_spa = client.get("/kanban")
        assert res_spa.status_code == 200
        assert "Custom SPA" in res_spa.text

        res_asset = client.get("/assets/app.js")
        assert res_asset.status_code == 200
        assert "console.log('custom');" in res_asset.text
