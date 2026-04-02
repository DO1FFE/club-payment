package com.darc.ovl11.clubpayment

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import org.mockito.kotlin.mock
import org.mockito.kotlin.whenever

class PaymentViewModelStateTest {

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
        assertEquals(1, viewModel.selectedItems.value.size)

        viewModel.clearCart()

        assertEquals(emptyMap<Int, Int>(), viewModel.selectedItems.value)
    }
}
