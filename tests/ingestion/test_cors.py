from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from ingestion.main import cors_settings


def _preflight(origin: str) -> str | None:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, **cors_settings(), allow_methods=["GET"], allow_headers=["*"]
    )
    resp = TestClient(app).options(
        "/x", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    return resp.headers.get("access-control-allow-origin")


def test_default_allows_localhost_only(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert _preflight("http://localhost:3000") == "http://localhost:3000"
    assert _preflight("https://dashboard.example.com") is None


def test_cors_origins_env_replaces_default(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://dashboard.example.com, http://10.0.0.5:3000")
    assert _preflight("https://dashboard.example.com") == "https://dashboard.example.com"
    assert _preflight("http://10.0.0.5:3000") == "http://10.0.0.5:3000"
    assert _preflight("http://localhost:3000") is None
