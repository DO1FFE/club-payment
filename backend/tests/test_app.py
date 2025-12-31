import importlib
from pathlib import Path
import sys

import pytest


@pytest.fixture()
def app_module(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost")
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-token")
    monkeypatch.setenv("ADMIN_NAME", "Admin Nutzer")

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    import app as app
    import device_registry as device_registry
    import users as users

    importlib.reload(app)
    importlib.reload(device_registry)
    importlib.reload(users)
    return app


@pytest.fixture()
def client(app_module):
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client, app_module


def test_connection_token_success(client, monkeypatch):
    test_client, app_module = client

    class DummyToken:
        def __init__(self, secret: str):
            self.secret = secret

    def fake_create():
        return DummyToken("token_secret")

    monkeypatch.setattr(app_module.stripe.terminal.ConnectionToken, "create", staticmethod(fake_create))

    response = test_client.post("/terminal/connection_token")
    assert response.status_code == 200
    assert response.get_json() == {"secret": "token_secret"}


def test_create_payment_intent_success(client, monkeypatch):
    test_client, app_module = client

    register_response = test_client.post(
        "/admin/devices",
        json={"device_id": "device1", "user_id": 1},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert register_response.status_code == 201

    class DummyIntent:
        def __init__(self):
            self.id = "pi_123"
            self.client_secret = "secret_123"
            self.amount = 500

    def fake_create(**kwargs):
        assert kwargs["amount"] == 500
        assert kwargs["currency"] == "eur"
        assert kwargs["metadata"]["item"] == "Cola"
        assert kwargs["metadata"]["kassierer"] == "Admin Nutzer"
        assert kwargs["metadata"]["user_id"] == "1"
        assert kwargs["metadata"]["role"] == "admin"
        assert kwargs["metadata"]["device"] == "device1"
        return DummyIntent()

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "create", staticmethod(fake_create))

    response = test_client.post(
        "/pos/create_intent",
        json={"amount_cents": 500, "item": "Cola", "kassierer": "Erik", "device": "device1"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == "pi_123"
    assert data["client_secret"] == "secret_123"
    assert data["amount_cents"] == 500


def test_create_payment_intent_validation(client):
    test_client, _ = client
    register_response = test_client.post(
        "/admin/devices",
        json={"device_id": "device2", "user_id": 1},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert register_response.status_code == 201
    response = test_client.post(
        "/pos/create_intent",
        json={"amount_cents": 0, "device": "device2"},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 400
    assert "größer als Null" in response.get_json()["error"]


def test_create_payment_intent_requires_auth(client):
    test_client, _ = client
    response = test_client.post("/pos/create_intent", json={"amount_cents": 200})
    assert response.status_code == 401
    assert response.get_json()["error"] == "Authorization-Header fehlt"


def test_admin_user_flow(client):
    test_client, _ = client

    create_response = test_client.post(
        "/admin/users",
        json={"name": "Kassierer 1", "role": "kassierer"},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["name"] == "Kassierer 1"
    assert created["role"] == "kassierer"
    assert created["active"] is True
    assert created["api_token"]

    list_response = test_client.get(
        "/admin/users",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_response.status_code == 200
    users = list_response.get_json()["users"]
    assert any(user["name"] == "Kassierer 1" for user in users)

    patch_response = test_client.patch(
        f"/admin/users/{created['id']}",
        json={"active": False},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert patch_response.status_code == 200
    assert patch_response.get_json()["active"] is False


def test_admin_device_flow(client):
    test_client, _ = client

    create_response = test_client.post(
        "/admin/users",
        json={"name": "Kassierer 2", "role": "kassierer"},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_response.status_code == 201
    user_id = create_response.get_json()["id"]

    register_response = test_client.post(
        "/admin/devices",
        json={"device_id": "kasse-02", "user_id": user_id},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert register_response.status_code == 201
    assert register_response.get_json()["device_id"] == "kasse-02"

    list_response = test_client.get(
        "/admin/devices",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_response.status_code == 200
    devices = list_response.get_json()["devices"]
    assert any(device["device_id"] == "kasse-02" for device in devices)


def test_webhook_invalid_signature(client, monkeypatch):
    test_client, app_module = client

    def fake_construct_event(payload, sig_header, secret):
        raise app_module.stripe.error.SignatureVerificationError("bad signature", sig_header)

    monkeypatch.setattr(app_module.stripe.Webhook, "construct_event", staticmethod(fake_construct_event))

    response = test_client.post("/webhook", data=b"{}", headers={"Stripe-Signature": "invalid"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid signature"
