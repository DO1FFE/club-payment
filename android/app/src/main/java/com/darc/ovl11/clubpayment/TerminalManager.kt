package com.darc.ovl11.clubpayment

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.stripe.stripeterminal.Terminal
import com.stripe.stripeterminal.external.callable.Callback
import com.stripe.stripeterminal.external.callable.Cancelable
import com.stripe.stripeterminal.external.callable.ConnectionTokenCallback
import com.stripe.stripeterminal.external.callable.ConnectionTokenProvider
import com.stripe.stripeterminal.external.callable.DiscoveryListener
import com.stripe.stripeterminal.external.callable.PaymentIntentCallback
import com.stripe.stripeterminal.external.callable.ReaderCallback
import com.stripe.stripeterminal.external.callable.TerminalListener
import com.stripe.stripeterminal.external.models.ConnectionConfiguration
import com.stripe.stripeterminal.external.models.ConnectionTokenException
import com.stripe.stripeterminal.external.models.ConnectionStatus
import com.stripe.stripeterminal.external.models.DiscoveryConfiguration
import com.stripe.stripeterminal.external.models.PaymentIntent
import com.stripe.stripeterminal.external.models.Reader
import com.stripe.stripeterminal.external.models.TerminalException
import com.stripe.stripeterminal.log.LogLevel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class BackendConnectionTokenProvider(private val service: BackendService) : ConnectionTokenProvider {
    private val scope = CoroutineScope(Dispatchers.IO)

    override fun fetchConnectionToken(callback: ConnectionTokenCallback) {
        scope.launch {
            try {
                val token = service.createConnectionToken()
                callback.onSuccess(token.secret)
            } catch (e: Exception) {
                callback.onFailure(ConnectionTokenException("Failed to fetch connection token", e))
            }
        }
    }
}

sealed class PaymentStatus {
    object Idle : PaymentStatus()
    object CreatingIntent : PaymentStatus()
    object ConnectingReader : PaymentStatus()
    object WaitingForTap : PaymentStatus()
    object Processing : PaymentStatus()
    object FetchingReceipt : PaymentStatus()
    data class Success(
        val amountCents: Int,
        val intentId: String,
        val receiptUrl: String?,
        val receiptError: String? = null,
    ) : PaymentStatus()
    data class Error(val message: String) : PaymentStatus()
}

class TerminalManager(private val context: Context, private val backendService: BackendService) {
    private fun ensureInitialized() {
        if (!Terminal.isInitialized()) {
            Terminal.initTerminal(
                context,
                if (BuildConfig.DEBUG) LogLevel.INFO else LogLevel.NONE,
                BackendConnectionTokenProvider(backendService),
                SimpleTerminalListener()
            )
        }
    }

    suspend fun createIntent(amountCents: Int, item: String, kassierer: String, device: String): PaymentIntent {
        val request = PaymentIntentRequest(
            amount_cents = amountCents,
            item = item,
            kassierer = kassierer,
            device = device
        )
        val response = backendService.createPaymentIntent(request)
        ensureInitialized()
        return retrievePaymentIntent(response.client_secret)
    }

    suspend fun ensureReaderConnected() {
        ensureInitialized()
        val terminal = Terminal.getInstance()
        if (terminal.connectionStatus == ConnectionStatus.CONNECTED && terminal.connectedReader != null) {
            return
        }
        val reader = discoverLocalMobileReader()
        connectLocalMobileReader(reader)
    }

    suspend fun collectPayment(paymentIntent: PaymentIntent): PaymentIntent = suspendCancellableCoroutine { cont ->
        ensureInitialized()
        Terminal.getInstance().collectPaymentMethod(paymentIntent, object : PaymentIntentCallback {
            override fun onSuccess(paymentIntent: PaymentIntent) {
                cont.resume(paymentIntent)
            }

            override fun onFailure(e: TerminalException) {
                cont.resumeWithException(e)
            }
        })
    }

    suspend fun processPayment(paymentIntent: PaymentIntent): PaymentIntent = suspendCancellableCoroutine { cont ->
        ensureInitialized()
        Terminal.getInstance().confirmPaymentIntent(paymentIntent, object : PaymentIntentCallback {
            override fun onSuccess(paymentIntent: PaymentIntent) {
                cont.resume(paymentIntent)
            }

            override fun onFailure(e: TerminalException) {
                cont.resumeWithException(e)
            }
        })
    }

    private suspend fun retrievePaymentIntent(clientSecret: String): PaymentIntent = suspendCancellableCoroutine { cont ->
        ensureInitialized()
        Terminal.getInstance().retrievePaymentIntent(clientSecret, object : PaymentIntentCallback {
            override fun onSuccess(paymentIntent: PaymentIntent) {
                cont.resume(paymentIntent)
            }

            override fun onFailure(e: TerminalException) {
                cont.resumeWithException(e)
            }
        })
    }

    private suspend fun discoverLocalMobileReader(): Reader = suspendCancellableCoroutine { cont ->
        ensureInitialized()
        var cancelable: Cancelable? = null
        var completed = false

        fun resumeWithReader(reader: Reader) {
            if (completed || !cont.isActive) {
                return
            }
            completed = true
            cancelable?.cancel(NoopCallback)
            cont.resume(reader)
        }

        cancelable = Terminal.getInstance().discoverReaders(
            DiscoveryConfiguration.LocalMobileDiscoveryConfiguration(BuildConfig.DEBUG),
            object : DiscoveryListener {
                override fun onUpdateDiscoveredReaders(readers: List<Reader>) {
                    readers.firstOrNull()?.let { reader -> resumeWithReader(reader) }
                }
            },
            object : Callback {
                override fun onSuccess() {
                    if (!completed && cont.isActive) {
                        completed = true
                        cont.resumeWithException(IllegalStateException("Kein Tap-to-Pay-Leser gefunden"))
                    }
                }

                override fun onFailure(e: TerminalException) {
                    if (!completed && cont.isActive) {
                        completed = true
                        cont.resumeWithException(e)
                    }
                }
            }
        )
        cont.invokeOnCancellation { cancelable?.cancel(NoopCallback) }
    }

    private suspend fun connectLocalMobileReader(reader: Reader): Reader = suspendCancellableCoroutine { cont ->
        ensureInitialized()
        val locationId = BuildConfig.LOCATION_ID.trim()
        if (locationId.isBlank()) {
            cont.resumeWithException(
                IllegalStateException("LOCATION_ID fehlt; fuer Stripe Tap to Pay muss eine Stripe-Location-ID konfiguriert sein")
            )
            return@suspendCancellableCoroutine
        }
        Terminal.getInstance().connectLocalMobileReader(
            reader,
            ConnectionConfiguration.LocalMobileConnectionConfiguration(locationId),
            object : ReaderCallback {
                override fun onSuccess(reader: Reader) {
                    cont.resume(reader)
                }

                override fun onFailure(e: TerminalException) {
                    cont.resumeWithException(e)
                }
            }
        )
    }

    fun readableDeviceName(): String {
        val model = Build.MODEL ?: "unknown"
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        return "$model-$androidId"
    }
}

class SimpleTerminalListener : TerminalListener {
    override fun onUnexpectedReaderDisconnect(reader: Reader) {
        // No-op, Tap to Pay handles lifecycle via Google Play Services.
    }
}

object NoopCallback : Callback {
    override fun onSuccess() = Unit

    override fun onFailure(e: TerminalException) = Unit
}
