import importlib
from pathlib import Path
import sys

import pytest


@pytest.fixture()
def app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost")
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-token")
    monkeypatch.setenv("ADMIN_NAME", "Admin Nutzer")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-passwort")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    import app as app
    import database as database
    import device_registry as device_registry
    import products as products
    import users as users

    importlib.reload(database)
    importlib.reload(users)
    importlib.reload(device_registry)
    importlib.reload(products)
    importlib.reload(app)
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

    response = test_client.post(
        "/terminal/connection_token",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    assert response.get_json() == {"secret": "token_secret"}


def test_connection_token_requires_auth(client):
    test_client, _ = client

    response = test_client.post("/terminal/connection_token")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Authorization-Header fehlt"


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
        assert kwargs["metadata"]["kassierer"] == "admin"
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


def test_get_receipt_returns_stripe_receipt_url(client, monkeypatch):
    test_client, app_module = client

    class DummyCharge:
        receipt_url = "https://pay.stripe.com/receipts/test-receipt"

    class DummyIntent:
        latest_charge = DummyCharge()

    def fake_retrieve(payment_intent_id, expand):
        assert payment_intent_id == "pi_paid"
        assert "latest_charge" in expand
        return DummyIntent()

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "retrieve", staticmethod(fake_retrieve))

    response = test_client.get(
        "/pos/receipt/pi_paid",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"receipt_url": "https://pay.stripe.com/receipts/test-receipt"}


def test_get_receipt_without_charge_returns_404(client, monkeypatch):
    test_client, app_module = client

    class DummyCharges:
        data = []

    class DummyIntent:
        latest_charge = None
        charges = DummyCharges()

    def fake_retrieve(payment_intent_id, expand):
        return DummyIntent()

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "retrieve", staticmethod(fake_retrieve))

    response = test_client.get(
        "/pos/receipt/pi_unpaid",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Beleg-URL nicht verfügbar"


def test_admin_user_flow(client):
    test_client, _ = client

    create_response = test_client.post(
        "/admin/users",
        json={
            "role": "kassierer",
            "username": "kassierer1",
            "password": "passwort-1",
            "api_token": "client-supplied-token",
        },
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["name"] == "kassierer1"
    assert created["username"] == "kassierer1"
    assert created["role"] == "kassierer"
    assert created["active"] is True
    assert created["api_token"]
    assert created["api_token"] != "client-supplied-token"

    list_response = test_client.get(
        "/admin/users",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_response.status_code == 200
    users = list_response.get_json()["users"]
    assert any(user["username"] == "kassierer1" for user in users)

    patch_response = test_client.patch(
        f"/admin/users/{created['id']}",
        json={"username": "kassierer1-neu", "password": "passwort-neu", "active": False},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert patch_response.status_code == 200
    assert patch_response.get_json()["active"] is False
    assert patch_response.get_json()["username"] == "kassierer1-neu"

    delete_response = test_client.delete(
        f"/admin/users/{created['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"] is True


def test_admin_device_flow(client):
    test_client, _ = client

    create_response = test_client.post(
        "/admin/users",
        json={
            "role": "kassierer",
            "username": "kassierer2",
            "password": "passwort-2",
        },
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


def test_create_user_requires_credentials(client):
    test_client, _ = client

    response = test_client.post(
        "/admin/users",
        json={"role": "kassierer"},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "username ist erforderlich"


def test_login_success(client):
    test_client, _ = client

    response = test_client.post(
        "/auth/login",
        json={"username": "admin", "password": "admin-passwort"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"token": "admin-token", "display_name": "admin", "device_pending": False}


def test_login_remembers_unassigned_device_for_admin_assignment(client):
    test_client, _ = client

    create_response = test_client.post(
        "/admin/users",
        json={
            "role": "kassierer",
            "username": "neue-kasse",
            "password": "passwort-kasse",
        },
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_response.status_code == 201
    user_id = create_response.get_json()["id"]

    login_response = test_client.post(
        "/auth/login",
        json={"username": "neue-kasse", "password": "passwort-kasse", "device_id": "SM-A536B-demo"},
    )
    assert login_response.status_code == 200
    assert login_response.get_json()["device_pending"] is True

    list_response = test_client.get(
        "/admin/devices",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_response.status_code == 200
    pending_devices = list_response.get_json()["pending_devices"]
    assert any(device["device_id"] == "SM-A536B-demo" for device in pending_devices)

    assign_response = test_client.post(
        "/admin/devices",
        json={"device_id": "SM-A536B-demo", "user_id": user_id},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert assign_response.status_code == 201

    list_after_assign_response = test_client.get(
        "/admin/devices",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_after_assign_response.status_code == 200
    assert list_after_assign_response.get_json()["pending_devices"] == []


def test_login_invalid_password(client):
    test_client, _ = client

    response = test_client.post(
        "/auth/login",
        json={"username": "admin", "password": "falsch"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Benutzername oder Passwort ungültig"


def test_webhook_invalid_signature(client, monkeypatch):
    test_client, app_module = client

    def fake_construct_event(payload, sig_header, secret):
        raise app_module.stripe.error.SignatureVerificationError("bad signature", sig_header)

    monkeypatch.setattr(app_module.stripe.Webhook, "construct_event", staticmethod(fake_construct_event))

    response = test_client.post("/webhook", data=b"{}", headers={"Stripe-Signature": "invalid"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid signature"


def test_admin_product_flow(client):
    test_client, _ = client

    create_response = test_client.post(
        "/admin/products",
        json={"name": "Apfelschorle", "price_cents": 180},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_response.status_code == 201
    created = create_response.get_json()
    assert created["name"] == "Apfelschorle"
    assert created["price_cents"] == 180
    assert created["active"] is True

    list_response = test_client.get(
        "/admin/products",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_response.status_code == 200
    products = list_response.get_json()["products"]
    assert any(product["name"] == "Apfelschorle" for product in products)

    patch_response = test_client.patch(
        f"/admin/products/{created['id']}",
        json={"active": False, "price_cents": 200},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert patch_response.status_code == 200
    updated = patch_response.get_json()
    assert updated["active"] is False
    assert updated["price_cents"] == 200

    delete_response = test_client.delete(
        f"/admin/products/{created['id']}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"] is True


def test_admin_product_validation(client):
    test_client, _ = client

    response = test_client.post(
        "/admin/products",
        json={"name": "Ungültig", "price_cents": 0},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 400
    assert "größer als Null" in response.get_json()["error"]


def test_products_are_persisted_in_database(client):
    test_client, _ = client
    import products as products_module

    create_response = test_client.post(
        "/admin/products",
        json={"name": "Persistente Mate", "price_cents": 230},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_response.status_code == 201
    product_id = create_response.get_json()["id"]

    products_module._STORE = None
    fresh_store = products_module.get_product_store()
    persisted_product = next(
        product for product in fresh_store.list_products()
        if product.id == product_id
    )

    assert persisted_product.name == "Persistente Mate"
    assert persisted_product.price_cents == 230
    assert persisted_product.active is True


def test_active_products_for_authenticated_user(client):
    test_client, _ = client

    create_user_response = test_client.post(
        "/admin/users",
        json={
            "role": "kassierer",
            "username": "kasse-user",
            "password": "passwort-kasse",
        },
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_user_response.status_code == 201
    kassierer_token = create_user_response.get_json()["api_token"]

    create_product_response = test_client.post(
        "/admin/products",
        json={"name": "Mate", "price_cents": 220, "active": True},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert create_product_response.status_code == 201

    inactive_product_response = test_client.post(
        "/admin/products",
        json={"name": "Test Inaktiv", "price_cents": 199, "active": False},
        headers={"Authorization": "Bearer admin-token"},
    )
    assert inactive_product_response.status_code == 201

    list_response = test_client.get(
        "/products",
        headers={"Authorization": f"Bearer {kassierer_token}"},
    )
    assert list_response.status_code == 200
    products = list_response.get_json()["products"]
    assert any(product["name"] == "Mate" for product in products)
    assert all(product["name"] != "Test Inaktiv" for product in products)


def test_interactive_admin_bootstrap_when_no_users(monkeypatch, tmp_path):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_NAME", raising=False)
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'interactive.sqlite3'}")

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    import database as database
    import users as users

    importlib.reload(database)
    importlib.reload(users)

    inputs = iter(["erstadmin", "Erster Admin"])
    passwords = iter(["supergeheim", "supergeheim"])

    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    monkeypatch.setattr(users, "getpass", lambda _: next(passwords))

    store = users.get_user_store()
    admin = store.get_by_username("erstadmin")

    assert admin is not None
    assert admin.role == users.Role.ADMIN
    assert admin.active is True
    assert admin.name == "Erster Admin"


def test_no_interactive_bootstrap_when_admin_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-token")
    monkeypatch.setenv("ADMIN_NAME", "Admin Nutzer")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-passwort")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'existing-admin.sqlite3'}")

    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    import database as database
    import users as users

    importlib.reload(database)
    importlib.reload(users)

    called = {"interactive": False}

    def fake_bootstrap(_: users.UserStore) -> None:
        called["interactive"] = True

    monkeypatch.setattr(users, "_bootstrap_admin_interactive", fake_bootstrap)

    store = users.get_user_store()
    admin = store.get_by_username("admin")

    assert admin is not None
    assert admin.role == users.Role.ADMIN
    assert called["interactive"] is False


def test_admin_web_login_and_users_page(client):
    test_client, _ = client

    response = test_client.get("/admin/web/users")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/web/login")

    login_response = test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert "Nutzerverwaltung" in login_response.get_data(as_text=True)
    assert "admin" in login_response.get_data(as_text=True)


def test_admin_web_user_validation(client):
    test_client, _ = client
    login_response = test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )
    assert login_response.status_code == 302

    response = test_client.post(
        "/admin/web/users",
        data={
            "role": "kassierer",
            "username": "web-user-1",
            "password": "",
            "active": "on",
        },
    )
    assert response.status_code == 200
    assert "password ist erforderlich" in response.get_data(as_text=True)


def test_admin_web_create_user_success_uses_credentials_only(client):
    test_client, app_module = client
    login_response = test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )
    assert login_response.status_code == 302

    create_response = test_client.post(
        "/admin/web/users",
        data={
            "role": "kassierer",
            "username": "web-kassierer",
            "password": "web-passwort",
            "active": "on",
            "device_id": "web-kasse-1",
        },
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith("/admin/web/users")

    store = app_module.get_user_store()
    user = store.get_by_username("web-kassierer")
    assert user is not None
    assert user.name == "web-kassierer"
    assert user.role == app_module.Role.KASSIERER
    assert user.active is True
    assert user.password_hash
    assert "web-passwort" not in user.password_hash

    registry = app_module.get_device_registry()
    assignment = registry.get_device("web-kasse-1")
    assert assignment is None


def test_admin_web_edit_and_delete_user(client):
    test_client, app_module = client
    login_response = test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )
    assert login_response.status_code == 302

    store = app_module.get_user_store()
    user = store.create_user(
        name="web-edit",
        role=app_module.Role.KASSIERER,
        active=True,
        username="web-edit",
        password_hash=store.hash_password("alt-passwort"),
    )

    update_response = test_client.post(
        "/admin/web/users",
        data={
            "action": "update",
            "user_id": str(user.id),
            "role": "admin",
            "username": "web-edit-neu",
            "password": "neu-passwort",
            "active": "on",
        },
    )
    assert update_response.status_code == 302

    updated = store.get_by_username("web-edit-neu")
    assert updated is not None
    assert updated.role == app_module.Role.ADMIN
    assert store.authenticate("web-edit-neu", "neu-passwort") is not None

    delete_response = test_client.post(
        "/admin/web/users",
        data={"action": "delete", "user_id": str(user.id)},
    )
    assert delete_response.status_code == 302
    assert store.get_by_id(user.id) is None


def test_admin_web_assign_device_to_existing_user(client):
    test_client, app_module = client
    login_response = test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )
    assert login_response.status_code == 302

    store = app_module.get_user_store()
    user = store.create_user(
        name="Bestehender Kassierer",
        role=app_module.Role.KASSIERER,
        active=True,
        username="bestehende-kasse",
        password_hash=store.hash_password("web-passwort"),
    )

    response = test_client.post(
        "/admin/web/devices",
        data={"device_id": "web-kasse-2", "user_id": str(user.id)},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/web/users")
    assignment = app_module.get_device_registry().get_device("web-kasse-2")
    assert assignment is not None
    assert assignment.user_id == user.id


def test_admin_web_lists_pending_device_after_app_login(client):
    test_client, app_module = client
    store = app_module.get_user_store()
    user = store.create_user(
        name="pending-kasse",
        role=app_module.Role.KASSIERER,
        active=True,
        username="pending-kasse",
        password_hash=store.hash_password("pending-passwort"),
    )

    login_response = test_client.post(
        "/auth/login",
        json={"username": "pending-kasse", "password": "pending-passwort", "device_id": "android-pending-1"},
    )
    assert login_response.status_code == 200

    admin_login_response = test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )
    assert admin_login_response.status_code == 302

    page_response = test_client.get("/admin/web/users")
    assert page_response.status_code == 200
    page = page_response.get_data(as_text=True)
    assert "android-pending-1" in page
    assert "pending-kasse" in page

    assign_response = test_client.post(
        "/admin/web/devices",
        data={"device_id": "android-pending-1", "user_id": str(user.id)},
    )
    assert assign_response.status_code == 302
    assignment = app_module.get_device_registry().get_device("android-pending-1")
    assert assignment is not None
    assert assignment.user_id == user.id


def test_admin_web_product_page_create_and_update(client):
    test_client, app_module = client
    login_response = test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )
    assert login_response.status_code == 302

    page_response = test_client.get("/admin/web/products")
    assert page_response.status_code == 200
    assert "Produktverwaltung" in page_response.get_data(as_text=True)

    create_response = test_client.post(
        "/admin/web/products",
        data={"action": "create", "name": "Web Mate", "price": "2,30", "active": "on"},
    )
    assert create_response.status_code == 302
    assert create_response.headers["Location"].endswith("/admin/web/products")

    store = app_module.get_product_store()
    product = next(product for product in store.list_products() if product.name == "Web Mate")
    product_id = product.id
    assert product.price_cents == 230
    assert product.active is True

    update_response = test_client.post(
        "/admin/web/products",
        data={
            "action": "update",
            "product_id": str(product_id),
            "name": "Web Mate Gross",
            "price": "2.50",
        },
    )
    assert update_response.status_code == 302

    updated = next(product for product in store.list_products() if product.id == product_id)
    assert updated.name == "Web Mate Gross"
    assert updated.price_cents == 250
    assert updated.active is False

    delete_response = test_client.post(
        "/admin/web/products",
        data={"action": "delete", "product_id": str(product_id)},
    )
    assert delete_response.status_code == 302
    assert all(product.id != product_id for product in store.list_products())
