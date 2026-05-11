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


def test_landing_page_links_latest_apk(client, monkeypatch, tmp_path):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "APK_DOWNLOAD_DIR", tmp_path)
    (tmp_path / "club-payment-1.0.9-release-signed.apk").write_bytes(b"old")
    (tmp_path / "club-payment-1.0.10-release-signed.apk").write_bytes(b"new")

    response = test_client.get("/")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Club Kasse" in page
    assert "Android-App herunterladen" in page
    assert "Version 1.0.10" in page
    assert "Version 1.0.10 - &copy;" in page
    assert "/apk/latest" in page


def test_latest_apk_downloads_newest_file(client, monkeypatch, tmp_path):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "APK_DOWNLOAD_DIR", tmp_path)
    (tmp_path / "club-payment-1.0.9-release-signed.apk").write_bytes(b"old")
    (tmp_path / "club-payment-1.0.10-release-signed.apk").write_bytes(b"new")

    response = test_client.get("/apk/latest")

    assert response.status_code == 200
    assert response.data == b"new"
    assert response.mimetype == "application/vnd.android.package-archive"
    assert "club-payment-1.0.10-release-signed.apk" in response.headers["Content-Disposition"]


def test_latest_apk_returns_404_when_missing(client, monkeypatch, tmp_path):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "APK_DOWNLOAD_DIR", tmp_path)

    response = test_client.get("/apk/latest")

    assert response.status_code == 404
    assert response.get_data(as_text=True) == "Keine APK verfuegbar"


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


def test_terminal_config_uses_configured_location(client, monkeypatch):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "STRIPE_LOCATION_ID", "tml_configured")

    response = test_client.get(
        "/terminal/config",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"location_id": "tml_configured"}


def test_terminal_config_uses_existing_stripe_location(client, monkeypatch):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "STRIPE_LOCATION_ID", "")

    class DummyLocation:
        id = "tml_existing"

    class DummyLocations:
        data = [DummyLocation()]

    def fake_list(limit):
        assert limit == 100
        return DummyLocations()

    monkeypatch.setattr(app_module.stripe.terminal.Location, "list", staticmethod(fake_list))

    response = test_client.get(
        "/terminal/config",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"location_id": "tml_existing"}


def test_terminal_config_creates_location_when_missing(client, monkeypatch):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "STRIPE_LOCATION_ID", "")

    class EmptyLocations:
        data = []

    class DummyLocation:
        id = "tml_created"

    def fake_list(limit):
        return EmptyLocations()

    def fake_create(**kwargs):
        assert kwargs["display_name"] == "DARC OV L11 Club Kasse"
        assert kwargs["address"]["country"] == "DE"
        assert kwargs["metadata"]["created_by"] == "club-payment-backend"
        return DummyLocation()

    monkeypatch.setattr(app_module.stripe.terminal.Location, "list", staticmethod(fake_list))
    monkeypatch.setattr(app_module.stripe.terminal.Location, "create", staticmethod(fake_create))

    response = test_client.get(
        "/terminal/config",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"location_id": "tml_created"}


def test_terminal_config_creates_location_after_empty_stripe_location(client, monkeypatch):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "STRIPE_LOCATION_ID", "")
    monkeypatch.setattr(app_module, "STRIPE_SECRET_KEY", "sk_live_dummy")

    class DummyLocation:
        id = None

    class DummyLocations:
        data = [DummyLocation()]

    class CreatedLocation:
        id = "tml_created_live"

    def fake_list(limit):
        assert limit == 100
        return DummyLocations()

    def fake_create(**kwargs):
        assert kwargs["display_name"] == "DARC OV L11 Club Kasse"
        return CreatedLocation()

    monkeypatch.setattr(app_module.stripe.terminal.Location, "list", staticmethod(fake_list))
    monkeypatch.setattr(app_module.stripe.terminal.Location, "create", staticmethod(fake_create))

    response = test_client.get(
        "/terminal/config",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"location_id": "tml_created_live"}


def test_terminal_config_rejects_empty_created_location(client, monkeypatch):
    test_client, app_module = client
    monkeypatch.setattr(app_module, "STRIPE_LOCATION_ID", "")

    class EmptyLocations:
        data = []

    class CreatedLocation:
        id = None

    def fake_list(limit):
        assert limit == 100
        return EmptyLocations()

    def fake_create(**kwargs):
        return CreatedLocation()

    monkeypatch.setattr(app_module.stripe.terminal.Location, "list", staticmethod(fake_list))
    monkeypatch.setattr(app_module.stripe.terminal.Location, "create", staticmethod(fake_create))

    response = test_client.get(
        "/terminal/config",
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 400
    assert "automatisch angelegt" in response.get_json()["error"]


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

    delete_response = test_client.delete(
        "/admin/devices/kasse-02",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert delete_response.status_code == 200
    assert delete_response.get_json() == {"deleted": True, "device_id": "kasse-02"}

    list_after_delete_response = test_client.get(
        "/admin/devices",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert list_after_delete_response.status_code == 200
    assert all(device["device_id"] != "kasse-02" for device in list_after_delete_response.get_json()["devices"])


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


def test_cashier_web_login_redirects_to_payments_view_only(client, monkeypatch):
    test_client, app_module = client
    store = app_module.get_user_store()
    store.create_user(
        name="cashier-web",
        role=app_module.Role.KASSIERER,
        active=True,
        username="cashier-web",
        password_hash=store.hash_password("cashier-passwort"),
    )

    login_response = test_client.post(
        "/admin/web/login",
        data={"username": "cashier-web", "password": "cashier-passwort"},
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/admin/web/payments")

    class DummyCharge:
        id = "ch_cashier"
        amount = 150
        amount_refunded = 0
        currency = "eur"
        refunded = False
        receipt_url = "https://pay.stripe.com/receipts/cashier"

    class DummyIntent:
        id = "pi_cashier"
        created = 1710000000
        status = "succeeded"
        amount = 150
        currency = "eur"
        latest_charge = DummyCharge()
        metadata = {"club": "DARC e.V. OV L11", "item": "Cola"}

    class DummyIntentList:
        data = [DummyIntent()]

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "list", staticmethod(lambda **kwargs: DummyIntentList()))

    response = test_client.get("/admin/web/payments")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Zahlungen" in page
    assert "Nutzer &amp; Ger" not in page
    assert "Produkte" not in page
    assert "Konto" in page
    assert "nur Ansicht" in page
    assert "Erstatten" not in page


def test_cashier_web_cannot_open_admin_management_pages(client):
    test_client, app_module = client
    store = app_module.get_user_store()
    store.create_user(
        name="cashier-limited",
        role=app_module.Role.KASSIERER,
        active=True,
        username="cashier-limited",
        password_hash=store.hash_password("cashier-passwort"),
    )
    test_client.post(
        "/admin/web/login",
        data={"username": "cashier-limited", "password": "cashier-passwort"},
    )

    users_response = test_client.get("/admin/web/users")
    products_response = test_client.get("/admin/web/products")
    devices_response = test_client.post("/admin/web/devices", data={"device_id": "x", "user_id": "1"})

    assert users_response.status_code == 302
    assert users_response.headers["Location"].endswith("/admin/web/payments")
    assert products_response.status_code == 302
    assert products_response.headers["Location"].endswith("/admin/web/payments")
    assert devices_response.status_code == 302
    assert devices_response.headers["Location"].endswith("/admin/web/payments")


def test_cashier_web_cannot_refund_payments(client, monkeypatch):
    test_client, app_module = client
    store = app_module.get_user_store()
    store.create_user(
        name="cashier-no-refund",
        role=app_module.Role.KASSIERER,
        active=True,
        username="cashier-no-refund",
        password_hash=store.hash_password("cashier-passwort"),
    )
    test_client.post(
        "/admin/web/login",
        data={"username": "cashier-no-refund", "password": "cashier-passwort"},
    )

    class DummyIntentList:
        data = []

    called = {"refund": False}

    def fake_refund_create(**kwargs):
        called["refund"] = True

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "list", staticmethod(lambda **kwargs: DummyIntentList()))
    monkeypatch.setattr(app_module.stripe.Refund, "create", staticmethod(fake_refund_create))

    response = test_client.post(
        "/admin/web/payments",
        data={"action": "refund", "payment_intent_id": "pi_cashier", "refund_amount": "1,50"},
    )

    assert response.status_code == 200
    assert "Nur Administratoren duerfen Rueckerstattungen ausloesen" in response.get_data(as_text=True)
    assert called["refund"] is False


def test_web_account_password_change_for_cashier(client):
    test_client, app_module = client
    store = app_module.get_user_store()
    cashier = store.create_user(
        name="cashier-password",
        role=app_module.Role.KASSIERER,
        active=True,
        username="cashier-password",
        password_hash=store.hash_password("old-passwort"),
    )
    test_client.post(
        "/admin/web/login",
        data={"username": "cashier-password", "password": "old-passwort"},
    )

    response = test_client.post(
        "/admin/web/account",
        data={
            "current_password": "old-passwort",
            "new_password": "new-passwort",
            "confirm_password": "new-passwort",
        },
    )

    assert response.status_code == 200
    assert "Passwort wurde aktualisiert" in response.get_data(as_text=True)
    assert store.authenticate("cashier-password", "old-passwort") is None
    assert store.authenticate("cashier-password", "new-passwort").id == cashier.id


def test_web_account_rejects_wrong_current_password(client):
    test_client, app_module = client
    store = app_module.get_user_store()
    store.create_user(
        name="cashier-wrong-password",
        role=app_module.Role.KASSIERER,
        active=True,
        username="cashier-wrong-password",
        password_hash=store.hash_password("old-passwort"),
    )
    test_client.post(
        "/admin/web/login",
        data={"username": "cashier-wrong-password", "password": "old-passwort"},
    )

    response = test_client.post(
        "/admin/web/account",
        data={
            "current_password": "falsch",
            "new_password": "new-passwort",
            "confirm_password": "new-passwort",
        },
    )

    assert response.status_code == 200
    assert "Aktuelles Passwort ist falsch" in response.get_data(as_text=True)
    assert store.authenticate("cashier-wrong-password", "old-passwort") is not None


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

    delete_response = test_client.post(
        "/admin/web/devices",
        data={"action": "delete", "device_id": "web-kasse-2"},
    )
    assert delete_response.status_code == 302
    assert delete_response.headers["Location"].endswith("/admin/web/users")
    assert app_module.get_device_registry().get_device("web-kasse-2") is None


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


def test_admin_web_payments_page_lists_successful_payments(client, monkeypatch):
    test_client, app_module = client
    test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )

    class DummyCharge:
        id = "ch_paid"
        amount = 500
        amount_refunded = 100
        currency = "eur"
        refunded = False
        receipt_url = "https://pay.stripe.com/receipts/test"
        balance_transaction = "txn_paid"

    class DummyIntent:
        id = "pi_paid"
        created = 1710000000
        status = "succeeded"
        amount = 500
        currency = "eur"
        latest_charge = DummyCharge()
        metadata = {
            "club": "DARC e.V. OV L11",
            "item": "Cola",
            "kassierer": "admin",
            "device": "android-1",
        }

    class DummyIntentList:
        data = [DummyIntent()]

    class DummyBalanceTransaction:
        id = "txn_paid"
        status = "available"
        available_on = 1710086400
        payout = "po_paid"

    class DummyPayout:
        id = "po_paid"
        status = "paid"
        arrival_date = 1710172800

    def fake_list(**kwargs):
        assert kwargs["limit"] == 100
        assert kwargs["expand"] == ["data.latest_charge", "data.latest_charge.balance_transaction"]
        return DummyIntentList()

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "list", staticmethod(fake_list))
    monkeypatch.setattr(
        app_module.stripe.BalanceTransaction,
        "retrieve",
        staticmethod(lambda balance_transaction_id: DummyBalanceTransaction()),
    )
    monkeypatch.setattr(app_module.stripe.Payout, "retrieve", staticmethod(lambda payout_id: DummyPayout()))

    response = test_client.get("/admin/web/payments")

    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Zahlungen" in page
    assert "Cola" in page
    assert "admin" in page
    assert "android-1" in page
    assert "https://pay.stripe.com/receipts/test" in page
    assert "ausgezahlt" in page
    assert "po_paid" in page
    assert "Erstatten" in page


def test_admin_web_payments_refund_success(client, monkeypatch):
    test_client, app_module = client
    test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )

    class DummyCharge:
        id = "ch_paid"
        amount = 500
        amount_refunded = 100
        currency = "eur"
        refunded = False
        receipt_url = "https://pay.stripe.com/receipts/test"

    class DummyIntent:
        id = "pi_paid"
        created = 1710000000
        status = "succeeded"
        amount = 500
        currency = "eur"
        latest_charge = DummyCharge()
        metadata = {"club": "DARC e.V. OV L11", "item": "Cola"}

    class DummyIntentList:
        data = [DummyIntent()]

    def fake_retrieve(payment_intent_id, **kwargs):
        assert payment_intent_id == "pi_paid"
        assert kwargs["expand"] == ["latest_charge"]
        return DummyIntent()

    created_refund = {}

    def fake_refund_create(**kwargs):
        created_refund.update(kwargs)
        return object()

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "retrieve", staticmethod(fake_retrieve))
    monkeypatch.setattr(app_module.stripe.PaymentIntent, "list", staticmethod(lambda **kwargs: DummyIntentList()))
    monkeypatch.setattr(app_module.stripe.Refund, "create", staticmethod(fake_refund_create))

    response = test_client.post(
        "/admin/web/payments",
        data={
            "action": "refund",
            "payment_intent_id": "pi_paid",
            "refund_amount": "4,00",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert created_refund == {
        "payment_intent": "pi_paid",
        "amount": 400,
        "reason": "requested_by_customer",
        "metadata": {"refunded_by": "club-payment-admin"},
    }
    assert "4,00 EUR wurden erstattet." in response.get_data(as_text=True)


def test_admin_web_payments_refund_rejects_too_large_amount(client, monkeypatch):
    test_client, app_module = client
    test_client.post(
        "/admin/web/login",
        data={"username": "admin", "password": "admin-passwort"},
    )

    class DummyCharge:
        amount = 500
        amount_refunded = 100
        currency = "eur"
        refunded = False

    class DummyIntent:
        id = "pi_paid"
        created = 1710000000
        status = "succeeded"
        amount = 500
        currency = "eur"
        latest_charge = DummyCharge()
        metadata = {"club": "DARC e.V. OV L11"}

    class DummyIntentList:
        data = [DummyIntent()]

    monkeypatch.setattr(app_module.stripe.PaymentIntent, "retrieve", staticmethod(lambda *args, **kwargs: DummyIntent()))
    monkeypatch.setattr(app_module.stripe.PaymentIntent, "list", staticmethod(lambda **kwargs: DummyIntentList()))

    response = test_client.post(
        "/admin/web/payments",
        data={
            "action": "refund",
            "payment_intent_id": "pi_paid",
            "refund_amount": "4,01",
        },
    )

    assert response.status_code == 200
    assert "Rueckerstattung darf den offenen Betrag nicht ueberschreiten" in response.get_data(as_text=True)
