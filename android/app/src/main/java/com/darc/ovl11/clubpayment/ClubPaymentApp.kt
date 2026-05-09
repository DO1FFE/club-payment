package com.darc.ovl11.clubpayment

import android.app.Application
import com.stripe.stripeterminal.TerminalApplicationDelegate

class ClubPaymentApp : Application() {
    override fun onCreate() {
        super.onCreate()
        TerminalApplicationDelegate.onCreate(this)
    }
}
