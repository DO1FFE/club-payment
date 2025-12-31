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
- `POST /pos/create_intent` → benötigt `Authorization: Bearer <token>`, body `{ "amount_cents": 150, "currency": "eur", "item": "Cola/Bier", "device": "Pixel" }`, Kassierer wird serverseitig aus dem Token gesetzt
- `POST /webhook` (optional) → verifies Stripe signature and appends event info to `payments.log`
- `POST /admin/users` → benötigt Admin-Token, legt Nutzer an (`name`, `role`, optional `active`, `api_token`) und liefert `api_token` zurück
- `GET /admin/users` → benötigt Admin-Token, listet Nutzer
- `PATCH /admin/users/<id>` → benötigt Admin-Token, ändert `name`, `role` und/oder `active`
- `POST /admin/devices` → benötigt Admin-Token, weist ein Gerät einem Nutzer zu (`device_id`, `user_id`)
- `GET /admin/devices` → benötigt Admin-Token, listet Gerätezuordnungen

Errors are returned as JSON with an `error` key and HTTP status code.

## Authentifizierung

Die API erwartet `Authorization: Bearer <token>` für alle geschützten Endpunkte. Ein initialer Admin kann über
`ADMIN_API_TOKEN` und optional `ADMIN_NAME` (Umgebungsvariablen) bereitgestellt werden. Tokens werden serverseitig
für neue Nutzer generiert, wenn kein `api_token` übergeben wird.

## Geräte-Registrierung

Geräte müssen vor dem Bezahlen registriert werden. Registrierungen erfolgen ausschließlich serverseitig über
`POST /admin/devices` mit `device_id` (z. B. Android-ID) und `user_id`. Beim Aufruf von
`POST /pos/create_intent` wird geprüft, ob das Gerät registriert ist und ob die Zuordnung zum angemeldeten
Benutzer passt. Die Zuordnung wird zusätzlich als `user_id` und `role` in der PaymentIntent-Metadata gespeichert.

## Notes

- This service purposely does not store payment data; all heavy lifting is done by Stripe.
- When exposing publicly, ensure HTTPS termination and restrict CORS to the production app domain.
