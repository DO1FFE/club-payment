package com.darc.ovl11.clubpayment

import android.app.Application
import android.content.res.Configuration
import com.stripe.stripeterminal.TerminalApplicationDelegate

class ClubPaymentApp : Application() {
    override fun onCreate() {
        super.onCreate()
        TerminalApplicationDelegate.onCreate(this)
    }

    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        TerminalApplicationDelegate.onTrimMemory(level)
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        TerminalApplicationDelegate.onConfigurationChanged(newConfig)
    }

    override fun onLowMemory() {
        super.onLowMemory()
        TerminalApplicationDelegate.onLowMemory()
    }
}
