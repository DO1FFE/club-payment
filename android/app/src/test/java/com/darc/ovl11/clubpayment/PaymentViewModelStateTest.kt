package com.darc.ovl11.clubpayment

import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever

class PaymentViewModelStateTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val cola = ProductDto(id = 1, name = "Cola", price_cents = 250, active = true)

    @Test
    fun `add und remove product aktualisieren mengen und summe`() = runTest {
        val terminalManager = mock<TerminalManager>()
        whenever(terminalManager.readableDeviceName()).thenReturn("test-geraet")
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()

        val viewModel = PaymentViewModel(terminalManager, authStore, backendService)

        viewModel.addProduct(cola)
        viewModel.addProduct(cola)

        assertEquals(2, viewModel.selectedItems.value[cola.id])

        viewModel.removeProduct(cola)
        assertEquals(1, viewModel.selectedItems.value[cola.id])

        viewModel.removeProduct(cola)
        assertEquals(null, viewModel.selectedItems.value[cola.id])
    }

    @Test
    fun `clearCart entfernt alle eintraege`() = runTest {
        val terminalManager = mock<TerminalManager>()
        whenever(terminalManager.readableDeviceName()).thenReturn("test-geraet")
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()

        val viewModel = PaymentViewModel(terminalManager, authStore, backendService)

        viewModel.addProduct(cola)
        viewModel.addCustomAmount("Gastbeitrag", 350)
        assertEquals(1, viewModel.selectedItems.value.size)
        assertEquals(1, viewModel.customItems.value.size)

        viewModel.clearCart()

        assertEquals(emptyMap<Int, Int>(), viewModel.selectedItems.value)
        assertEquals(emptyList<CustomCartItem>(), viewModel.customItems.value)
    }

    @Test
    fun `checkForAppUpdate meldet neue apk version`() = runTest {
        val terminalManager = mock<TerminalManager>()
        whenever(terminalManager.readableDeviceName()).thenReturn("test-geraet")
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()
        whenever(backendService.getLatestAppVersion()).thenReturn(
            AppVersionResponse(
                available = true,
                version = "1.0.13",
                sizeMb = "46,5",
                downloadPath = "/apk/latest",
            )
        )

        val viewModel = PaymentViewModel(terminalManager, authStore, backendService)

        viewModel.checkForAppUpdate(currentVersion = "1.0.12")
        advanceUntilIdle()

        val update = viewModel.appUpdate.value
        assertTrue(update is AppUpdateState.Available)
        update as AppUpdateState.Available
        assertEquals("1.0.13", update.version)
        assertEquals("https://payment.lima11.de/apk/latest", update.downloadUrl)
    }

    @Test
    fun `checkForAppUpdate bleibt ruhig wenn version aktuell ist`() = runTest {
        val terminalManager = mock<TerminalManager>()
        whenever(terminalManager.readableDeviceName()).thenReturn("test-geraet")
        val authStore = mock<AuthStore>()
        val backendService = mock<BackendService>()
        whenever(backendService.getLatestAppVersion()).thenReturn(
            AppVersionResponse(
                available = true,
                version = "1.0.12",
                downloadPath = "/apk/latest",
            )
        )

        val viewModel = PaymentViewModel(terminalManager, authStore, backendService)

        viewModel.checkForAppUpdate(currentVersion = "1.0.12")
        advanceUntilIdle()

        assertEquals(AppUpdateState.UpToDate, viewModel.appUpdate.value)
    }
}
