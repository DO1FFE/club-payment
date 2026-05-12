# Club Payment – DARC e.V. OV L11

Monorepo mit Android-App (Tap to Pay mit Stripe Terminal) und Flask-Backend für eine einfache Getränke-Kasse.

Version 1.0.14 - © 2026 Erik Schauer, do1ffe@darc.de

## Voraussetzungen

### Allgemein
- Git, Bash

### Backend
- Python 3.11+

### Android
- Android Studio Iguana/Koala+
- JDK 17
- Android SDK 34
- Gradle Wrapper liegt bei

## Projektstruktur
- `backend/` – Flask-Service mit Stripe-Terminal-Endpunkten
- `android/` – Android-Projekt (Jetpack Compose, Stripe Terminal SDK)

## Backend lokal starten
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env  # STRIPE_SECRET_KEY usw. eintragen
python app.py  # läuft auf Port 4040
```

## Landingpage und APK-Download
- `/` zeigt eine deutsche Landingpage mit Link zur aktuellen Android-APK.
- `/apk/latest` liefert automatisch die neueste Datei aus `artifacts/club-payment-*-release-signed.apk` als Download aus.
- Optional kann `APK_DOWNLOAD_DIR` gesetzt werden, wenn die APKs auf dem Server in einem anderen Ordner liegen.

## Web-Bereich
- Admins koennen Nutzer, Geraete, Produkte und Zahlungen verwalten.
- Kassierer koennen sich im Web anmelden, Zahlungen/Belege ansehen und ihr eigenes Passwort aendern.
- Kassierer haben keinen Zugriff auf Nutzer-, Geraete- oder Produktverwaltung und koennen keine Rueckerstattungen ausloesen.

## Android-App konfigurieren
1. `android/gradle.properties` enthält Platzhalter:
   - `BACKEND_BASE_URL=https://payment.lima11.de/`
   - `LOCATION_ID=` (optional; wenn leer, holt die App die Stripe Terminal Location vom Backend)
2. Für lokale Emulator-Tests gegen einen direkt gestarteten Backend-Prozess kannst du temporär `BACKEND_BASE_URL=http://10.0.2.2:4040/` in `android/local.properties` setzen.
3. Alternativ kannst du in `android/local.properties` dieselben Keys setzen, sie überschreiben `gradle.properties`.
4. Keine Secret Keys in der App; die App holt Connection Token & PaymentIntents ausschließlich vom Backend.

5. Die App zeigt ihre Geraete-ID im Login- und Zahlungsbildschirm an; diese ID muss im Admin-Web einem Nutzer zugewiesen werden.
6. Die Zahlung laeuft ueber das NFC-Modul des Android-Handys mit Stripe Tap to Pay. Es wird kein externes Terminal oder Kartenlesegeraet verbunden. Die Stripe Terminal Location kommt aus `LOCATION_ID` oder vom Backend-Endpunkt `/terminal/config`.
7. Beim ersten Login meldet die App ihre Geraete-ID an das Backend; im Admin-Web kann diese ID einem Nutzer zugeordnet werden.
8. Neben Produkten kann in der App ein freier Einmalbetrag mit Kurzbeschreibung in den Warenkorb gelegt und bezahlt werden.

## APK bauen
```bash
cd android
./gradlew :app:assembleDebug      # Debug APK
./gradlew :app:assembleRelease    # Release (unsigned, falls keine Signatur konfiguriert)
```
Vor jedem signierten APK-Build `versionCode` und `versionName` in `android/app/build.gradle.kts` erhoehen.

Falls der Checkout in einem OneDrive-Ordner liegt und Gradle über ReparsePoint-/Dateisperren stolpert, kannst du Build-Artefakte lokal auslagern:
```bash
./gradlew :app:assembleDebug -PCLUB_PAYMENT_BUILD_DIR="$LOCALAPPDATA/CodexTools/club-payment-gradle-build"
```
Hinweis: Für Pull Requests erzeugt die GitHub-Actions-Pipeline automatisch eine Debug-APK als Artefakt.

### Release signieren
1. Keystore erstellen (einmalig):
   ```bash
   keytool -genkeypair -v -keystore clubpayment.keystore -alias clubpayment -keyalg RSA -keysize 2048 -validity 10000
   ```
2. In `android/app/build.gradle.kts` eine `signingConfig` für `release` ergänzen oder via `gradle.properties` Referenzen setzen.
3. Danach: `./gradlew :app:assembleRelease`.

### Artefakte
- APK: `android/app/build/outputs/apk/debug/app-debug.apk`
- Release APK: `android/app/build/outputs/apk/release/app-release.apk`
- Signierte PR-APK: `artifacts/club-payment-1.0.14-release-signed.apk`
- AAB (optional): `./gradlew :app:bundleRelease` → `android/app/build/outputs/bundle/release/app-release.aab`

## Hinweise zu Netzwerk & Sicherheit
- Network Security Config erlaubt Klartext nur für lokale Emulator-Tests über `10.0.2.2/localhost`; die produktive Server-URL nutzt HTTPS.
- R8/ProGuard ist für Release aktiviert; Stripe Terminal-Klassen werden per Rule erhalten.
- Tap to Pay Flow ist nativ ueber das Stripe Terminal SDK implementiert (Connection Token vom Backend, PaymentIntent in-person/card_present, NFC direkt am Android-Handy).
- NFC, Standort-Hardware und WLAN sind keine Installationsfilter mehr. Geraete ohne NFC koennen die App starten, erhalten aber einen Hinweis und koennen keine Tap-to-Pay-Zahlungen annehmen. Android 11 oder neuer bleibt erforderlich.
- Auth-Persistenz-Entscheidung (Android): Bei aktivierter Option `Zugangsdaten merken` werden Benutzername und Passwort lokal in der App gespeichert und beim naechsten Login vorausgefuellt. Beim Abmelden bleibt diese Vorbelegung erhalten; Login ohne aktivierte Option loescht sie.

## Stripe-Sprache fuer Belege
- Stripe kann Belege, E-Mails und PDFs auf Deutsch lokalisieren, wenn im Stripe-Dashboard Deutsch als Sprache fuer Kunden-E-Mails/Belege gesetzt ist oder ein Stripe-Customer mit `preferred_locales=["de"]` verwendet wird.
- Die App nutzt fuer Kartenzahlungen anonyme Terminal-PaymentIntents. Ohne Kundendatensatz oder E-Mail kann der von Stripe gehostete `receipt_url` nicht sicher pro Zahlung auf Deutsch erzwungen werden; hier greifen Stripe-Dashboard- und Browser-/Account-Einstellungen.
- Wenn eine garantiert deutsche, eigene Quittungsseite benoetigt wird, sollte der QR-Code auf eine serverseitig erzeugte Club-Kasse-Quittung zeigen, die die benoetigten Stripe-Terminal-Belegdaten aus der API rendert.

## Backend-API aus der App
- `GET /api/app/latest` -> prueft die neueste signierte APK fuer den Update-Hinweis in der Android-App
- `GET /terminal/config` → holt mit `Authorization: Bearer <token>` die Stripe Terminal Location fuer Tap to Pay
- `POST /terminal/connection_token` → holt mit `Authorization: Bearer <token>` ein Connection Token für das Terminal SDK
- `POST /pos/create_intent` → erzeugt PaymentIntent (EUR, card_present) mit Metadaten (`club`, `item`, `kassierer`, `device`)

Weitere Details je Ordner:
- [backend/README.md](backend/README.md)
