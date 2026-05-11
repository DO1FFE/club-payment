package com.darc.ovl11.clubpayment

import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
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
    fun `normalizeStripeLocationId akzeptiert null und trimmt werte`() {
        assertEquals("", normalizeStripeLocationId(null))
        assertEquals("tml_123", normalizeStripeLocationId("  tml_123  "))
    }

    @Test
    fun `TerminalConfigResponse liest stripe location aus backend json`() {
        val moshi = Moshi.Builder()
            .add(KotlinJsonAdapterFactory())
            .build()
        val adapter = moshi.adapter(TerminalConfigResponse::class.java)

        val response = adapter.fromJson("""{"location_id":"tml_123"}""")

        assertEquals("tml_123", response?.locationId)
    }

    @Test
    fun `AppVersionResponse liest update metadaten aus backend json`() {
        val moshi = Moshi.Builder()
            .add(KotlinJsonAdapterFactory())
            .build()
        val adapter = moshi.adapter(AppVersionResponse::class.java)

        val response = adapter.fromJson(
            """{"available":true,"version":"1.0.13","size_mb":"46,5","download_path":"/apk/latest"}"""
        )

        assertEquals(true, response?.available)
        assertEquals("1.0.13", response?.version)
        assertEquals("46,5", response?.sizeMb)
        assertEquals("/apk/latest", response?.downloadPath)
    }

    @Test
    fun `ReceiptResponse liest beleg url aus backend json`() {
        val moshi = Moshi.Builder()
            .add(KotlinJsonAdapterFactory())
            .build()
        val adapter = moshi.adapter(ReceiptResponse::class.java)

        val response = adapter.fromJson("""{"receipt_url":"https://pay.stripe.com/receipts/test"}""")

        assertEquals("https://pay.stripe.com/receipts/test", response?.receiptUrl)
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
        assertFalse(isPayButtonEnabled(100, PaymentStatus.Idle, NfcAvailability.Disabled))
        assertFalse(isPayButtonEnabled(100, PaymentStatus.Idle, NfcAvailability.Unavailable))
    }

    @Test
    fun `compareVersionNames erkennt neuere versionen`() {
        assertTrue(compareVersionNames("1.0.13", "1.0.12") > 0)
        assertEquals(0, compareVersionNames("1.0.12", "1.0.12"))
        assertTrue(compareVersionNames("1.0.12", "1.0.13") < 0)
        assertEquals(0, compareVersionNames("1.0", "1.0.0"))
    }

    @Test
    fun `shouldShowPaymentResultDialog reagiert nur auf erfolg und fehler`() {
        assertFalse(shouldShowPaymentResultDialog(PaymentStatus.Idle))
        assertFalse(shouldShowPaymentResultDialog(PaymentStatus.Processing))
        assertTrue(shouldShowPaymentResultDialog(PaymentStatus.Error("Fehler")))
        assertTrue(
            shouldShowPaymentResultDialog(
                PaymentStatus.Success(
                    amountCents = 150,
                    intentId = "pi_test",
                    receiptUrl = "https://pay.stripe.com/receipts/test",
                )
            )
        )
    }

    @Test
    fun `canShowAppUpdateDialog erscheint nur im ruhezustand`() {
        assertTrue(canShowAppUpdateDialog(PaymentStatus.Idle))
        assertFalse(canShowAppUpdateDialog(PaymentStatus.Processing))
        assertFalse(canShowAppUpdateDialog(PaymentStatus.Error("Fehler")))
    }
}
