import logging
import os
from functools import wraps
from typing import Any, Dict

from device_registry import get_device, list_devices, register_device

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
import stripe

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


class APIError(Exception):
    def __init__(self, message: str, status_code: int = 400, extra: Dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.extra = extra or {}


def handle_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as api_err:
            logger.warning("API error: %s", api_err)
            response = {"error": str(api_err)}
            response.update(api_err.extra)
            return jsonify(response), api_err.status_code
        except stripe.error.StripeError as err:
            logger.exception("Stripe error while processing request")
            return jsonify({"error": str(err)}), 500
        except Exception as err:  # noqa: BLE001
            logger.exception("Unhandled error")
            return jsonify({"error": "Internal server error"}), 500

    return wrapper


def validate_amount_cents(amount_cents: Any) -> int:
    try:
        value = int(amount_cents)
    except (TypeError, ValueError):
        raise APIError("amount_cents must be an integer representing cents", 400)
    if value <= 0:
        raise APIError("amount_cents must be greater than zero", 400)
    return value


def get_authenticated_user() -> Dict[str, str]:
    user_id = request.headers.get("X-User-Id")
    role = request.headers.get("X-User-Role")
    if not user_id or not role:
        raise APIError("Authentifizierung erforderlich.", 401)
    return {"user_id": user_id, "role": role}


def require_admin() -> Dict[str, str]:
    auth = get_authenticated_user()
    if auth["role"] != "admin":
        raise APIError("Adminrechte erforderlich.", 403)
    return auth


def parse_required_string(payload: Dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise APIError(f"{field} fehlt oder ist ungültig.", 400)
    return value.strip()


@app.route("/terminal/connection_token", methods=["POST"])
@handle_errors
def create_connection_token():
    token = stripe.terminal.ConnectionToken.create()
    return jsonify({"secret": token.secret})


@app.route("/admin/devices", methods=["POST"])
@handle_errors
def assign_device():
    require_admin()
    payload = request.get_json(force=True, silent=True) or {}
    device_id = parse_required_string(payload, "device_id")
    user_id = parse_required_string(payload, "user_id")
    role = parse_required_string(payload, "role")

    register_device(device_id=device_id, user_id=user_id, role=role)
    return jsonify({"device_id": device_id, "user_id": user_id, "role": role}), 201


@app.route("/admin/devices", methods=["GET"])
@handle_errors
def list_device_assignments():
    require_admin()
    devices = [
        {"device_id": assignment.device_id, "user_id": assignment.user_id, "role": assignment.role}
        for assignment in list_devices()
    ]
    return jsonify({"devices": devices})


@app.route("/pos/create_intent", methods=["POST"])
@handle_errors
def create_payment_intent():
    auth = get_authenticated_user()
    payload = request.get_json(force=True, silent=True) or {}
    amount_cents = validate_amount_cents(payload.get("amount_cents"))
    currency = payload.get("currency", "eur")
    item = payload.get("item", "unknown")
    kassierer = payload.get("kassierer", "unbekannt")
    device = payload.get("android_id") or payload.get("device")
    if not device:
        raise APIError("Gerät fehlt.", 400)

    assignment = get_device(str(device))
    if assignment is None:
        raise APIError("Gerät ist nicht registriert.", 403)
    if assignment.user_id != auth["user_id"]:
        raise APIError("Gerät gehört nicht zum angemeldeten Benutzer.", 403)

    description = "DARC e.V. OV L11 Getränke"
    metadata = {
        "club": "DARC e.V. OV L11",
        "item": str(item),
        "kassierer": str(kassierer),
        "device": str(device),
        "user_id": str(assignment.user_id),
        "role": str(assignment.role),
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
