import logging
from functools import wraps
from typing import Any, Dict

from flask import jsonify
import stripe

logger = logging.getLogger(__name__)


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
        except Exception:  # noqa: BLE001
            logger.exception("Unhandled error")
            return jsonify({"error": "Internal server error"}), 500

    return wrapper


def validate_amount_cents(amount_cents: Any) -> int:
    try:
        value = int(amount_cents)
    except (TypeError, ValueError):
        raise APIError("amount_cents muss eine ganze Zahl in Cent sein", 400)
    if value <= 0:
        raise APIError("amount_cents muss größer als Null sein", 400)
    return value
