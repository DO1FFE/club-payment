# Kassivo

Mandantenfaehige DARC-Kassenplattform mit Flask-Backend, Admin-Webbereich und Android-App fuer Stripe Terminal Tap to Pay.

Version 1.0.16 - © 2026 Erik Schauer, do1ffe@darc.de

## Konzept

Kassivo verwaltet mehrere DARC-Ortsverbaende als eigene Mandanten. Jeder OV hat eigene Nutzer, Geraete, Produkte, Zahlungen, eine eigene Stripe Terminal Location und einen eigenen Stripe Connect Account.

Rollen:

- `system_admin`: Betreiber der Plattform; legt OVs an, verwaltet OV-Oberaccounts, sieht Connect-Status und Plattformgebuehren.
- `ov_admin`: Verantwortlicher eines OV; verwaltet Kassierer, Geraete, Produkte, Zahlungen und Stripe-Onboarding des eigenen OV.
- `kassierer`: nimmt Zahlungen in der Android-App an und kann eigene Zugangsdaten aendern.

Die Plattform kann eine vom Betreiber festgelegte Plattformgebuehr pro Zahlung einbehalten. Diese wird ueber Stripe Connect als Application Fee verarbeitet und ist fuer den jeweiligen OV im Adminbereich sichtbar.

## Migration

Vor einem Update unbedingt ein Backup der SQLite-Datenbank erstellen:

```bash
copy backend\club_payment.sqlite3 backend\club_payment.sqlite3.backup
```

Beim Start fuehrt das Backend eine idempotente Migration aus:

- Falls noch keine Organisation existiert, wird L11 als Default-OV angelegt.
- Alte Nutzer, Produkte und Geraete ohne `organization_id` werden L11 zugeordnet.
- Alte Rolle `admin` wird auf `ov_admin` migriert; der erste bestehende Admin kann per `INITIAL_ADMIN_AS_SYSTEM_ADMIN=true` zum `system_admin` werden.
- `STRIPE_SECRET_KEY` wird rueckwaertskompatibel weiter akzeptiert, gilt aber kuenftig als Plattform-Key.

## Backend lokal starten

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env
python app.py
```

Der Server laeuft standardmaessig auf Port `4040`.

Wichtige Umgebungsvariablen:

- `STRIPE_PLATFORM_SECRET_KEY`: Secret Key des Plattform-Stripe-Accounts.
- `STRIPE_SECRET_KEY`: alter Name, wird nur noch als Plattform-Key fallback genutzt.
- `STRIPE_CONNECT_CLIENT_ID`: optional fuer spaeteres OAuth.
- `PLATFORM_FEE_BASIS_POINTS`: Default-Plattformgebuehr, z. B. `100` = 1,00 %, `50` = 0,50 %, `0` = keine Gebuehr.
- `PLATFORM_BASE_URL`: z. B. `https://payment.lima11.de`.
- `FLASK_SECRET_KEY`, `DATABASE_URL`, `STRIPE_WEBHOOK_SECRET`.

## Stripe Connect

Jeder OV verbindet ein eigenes Stripe-Konto ueber Stripe Express/Connect. Der OV-Admin startet das Onboarding unter `Admin > Stripe`; das Backend erstellt bei Bedarf einen Connected Account und einen Account-Link. PaymentIntents werden anschliessend im Kontext dieses Connected Accounts erzeugt. Die Plattformgebuehr wird als `application_fee_amount` gesetzt.

Terminal Locations werden pro OV gespeichert. Wenn noch keine Location vorhanden ist, listet das Backend die Locations im Connected Account und legt bei Bedarf eine neue Location an.

## Admin-Web

- `/admin/system` und `/admin/system/organizations`: Systembereich fuer Plattformbetreiber.
- `/admin/web`: OV-Kontext fuer OV-Admins und Kassierer.
- `/admin/web/users`: Nutzer und Geraete des eigenen OV.
- `/admin/web/products`: Produkte des eigenen OV.
- `/admin/web/payments`: erfolgreiche Zahlungen, Auszahlungsstatus und Rueckerstattung.
- `/admin/web/stripe`: Stripe Connect Status und Onboarding.

## Android-App

Die App spricht produktiv `https://payment.lima11.de/` an. Port `4040` wird in der App nicht angegeben, da NGINX extern ueber HTTPS/Port 443 bzw. HTTP/Port 80 proxyt.

Keine Stripe Secret Keys werden in der App gespeichert. Die App holt Connection Tokens, Terminal Location und PaymentIntents ausschliesslich vom Backend. Bezahlt wird mit dem NFC-Modul des Android-Handys per Stripe Tap to Pay.

Beim ersten Login meldet die App ihre Geraete-ID an das Backend; ein OV-Admin kann diese ID im Adminbereich einem Kassierer zuordnen. Nach erfolgreicher Zahlung zeigt die App einen QR-Code zur Beleg-URL an.

## Landingpage und APK-Download

- `/` zeigt eine deutsche Landingpage mit Download-Link zur aktuellen Android-APK.
- `/apk/latest` liefert die neueste Datei aus `artifacts/kassivo-*-release-signed.apk` oder dem alten Muster `artifacts/club-payment-*-release-signed.apk`.
- `APK_DOWNLOAD_DIR` kann den Artefaktordner ueberschreiben.

## APK bauen

```bash
cd android
.\gradlew.bat :app:assembleDebug
.\gradlew.bat :app:assembleRelease
```

Vor jedem Build `versionCode` und `versionName` in `android/app/build.gradle.kts` erhoehen. Aktuelle Version: `1.0.16`.

Artefakte:

- Debug APK: `android/app/build/outputs/apk/debug/app-debug.apk`
- Release APK: `android/app/build/outputs/apk/release/app-release.apk`
- AAB fuer Google Play: `.\gradlew.bat :app:bundleRelease`

## Tests

```bash
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

## Sicherheit

- OV-Zugehoerigkeit wird immer aus dem authentifizierten Nutzer abgeleitet.
- `organization_id` aus Requests wird fuer Zahlungsfluesse nicht vertraut.
- Produkte, Geraete und Zahlungen werden pro OV gefiltert.
- Stripe Secret Keys bleiben ausschliesslich im Backend.
- Produktiv nur HTTPS verwenden.
