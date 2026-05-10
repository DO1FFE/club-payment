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
    fun `calculateCartTotalAmountCents addiert freie betraege`() {
        val selectedItems = mapOf(cola.id to 1)
        val customItems = listOf(CustomCartItem(id = 1, description = "Spende", amountCents = 500))

        val total = calculateCartTotalAmountCents(listOf(cola), selectedItems, customItems)

        assertEquals(750, total)
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
    fun `createCartItemLabel enthaelt freie betraege mit beschreibung`() {
        val label = createCartItemLabel(
            products = listOf(cola),
            selectedItems = mapOf(cola.id to 1),
            customItems = listOf(CustomCartItem(id = 1, description = "Gastbeitrag", amountCents = 375)),
        )

        assertTrue(label.contains("Cola"))
        assertTrue(label.contains("Gastbeitrag"))
        assertTrue(label.contains("3,75"))
    }

    @Test
    fun `parseEuroAmountToCents akzeptiert komma und lehnt ungueltige werte ab`() {
        assertEquals(250, parseEuroAmountToCents("2,50"))
        assertEquals(200, parseEuroAmountToCents("2"))
        assertEquals(null, parseEuroAmountToCents("0"))
        assertEquals(null, parseEuroAmountToCents("1,234"))
    }

    @Test
    fun `generateQrCodePixels erstellt quittungs qr code`() {
        val pixels = generateQrCodePixels("https://pay.stripe.com/receipts/test", size = 128)

        assertEquals(128 * 128, pixels?.size)
    }

    @Test
    fun `isPayButtonEnabled ist nur bei positivem betrag und ohne laufende zahlung aktiv`() {
        assertFalse(isPayButtonEnabled(0, PaymentStatus.Idle))
        assertTrue(isPayButtonEnabled(100, PaymentStatus.Idle))
        assertFalse(isPayButtonEnabled(100, PaymentStatus.ActivatingPhoneNfc))
        assertFalse(isPayButtonEnabled(100, PaymentStatus.Processing))
        assertTrue(isPayButtonEnabled(100, PaymentStatus.Error("Fehler")))
    }
}
