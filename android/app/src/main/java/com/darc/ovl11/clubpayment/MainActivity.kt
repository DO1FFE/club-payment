package com.darc.ovl11.clubpayment

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.text.NumberFormat
import java.util.Locale

class MainActivity : ComponentActivity() {
    private val authStore by lazy { AuthStore(applicationContext) }
    private val backendService by lazy { provideBackendService(BuildConfig.BACKEND_BASE_URL, authStore) }
    private val terminalManager by lazy { TerminalManager(applicationContext, backendService) }

    private val viewModel: PaymentViewModel by viewModels {
        object : ViewModelProvider.Factory {
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                @Suppress("UNCHECKED_CAST")
                return PaymentViewModel(terminalManager, authStore) as T
            }
        }
    }

    private val authViewModel: AuthViewModel by viewModels {
        object : ViewModelProvider.Factory {
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                @Suppress("UNCHECKED_CAST")
                return AuthViewModel(authStore, backendService) as T
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                AppContent(viewModel, authViewModel)
            }
        }
    }
}

class PaymentViewModel(
    private val terminalManager: TerminalManager,
    private val authStore: AuthStore,
) : ViewModel() {
    private val _status = MutableStateFlow<PaymentStatus>(PaymentStatus.Idle)
    val status: StateFlow<PaymentStatus> = _status

    val deviceName: String = terminalManager.readableDeviceName()

    fun startPayment(amountCents: Int, itemLabel: String) {
        viewModelScope.launch {
            try {
                val userName = authStore.currentUserName()
                if (userName.isNullOrBlank()) {
                    _status.value = PaymentStatus.Error("Bitte zuerst anmelden")
                    return@launch
                }
                _status.value = PaymentStatus.CreatingIntent
                val intent = terminalManager.createIntent(amountCents, itemLabel, userName, deviceName)
                _status.value = PaymentStatus.WaitingForTap
                val collected = terminalManager.collectPayment(intent)
                _status.value = PaymentStatus.Processing
                val processed = terminalManager.processPayment(collected)
                _status.value = PaymentStatus.Success(processed.amount ?: intent.amount!!, processed.id)
            } catch (e: Exception) {
                _status.value = PaymentStatus.Error(e.message ?: "Unbekannter Fehler")
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppContent(viewModel: PaymentViewModel, authViewModel: AuthViewModel) {
    val authState by authViewModel.authState.collectAsState()

    if (authState == null) {
        LoginScreen(authViewModel)
    } else {
        PaymentScreen(
            viewModel = viewModel,
            userName = authState?.userName.orEmpty(),
            onLogout = { authViewModel.logout() }
        )
    }
}

@Composable
fun LoginScreen(authViewModel: AuthViewModel) {
    var userName by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    val loginStatus by authViewModel.loginStatus.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(text = "Gerät anmelden", style = MaterialTheme.typography.headlineSmall)
        OutlinedTextField(
            value = userName,
            onValueChange = { userName = it },
            label = { Text("Benutzername") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
            modifier = Modifier.fillMaxWidth()
        )
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Passwort") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            visualTransformation = PasswordVisualTransformation(),
            modifier = Modifier.fillMaxWidth()
        )
        Button(
            onClick = { authViewModel.login(userName.trim(), password) },
            enabled = userName.isNotBlank() && password.isNotBlank() && loginStatus !is LoginStatus.Loading,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Anmelden")
        }
        if (loginStatus is LoginStatus.Error) {
            Text(
                text = "Fehler: ${(loginStatus as LoginStatus.Error).message}",
                color = MaterialTheme.colorScheme.error
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PaymentScreen(viewModel: PaymentViewModel, userName: String, onLogout: () -> Unit) {
    var freeAmountText by remember { mutableStateOf("") }

    val status by viewModel.status.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(text = "DARC e.V. OV L11 – Getränke", style = MaterialTheme.typography.headlineSmall)
                Text(text = "Angemeldet als $userName", style = MaterialTheme.typography.bodyMedium)
            }
            Button(onClick = onLogout) {
                Text("Abmelden")
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            PriceButton("Cola/Bier", 150) { viewModel.startPayment(150, "Cola/Bier") }
            PriceButton("Wasser", 50) { viewModel.startPayment(50, "Wasser") }
        }

        OutlinedTextField(
            value = freeAmountText,
            onValueChange = { freeAmountText = it },
            label = { Text("Freier Betrag (€)") },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            colors = TextFieldDefaults.outlinedTextFieldColors()
        )

        Button(
            onClick = {
                parseAmountToCents(freeAmountText)?.let { cents ->
                    viewModel.startPayment(cents, "Freier Betrag")
                }
            },
            enabled = parseAmountToCents(freeAmountText) != null,
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Zahlung starten")
        }

        StatusCard(status)
    }
}

@Composable
fun PriceButton(label: String, amountCents: Int, onClick: () -> Unit) {
    val formatter = NumberFormat.getCurrencyInstance(Locale.GERMANY)
    val amountFormatted = formatter.format(amountCents / 100.0)
    Button(onClick = onClick, modifier = Modifier.weight(1f)) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(text = label)
            Text(text = amountFormatted, style = MaterialTheme.typography.titleMedium)
        }
    }
}

@Composable
fun StatusCard(status: PaymentStatus) {
    val message = when (status) {
        PaymentStatus.Idle -> "Bereit für Zahlung"
        PaymentStatus.CreatingIntent -> "Intent wird erstellt..."
        PaymentStatus.WaitingForTap -> "Bitte Karte/Handy an das Gerät halten"
        PaymentStatus.Processing -> "Zahlung wird verarbeitet"
        is PaymentStatus.Success -> "Erfolg: ${(status.amountCents / 100.0)} € – ${status.intentId}"
        is PaymentStatus.Error -> "Fehler: ${status.message}"
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Text(text = message, modifier = Modifier.padding(16.dp))
    }
}

fun parseAmountToCents(input: String): Int? {
    if (input.isBlank()) return null
    val normalized = input.replace(",", ".")
    val value = normalized.toDoubleOrNull() ?: return null
    if (value < 0.1 || value > 99.99) return null
    return (value * 100).toInt()
}
