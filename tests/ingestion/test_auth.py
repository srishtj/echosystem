import pytest
from fastapi import HTTPException

import ingestion.main as main


def test_require_api_key_noop_when_unset(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", None)
    assert main.require_api_key(None) is None
    assert main.require_api_key("anything") is None


def test_require_api_key_rejects_missing_key(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "secret")
    with pytest.raises(HTTPException) as exc_info:
        main.require_api_key(None)
    assert exc_info.value.status_code == 401


def test_require_api_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "secret")
    with pytest.raises(HTTPException) as exc_info:
        main.require_api_key("wrong")
    assert exc_info.value.status_code == 401


def test_require_api_key_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "secret")
    assert main.require_api_key("secret") is None


def test_health_route_has_no_auth_dependency():
    health_route = next(r for r in main.app.routes if getattr(r, "path", None) == "/health")
    assert main.require_api_key not in [d.dependency for d in health_route.dependencies]


def test_api_routes_carry_auth_dependency():
    # /api/* routes live on the `api` sub-router (mounted via app.include_router),
    # not flattened into app.routes directly.
    watchlist_route = next(r for r in main.api.routes if r.path == "/api/watchlist")
    assert main.require_api_key in [d.dependency for d in watchlist_route.dependencies]


def test_every_api_route_carries_auth_dependency():
    for route in main.api.routes:
        assert main.require_api_key in [d.dependency for d in route.dependencies], route.path
