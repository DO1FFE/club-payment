package com.darc.ovl11.clubpayment

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

class AuthViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `app neustart mit token im store fuehrt zu auto login state`() = runTest {
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()
        val gespeicherteAuth = AuthData(token = "token-123", userName = "Max Mustermann")
        whenever(authStore.authData).thenReturn(MutableStateFlow(gespeicherteAuth))
        whenever(authStore.rememberedCredentials).thenReturn(MutableStateFlow(null))

        val viewModel = AuthViewModel(authStore, backendService)
        advanceUntilIdle()

        assertEquals(gespeicherteAuth, viewModel.authState.value)
    }

    @Test
    fun `login mit merken speichert token und zugangsdaten`() = runTest {
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()
        whenever(authStore.authData).thenReturn(MutableStateFlow(null))
        whenever(authStore.rememberedCredentials).thenReturn(MutableStateFlow(null))
        whenever(backendService.login(LoginRequest("max", "geheim", "geraet-1")))
            .thenReturn(LoginResponse(token = "token-xyz", displayName = "Max"))
        val viewModel = AuthViewModel(authStore, backendService)

        viewModel.login(userName = "max", password = "geheim", rememberCredentials = true, deviceId = "geraet-1")
        advanceUntilIdle()

        verify(authStore).saveAuth("token-xyz", "Max")
        verify(authStore).saveRememberedCredentials("max", "geheim")
    }

    @Test
    fun `logout loescht den aktiven token`() = runTest {
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()
        whenever(authStore.authData).thenReturn(MutableStateFlow(null))
        whenever(authStore.rememberedCredentials)
            .thenReturn(MutableStateFlow(RememberedCredentials("Max", "geheim")))
        val viewModel = AuthViewModel(authStore, backendService)

        viewModel.logout()
        advanceUntilIdle()

        verify(authStore).clearAuth()
    }

    @Test
    fun `login ohne merken entfernt gemerkte zugangsdaten`() = runTest {
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()
        whenever(authStore.authData).thenReturn(MutableStateFlow(null))
        whenever(authStore.rememberedCredentials)
            .thenReturn(MutableStateFlow(RememberedCredentials("Max", "geheim")))
        whenever(backendService.login(LoginRequest("max", "geheim")))
            .thenReturn(LoginResponse(token = "token-xyz", displayName = "Max"))
        val viewModel = AuthViewModel(authStore, backendService)

        viewModel.login(userName = "max", password = "geheim", rememberCredentials = false)
        advanceUntilIdle()

        verify(authStore).clearRememberedCredentials()
    }
}
