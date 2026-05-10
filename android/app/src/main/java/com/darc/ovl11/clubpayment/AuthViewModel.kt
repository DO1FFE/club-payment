package com.darc.ovl11.clubpayment

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

sealed class LoginStatus {
    data object Idle : LoginStatus()
    data object Loading : LoginStatus()
    data class Error(val message: String) : LoginStatus()
}

class AuthViewModel(
    private val authStore: AuthStore,
    private val backendService: BackendService,
) : ViewModel() {
    val authState: StateFlow<AuthData?> = authStore.authData
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    val rememberedCredentials: StateFlow<RememberedCredentials?> = authStore.rememberedCredentials
        .stateIn(viewModelScope, SharingStarted.Eagerly, null)

    private val _loginStatus = MutableStateFlow<LoginStatus>(LoginStatus.Idle)
    val loginStatus: StateFlow<LoginStatus> = _loginStatus.asStateFlow()

    fun login(userName: String, password: String, rememberCredentials: Boolean, deviceId: String? = null) {
        viewModelScope.launch {
            _loginStatus.value = LoginStatus.Loading
            try {
                val response = backendService.login(
                    LoginRequest(username = userName, password = password, device_id = deviceId)
                )
                authStore.saveAuth(response.token, response.displayName)
                if (rememberCredentials) {
                    authStore.saveRememberedCredentials(userName, password)
                } else {
                    authStore.clearRememberedCredentials()
                }
                _loginStatus.value = LoginStatus.Idle
            } catch (e: Exception) {
                _loginStatus.value = LoginStatus.Error(e.backendErrorMessage("Login fehlgeschlagen"))
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            authStore.clearAuth()
            _loginStatus.value = LoginStatus.Idle
        }
    }
}
