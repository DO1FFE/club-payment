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
- Gradle Wrapper-Skripte liegen bei; die Wrapper-JAR musst du lokal erzeugen (siehe unten)

## Projektstruktur
- `backend/` – Flask-Service mit Stripe-Terminal-Endpunkten
- `android/` – Android-Projekt (Jetpack Compose, Stripe Terminal SDK)

## Backend lokal starten
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # STRIPE_SECRET_KEY usw. eintragen
python app.py  # läuft auf Port 5000
```

## Android-App konfigurieren
1. `android/gradle.properties` enthält Platzhalter:
   - `BACKEND_BASE_URL=https://example.com`
   - `LOCATION_ID=` (optional, falls du explizit ein Terminal-Location-ID setzen willst)
2. Für lokale Emulator-Tests: setze `BACKEND_BASE_URL=http://10.0.2.2:5000`.
3. Alternativ kannst du in `android/local.properties` dieselben Keys setzen, sie überschreiben `gradle.properties`.
4. Keine Secret Keys in der App; die App holt Connection Token & PaymentIntents ausschließlich vom Backend.

## APK bauen
```bash
cd android
# Gradle-Wrapper-JAR erzeugen, falls nicht vorhanden
gradle wrapper --gradle-version 8.7

./gradlew :app:assembleDebug      # Debug APK
./gradlew :app:assembleRelease    # Release (unsigned, falls keine Signatur konfiguriert)
```

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
- Network Security Config erlaubt Klartext nur für `10.0.2.2/localhost` (Emulator); produktiv HTTPS nutzen.
- R8/ProGuard ist für Release aktiviert; Stripe Terminal-Klassen werden per Rule erhalten.
- Tap to Pay Flow ist nativ über das Stripe Terminal SDK implementiert (Connection Token vom Backend, PaymentIntent in-person/card_present).

## Backend-API aus der App
- `POST /terminal/connection_token` → holt Connection Token für das Terminal SDK
- `POST /pos/create_intent` → erzeugt PaymentIntent (EUR, card_present) mit Metadaten (`club`, `item`, `kassierer`, `device`)

Weitere Details je Ordner:
- [backend/README.md](backend/README.md)
