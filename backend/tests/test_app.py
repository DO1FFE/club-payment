import importlib
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

import device_registry

@pytest.fixture()
def app_module(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost")

    import app as app

    importlib.reload(app)
    device_registry.reset_registry()
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
    device_registry.register_device(device_id="device1", user_id="user1", role="kassierer")

    class DummyIntent:
        def __init__(self):
            self.id = "pi_123"
            self.client_secret = "secret_123"
            self.amount = 500

    def fake_create(**kwargs):
        assert kwargs["amount"] == 500
        assert kwargs["currency"] == "eur"
        assert kwargs["metadata"]["item"] == "Cola"
        assert kwargs["metadata"]["user_id"] == "user1"
        assert kwargs["metadata"]["role"] == "kassierer"
        return DummyIntent()

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "create", staticmethod(fake_create))

    response = test_client.post(
        "/pos/create_intent",
        json={"amount_cents": 500, "item": "Cola", "kassierer": "Erik", "device": "device1"},
        headers={"X-User-Id": "user1", "X-User-Role": "kassierer"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == "pi_123"
    assert data["client_secret"] == "secret_123"
    assert data["amount_cents"] == 500


def test_create_payment_intent_validation(client):
    test_client, _ = client
    response = test_client.post(
        "/pos/create_intent",
        json={"amount_cents": 0, "device": "device1"},
        headers={"X-User-Id": "user1", "X-User-Role": "kassierer"},
    )
    assert response.status_code == 400
    assert "greater than zero" in response.get_json()["error"]


def test_create_payment_intent_device_not_registered(client):
    test_client, _ = client
    response = test_client.post(
        "/pos/create_intent",
        json={"amount_cents": 500, "device": "device-x"},
        headers={"X-User-Id": "user1", "X-User-Role": "kassierer"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "Gerät ist nicht registriert."


def test_create_payment_intent_device_mismatch(client):
    test_client, _ = client
    device_registry.register_device(device_id="device1", user_id="user2", role="kassierer")
    response = test_client.post(
        "/pos/create_intent",
        json={"amount_cents": 500, "device": "device1"},
        headers={"X-User-Id": "user1", "X-User-Role": "kassierer"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "Gerät gehört nicht zum angemeldeten Benutzer."


def test_admin_device_endpoints(client):
    test_client, _ = client
    response = test_client.post(
        "/admin/devices",
        json={"device_id": "device1", "user_id": "user1", "role": "kassierer"},
        headers={"X-User-Id": "admin1", "X-User-Role": "admin"},
    )
    assert response.status_code == 201
    assert response.get_json() == {"device_id": "device1", "user_id": "user1", "role": "kassierer"}

    response = test_client.get(
        "/admin/devices",
        headers={"X-User-Id": "admin1", "X-User-Role": "admin"},
    )
    assert response.status_code == 200
    assert response.get_json() == {
        "devices": [{"device_id": "device1", "user_id": "user1", "role": "kassierer"}]
    }


def test_webhook_invalid_signature(client, monkeypatch):
    test_client, app_module = client

    def fake_construct_event(payload, sig_header, secret):
        raise app_module.stripe.error.SignatureVerificationError("bad signature", sig_header)

    monkeypatch.setattr(app_module.stripe.Webhook, "construct_event", staticmethod(fake_construct_event))

    response = test_client.post("/webhook", data=b"{}", headers={"Stripe-Signature": "invalid"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid signature"
