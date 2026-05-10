import logging
import os
import secrets
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_cors import CORS
import stripe

from auth import authenticate_request
from device_registry import get_device_registry
from errors import APIError, handle_errors, validate_amount_cents
from products import get_product_store
from users import Role, get_user_store

load_dotenv()

app = Flask(__name__)

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    logger.warning("FLASK_SECRET_KEY is not set; using an ephemeral development secret.")
    FLASK_SECRET_KEY = secrets.token_hex(32)
app.secret_key = FLASK_SECRET_KEY

# Stripe configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY is not set. Provide it via environment variable or .env file.")
stripe.api_key = STRIPE_SECRET_KEY
stripe.api_version = "2024-06-20"

# CORS configuration
raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
CORS(app, origins=allowed_origins or "*")

WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


def _get_admin_user_from_session():
    user_id = session.get("admin_user_id")
    if not isinstance(user_id, int):
        return None
    store = get_user_store()
    user = store.get_by_id(user_id)
    if not user or not user.active or user.role != Role.ADMIN:
        session.pop("admin_user_id", None)
        return None
    return user


def _format_price_euros(price_cents: int) -> str:
    return f"{price_cents / 100:.2f}".replace(".", ",")


def _user_identifier(user) -> str:
    return user.username or user.name


def _active_admin_count() -> int:
    store = get_user_store()
    return sum(1 for user in store.list_users() if user.active and user.role == Role.ADMIN)


def _would_remove_last_active_admin(user, role: Role | None = None, active: bool | None = None) -> bool:
    next_role = role if role is not None else user.role
    next_active = active if active is not None else user.active
    if user.role != Role.ADMIN or not user.active:
        return False
    if next_role == Role.ADMIN and next_active:
        return False
    return _active_admin_count() <= 1


def _parse_price_cents_from_form(value: str | None) -> int:
    if not isinstance(value, str) or not value.strip():
        raise APIError("preis ist erforderlich", 400)
    try:
        euros = Decimal(value.strip().replace(",", "."))
    except InvalidOperation:
        raise APIError("preis muss eine Zahl sein", 400)
    cents = euros * 100
    if cents != cents.to_integral_value():
        raise APIError("preis darf hoechstens zwei Nachkommastellen haben", 400)
    return validate_amount_cents(int(cents))


def _render_admin_users(admin_user, error_message: str | None = None):
    store = get_user_store()
    users = list(store.list_users())
    registry = get_device_registry()
    assignments = {assignment.user_id: assignment.device_id for assignment in registry.list_devices()}
    devices = []
    for assignment in registry.list_devices():
        user = store.get_by_id(assignment.user_id)
        devices.append({
            "device_id": assignment.device_id,
            "user": user,
        })
    pending_devices = list(registry.list_pending_devices())
    return render_template(
        "admin_users.html",
        admin_name=_user_identifier(admin_user),
        users=users,
        assignments=assignments,
        devices=devices,
        pending_devices=pending_devices,
        user_identifier=_user_identifier,
        error_message=error_message,
    )


def _render_admin_products(admin_user, error_message: str | None = None):
    store = get_product_store()
    return render_template(
        "admin_products.html",
        admin_name=_user_identifier(admin_user),
        products=list(store.list_products()),
        format_price_euros=_format_price_euros,
        error_message=error_message,
    )


@app.route("/terminal/connection_token", methods=["POST"])
@handle_errors
def create_connection_token():
    authenticate_request(request)
    token = stripe.terminal.ConnectionToken.create()
    return jsonify({"secret": token.secret})


@app.route("/pos/create_intent", methods=["POST"])
@handle_errors
def create_payment_intent():
    user = authenticate_request(request)
    payload = request.get_json(force=True, silent=True) or {}
    amount_cents = validate_amount_cents(payload.get("amount_cents"))
    currency = payload.get("currency", "eur")
    item = payload.get("item", "unknown")
    device = payload.get("device") or payload.get("android_id") or payload.get("device_id")
    if not isinstance(device, str) or not device.strip():
        raise APIError("device ist erforderlich", 400)

    registry = get_device_registry()
    assignment = registry.get_device(device)
    if not assignment:
        raise APIError("Gerät ist nicht registriert", 403)

    store = get_user_store()
    assigned_user = store.get_by_id(assignment.user_id)
    if not assigned_user:
        raise APIError("Zugeordneter Benutzer existiert nicht", 400)
    if assigned_user.id != user.id:
        raise APIError("Gerät gehört nicht zum angemeldeten Benutzer", 403)

    kassierer = _user_identifier(assigned_user)

    description = "DARC e.V. OV L11 Getränke"
    metadata = {
        "club": "DARC e.V. OV L11",
        "item": str(item),
        "kassierer": str(kassierer),
        "device": str(device),
        "user_id": str(assigned_user.id),
        "role": assigned_user.role.value,
    }

    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency,
        description=description,
        payment_method_types=["card_present"],
        capture_method="automatic",
        metadata=metadata,
    )
    return jsonify({
        "id": intent.id,
        "client_secret": intent.client_secret,
        "amount_cents": intent.amount,
    })


@app.route("/pos/receipt/<string:payment_intent_id>", methods=["GET"])
@handle_errors
def get_receipt(payment_intent_id: str):
    authenticate_request(request)
    if not payment_intent_id.strip():
        raise APIError("payment_intent_id ist erforderlich", 400)
    intent = stripe.PaymentIntent.retrieve(
        payment_intent_id,
        expand=["latest_charge", "charges"],
    )
    charge = intent.latest_charge
    if not charge and getattr(intent, "charges", None) and intent.charges.data:
        charge = intent.charges.data[0]
    receipt_url = getattr(charge, "receipt_url", None) if charge else None
    if not receipt_url:
        raise APIError("Beleg-URL nicht verfügbar", 404)
    return jsonify({"receipt_url": receipt_url})


@app.route("/admin/devices", methods=["POST"])
@handle_errors
def assign_device():
    authenticate_request(request, require_admin=True)
    payload = request.get_json(force=True, silent=True) or {}
    device_id = payload.get("device_id") or payload.get("device") or payload.get("android_id")
    user_id = payload.get("user_id")

    if not isinstance(device_id, str) or not device_id.strip():
        raise APIError("device_id ist erforderlich", 400)
    try:
        user_id_value = int(user_id)
    except (TypeError, ValueError):
        raise APIError("user_id muss eine ganze Zahl sein", 400)

    store = get_user_store()
    user = store.get_by_id(user_id_value)
    if not user:
        raise APIError("User nicht gefunden", 404)

    registry = get_device_registry()
    assignment = registry.assign_device(device_id=device_id.strip(), user_id=user.id)
    return jsonify({
        "device_id": assignment.device_id,
        "user_id": assignment.user_id,
        "role": user.role.value,
        "name": _user_identifier(user),
        "username": user.username,
    }), 201


@app.route("/admin/devices", methods=["GET"])
@handle_errors
def list_devices():
    authenticate_request(request, require_admin=True)
    registry = get_device_registry()
    store = get_user_store()
    devices = []
    for assignment in registry.list_devices():
        user = store.get_by_id(assignment.user_id)
        devices.append({
            "device_id": assignment.device_id,
            "user_id": assignment.user_id,
            "name": _user_identifier(user) if user else None,
            "username": user.username if user else None,
            "role": user.role.value if user else None,
            "active": user.active if user else None,
        })
    pending_devices = [
        {
            "device_id": pending.device_id,
            "user_id": pending.user_id,
            "username": pending.username,
            "last_seen_at": pending.last_seen_at.isoformat(),
        }
        for pending in registry.list_pending_devices()
    ]
    return jsonify({"devices": devices, "pending_devices": pending_devices})


@app.route("/admin/users", methods=["POST"])
@handle_errors
def create_user():
    authenticate_request(request, require_admin=True)
    payload = request.get_json(force=True, silent=True) or {}
    role_value = payload.get("role")
    active = payload.get("active", True)
    username = payload.get("username")
    password = payload.get("password")

    if role_value not in {Role.ADMIN.value, Role.KASSIERER.value}:
        raise APIError("role muss 'admin' oder 'kassierer' sein", 400)
    if not isinstance(active, bool):
        raise APIError("active muss ein boolescher Wert sein", 400)
    if not isinstance(username, str) or not username.strip():
        raise APIError("username ist erforderlich", 400)
    if not isinstance(password, str) or not password.strip():
        raise APIError("password ist erforderlich", 400)

    store = get_user_store()
    normalized_username = username.strip()
    if store.get_by_username(normalized_username):
        raise APIError("username ist bereits vergeben", 400)

    password_hash = store.hash_password(password)
    user = store.create_user(
        name=normalized_username,
        role=Role(role_value),
        active=active,
        username=normalized_username,
        password_hash=password_hash,
    )
    return jsonify({
        "id": user.id,
        "name": _user_identifier(user),
        "username": user.username,
        "role": user.role.value,
        "active": user.active,
        "api_token": user.api_token,
    }), 201


@app.route("/auth/login", methods=["POST"])
@handle_errors
def login():
    payload = request.get_json(force=True, silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    device_id = payload.get("device_id") or payload.get("device") or payload.get("android_id")

    if not isinstance(username, str) or not username.strip():
        raise APIError("username ist erforderlich", 400)
    if not isinstance(password, str) or not password.strip():
        raise APIError("password ist erforderlich", 400)

    store = get_user_store()
    user = store.authenticate(username.strip(), password)
    if not user:
        raise APIError("Benutzername oder Passwort ungültig", 401)
    if not user.active:
        raise APIError("Benutzer ist deaktiviert", 403)

    device_pending = False
    if isinstance(device_id, str) and device_id.strip():
        registry = get_device_registry()
        pending_device = registry.remember_pending_device(
            device_id=device_id.strip(),
            user_id=user.id,
            username=_user_identifier(user),
        )
        device_pending = pending_device is not None

    return jsonify({
        "token": user.api_token,
        "display_name": _user_identifier(user),
        "device_pending": device_pending,
    })


@app.route("/admin/web/login", methods=["GET", "POST"])
def admin_web_login():
    if _get_admin_user_from_session():
        return redirect(url_for("admin_web_users"))

    error_message = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not isinstance(username, str) or not username.strip():
            error_message = "username ist erforderlich"
        elif not isinstance(password, str) or not password.strip():
            error_message = "password ist erforderlich"
        else:
            store = get_user_store()
            user = store.authenticate(username.strip(), password)
            if not user:
                error_message = "Benutzername oder Passwort ungültig"
            elif not user.active:
                error_message = "Benutzer ist deaktiviert"
            elif user.role != Role.ADMIN:
                error_message = "Nur Administratoren dürfen diese Aktion ausführen"
            else:
                session["admin_user_id"] = user.id
                return redirect(url_for("admin_web_users"))

    return render_template("admin_login.html", error_message=error_message)


@app.route("/admin/web/logout", methods=["POST"])
def admin_web_logout():
    session.pop("admin_user_id", None)
    return redirect(url_for("admin_web_login"))


@app.route("/admin/web")
def admin_web_index():
    if not _get_admin_user_from_session():
        return redirect(url_for("admin_web_login"))
    return redirect(url_for("admin_web_users"))


@app.route("/admin/web/users", methods=["GET", "POST"])
def admin_web_users():
    admin_user = _get_admin_user_from_session()
    if not admin_user:
        return redirect(url_for("admin_web_login"))

    error_message = None
    if request.method == "POST":
        action = request.form.get("action", "create")
        role_value = request.form.get("role")
        username = request.form.get("username")
        password = request.form.get("password")
        active = request.form.get("active") == "on"
        store = get_user_store()

        try:
            if action == "delete":
                try:
                    user_id = int(request.form.get("user_id"))
                except (TypeError, ValueError):
                    raise APIError("user_id muss eine ganze Zahl sein", 400)
                user = store.get_by_id(user_id)
                if not user:
                    raise APIError("User nicht gefunden", 404)
                if user.id == admin_user.id:
                    raise APIError("Der eigene Admin-Nutzer kann hier nicht geloescht werden", 400)
                if _would_remove_last_active_admin(user, active=False):
                    raise APIError("Der letzte aktive Admin kann nicht geloescht werden", 400)
                registry = get_device_registry()
                registry.delete_devices_for_user(user.id)
                store.delete_user(user.id)
                return redirect(url_for("admin_web_users"))

            if role_value not in {Role.ADMIN.value, Role.KASSIERER.value}:
                raise APIError("role muss 'admin' oder 'kassierer' sein", 400)
            role = Role(role_value)
            if not isinstance(username, str) or not username.strip():
                raise APIError("username ist erforderlich", 400)
            normalized_username = username.strip()
            existing_user = store.get_by_username(normalized_username)

            if action == "create":
                if not isinstance(password, str) or not password.strip():
                    raise APIError("password ist erforderlich", 400)
                if existing_user:
                    raise APIError("username ist bereits vergeben", 400)
                store.create_user(
                    name=normalized_username,
                    role=role,
                    active=active,
                    username=normalized_username,
                    password_hash=store.hash_password(password),
                )
                return redirect(url_for("admin_web_users"))

            if action == "update":
                try:
                    user_id = int(request.form.get("user_id"))
                except (TypeError, ValueError):
                    raise APIError("user_id muss eine ganze Zahl sein", 400)
                user = store.get_by_id(user_id)
                if not user:
                    raise APIError("User nicht gefunden", 404)
                if existing_user and existing_user.id != user.id:
                    raise APIError("username ist bereits vergeben", 400)
                if _would_remove_last_active_admin(user, role=role, active=active):
                    raise APIError("Der letzte aktive Admin muss aktiv bleiben", 400)
                password_hash = store.hash_password(password) if isinstance(password, str) and password.strip() else None
                store.update_user(
                    user_id=user.id,
                    name=normalized_username,
                    role=role,
                    active=active,
                    username=normalized_username,
                    password_hash=password_hash,
                )
                return redirect(url_for("admin_web_users"))

            raise APIError("Unbekannte Aktion", 400)
        except APIError as err:
            error_message = str(err)

    return _render_admin_users(admin_user, error_message=error_message)


@app.route("/admin/web/devices", methods=["POST"])
def admin_web_devices():
    admin_user = _get_admin_user_from_session()
    if not admin_user:
        return redirect(url_for("admin_web_login"))

    device_id = request.form.get("device_id")
    user_id = request.form.get("user_id")
    error_message = None

    if not isinstance(device_id, str) or not device_id.strip():
        error_message = "device_id ist erforderlich"
    else:
        try:
            user_id_value = int(user_id)
        except (TypeError, ValueError):
            error_message = "user_id muss eine ganze Zahl sein"
        else:
            store = get_user_store()
            user = store.get_by_id(user_id_value)
            if not user:
                error_message = "User nicht gefunden"
            else:
                registry = get_device_registry()
                registry.assign_device(device_id=device_id.strip(), user_id=user.id)
                return redirect(url_for("admin_web_users"))

    return _render_admin_users(admin_user, error_message=error_message)


@app.route("/admin/web/products", methods=["GET", "POST"])
def admin_web_products():
    admin_user = _get_admin_user_from_session()
    if not admin_user:
        return redirect(url_for("admin_web_login"))

    error_message = None
    if request.method == "POST":
        action = request.form.get("action", "create")
        name = request.form.get("name")
        price = request.form.get("price")
        active = request.form.get("active") == "on"
        store = get_product_store()

        try:
            if action == "delete":
                try:
                    product_id = int(request.form.get("product_id"))
                except (TypeError, ValueError):
                    raise APIError("product_id muss eine ganze Zahl sein", 400)
                if not store.delete_product(product_id):
                    raise APIError("Produkt nicht gefunden", 404)
            else:
                if not isinstance(name, str) or not name.strip():
                    raise APIError("name ist erforderlich", 400)
                price_cents = _parse_price_cents_from_form(price)

            if action == "create":
                store.create_product(name=name.strip(), price_cents=price_cents, active=active)
            elif action == "update":
                try:
                    product_id = int(request.form.get("product_id"))
                except (TypeError, ValueError):
                    raise APIError("product_id muss eine ganze Zahl sein", 400)
                product = store.update_product(
                    product_id=product_id,
                    name=name.strip(),
                    price_cents=price_cents,
                    active=active,
                )
                if not product:
                    raise APIError("Produkt nicht gefunden", 404)
            elif action == "delete":
                pass
            else:
                raise APIError("Unbekannte Aktion", 400)
            return redirect(url_for("admin_web_products"))
        except APIError as err:
            error_message = str(err)

    return _render_admin_products(admin_user, error_message=error_message)


@app.route("/admin/users", methods=["GET"])
@handle_errors
def list_users():
    authenticate_request(request, require_admin=True)
    store = get_user_store()
    users = [
        {
            "id": user.id,
            "name": _user_identifier(user),
            "username": user.username,
            "role": user.role.value,
            "active": user.active,
        }
        for user in store.list_users()
    ]
    return jsonify({"users": users})


@app.route("/admin/users/<int:user_id>", methods=["PATCH"])
@handle_errors
def update_user(user_id: int):
    authenticate_request(request, require_admin=True)
    payload = request.get_json(force=True, silent=True) or {}
    username = payload.get("username")
    password = payload.get("password")
    role_value = payload.get("role")
    active = payload.get("active")

    role = None
    if role_value is not None:
        if role_value not in {Role.ADMIN.value, Role.KASSIERER.value}:
            raise APIError("role muss 'admin' oder 'kassierer' sein", 400)
        role = Role(role_value)
    if active is not None and not isinstance(active, bool):
        raise APIError("active muss ein boolescher Wert sein", 400)
    if username is not None and (not isinstance(username, str) or not username.strip()):
        raise APIError("username darf nicht leer sein", 400)
    if password is not None and (not isinstance(password, str) or not password.strip()):
        raise APIError("password darf nicht leer sein", 400)

    store = get_user_store()
    current_user = store.get_by_id(user_id)
    if not current_user:
        raise APIError("User nicht gefunden", 404)
    normalized_username = username.strip() if isinstance(username, str) else None
    if normalized_username:
        existing_user = store.get_by_username(normalized_username)
        if existing_user and existing_user.id != user_id:
            raise APIError("username ist bereits vergeben", 400)
    if _would_remove_last_active_admin(current_user, role=role, active=active):
        raise APIError("Der letzte aktive Admin muss aktiv bleiben", 400)
    user = store.update_user(
        user_id=user_id,
        name=normalized_username,
        role=role,
        active=active,
        username=normalized_username,
        password_hash=store.hash_password(password) if isinstance(password, str) else None,
    )
    return jsonify({
        "id": user.id,
        "name": _user_identifier(user),
        "username": user.username,
        "role": user.role.value,
        "active": user.active,
    })


@app.route("/admin/users/<int:user_id>", methods=["DELETE"])
@handle_errors
def delete_user(user_id: int):
    admin_user = authenticate_request(request, require_admin=True)
    store = get_user_store()
    user = store.get_by_id(user_id)
    if not user:
        raise APIError("User nicht gefunden", 404)
    if user.id == admin_user.id:
        raise APIError("Der eigene Admin-Nutzer kann nicht geloescht werden", 400)
    if _would_remove_last_active_admin(user, active=False):
        raise APIError("Der letzte aktive Admin kann nicht geloescht werden", 400)

    registry = get_device_registry()
    registry.delete_devices_for_user(user.id)
    store.delete_user(user.id)
    return jsonify({"deleted": True, "id": user_id})


@app.route("/admin/products", methods=["POST"])
@handle_errors
def create_product():
    authenticate_request(request, require_admin=True)
    payload = request.get_json(force=True, silent=True) or {}
    name = payload.get("name")
    price_cents = payload.get("price_cents")
    active = payload.get("active", True)

    if not isinstance(name, str) or not name.strip():
        raise APIError("name ist erforderlich", 400)
    if not isinstance(active, bool):
        raise APIError("active muss ein boolescher Wert sein", 400)

    store = get_product_store()
    product = store.create_product(
        name=name.strip(),
        price_cents=validate_amount_cents(price_cents),
        active=active,
    )
    return jsonify({
        "id": product.id,
        "name": product.name,
        "price_cents": product.price_cents,
        "active": product.active,
    }), 201


@app.route("/admin/products", methods=["GET"])
@handle_errors
def list_products():
    authenticate_request(request, require_admin=True)
    store = get_product_store()
    products = [
        {
            "id": product.id,
            "name": product.name,
            "price_cents": product.price_cents,
            "active": product.active,
        }
        for product in store.list_products()
    ]
    return jsonify({"products": products})


@app.route("/products", methods=["GET"])
@handle_errors
def list_active_products():
    authenticate_request(request)
    store = get_product_store()
    products = [
        {
            "id": product.id,
            "name": product.name,
            "price_cents": product.price_cents,
            "active": product.active,
        }
        for product in store.list_products()
        if product.active
    ]
    return jsonify({"products": products})


@app.route("/admin/products/<int:product_id>", methods=["PATCH"])
@handle_errors
def update_product(product_id: int):
    authenticate_request(request, require_admin=True)
    payload = request.get_json(force=True, silent=True) or {}
    name = payload.get("name")
    price_cents = payload.get("price_cents")
    active = payload.get("active")

    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise APIError("name darf nicht leer sein", 400)
    validated_price_cents = None
    if price_cents is not None:
        validated_price_cents = validate_amount_cents(price_cents)
    if active is not None and not isinstance(active, bool):
        raise APIError("active muss ein boolescher Wert sein", 400)
    if name is None and price_cents is None and active is None:
        raise APIError("Mindestens ein Feld zum Aktualisieren ist erforderlich", 400)

    store = get_product_store()
    product = store.update_product(
        product_id=product_id,
        name=name.strip() if isinstance(name, str) else None,
        price_cents=validated_price_cents,
        active=active,
    )
    if not product:
        raise APIError("Produkt nicht gefunden", 404)
    return jsonify({
        "id": product.id,
        "name": product.name,
        "price_cents": product.price_cents,
        "active": product.active,
    })


@app.route("/admin/products/<int:product_id>", methods=["DELETE"])
@handle_errors
def delete_product(product_id: int):
    authenticate_request(request, require_admin=True)
    store = get_product_store()
    if not store.delete_product(product_id):
        raise APIError("Produkt nicht gefunden", 404)
    return jsonify({"deleted": True, "id": product_id})


@app.route("/webhook", methods=["POST"])
@handle_errors
def webhook():
    if not WEBHOOK_SECRET:
        raise APIError("Webhook secret not configured", 400)

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except ValueError:
        raise APIError("Invalid payload", 400)
    except stripe.error.SignatureVerificationError:
        raise APIError("Invalid signature", 400)

    logger.info("Received event: %s", event["type"])
    with open("payments.log", "a", encoding="utf-8") as log_file:
        log_file.write(f"{event['id']} - {event['type']} - {event['created']}\n")

    return jsonify({"status": "received"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 4040)), debug=True)
