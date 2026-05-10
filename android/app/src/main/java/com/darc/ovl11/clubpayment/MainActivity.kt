package com.darc.ovl11.clubpayment

import android.graphics.Bitmap
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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

private val ClubGreen = Color(0xFF0D5C46)
private val ClubGreenDark = Color(0xFF094333)
private val ClubGold = Color(0xFFF1B642)
private val ClubBackground = Color(0xFFF5F7F4)
private val ClubSurface = Color(0xFFFFFFFF)
private val ClubInk = Color(0xFF16211D)
private val ClubMuted = Color(0xFF60716A)
private val ClubBorder = Color(0xFFD9E1DC)
private val ClubDanger = Color(0xFFB42318)

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
            ClubPaymentTheme {
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
                _productsError.value = e.backendErrorMessage("Produkte konnten nicht geladen werden")
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
                _status.value = PaymentStatus.ActivatingPhoneNfc
                terminalManager.ensurePhoneNfcReady()
                _status.value = PaymentStatus.WaitingForTap
                val collected = terminalManager.collectPayment(intent)
                _status.value = PaymentStatus.Processing
                val processed = terminalManager.processPayment(collected)
                _status.value = PaymentStatus.FetchingReceipt
                val processedIntentId = processed.id ?: intent.id
                if (processedIntentId.isNullOrBlank()) {
                    _status.value = PaymentStatus.Error("PaymentIntent-ID fehlt")
                    return@launch
                }
                val paidAmountCents = processed.amount.toInt()
                val receiptResult = fetchReceiptUrl(processedIntentId)
                _status.value = PaymentStatus.Success(
                    amountCents = paidAmountCents,
                    intentId = processedIntentId,
                    receiptUrl = receiptResult.first,
                    receiptError = receiptResult.second
                )
                clearCart()
            } catch (e: Exception) {
                _status.value = PaymentStatus.Error(e.backendErrorMessage("Unbekannter Fehler"))
            }
        }
    }

    private suspend fun fetchReceiptUrl(paymentIntentId: String): Pair<String?, String?> {
        return try {
            val response = backendService.getReceipt(paymentIntentId)
            Pair(response.receipt_url, null)
        } catch (e: Exception) {
            Pair(null, e.backendErrorMessage("Beleg konnte nicht geladen werden"))
        }
    }
}

@Composable
fun ClubPaymentTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = ClubGreen,
            onPrimary = Color.White,
            secondary = ClubGold,
            onSecondary = ClubInk,
            background = ClubBackground,
            surface = ClubSurface,
            onSurface = ClubInk,
            error = ClubDanger,
        ),
        content = content
    )
}

@Composable
fun AppContent(viewModel: PaymentViewModel, authViewModel: AuthViewModel) {
    val authState by authViewModel.authState.collectAsState()
    val deviceName = viewModel.deviceName

    Surface(
        modifier = Modifier.fillMaxSize(),
        color = ClubBackground
    ) {
        if (authState == null) {
            LoginScreen(authViewModel, deviceName)
        } else {
            LaunchedEffect(authState?.token) {
                viewModel.loadProducts()
            }
            PaymentScreen(
                viewModel = viewModel,
                userName = authState?.userName.orEmpty(),
                deviceName = deviceName,
                onLogout = { authViewModel.logout() }
            )
        }
    }
}

@Composable
fun LoginScreen(authViewModel: AuthViewModel, deviceName: String) {
    var userName by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var rememberCredentials by remember { mutableStateOf(false) }
    val rememberedCredentials by authViewModel.rememberedCredentials.collectAsState()
    val loginStatus by authViewModel.loginStatus.collectAsState()

    LaunchedEffect(rememberedCredentials) {
        val credentials = rememberedCredentials
        if (credentials != null) {
            if (userName.isBlank()) {
                userName = credentials.userName
            }
            if (password.isBlank()) {
                password = credentials.password
            }
            rememberCredentials = true
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(ClubBackground)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp)
        ) {
            BrandHeader(
                title = "Club Kasse",
                subtitle = "DARC OV L11",
                detail = "Kartenzahlung per NFC"
            )

            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(8.dp),
                colors = CardDefaults.cardColors(containerColor = ClubSurface),
                elevation = CardDefaults.cardElevation(defaultElevation = 3.dp)
            ) {
                Column(
                    modifier = Modifier.padding(18.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp)
                ) {
                    Text(
                        text = "Anmelden",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    OutlinedTextField(
                        value = userName,
                        onValueChange = { userName = it },
                        label = { Text("Benutzername") },
                        leadingIcon = {
                            Icon(
                                painter = painterResource(R.drawable.ic_person),
                                contentDescription = null
                            )
                        },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                        modifier = Modifier.fillMaxWidth()
                    )
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Passwort") },
                        leadingIcon = {
                            Icon(
                                painter = painterResource(R.drawable.ic_lock),
                                contentDescription = null
                            )
                        },
                        singleLine = true,
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
                        Text(
                            text = "Zugangsdaten merken",
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.weight(1f)
                        )
                    }
                    InfoPill(
                        icon = R.drawable.ic_device,
                        text = "Geräte-ID: $deviceName"
                    )
                    Button(
                        onClick = { authViewModel.login(userName.trim(), password, rememberCredentials) },
                        enabled = userName.isNotBlank() && password.isNotBlank() && loginStatus !is LoginStatus.Loading,
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = ClubGreen),
                        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp)
                    ) {
                        if (loginStatus is LoginStatus.Loading) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                strokeWidth = 2.dp,
                                color = Color.White
                            )
                        } else {
                            Icon(
                                painter = painterResource(R.drawable.ic_login),
                                contentDescription = null,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Anmelden")
                    }
                    if (loginStatus is LoginStatus.Error) {
                        ErrorText("Fehler: ${(loginStatus as LoginStatus.Error).message}")
                    }
                }
            }
        }
    }
}

@Composable
fun PaymentScreen(viewModel: PaymentViewModel, userName: String, deviceName: String, onLogout: () -> Unit) {
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
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        PaymentHeader(
            userName = userName,
            deviceName = deviceName,
            onLogout = onLogout
        )

        productsError?.let { errorText ->
            ErrorPanel("Produkte konnten nicht geladen werden: $errorText")
        }

        ProductSection(
            products = products,
            productsLoading = productsLoading,
            onAddProduct = { viewModel.addProduct(it) }
        )

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
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 54.dp),
            colors = ButtonDefaults.buttonColors(containerColor = ClubGreen),
            contentPadding = PaddingValues(horizontal = 18.dp, vertical = 14.dp)
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_nfc),
                contentDescription = null,
                modifier = Modifier.size(22.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text("Bezahlen", fontWeight = FontWeight.Bold)
        }

        StatusCard(status)

        val success = status as? PaymentStatus.Success
        if (success?.receiptUrl != null) {
            ReceiptQrCard(success.receiptUrl)
        }
    }
}

@Composable
fun BrandHeader(title: String, subtitle: String, detail: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Image(
            painter = painterResource(R.drawable.ic_club_payment_logo),
            contentDescription = null,
            modifier = Modifier.size(56.dp)
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = subtitle.uppercase(Locale.GERMANY),
                color = ClubMuted,
                fontSize = 12.sp,
                fontWeight = FontWeight.ExtraBold
            )
            Text(
                text = title,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.ExtraBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = detail,
                color = ClubMuted,
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
fun PaymentHeader(userName: String, deviceName: String, onLogout: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = ClubGreen),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    Image(
                        painter = painterResource(R.drawable.ic_club_payment_logo),
                        contentDescription = null,
                        modifier = Modifier.size(48.dp)
                    )
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Club Kasse",
                            color = Color.White,
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.ExtraBold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                        Text(
                            text = "Angemeldet als $userName",
                            color = Color.White.copy(alpha = 0.86f),
                            style = MaterialTheme.typography.bodyMedium,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
                TextButton(onClick = onLogout) {
                    Icon(
                        painter = painterResource(R.drawable.ic_logout),
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Abmelden", color = Color.White)
                }
            }
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = Color.White.copy(alpha = 0.12f),
                contentColor = Color.White
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 9.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        painter = painterResource(R.drawable.ic_device),
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Text(
                        text = "Geräte-ID: $deviceName",
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}

@Composable
fun ProductSection(
    products: List<ProductDto>,
    productsLoading: Boolean,
    onAddProduct: (ProductDto) -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = ClubSurface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionTitle(
                icon = R.drawable.ic_card,
                title = "Produkte",
                trailing = if (productsLoading) "Lädt" else "${products.size} aktiv"
            )
            if (productsLoading) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                    Text("Produkte werden geladen", color = ClubMuted)
                }
            } else if (products.isEmpty()) {
                Text(
                    text = "Keine aktiven Produkte vorhanden.",
                    color = ClubMuted,
                    style = MaterialTheme.typography.bodyMedium
                )
            } else {
                products.chunked(2).forEach { rowProducts ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        rowProducts.forEach { product ->
                            PriceButton(product.name, product.price_cents) {
                                onAddProduct(product)
                            }
                        }
                        if (rowProducts.size == 1) {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
        }
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
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = ClubSurface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionTitle(
                icon = R.drawable.ic_cart,
                title = "Warenkorb",
                trailing = formatCurrency(totalAmountCents)
            )
            if (selectedItems.isEmpty()) {
                Text(
                    text = "Noch keine Produkte ausgewählt.",
                    color = ClubMuted,
                    style = MaterialTheme.typography.bodyMedium
                )
            } else {
                val selectedProducts = products.filter { selectedItems.containsKey(it.id) }
                selectedProducts.forEachIndexed { index, product ->
                    val quantity = selectedItems[product.id] ?: 0
                    CartItemRow(
                        product = product,
                        quantity = quantity,
                        onAddProduct = onAddProduct,
                        onRemoveProduct = onRemoveProduct
                    )
                    if (index < selectedProducts.size - 1) {
                        HorizontalDivider(color = ClubBorder)
                    }
                }
                OutlinedButton(
                    onClick = onClearCart,
                    modifier = Modifier.fillMaxWidth(),
                    border = BorderStroke(1.dp, ClubBorder)
                ) {
                    Icon(
                        painter = painterResource(R.drawable.ic_clear),
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Warenkorb leeren")
                }
            }
        }
    }
}

@Composable
fun CartItemRow(
    product: ProductDto,
    quantity: Int,
    onAddProduct: (ProductDto) -> Unit,
    onRemoveProduct: (ProductDto) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = product.name,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = "${quantity} x ${formatCurrency(product.price_cents)}",
                color = ClubMuted,
                style = MaterialTheme.typography.bodySmall
            )
        }
        Surface(
            shape = CircleShape,
            color = ClubBackground,
            contentColor = ClubInk
        ) {
            Text(
                text = quantity.toString(),
                modifier = Modifier
                    .widthIn(min = 34.dp)
                    .padding(horizontal = 10.dp, vertical = 7.dp),
                fontWeight = FontWeight.Bold
            )
        }
        IconButton(
            onClick = { onRemoveProduct(product) },
            modifier = Modifier.size(42.dp)
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_remove),
                contentDescription = "${product.name} entfernen"
            )
        }
        IconButton(
            onClick = { onAddProduct(product) },
            modifier = Modifier.size(42.dp)
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_add),
                contentDescription = "${product.name} hinzufügen"
            )
        }
    }
}

@Composable
fun RowScope.PriceButton(label: String, amountCents: Int, onClick: () -> Unit) {
    OutlinedButton(
        onClick = onClick,
        modifier = Modifier
            .weight(1f)
            .heightIn(min = 92.dp),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, ClubBorder),
        contentPadding = PaddingValues(12.dp)
    ) {
        Column(
            horizontalAlignment = Alignment.Start,
            verticalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_add),
                contentDescription = null,
                tint = ClubGreen,
                modifier = Modifier.size(18.dp)
            )
            Text(
                text = label,
                color = ClubInk,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = formatCurrency(amountCents),
                color = ClubGreen,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
fun StatusCard(status: PaymentStatus) {
    val statusInfo = statusInfo(status)
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = ClubSurface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Surface(
                    modifier = Modifier.size(42.dp),
                    shape = CircleShape,
                    color = statusInfo.tint.copy(alpha = 0.14f),
                    contentColor = statusInfo.tint
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            painter = painterResource(statusInfo.icon),
                            contentDescription = null,
                            modifier = Modifier.size(22.dp)
                        )
                    }
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = statusInfo.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = statusInfo.message,
                        color = ClubMuted,
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }
            val success = status as? PaymentStatus.Success
            if (success?.receiptError != null) {
                ErrorText("Beleg konnte nicht geladen werden: ${success.receiptError}")
            }
        }
    }
}

@Composable
fun ReceiptQrCard(receiptUrl: String) {
    val qrBitmap = remember(receiptUrl) { generateQrCodeBitmap(receiptUrl) }
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = ClubSurface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(
            modifier = Modifier.padding(18.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            SectionTitle(
                icon = R.drawable.ic_receipt,
                title = "Quittung",
                trailing = "QR-Code"
            )
            if (qrBitmap == null) {
                ErrorText("QR-Code konnte nicht erstellt werden")
            } else {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, ClubBorder),
                    color = Color.White
                ) {
                    Image(
                        bitmap = qrBitmap.asImageBitmap(),
                        contentDescription = "QR-Code für die Quittung",
                        modifier = Modifier
                            .size(220.dp)
                            .padding(10.dp)
                    )
                }
                Text(
                    text = "QR-Code scannen, um die Quittung anzusehen.",
                    color = ClubMuted,
                    style = MaterialTheme.typography.bodyMedium
                )
                Text(
                    text = receiptUrl,
                    color = ClubMuted,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }
}

@Composable
fun SectionTitle(icon: Int, title: String, trailing: String? = null) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Surface(
            modifier = Modifier.size(34.dp),
            shape = CircleShape,
            color = ClubGreen.copy(alpha = 0.12f),
            contentColor = ClubGreen
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(
                    painter = painterResource(icon),
                    contentDescription = null,
                    modifier = Modifier.size(18.dp)
                )
            }
        }
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.weight(1f)
        )
        trailing?.let {
            Text(
                text = it,
                color = ClubMuted,
                style = MaterialTheme.typography.labelLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
fun InfoPill(icon: Int, text: String) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = ClubBackground,
        contentColor = ClubInk,
        border = BorderStroke(1.dp, ClubBorder)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Icon(
                painter = painterResource(icon),
                contentDescription = null,
                modifier = Modifier.size(18.dp)
            )
            Text(
                text = text,
                style = MaterialTheme.typography.bodySmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
fun ErrorPanel(message: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        color = ClubDanger.copy(alpha = 0.09f),
        contentColor = ClubDanger,
        border = BorderStroke(1.dp, ClubDanger.copy(alpha = 0.24f))
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Icon(
                painter = painterResource(R.drawable.ic_warning),
                contentDescription = null,
                modifier = Modifier.size(20.dp)
            )
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f)
            )
        }
    }
}

@Composable
fun ErrorText(message: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Icon(
            painter = painterResource(R.drawable.ic_warning),
            contentDescription = null,
            tint = ClubDanger,
            modifier = Modifier.size(18.dp)
        )
        Text(
            text = message,
            color = ClubDanger,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f)
        )
    }
}

private data class StatusInfo(
    val title: String,
    val message: String,
    val icon: Int,
    val tint: Color,
)

private fun statusInfo(status: PaymentStatus): StatusInfo {
    return when (status) {
        PaymentStatus.Idle -> StatusInfo(
            title = "Bereit",
            message = "Warenkorb füllen und NFC-Zahlung starten.",
            icon = R.drawable.ic_nfc,
            tint = ClubGreen
        )
        PaymentStatus.CreatingIntent -> StatusInfo(
            title = "Zahlung wird vorbereitet",
            message = "Der Zahlungsauftrag wird beim Server erstellt.",
            icon = R.drawable.ic_card,
            tint = ClubGold
        )
        PaymentStatus.ActivatingPhoneNfc -> StatusInfo(
            title = "Handy-NFC wird aktiviert",
            message = "Dieses Handy wird als Tap-to-Pay-Terminal vorbereitet.",
            icon = R.drawable.ic_device,
            tint = ClubGold
        )
        PaymentStatus.WaitingForTap -> StatusInfo(
            title = "Bereit zum Auflegen",
            message = "Karte oder Wallet an den NFC-Bereich dieses Handys halten.",
            icon = R.drawable.ic_nfc,
            tint = ClubGold
        )
        PaymentStatus.Processing -> StatusInfo(
            title = "Zahlung läuft",
            message = "Die Zahlung wird verarbeitet.",
            icon = R.drawable.ic_card,
            tint = ClubGold
        )
        PaymentStatus.FetchingReceipt -> StatusInfo(
            title = "Quittung wird geladen",
            message = "Die Beleg-URL wird von Stripe abgerufen.",
            icon = R.drawable.ic_receipt,
            tint = ClubGold
        )
        is PaymentStatus.Success -> StatusInfo(
            title = "Zahlung erfolgreich",
            message = "${formatCurrency(status.amountCents)} bezahlt. PaymentIntent: ${status.intentId}",
            icon = R.drawable.ic_receipt,
            tint = ClubGreen
        )
        is PaymentStatus.Error -> StatusInfo(
            title = "Fehler",
            message = status.message,
            icon = R.drawable.ic_warning,
            tint = ClubDanger
        )
    }
}

fun generateQrCodeBitmap(content: String, size: Int = 512): Bitmap? {
    return try {
        val pixels = generateQrCodePixels(content, size) ?: return null
        Bitmap.createBitmap(pixels, size, size, Bitmap.Config.ARGB_8888)
    } catch (e: Exception) {
        null
    }
}

fun generateQrCodePixels(content: String, size: Int = 512): IntArray? {
    return try {
        val matrix = QRCodeWriter().encode(content, BarcodeFormat.QR_CODE, size, size)
        IntArray(size * size) { index ->
            val x = index % size
            val y = index / size
            if (matrix.get(x, y)) {
                0xFF000000.toInt()
            } else {
                0xFFFFFFFF.toInt()
            }
        }
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
        status is PaymentStatus.ActivatingPhoneNfc ||
        status is PaymentStatus.WaitingForTap ||
        status is PaymentStatus.Processing ||
        status is PaymentStatus.FetchingReceipt
    return totalAmountCents > 0 && !paymentInProgress
}

fun formatCurrency(amountCents: Int): String {
    val formatter = NumberFormat.getCurrencyInstance(Locale.GERMANY)
    return formatter.format(amountCents / 100.0)
}
