package com.darc.ovl11.clubpayment

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PaymentViewModelCartTest {

    private val cola = ProductDto(id = 1, name = "Cola", price_cents = 250, active = true)
    private val wasser = ProductDto(id = 2, name = "Wasser", price_cents = 150, active = true)

    @Test
    fun `calculateTotalAmountCents berechnet summen mit mengen korrekt`() {
        val selectedItems = mapOf(
            cola.id to 2,
            wasser.id to 1,
        )

        val total = calculateTotalAmountCents(listOf(cola, wasser), selectedItems)

        assertEquals(650, total)
    }

    @Test
    fun `createItemLabel erstellt komprimierte artikelliste`() {
        val selectedItems = mapOf(
            wasser.id to 3,
            cola.id to 1,
        )

        val label = createItemLabel(listOf(cola, wasser), selectedItems)

        assertEquals("1× Cola, 3× Wasser", label)
    }

    @Test
    fun `isPayButtonEnabled ist nur bei positivem betrag und ohne laufende zahlung aktiv`() {
        assertFalse(isPayButtonEnabled(0, PaymentStatus.Idle))
        assertTrue(isPayButtonEnabled(100, PaymentStatus.Idle))
        assertFalse(isPayButtonEnabled(100, PaymentStatus.ConnectingReader))
        assertFalse(isPayButtonEnabled(100, PaymentStatus.Processing))
        assertTrue(isPayButtonEnabled(100, PaymentStatus.Error("Fehler")))
    }
}
