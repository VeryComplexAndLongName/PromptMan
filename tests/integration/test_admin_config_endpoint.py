from __future__ import annotations


def test_admin_config_list_returns_global_keys(client):  # type: ignore[no-untyped-def]
    response = client.get("/v1/admin/config/")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, dict)
    assert "OPTIMIZER_PROVIDER" in payload
    assert "PROMPTMAN_CACHE_ENABLED" in payload


def test_admin_config_update_roundtrip(client):  # type: ignore[no-untyped-def]
    update_response = client.put(
        "/v1/admin/config/OPTIMIZER_PROVIDER",
        params={"value": "openai"},
    )
    assert update_response.status_code == 200
    assert update_response.json() == {"key": "OPTIMIZER_PROVIDER", "value": "openai"}

    read_response = client.get("/v1/admin/config/OPTIMIZER_PROVIDER")
    assert read_response.status_code == 200
    assert read_response.json() == {"key": "OPTIMIZER_PROVIDER", "value": "openai"}
