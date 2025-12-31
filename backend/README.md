# Backend – Flask Stripe Terminal service

This Flask service exposes minimal endpoints to support Stripe Terminal Tap to Pay on Android for **DARC e.V. OV L11**.

## Prerequisites

- Python 3.11+
- A Stripe account with Terminal enabled
- Stripe Secret Key (test or live) and optional webhook signing secret

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit with your keys
```

Environment variables used:

- `STRIPE_SECRET_KEY` – required secret key
- `STRIPE_WEBHOOK_SECRET` – optional, enables webhook signature verification
- `ALLOWED_ORIGINS` – comma-separated CORS origins (use `*` to allow all during development)
- `PORT` – port to bind (default 5000)

## Run locally

```bash
flask --app app run --host 0.0.0.0 --port 5000 --debug
```

or simply:

```bash
python app.py
```

## Endpoints

- `POST /terminal/connection_token` → returns `{ "secret": "..." }` for Stripe Terminal SDK
- `POST /pos/create_intent` → body `{ "amount_cents": 150, "currency": "eur", "item": "Cola/Bier", "kassierer": "Dienst 1", "device": "Pixel" }`, returns PaymentIntent details
- `POST /webhook` (optional) → verifies Stripe signature and appends event info to `payments.log`

Errors are returned as JSON with an `error` key and HTTP status code.

## Geräte-Registrierung (Admin)

Für den POS-Flow muss jedes Gerät serverseitig registriert sein. Die Authentifizierung erfolgt über Header:

- `X-User-Id`: Benutzer-ID
- `X-User-Role`: Rolle (z. B. `admin`, `kassierer`)

Admin-Endpunkte:

- `POST /admin/devices` → weist ein Gerät zu (`{ "device_id": "...", "user_id": "...", "role": "..." }`)
- `GET /admin/devices` → listet alle Zuordnungen

`POST /pos/create_intent` prüft zusätzlich:

- Gerät ist registriert
- Gerät gehört zum authentifizierten Benutzer
- Metadata enthält `user_id` und `role` aus der Zuordnung

## Notes

- This service purposely does not store payment data; all heavy lifting is done by Stripe.
- When exposing publicly, ensure HTTPS termination and restrict CORS to the production app domain.
