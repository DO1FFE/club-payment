buildscript {
    dependencies {
        classpath("com.android.tools.build:gradle:8.5.1")
        classpath(kotlin("gradle-plugin", version = "1.9.24"))
    }
}

allprojects {
    repositories {
        google()
        mavenCentral()
    }
}
