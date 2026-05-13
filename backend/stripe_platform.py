from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import stripe

from errors import APIError, validate_amount_cents
from organizations import Organization, get_organization_store
from users import User


DEFAULT_PLATFORM_FEE_BASIS_POINTS = 100
DEFAULT_TERMINAL_ADDRESS = {
    "line1": os.getenv("STRIPE_LOCATION_ADDRESS_LINE1", "DARC Ortsverband"),
    "city": os.getenv("STRIPE_LOCATION_ADDRESS_CITY", "Berlin"),
    "country": os.getenv("STRIPE_LOCATION_ADDRESS_COUNTRY", "DE"),
    "postal_code": os.getenv("STRIPE_LOCATION_ADDRESS_POSTAL_CODE", "10115"),
}


def _stripe_obj_value(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def get_platform_api_key() -> str:
    api_key = (os.getenv("STRIPE_PLATFORM_SECRET_KEY") or os.getenv("STRIPE_SECRET_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            "STRIPE_PLATFORM_SECRET_KEY ist nicht gesetzt. STRIPE_SECRET_KEY wird nur noch "
            "rueckwaertskompatibel als Plattform-Key akzeptiert."
        )
    return api_key


def _stripe_request_options(organization: Organization) -> dict:
    if not organization.stripe_connect_account_id:
        raise APIError("Fuer diesen OV ist noch kein Stripe-Connect-Konto verbunden", 400)
    return {"api_key": get_platform_api_key(), "stripe_account": organization.stripe_connect_account_id}


def get_platform_fee_basis_points(organization: Organization | None) -> int:
    if organization is not None and organization.platform_fee_basis_points is not None:
        value = organization.platform_fee_basis_points
    else:
        value = os.getenv("PLATFORM_FEE_BASIS_POINTS", str(DEFAULT_PLATFORM_FEE_BASIS_POINTS))
    try:
        basis_points = int(value)
    except (TypeError, ValueError):
        basis_points = DEFAULT_PLATFORM_FEE_BASIS_POINTS
    return max(0, min(basis_points, 10_000))


def calculate_application_fee_cents(amount_cents: int, basis_points: int) -> int:
    amount = validate_amount_cents(amount_cents)
    basis_points = max(0, min(int(basis_points), 10_000))
    if amount <= 0 or basis_points <= 0:
        return 0

    # Stripe akzeptiert nur ganze Cent. HALF_UP macht 1,5 Cent nachvollziehbar zu 2 Cent.
    raw_fee = Decimal(amount) * Decimal(basis_points) / Decimal(10_000)
    fee = int(raw_fee.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if fee == 0 and amount >= 100:
        fee = 1
    return min(fee, amount)


def create_connected_account_for_organization(organization: Organization, email: str | None = None):
    if organization.stripe_connect_account_id:
        return stripe.Account.retrieve(
            organization.stripe_connect_account_id,
            api_key=get_platform_api_key(),
        )

    account = stripe.Account.create(
        type="express",
        country="DE",
        email=email,
        business_type="non_profit",
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        metadata={
            "organization_id": str(organization.id),
            "organization_slug": organization.slug,
            "dok": organization.dok,
            "platform": "kassivo",
        },
        api_key=get_platform_api_key(),
    )
    account_id = str(_stripe_obj_value(account, "id", "")).strip()
    if not account_id:
        raise APIError("Stripe Connect Account konnte nicht erstellt werden", 502)
    updated = get_organization_store().set_stripe_account(organization.id, account_id, onboarding_complete=False)
    return account if updated else account


def create_account_onboarding_link(organization: Organization):
    organization = get_organization_store().get_by_id(organization.id) or organization
    if not organization.stripe_connect_account_id:
        create_connected_account_for_organization(organization)
        organization = get_organization_store().get_by_id(organization.id) or organization

    base_url = (os.getenv("PLATFORM_BASE_URL") or "https://payment.lima11.de").rstrip("/")
    return stripe.AccountLink.create(
        account=organization.stripe_connect_account_id,
        refresh_url=f"{base_url}/admin/stripe/refresh?ov={organization.slug}",
        return_url=f"{base_url}/admin/stripe/return?ov={organization.slug}",
        type="account_onboarding",
        api_key=get_platform_api_key(),
    )


def retrieve_connected_account(organization: Organization):
    if not organization.stripe_connect_account_id:
        return None
    return stripe.Account.retrieve(
        organization.stripe_connect_account_id,
        api_key=get_platform_api_key(),
    )


def connected_account_ready(organization: Organization) -> bool:
    if not organization.active or not organization.stripe_connect_account_id:
        return False
    if organization.stripe_connect_onboarding_complete:
        return True
    account = retrieve_connected_account(organization)
    if not account:
        return False
    charges_enabled = bool(_stripe_obj_value(account, "charges_enabled", False))
    details_submitted = bool(_stripe_obj_value(account, "details_submitted", False))
    ready = charges_enabled and details_submitted
    if ready and not organization.stripe_connect_onboarding_complete:
        get_organization_store().update_organization(
            organization_id=organization.id,
            stripe_connect_onboarding_complete=True,
        )
    return ready


def _terminal_address_for_organization(organization: Organization) -> dict:
    return {
        "line1": organization.address_line1 or DEFAULT_TERMINAL_ADDRESS["line1"],
        "city": organization.address_city or DEFAULT_TERMINAL_ADDRESS["city"],
        "country": organization.address_country or DEFAULT_TERMINAL_ADDRESS["country"],
        "postal_code": organization.address_postal_code or DEFAULT_TERMINAL_ADDRESS["postal_code"],
    }


def resolve_terminal_location_id(organization: Organization) -> str:
    if organization.stripe_location_id:
        return organization.stripe_location_id

    options = _stripe_request_options(organization)
    try:
        locations = stripe.terminal.Location.list(limit=100, **options)
        for location in _stripe_obj_value(locations, "data", []) or []:
            location_id = str(_stripe_obj_value(location, "id", "") or "").strip()
            if location_id:
                get_organization_store().set_terminal_location(organization.id, location_id)
                return location_id

        location = stripe.terminal.Location.create(
            display_name=f"{organization.dok} Kassivo",
            address=_terminal_address_for_organization(organization),
            metadata={
                "organization_id": str(organization.id),
                "organization_slug": organization.slug,
                "dok": organization.dok,
                "platform": "kassivo",
            },
            **options,
        )
        location_id = str(_stripe_obj_value(location, "id", "") or "").strip()
        if location_id:
            get_organization_store().set_terminal_location(organization.id, location_id)
            return location_id
    except stripe.error.StripeError as err:
        raise APIError("Stripe Terminal Location konnte nicht geladen werden", 502) from err

    raise APIError("Keine Stripe Terminal Location gefunden oder automatisch angelegt", 400)


def create_terminal_connection_token(organization: Organization):
    location_id = resolve_terminal_location_id(organization)
    return stripe.terminal.ConnectionToken.create(
        location=location_id,
        **_stripe_request_options(organization),
    )


def create_payment_intent_for_organization(
    organization: Organization,
    user: User,
    amount_cents: int,
    currency: str,
    item: str,
    device: str,
):
    if not organization.active:
        raise APIError("Dieser OV ist deaktiviert", 403)
    if not connected_account_ready(organization):
        raise APIError("Stripe Connect ist fuer diesen OV noch nicht bereit", 400)

    amount = validate_amount_cents(amount_cents)
    basis_points = get_platform_fee_basis_points(organization)
    fee_cents = calculate_application_fee_cents(amount, basis_points)
    cashier_name = user.username or user.name

    metadata = {
        "organization_id": str(organization.id),
        "organization_slug": organization.slug,
        "dok": organization.dok,
        "club": organization.name,
        "item": str(item),
        "kassierer": str(cashier_name),
        "device": str(device),
        "user_id": str(user.id),
        "role": user.role.value,
        "platform_fee_basis_points": str(basis_points),
        "application_fee_amount_cents": str(fee_cents),
    }
    params = {
        "amount": amount,
        "currency": currency,
        "description": f"{organization.name} {organization.dok} Kassivo",
        "payment_method_types": ["card_present"],
        "capture_method": "automatic",
        "metadata": metadata,
    }
    if fee_cents > 0:
        params["application_fee_amount"] = fee_cents
    return stripe.PaymentIntent.create(
        **params,
        **_stripe_request_options(organization),
    )


def refund_payment_for_organization(
    organization: Organization,
    payment_intent_id: str,
    refund_amount_cents: int | None = None,
):
    payment_intent_id = payment_intent_id.strip()
    if not payment_intent_id:
        raise APIError("payment_intent_id ist erforderlich", 400)
    options = _stripe_request_options(organization)
    intent = stripe.PaymentIntent.retrieve(payment_intent_id, expand=["latest_charge"], **options)
    if _stripe_obj_value(intent, "status") != "succeeded":
        raise APIError("Nur erfolgreiche Zahlungen koennen erstattet werden", 400)

    charge = _stripe_obj_value(intent, "latest_charge")
    amount_cents = int(_stripe_obj_value(charge, "amount", _stripe_obj_value(intent, "amount", 0)) or 0)
    amount_refunded_cents = int(_stripe_obj_value(charge, "amount_refunded", 0) or 0)
    refundable_cents = max(amount_cents - amount_refunded_cents, 0)
    if refundable_cents <= 0:
        raise APIError("Diese Zahlung ist bereits voll erstattet", 400)

    amount = refund_amount_cents or refundable_cents
    if amount > refundable_cents:
        raise APIError("Rueckerstattung darf den offenen Betrag nicht ueberschreiten", 400)
    return stripe.Refund.create(
        payment_intent=payment_intent_id,
        amount=amount,
        reason="requested_by_customer",
        metadata={
            "refunded_by": "kassivo-admin",
            "organization_id": str(organization.id),
            "organization_slug": organization.slug,
        },
        **options,
    )
