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
pip install -r requirements-dev.txt
cp .env.example .env  # then edit with your keys
```

Environment variables used:

- `STRIPE_SECRET_KEY` – required secret key
- `STRIPE_LOCATION_ID` – optional Terminal Location ID (`tml_...`) for Tap to Pay; when empty, the backend reads the first existing Stripe Terminal location or creates a default location automatically
- `STRIPE_LOCATION_DISPLAY_NAME`, `STRIPE_LOCATION_ADDRESS_LINE1`, `STRIPE_LOCATION_ADDRESS_CITY`, `STRIPE_LOCATION_ADDRESS_COUNTRY`, `STRIPE_LOCATION_ADDRESS_POSTAL_CODE` – optional defaults when automatically creating a Terminal location
- `STRIPE_WEBHOOK_SECRET` – optional, enables webhook signature verification
- `FLASK_SECRET_KEY` – required for stable admin web sessions in non-development deployments
- `ADMIN_API_TOKEN`, `ADMIN_NAME`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` – optional initial admin bootstrap
- `ALLOWED_ORIGINS` – comma-separated CORS origins (use `*` to allow all during development)
- `PORT` – port to bind (default 4040)

Additional optional variable:

- `APK_DOWNLOAD_DIR` -> optional path for signed APK downloads; defaults to the repository `artifacts/` folder

## Run locally

```bash
flask --app app run --host 0.0.0.0 --port 4040 --debug
```

or simply:

```bash
python app.py
```

## Endpoints

- `GET /` -> deutsche Landingpage mit Download-Link zur aktuellen Android-APK
- `GET /apk/latest` -> laedt die neueste signierte APK aus `APK_DOWNLOAD_DIR` herunter
- `GET /admin/web/login` und `/admin/web` -> Weboberflaeche fuer Admins und Kassierer
- `GET/POST /admin/web/account` -> eigenes Passwort aendern

- `GET /terminal/config` -> benoetigt `Authorization: Bearer <token>`, returns `{ "location_id": "tml_..." }` for Tap to Pay
- `POST /terminal/connection_token` → benötigt `Authorization: Bearer <token>`, returns `{ "secret": "..." }` for Stripe Terminal SDK
- `POST /pos/create_intent` → benötigt `Authorization: Bearer <token>`, body `{ "amount_cents": 150, "currency": "eur", "item": "Cola/Bier", "device": "Pixel" }`, Kassierer wird serverseitig aus dem Token gesetzt
- `POST /webhook` (optional) → verifies Stripe signature and appends event info to `payments.log`
- `POST /admin/users` → benötigt Admin-Token, legt Nutzer an (`name`, `role`, optional `active`, `api_token`) und liefert `api_token` zurück
- `GET /admin/users` → benötigt Admin-Token, listet Nutzer
- `PATCH /admin/users/<id>` → benötigt Admin-Token, ändert `name`, `role` und/oder `active`
- `POST /admin/devices` → benötigt Admin-Token, weist ein Gerät einem Nutzer zu (`device_id`, `user_id`)
- `GET /admin/devices` → benötigt Admin-Token, listet Gerätezuordnungen
- `DELETE /admin/devices/<device_id>` -> benoetigt Admin-Token, loescht eine Geraetezuordnung

- `POST /admin/products`, `GET /admin/products`, `PATCH /admin/products/<id>` -> Produkte verwalten
- `GET/POST /admin/web/payments` -> erfolgreiche Stripe-Zahlungen samt Auszahlungsstatus anzeigen; Rueckerstattungen sind nur fuer Admins erlaubt

Errors are returned as JSON with an `error` key and HTTP status code.

## Authentifizierung

Die API erwartet `Authorization: Bearer <token>` für alle geschützten Endpunkte. Ein initialer Admin kann über
`ADMIN_API_TOKEN` und optional `ADMIN_NAME` (Umgebungsvariablen) bereitgestellt werden. Tokens werden serverseitig
für neue Nutzer generiert, wenn kein `api_token` übergeben wird.

## Web-Rollen

- Admins koennen Nutzer, Geraete, Produkte und Zahlungen verwalten.
- Kassierer koennen sich im Web anmelden, Zahlungen/Belege ansehen und ihr eigenes Passwort aendern.
- Kassierer koennen keine Nutzer, Geraete oder Produkte verwalten und keine Rueckerstattungen ausloesen.

## Geräte-Registrierung

Geräte müssen vor dem Bezahlen registriert werden. Registrierungen erfolgen ausschließlich serverseitig über
`POST /admin/devices` mit `device_id` (z. B. Android-ID) und `user_id`. Beim Aufruf von
`POST /pos/create_intent` wird geprüft, ob das Gerät registriert ist und ob die Zuordnung zum angemeldeten
Benutzer passt. Die Zuordnung wird zusätzlich als `user_id` und `role` in der PaymentIntent-Metadata gespeichert.

## Notes

- This service purposely does not store payment data; all heavy lifting is done by Stripe.
- Stripe-hosted receipts can be localized in German through the Stripe Dashboard customer email/receipt language or through Customer `preferred_locales=["de"]`. Anonymous Terminal receipt links without Customer or email cannot be forced per payment by this backend.
- When exposing publicly, ensure HTTPS termination and restrict CORS to the production app domain.
