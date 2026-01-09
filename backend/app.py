import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import stripe

from auth import authenticate_request
from device_registry import get_device_registry
from errors import APIError, handle_errors, validate_amount_cents
from users import Role, get_user_store

load_dotenv()

app = Flask(__name__)

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

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


@app.route("/terminal/connection_token", methods=["POST"])
@handle_errors
def create_connection_token():
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

    kassierer = assigned_user.name

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
    assignment = registry.assign_device(device_id=device_id, user_id=user.id)
    return jsonify({
        "device_id": assignment.device_id,
        "user_id": assignment.user_id,
        "role": user.role.value,
        "name": user.name,
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
            "name": user.name if user else None,
            "role": user.role.value if user else None,
            "active": user.active if user else None,
        })
    return jsonify({"devices": devices})


@app.route("/admin/users", methods=["POST"])
@handle_errors
def create_user():
    authenticate_request(request, require_admin=True)
    payload = request.get_json(force=True, silent=True) or {}
    name = payload.get("name")
    role_value = payload.get("role")
    active = payload.get("active", True)
    api_token = payload.get("api_token")
    username = payload.get("username")
    password = payload.get("password")

    if not isinstance(name, str) or not name.strip():
        raise APIError("name ist erforderlich", 400)
    if role_value not in {Role.ADMIN.value, Role.KASSIERER.value}:
        raise APIError("role muss 'admin' oder 'kassierer' sein", 400)
    if not isinstance(active, bool):
        raise APIError("active muss ein boolescher Wert sein", 400)
    if username is not None and (not isinstance(username, str) or not username.strip()):
        raise APIError("username darf nicht leer sein", 400)
    if password is not None and (not isinstance(password, str) or not password.strip()):
        raise APIError("password darf nicht leer sein", 400)
    if (username is None) != (password is None):
        raise APIError("username und password müssen gemeinsam gesetzt werden", 400)

    store = get_user_store()
    if isinstance(username, str) and store.get_by_username(username):
        raise APIError("username ist bereits vergeben", 400)

    password_hash = store.hash_password(password) if isinstance(password, str) else None
    user = store.create_user(
        name=name.strip(),
        role=Role(role_value),
        active=active,
        api_token=api_token,
        username=username.strip() if isinstance(username, str) else None,
        password_hash=password_hash,
    )
    return jsonify({
        "id": user.id,
        "name": user.name,
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

    return jsonify({
        "token": user.api_token,
        "display_name": user.name,
    })


@app.route("/admin/users", methods=["GET"])
@handle_errors
def list_users():
    authenticate_request(request, require_admin=True)
    store = get_user_store()
    users = [
        {"id": user.id, "name": user.name, "role": user.role.value, "active": user.active}
        for user in store.list_users()
    ]
    return jsonify({"users": users})


@app.route("/admin/users/<int:user_id>", methods=["PATCH"])
@handle_errors
def update_user(user_id: int):
    authenticate_request(request, require_admin=True)
    payload = request.get_json(force=True, silent=True) or {}
    name = payload.get("name")
    role_value = payload.get("role")
    active = payload.get("active")

    role = None
    if role_value is not None:
        if role_value not in {Role.ADMIN.value, Role.KASSIERER.value}:
            raise APIError("role muss 'admin' oder 'kassierer' sein", 400)
        role = Role(role_value)
    if active is not None and not isinstance(active, bool):
        raise APIError("active muss ein boolescher Wert sein", 400)
    if name is not None and (not isinstance(name, str) or not name.strip()):
        raise APIError("name darf nicht leer sein", 400)

    store = get_user_store()
    user = store.update_user(
        user_id=user_id,
        name=name.strip() if isinstance(name, str) else None,
        role=role,
        active=active,
    )
    if not user:
        raise APIError("User nicht gefunden", 404)
    return jsonify({
        "id": user.id,
        "name": user.name,
        "role": user.role.value,
        "active": user.active,
    })


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
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
