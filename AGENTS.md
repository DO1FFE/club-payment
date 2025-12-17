# Agent Instructions

Diese Hinweise gelten für das gesamte Repository (Android-App + Flask-Backend).

## Allgemein
- Keine Secrets ins Repository commiten; Backend-Keys gehören in `.env`, Android-URLs/IDs in `local.properties` oder `gradle.properties`.
- Bevorzugt klare Typannotationen (Python) bzw. `sealed`/`data`-Typen (Kotlin) und lasse bestehende Fehlermuster unangetastet.
- Halte die Stripe-Konfiguration konsistent: API-Version `2024-06-20`, Tap-to-Pay-Flows laufen komplett über das Stripe Terminal SDK.
- Nutze bestehende Logging-/Error-Hooks statt eigene Ad-hoc-Ausgaben einzubauen.

## Backend (Flask)
- Neue Endpunkte sollten `APIError` + `handle_errors` nutzen, JSON-Antworten mit `jsonify` zurückgeben und HTTP-Statuscodes setzen.
- Validierung: Geldbeträge sind Cent-genau als `int` und müssen > 0 sein (`validate_amount_cents`). Fehlertexte deutsch beibehalten.
- Stripe-Aufrufe laufen über das globale `stripe`-Objekt; behalte `stripe.api_key` aus der Umgebung und ändere den API-Version-String nicht ohne Grund.
- Tests liegen in `backend/tests`; setze für Testläufe die Umgebungsvariablen wie im Fixture (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `ALLOWED_ORIGINS`). Standardbefehl: `cd backend && pytest`.

## Android (Jetpack Compose)
- Konfigurationswerte kommen über `BuildConfig` aus `gradle.properties`/`local.properties` (`BACKEND_BASE_URL`, optional `LOCATION_ID`); nichts hartkodieren.
- Netzwerk: Retrofit + Moshi + OkHttp-Logging sind bereits verdrahtet. Nutze die bestehenden `BackendService`-Interfaces und Datenklassen statt neue Clients anzulegen.
- Zahlungsfluss beibehalten: `PaymentViewModel.startPayment` ruft nacheinander `createIntent` → `collectPayment` → `processPayment` und aktualisiert den `PaymentStatus`-StateFlow.
- UI-Texte sind bewusst deutsch gehalten; bei neuen Strings Konsistenz wahren. Compose-Elemente nutzen Material 3 wie in `PaymentScreen`.
- Terminal-Initialisierung erfolgt in `TerminalManager` über `Terminal.initTerminal` mit `BackendConnectionTokenProvider`; Lifecycle-Delegates liegen in `ClubPaymentApp`.

## Tests & Builds
- Backend: `cd backend && pytest`.
- Android: Verwende den Gradle-Wrapper (`./gradlew`) aus `android/` für Builds/Checks (z. B. `./gradlew :app:assembleDebug`).
