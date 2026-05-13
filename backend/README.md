# Kassivo Backend

Flask-Service fuer Kassivo: Authentifizierung, Admin-Web, Mandantenmodell, Stripe Connect, Stripe Terminal Tap to Pay und APK-Landingpage.

Version 1.0.16 - © 2026 Erik Schauer, do1ffe@darc.de

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
python app.py
```

## Umgebungsvariablen

- `STRIPE_PLATFORM_SECRET_KEY`: Secret Key des Plattform-Stripe-Accounts.
- `STRIPE_SECRET_KEY`: alter Name, wird fallbackweise als Plattform-Key verwendet.
- `PLATFORM_BASE_URL`: oeffentliche Basis-URL, z. B. `https://payment.lima11.de`.
- `PLATFORM_FEE_BASIS_POINTS`: globale Default-Gebuehr in Basispunkten. `100` = 1,00 %, `50` = 0,50 %, `0` = keine Gebuehr.
- `STRIPE_CONNECT_CLIENT_ID`: optional fuer spaetere Standard/OAuth-Connect-Flows.
- `STRIPE_WEBHOOK_SECRET`: optional fuer Webhook-Signaturpruefung.
- `FLASK_SECRET_KEY`: Secret fuer Web-Sessions.
- `DATABASE_URL`: optional; sonst `backend/club_payment.sqlite3`.
- `ADMIN_API_TOKEN`, `ADMIN_NAME`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_ROLE`: optionaler Bootstrap-Admin.
- `INITIAL_ADMIN_AS_SYSTEM_ADMIN`: steuert die Migration alter `admin`-Nutzer.
- `APK_DOWNLOAD_DIR`: optionaler Ordner fuer APK-Downloads.
- `PORT`: Port, Default `4040`.

## Rollen

- `system_admin`: Betreiber der Plattform, verwaltet OVs und Plattformgebuehren.
- `ov_admin`: verwaltet Nutzer, Geraete, Produkte, Zahlungen und Stripe Connect des eigenen OV.
- `kassierer`: meldet sich in der Android-App an und nimmt Zahlungen fuer den eigenen OV an.

## Stripe Connect

Jeder OV erhaelt einen Stripe Connected Account. PaymentIntents werden im Connected Account erzeugt und enthalten bei aktiver Plattformgebuehr `application_fee_amount`. Der Plattform-Key bleibt im Backend; in der Android-App oder in Templates werden keine Secret Keys ausgegeben.

Die Plattform kann eine vom Betreiber festgelegte Plattformgebuehr pro Zahlung einbehalten. Diese wird ueber Stripe Connect als Application Fee verarbeitet und ist fuer den jeweiligen OV im Adminbereich sichtbar.

## Migration

Vor Updates bitte `backend/club_payment.sqlite3` sichern. Die Startmigration ist idempotent und loescht keine Daten. Sie legt L11 als Default-OV an, fuegt `organization_id` an bestehende Tabellen an und ordnet alte Nutzer, Produkte und Geraete L11 zu.

## Wichtige Endpunkte

- `POST /auth/login`
- `GET /terminal/config`
- `POST /terminal/connection_token`
- `POST /pos/create_intent`
- `GET /pos/receipt/<payment_intent_id>`
- `GET /admin/system/organizations`
- `GET /admin/web/users`
- `GET /admin/web/products`
- `GET/POST /admin/web/payments`
- `GET /admin/web/stripe`
- `GET /api/app/latest`
- `GET /apk/latest`
- `POST /webhook`

## Tests

```bash
.venv\Scripts\python.exe -m pytest tests -q
```
