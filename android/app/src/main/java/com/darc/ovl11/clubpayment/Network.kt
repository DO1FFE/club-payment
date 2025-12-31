package com.darc.ovl11.clubpayment

import com.squareup.moshi.Json
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import kotlinx.serialization.Serializable
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST
import kotlinx.coroutines.runBlocking

@Serializable
data class ConnectionTokenResponse(val secret: String)

@Serializable
data class LoginRequest(
    val username: String,
    val password: String,
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

interface BackendService {
    @POST("/terminal/connection_token")
    suspend fun createConnectionToken(): ConnectionTokenResponse

    @POST("/auth/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    @POST("/pos/create_intent")
    suspend fun createPaymentIntent(@Body request: PaymentIntentRequest): PaymentIntentResponse
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
        level = HttpLoggingInterceptor.Level.BODY
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
