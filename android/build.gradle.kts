buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.5.1")
        classpath(kotlin("gradle-plugin", version = "1.9.25"))
    }
}

val externalBuildRoot = providers.gradleProperty("CLUB_PAYMENT_BUILD_DIR")
if (externalBuildRoot.isPresent) {
    allprojects {
        val projectBuildName = path.trimStart(':').replace(':', '_').ifBlank { "root" }
        layout.buildDirectory.set(file("${externalBuildRoot.get()}/$projectBuildName"))
    }
}
