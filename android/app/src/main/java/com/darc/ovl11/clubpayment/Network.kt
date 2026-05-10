package com.darc.ovl11.clubpayment

import com.squareup.moshi.Json
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.serialization.Serializable
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.logging.HttpLoggingInterceptor
import org.json.JSONObject
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.HttpException
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import kotlinx.coroutines.runBlocking

@Serializable
data class ConnectionTokenResponse(val secret: String)

@Serializable
data class TerminalConfigResponse(
    val location_id: String,
)

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
    val device_id: String? = null,
)

@Serializable
data class LoginResponse(
    val token: String,
    @Json(name = "display_name")
    val displayName: String,
)

@Serializable
data class PaymentIntentRequest(
    val amount_cents: Int,
    val currency: String = "eur",
    val item: String,
    val kassierer: String,
    val device: String,
)

@Serializable
data class PaymentIntentResponse(
    val id: String,
    val client_secret: String,
    val amount_cents: Int,
)

@Serializable
data class ReceiptResponse(
    val receipt_url: String,
)

@Serializable
data class ProductDto(
    val id: Int,
    val name: String,
    val price_cents: Int,
    val active: Boolean,
)

@Serializable
data class ProductListResponse(
    val products: List<ProductDto>,
)

@Serializable
data class CreateProductRequest(
    val name: String,
    val price_cents: Int,
    val active: Boolean = true,
)

@Serializable
data class UpdateProductRequest(
    val name: String? = null,
    val price_cents: Int? = null,
    val active: Boolean? = null,
)

fun Throwable.backendErrorMessage(defaultMessage: String): String {
    val httpException = this as? HttpException
    val errorBody = httpException?.response()?.errorBody()?.string()
    val backendMessage = errorBody
        ?.let { body -> runCatching { JSONObject(body).optString("error") }.getOrNull() }
        ?.takeIf { it.isNotBlank() }
    return backendMessage ?: message ?: defaultMessage
}

interface BackendService {
    @POST("/terminal/connection_token")
    suspend fun createConnectionToken(): ConnectionTokenResponse

    @GET("/terminal/config")
    suspend fun getTerminalConfig(): TerminalConfigResponse

    @POST("/auth/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    @POST("/pos/create_intent")
    suspend fun createPaymentIntent(@Body request: PaymentIntentRequest): PaymentIntentResponse

    @GET("/pos/receipt/{payment_intent_id}")
    suspend fun getReceipt(@Path("payment_intent_id") paymentIntentId: String): ReceiptResponse

    @GET("/products")
    suspend fun listProducts(): ProductListResponse

    @POST("/admin/products")
    suspend fun createProduct(@Body request: CreateProductRequest): ProductDto

    @PATCH("/admin/products/{id}")
    suspend fun updateProduct(@Path("id") id: Int, @Body request: UpdateProductRequest): ProductDto
}

class AuthInterceptor(private val authStore: AuthStore) : okhttp3.Interceptor {
    override fun intercept(chain: okhttp3.Interceptor.Chain): okhttp3.Response {
        val token = runBlocking { authStore.currentToken() }
        val request = token?.takeIf { it.isNotBlank() }?.let {
            val newRequest: Request = chain.request().newBuilder()
                .addHeader("Authorization", "Bearer $it")
                .build()
            newRequest
        } ?: chain.request()
        return chain.proceed(request)
    }
}

fun provideBackendService(baseUrl: String, authStore: AuthStore): BackendService {
    val logging = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.DEBUG) {
            HttpLoggingInterceptor.Level.BASIC
        } else {
            HttpLoggingInterceptor.Level.NONE
        }
    }
    val client = OkHttpClient.Builder()
        .addInterceptor(AuthInterceptor(authStore))
        .addInterceptor(logging)
        .build()

    val moshi = Moshi.Builder()
        .add(KotlinJsonAdapterFactory())
        .build()

    val retrofit = Retrofit.Builder()
        .baseUrl(baseUrl)
        .addConverterFactory(MoshiConverterFactory.create(moshi))
        .client(client)
        .build()
    return retrofit.create(BackendService::class.java)
}
