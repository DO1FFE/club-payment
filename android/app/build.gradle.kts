import com.android.build.gradle.internal.cxx.configure.gradleLocalProperties
import java.net.URI
import java.net.URISyntaxException

plugins {
    id("com.android.application")
    kotlin("android")
    kotlin("plugin.serialization") version "1.9.25"
}

android {
    namespace = "com.darc.ovl11.clubpayment"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.darc.ovl11.clubpayment"
        minSdk = 30
        targetSdk = 34
        versionCode = 15
        versionName = "1.0.14"

        val props = gradleLocalProperties(rootDir, providers)
        val backendUrl = props.getProperty("BACKEND_BASE_URL") ?: project.findProperty("BACKEND_BASE_URL")?.toString()
        val locationId = props.getProperty("LOCATION_ID") ?: project.findProperty("LOCATION_ID")?.toString()
        if (backendUrl.isNullOrBlank()) {
            throw GradleException("BACKEND_BASE_URL must be set in local.properties or gradle.properties")
        }
        val backendUri = try {
            URI(backendUrl)
        } catch (error: URISyntaxException) {
            throw GradleException("BACKEND_BASE_URL is not a valid URL: $backendUrl", error)
        }
        val localCleartextHosts = setOf("10.0.2.2", "localhost", "127.0.0.1")
        if (backendUri.scheme == "http" && backendUri.host !in localCleartextHosts) {
            throw GradleException("BACKEND_BASE_URL must use HTTPS for non-local hosts: $backendUrl")
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
        buildConfig = true
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
    implementation("com.stripe:stripeterminal-localmobile:3.10.1")
    implementation("com.google.zxing:core:3.5.3")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    testImplementation("org.mockito:mockito-inline:5.2.0")
    testImplementation("org.mockito.kotlin:mockito-kotlin:5.4.0")
}
