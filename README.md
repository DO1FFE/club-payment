# Club Payment – DARC e.V. OV L11

Monorepo mit Android-App (Tap to Pay mit Stripe Terminal) und Flask-Backend für eine einfache Getränke-Kasse.

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

## Android-App konfigurieren
1. `android/gradle.properties` enthält Platzhalter:
   - `BACKEND_BASE_URL=http://payment.lima11.de/`
   - `LOCATION_ID=` (fuer echte Stripe Tap-to-Pay-Zahlungen erforderlich)
2. Für lokale Emulator-Tests gegen einen direkt gestarteten Backend-Prozess kannst du temporär `BACKEND_BASE_URL=http://10.0.2.2:4040/` in `android/local.properties` setzen.
3. Alternativ kannst du in `android/local.properties` dieselben Keys setzen, sie überschreiben `gradle.properties`.
4. Keine Secret Keys in der App; die App holt Connection Token & PaymentIntents ausschließlich vom Backend.

5. Die App zeigt ihre Geraete-ID im Login- und Zahlungsbildschirm an; diese ID muss im Admin-Web einem Nutzer zugewiesen werden.
6. Die Zahlung laeuft ueber das NFC-Modul des Android-Handys mit Stripe Tap to Pay. Es wird kein externes Terminal oder Kartenlesegeraet verbunden. Ohne `LOCATION_ID` bricht der echte NFC-Zahlungsfluss mit einer klaren Fehlermeldung ab.

## APK bauen
```bash
cd android
./gradlew :app:assembleDebug      # Debug APK
./gradlew :app:assembleRelease    # Release (unsigned, falls keine Signatur konfiguriert)
```
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
- AAB (optional): `./gradlew :app:bundleRelease` → `android/app/build/outputs/bundle/release/app-release.aab`

## Hinweise zu Netzwerk & Sicherheit
- Network Security Config erlaubt Klartext für `payment.lima11.de` sowie `10.0.2.2/localhost` für lokale Emulator-Tests; produktiv HTTPS nutzen, sobald der Proxy TLS bereitstellt.
- R8/ProGuard ist für Release aktiviert; Stripe Terminal-Klassen werden per Rule erhalten.
- Tap to Pay Flow ist nativ ueber das Stripe Terminal SDK implementiert (Connection Token vom Backend, PaymentIntent in-person/card_present, NFC direkt am Android-Handy).
- Auth-Persistenz-Entscheidung (Android): Bei aktivierter Option `Zugangsdaten merken` werden Benutzername und Passwort lokal in der App gespeichert und beim naechsten Login vorausgefuellt. Beim Abmelden bleibt diese Vorbelegung erhalten; Login ohne aktivierte Option loescht sie.

## Backend-API aus der App
- `POST /terminal/connection_token` → holt mit `Authorization: Bearer <token>` ein Connection Token für das Terminal SDK
- `POST /pos/create_intent` → erzeugt PaymentIntent (EUR, card_present) mit Metadaten (`club`, `item`, `kassierer`, `device`)

Weitere Details je Ordner:
- [backend/README.md](backend/README.md)
