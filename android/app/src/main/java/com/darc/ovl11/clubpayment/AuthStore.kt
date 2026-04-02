package com.darc.ovl11.clubpayment

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.authDataStore by preferencesDataStore(name = "auth")

data class AuthData(
    val token: String,
    val userName: String,
)

class AuthStore(private val context: Context) {
    private val tokenKey = stringPreferencesKey("auth_token")
    private val userKey = stringPreferencesKey("auth_user")
    private val rememberedUserKey = stringPreferencesKey("remembered_user_name")

    val authData: Flow<AuthData?> = context.authDataStore.data.map { prefs ->
        val token = prefs[tokenKey]
        val userName = prefs[userKey]
        if (token.isNullOrBlank() || userName.isNullOrBlank()) {
            null
        } else {
            AuthData(token = token, userName = userName)
        }
    }

    val rememberedUserName: Flow<String?> = context.authDataStore.data.map { prefs ->
        prefs[rememberedUserKey]?.takeIf { it.isNotBlank() }
    }

    suspend fun saveAuth(token: String, userName: String) {
        context.authDataStore.edit { prefs ->
            prefs[tokenKey] = token
            prefs[userKey] = userName
        }
    }

    suspend fun saveRememberedUserName(userName: String) {
        context.authDataStore.edit { prefs ->
            prefs[rememberedUserKey] = userName
        }
    }

    suspend fun clearRememberedCredentials() {
        context.authDataStore.edit { prefs ->
            prefs.remove(rememberedUserKey)
        }
    }

    suspend fun clearAuth() {
        context.authDataStore.edit { prefs ->
            prefs.remove(tokenKey)
            prefs.remove(userKey)
            prefs.remove(rememberedUserKey)
        }
    }

    suspend fun currentToken(): String? {
        return context.authDataStore.data.map { prefs -> prefs[tokenKey] }.first()
    }

    suspend fun currentUserName(): String? {
        return context.authDataStore.data.map { prefs -> prefs[userKey] }.first()
    }

    suspend fun currentRememberedUserName(): String? {
        return context.authDataStore.data.map { prefs -> prefs[rememberedUserKey] }.first()
    }
}
