package com.darc.ovl11.clubpayment

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.stripe.stripeterminal.Terminal
import com.stripe.stripeterminal.external.callable.Callback
import com.stripe.stripeterminal.external.callable.PaymentIntentCallback
import com.stripe.stripeterminal.external.callable.TerminalListener
import com.stripe.stripeterminal.external.models.ConnectionTokenException
import com.stripe.stripeterminal.external.models.ConnectionTokenProvider
import com.stripe.stripeterminal.external.models.LogLevel
import com.stripe.stripeterminal.external.models.PaymentIntent
import com.stripe.stripeterminal.external.models.TerminalException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class BackendConnectionTokenProvider(private val service: BackendService) : ConnectionTokenProvider {
    private val scope = CoroutineScope(Dispatchers.IO)

    override fun fetchConnectionToken(callback: Callback) {
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

    init {
        if (!Terminal.isInitialized()) {
            Terminal.initTerminal(
                context,
                LogLevel.VERBOSE,
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
        return retrievePaymentIntent(response.client_secret)
    }

    suspend fun collectPayment(paymentIntent: PaymentIntent): PaymentIntent = suspendCancellableCoroutine { cont ->
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
        Terminal.getInstance().processPayment(paymentIntent, object : PaymentIntentCallback {
            override fun onSuccess(paymentIntent: PaymentIntent) {
                cont.resume(paymentIntent)
            }

            override fun onFailure(e: TerminalException) {
                cont.resumeWithException(e)
            }
        })
    }

    private suspend fun retrievePaymentIntent(clientSecret: String): PaymentIntent = suspendCancellableCoroutine { cont ->
        Terminal.getInstance().retrievePaymentIntent(clientSecret, object : PaymentIntentCallback {
            override fun onSuccess(paymentIntent: PaymentIntent) {
                cont.resume(paymentIntent)
            }

            override fun onFailure(e: TerminalException) {
                cont.resumeWithException(e)
            }
        })
    }

    fun readableDeviceName(): String {
        val model = Build.MODEL ?: "unknown"
        val androidId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        return "$model-$androidId"
    }
}

class SimpleTerminalListener : TerminalListener {
    override fun onUnexpectedReaderDisconnect() {
        // No-op, Tap to Pay handles lifecycle via Google Play Services.
    }
}
