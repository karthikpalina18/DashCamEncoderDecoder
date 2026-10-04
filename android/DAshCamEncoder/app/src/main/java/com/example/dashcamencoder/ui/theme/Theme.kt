package com.example.dashcamencoder.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

// A dashcam is used in cars and at night: always dark, no dynamic color.
private val DashColors = darkColorScheme(
    primary = Accent,
    onPrimary = Ink,
    secondary = Amber,
    tertiary = Alert,
    background = Ink,
    surface = Ink,
    onBackground = TextPrimary,
    onSurface = TextPrimary
)

@Composable
fun DashCamEncoderTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DashColors,
        typography = Typography,
        content = content
    )
}
