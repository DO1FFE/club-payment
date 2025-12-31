import com.android.build.gradle.internal.cxx.configure.gradleLocalProperties

plugins {
    id("com.android.application")
    kotlin("android")
    kotlin("plugin.serialization") version "1.9.24"
}

android {
    namespace = "com.darc.ovl11.clubpayment"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.darc.ovl11.clubpayment"
        minSdk = 30
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        val props = gradleLocalProperties(rootDir)
        val backendUrl = props.getProperty("BACKEND_BASE_URL") ?: project.findProperty("BACKEND_BASE_URL")?.toString()
        val locationId = props.getProperty("LOCATION_ID") ?: project.findProperty("LOCATION_ID")?.toString()
        if (backendUrl.isNullOrBlank()) {
            throw GradleException("BACKEND_BASE_URL must be set in local.properties or gradle.properties")
        }

        buildConfigField("String", "BACKEND_BASE_URL", "\"$backendUrl\"")
        buildConfigField("String", "LOCATION_ID", "\"${locationId ?: ""}\"")
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.15"
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.08.00"))
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.4")
    implementation("androidx.datastore:datastore-preferences:1.1.1")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-moshi:2.11.0")
    implementation("com.squareup.moshi:moshi-kotlin:1.15.1")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    implementation("com.stripe:stripeterminal:3.10.1")
}
