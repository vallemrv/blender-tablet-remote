plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.blendertablet.remote"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.blendertablet.remote"
        minSdk = 26
        targetSdk = 36
        versionCode = 4
        versionName = "0.1.3"
    }

    buildFeatures { compose = true }
    sourceSets.getByName("test").resources.srcDir("${rootDir}/blender-backend/tests/fixtures")

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions { jvmTarget = "17" }

    packaging.resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.06.00")
    implementation(composeBom)

    implementation("androidx.activity:activity-compose:1.12.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.10.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    // 5.2 reimplementó el transporte WebSocket. En el dispositivo de prueba 5.3.0
    // envía una clave correcta pero valida la respuesta contra otra distinta.
    // 4.12 usa la implementación WebSocket madura anterior.
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20231013")
    debugImplementation("androidx.compose.ui:ui-tooling")
}
