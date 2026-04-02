package com.darc.ovl11.clubpayment

import android.graphics.Bitmap
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
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
                return PaymentViewModel(terminalManager, authStore, backendService) as T
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
    private val backendService: BackendService,
) : ViewModel() {
    private val _status = MutableStateFlow<PaymentStatus>(PaymentStatus.Idle)
    val status: StateFlow<PaymentStatus> = _status

    private val _products = MutableStateFlow<List<ProductDto>>(emptyList())
    val products: StateFlow<List<ProductDto>> = _products

    private val _selectedItems = MutableStateFlow<Map<Int, Int>>(emptyMap())
    val selectedItems: StateFlow<Map<Int, Int>> = _selectedItems

    val totalAmountCents: StateFlow<Int> = combine(_products, _selectedItems) { products, selectedItems ->
        calculateTotalAmountCents(products, selectedItems)
    }.stateIn(viewModelScope, SharingStarted.Eagerly, 0)

    val itemLabel: StateFlow<String> = combine(_products, _selectedItems) { products, selectedItems ->
        createItemLabel(products, selectedItems)
    }.stateIn(viewModelScope, SharingStarted.Eagerly, "")

    private val _productsLoading = MutableStateFlow(false)
    val productsLoading: StateFlow<Boolean> = _productsLoading

    private val _productsError = MutableStateFlow<String?>(null)
    val productsError: StateFlow<String?> = _productsError

    val deviceName: String = terminalManager.readableDeviceName()

    fun loadProducts() {
        viewModelScope.launch {
            _productsLoading.value = true
            _productsError.value = null
            try {
                val response = backendService.listProducts()
                _products.value = response.products.filter { it.active }
            } catch (e: Exception) {
                _products.value = emptyList()
                _productsError.value = e.message ?: "Produkte konnten nicht geladen werden"
            } finally {
                _productsLoading.value = false
            }
        }
    }

    fun addProduct(product: ProductDto) {
        _selectedItems.value = _selectedItems.value.toMutableMap().apply {
            val quantity = getOrDefault(product.id, 0) + 1
            this[product.id] = quantity
        }
    }

    fun removeProduct(product: ProductDto) {
        _selectedItems.value = _selectedItems.value.toMutableMap().apply {
            val oldQuantity = getOrDefault(product.id, 0)
            when {
                oldQuantity <= 1 -> remove(product.id)
                oldQuantity > 1 -> this[product.id] = oldQuantity - 1
            }
        }
    }

    fun clearCart() {
        _selectedItems.value = emptyMap()
    }

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
                _status.value = PaymentStatus.FetchingReceipt
                val amountCents = processed.amount ?: intent.amount!!
                val receiptResult = fetchReceiptUrl(processed.id)
                _status.value = PaymentStatus.Success(
                    amountCents = amountCents,
                    intentId = processed.id,
                    receiptUrl = receiptResult.first,
                    receiptError = receiptResult.second
                )
                clearCart()
            } catch (e: Exception) {
                _status.value = PaymentStatus.Error(e.message ?: "Unbekannter Fehler")
            }
        }
    }

    private suspend fun fetchReceiptUrl(paymentIntentId: String): Pair<String?, String?> {
        return try {
            val response = backendService.getReceipt(paymentIntentId)
            Pair(response.receipt_url, null)
        } catch (e: Exception) {
            Pair(null, e.message ?: "Beleg konnte nicht geladen werden")
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
        androidx.compose.runtime.LaunchedEffect(authState?.token) {
            viewModel.loadProducts()
        }
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
    var rememberCredentials by remember { mutableStateOf(false) }
    val rememberedUserName by authViewModel.rememberedUserName.collectAsState()
    val loginStatus by authViewModel.loginStatus.collectAsState()

    LaunchedEffect(rememberedUserName) {
        if (userName.isBlank() && !rememberedUserName.isNullOrBlank()) {
            userName = rememberedUserName.orEmpty()
            rememberCredentials = true
        }
    }

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
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Checkbox(
                checked = rememberCredentials,
                onCheckedChange = { rememberCredentials = it }
            )
            Text("Anmeldedaten merken (nur Benutzername)")
        }
        Text(
            text = "Angemeldet bleiben nutzt ausschließlich Token-Speicherung.",
            style = MaterialTheme.typography.bodySmall
        )
        Button(
            onClick = { authViewModel.login(userName.trim(), password, rememberCredentials) },
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
    val status by viewModel.status.collectAsState()
    val products by viewModel.products.collectAsState()
    val productsLoading by viewModel.productsLoading.collectAsState()
    val productsError by viewModel.productsError.collectAsState()
    val selectedItems by viewModel.selectedItems.collectAsState()
    val totalAmountCents by viewModel.totalAmountCents.collectAsState()
    val itemLabel by viewModel.itemLabel.collectAsState()

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

        if (productsLoading) {
            CircularProgressIndicator()
        }

        productsError?.let { errorText ->
            Text(
                text = "Produkte konnten nicht geladen werden: $errorText",
                color = MaterialTheme.colorScheme.error
            )
        }

        products.chunked(2).forEach { rowProducts ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                rowProducts.forEach { product ->
                    PriceButton(product.name, product.price_cents) {
                        viewModel.addProduct(product)
                    }
                }
                if (rowProducts.size == 1) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
        }

        CartCard(
            products = products,
            selectedItems = selectedItems,
            totalAmountCents = totalAmountCents,
            onAddProduct = { viewModel.addProduct(it) },
            onRemoveProduct = { viewModel.removeProduct(it) },
            onClearCart = { viewModel.clearCart() }
        )

        Button(
            onClick = { viewModel.startPayment(totalAmountCents, itemLabel) },
            enabled = isPayButtonEnabled(totalAmountCents, status),
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Bezahlen")
        }

        StatusCard(status)
    }
}

@Composable
fun CartCard(
    products: List<ProductDto>,
    selectedItems: Map<Int, Int>,
    totalAmountCents: Int,
    onAddProduct: (ProductDto) -> Unit,
    onRemoveProduct: (ProductDto) -> Unit,
    onClearCart: () -> Unit,
) {
    val formatter = NumberFormat.getCurrencyInstance(Locale.GERMANY)
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(text = "Warenkorb", style = MaterialTheme.typography.titleMedium)
            if (selectedItems.isEmpty()) {
                Text(text = "Noch keine Produkte ausgewählt.")
            } else {
                products
                    .filter { selectedItems.containsKey(it.id) }
                    .forEach { product ->
                        val quantity = selectedItems[product.id] ?: 0
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(text = "${product.name} × $quantity")
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = { onRemoveProduct(product) }) { Text("−") }
                                Button(onClick = { onAddProduct(product) }) { Text("+") }
                            }
                        }
                    }
                Button(onClick = onClearCart, modifier = Modifier.fillMaxWidth()) {
                    Text("Warenkorb leeren")
                }
            }
            Text(
                text = "Gesamt: ${formatter.format(totalAmountCents / 100.0)}",
                style = MaterialTheme.typography.titleMedium
            )
        }
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
        PaymentStatus.FetchingReceipt -> "Beleg wird abgerufen..."
        is PaymentStatus.Success -> "Erfolg: ${(status.amountCents / 100.0)} € – ${status.intentId}"
        is PaymentStatus.Error -> "Fehler: ${status.message}"
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(text = message)
            if (status is PaymentStatus.Success) {
                status.receiptError?.let { errorText ->
                    Text(text = "Beleg konnte nicht geladen werden: $errorText", color = MaterialTheme.colorScheme.error)
                }
                status.receiptUrl?.let { receiptUrl ->
                    ReceiptQrCard(receiptUrl)
                }
            }
        }
    }
}

@Composable
fun ReceiptQrCard(receiptUrl: String) {
    val qrBitmap = remember(receiptUrl) { generateQrCodeBitmap(receiptUrl) }
    if (qrBitmap == null) {
        Text(text = "QR-Code konnte nicht erstellt werden", color = MaterialTheme.colorScheme.error)
        return
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Text(text = "Beleg als QR-Code", style = MaterialTheme.typography.titleMedium)
            Image(
                bitmap = qrBitmap.asImageBitmap(),
                contentDescription = "QR-Code für den Beleg",
                modifier = Modifier.fillMaxWidth()
            )
        }
    }
}

fun generateQrCodeBitmap(content: String, size: Int = 512): Bitmap? {
    return try {
        val writer = QRCodeWriter()
        val matrix = writer.encode(content, BarcodeFormat.QR_CODE, size, size)
        val pixels = IntArray(size * size)
        for (y in 0 until size) {
            val offset = y * size
            for (x in 0 until size) {
                pixels[offset + x] = if (matrix.get(x, y)) {
                    0xFF000000.toInt()
                } else {
                    0xFFFFFFFF.toInt()
                }
            }
        }
        Bitmap.createBitmap(pixels, size, size, Bitmap.Config.ARGB_8888)
    } catch (e: Exception) {
        null
    }
}

fun calculateTotalAmountCents(products: List<ProductDto>, selectedItems: Map<Int, Int>): Int {
    val priceById = products.associateBy({ it.id }, { it.price_cents })
    return selectedItems.entries.sumOf { (id, quantity) ->
        val price = priceById[id] ?: 0
        price * quantity
    }
}

fun createItemLabel(products: List<ProductDto>, selectedItems: Map<Int, Int>): String {
    val productById = products.associateBy { it.id }
    return selectedItems.entries
        .sortedBy { entry -> productById[entry.key]?.name ?: "" }
        .mapNotNull { (id, quantity) ->
            val product = productById[id] ?: return@mapNotNull null
            "$quantity× ${product.name}"
        }
        .joinToString(", ")
}

fun isPayButtonEnabled(totalAmountCents: Int, status: PaymentStatus): Boolean {
    val paymentInProgress = status is PaymentStatus.CreatingIntent ||
        status is PaymentStatus.WaitingForTap ||
        status is PaymentStatus.Processing ||
        status is PaymentStatus.FetchingReceipt
    return totalAmountCents > 0 && !paymentInProgress
}
