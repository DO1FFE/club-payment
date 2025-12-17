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
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenu
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
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
    private val viewModel: PaymentViewModel by viewModels {
        object : ViewModelProvider.Factory {
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                val backend = provideBackendService(BuildConfig.BACKEND_BASE_URL)
                val manager = TerminalManager(applicationContext, backend)
                @Suppress("UNCHECKED_CAST")
                return PaymentViewModel(manager) as T
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                PaymentScreen(viewModel)
            }
        }
    }
}

class PaymentViewModel(private val terminalManager: TerminalManager) : ViewModel() {
    private val _status = MutableStateFlow<PaymentStatus>(PaymentStatus.Idle)
    val status: StateFlow<PaymentStatus> = _status

    private val kassiererList = listOf("Dienst 1", "Dienst 2", "Erik")
    val deviceName: String = terminalManager.readableDeviceName()

    fun kassiererOptions(): List<String> = kassiererList + deviceName

    fun startPayment(amountCents: Int, itemLabel: String, kassierer: String) {
        viewModelScope.launch {
            try {
                _status.value = PaymentStatus.CreatingIntent
                val intent = terminalManager.createIntent(amountCents, itemLabel, kassierer, deviceName)
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
fun PaymentScreen(viewModel: PaymentViewModel) {
    val kassiererOptions = remember { viewModel.kassiererOptions() }

    var freeAmountText by remember { mutableStateOf("") }
    var kassiererSelection by remember { mutableStateOf(kassiererOptions.first()) }

    val status by viewModel.status.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(text = "DARC e.V. OV L11 – Getränke", style = MaterialTheme.typography.headlineSmall)

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            PriceButton("Cola/Bier", 150) { viewModel.startPayment(150, "Cola/Bier", kassiererSelection) }
            PriceButton("Wasser", 50) { viewModel.startPayment(50, "Wasser", kassiererSelection) }
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

        KassiererDropdown(
            options = kassiererOptions,
            selected = kassiererSelection,
            onSelect = { kassiererSelection = it }
        )

        Button(
            onClick = {
                parseAmountToCents(freeAmountText)?.let { cents ->
                    viewModel.startPayment(cents, "Freier Betrag", kassiererSelection)
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KassiererDropdown(options: List<String>, selected: String, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = !expanded }) {
        OutlinedTextField(
            value = selected,
            onValueChange = {},
            readOnly = true,
            label = { Text("Kassierer") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier.menuAnchor().fillMaxWidth()
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { option ->
                DropdownMenuItem(text = { Text(option) }, onClick = {
                    onSelect(option)
                    expanded = false
                })
            }
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
