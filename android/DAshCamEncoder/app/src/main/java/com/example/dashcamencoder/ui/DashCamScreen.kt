package com.example.dashcamencoder.ui

import android.content.res.Configuration
import androidx.camera.view.PreviewView
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateDp
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.updateTransition
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.example.dashcamencoder.ApiClient
import com.example.dashcamencoder.ui.theme.Accent
import com.example.dashcamencoder.ui.theme.Alert
import com.example.dashcamencoder.ui.theme.Amber
import com.example.dashcamencoder.ui.theme.Ink
import com.example.dashcamencoder.ui.theme.Panel
import com.example.dashcamencoder.ui.theme.PanelBorder
import com.example.dashcamencoder.ui.theme.TextMuted
import com.example.dashcamencoder.ui.theme.TextPrimary
import kotlinx.coroutines.delay

@Composable
fun DashCamScreen(
    recording: Boolean,
    frameCount: Int,
    uploadedCount: Int,
    pendingCount: Int,
    lastHash: String,
    lastTimestamp: String,
    serverOnline: Boolean,
    serverUrl: String,
    evidenceId: String,
    onPreviewReady: (PreviewView) -> Unit,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onSaveServerUrl: (String) -> Unit
) {
    var showSettings by remember { mutableStateOf(false) }
    val landscape = LocalConfiguration.current.orientation == Configuration.ORIENTATION_LANDSCAPE

    // Keep the display awake while recording (it's a dash cam)
    val hostView = LocalView.current
    DisposableEffect(recording) {
        hostView.keepScreenOn = recording
        onDispose { hostView.keepScreenOn = false }
    }

    // Elapsed recording time
    var elapsed by remember { mutableLongStateOf(0L) }
    LaunchedEffect(recording) {
        if (recording) {
            val start = System.currentTimeMillis()
            while (true) {
                elapsed = (System.currentTimeMillis() - start) / 1000
                delay(500)
            }
        } else {
            elapsed = 0L
        }
    }

    Box(Modifier.fillMaxSize().background(Ink)) {

        // ---- Camera fills the whole screen -------------------------
        AndroidView(
            factory = { context ->
                PreviewView(context).also { view ->
                    view.scaleType = PreviewView.ScaleType.FILL_CENTER
                    onPreviewReady(view)
                }
            },
            modifier = Modifier.fillMaxSize()
        )

        // ---- Scrims keep overlay text readable on any scene --------
        Box(
            Modifier.fillMaxWidth().height(140.dp).align(Alignment.TopCenter)
                .background(Brush.verticalGradient(listOf(Color(0xCC000000), Color.Transparent)))
        )
        if (landscape) {
            Box(
                Modifier.fillMaxHeight().width(420.dp).align(Alignment.CenterEnd)
                    .background(Brush.horizontalGradient(listOf(Color.Transparent, Color(0xEE000000))))
            )
        } else {
            Box(
                Modifier.fillMaxWidth().height(460.dp).align(Alignment.BottomCenter)
                    .background(Brush.verticalGradient(listOf(Color.Transparent, Color(0xEE000000))))
            )
        }

        // ---- Viewfinder + recording frame --------------------------
        ViewfinderBrackets(landscape, recording)
        AnimatedVisibility(visible = recording, enter = fadeIn(), exit = fadeOut()) {
            RecordingFrame()
        }

        // ---- Top bar ------------------------------------------------
        Row(
            modifier = Modifier
                .systemBarsPadding()
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
                .align(Alignment.TopCenter),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            RecBadge(recording, elapsed)

            Row(verticalAlignment = Alignment.CenterVertically) {
                NetworkPill(serverOnline)
                Spacer(Modifier.width(8.dp))
                SettingsButton(enabled = !recording) { showSettings = true }
            }
        }

        // ---- Controls -----------------------------------------------
        if (landscape) {
            Column(
                modifier = Modifier
                    .align(Alignment.CenterEnd)
                    .systemBarsPadding()
                    .width(340.dp)
                    .padding(top = 48.dp, start = 16.dp, end = 16.dp, bottom = 8.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    RecordButton(recording, onStart, onStop)
                    Spacer(Modifier.width(14.dp))
                    Column {
                        Text(
                            if (recording) "Recording" else "Ready",
                            color = TextPrimary,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                        Text(
                            if (recording) "Tap to stop and sync" else "Tap to start",
                            color = TextMuted,
                            fontSize = 12.sp
                        )
                        if (evidenceId.isNotEmpty()) {
                            Text(
                                evidenceId,
                                color = TextMuted,
                                fontSize = 11.sp,
                                fontFamily = FontFamily.Monospace
                            )
                        }
                    }
                }
                Stats(frameCount, uploadedCount, pendingCount)
                SyncStatus(frameCount, uploadedCount, pendingCount, serverOnline)
                HashChip(lastHash, lastTimestamp)
            }
        } else {
            Column(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .systemBarsPadding()
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                if (evidenceId.isNotEmpty()) {
                    Text(
                        evidenceId,
                        color = TextMuted,
                        fontSize = 12.sp,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.padding(start = 4.dp)
                    )
                }

                Stats(frameCount, uploadedCount, pendingCount)
                SyncStatus(frameCount, uploadedCount, pendingCount, serverOnline)
                HashChip(lastHash, lastTimestamp)

                Spacer(Modifier.height(4.dp))

                Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    RecordButton(recording, onStart, onStop)
                }

                Text(
                    if (recording) "Tap to stop and sync" else "Tap to start recording",
                    color = TextMuted,
                    fontSize = 12.sp,
                    modifier = Modifier.fillMaxWidth(),
                    textAlign = TextAlign.Center
                )
            }
        }
    }

    if (showSettings) {
        ServerDialog(
            current = serverUrl,
            onDismiss = { showSettings = false },
            onSave = {
                onSaveServerUrl(it)
                showSettings = false
            }
        )
    }
}

// ================================================================
// OVERLAYS
// ================================================================

@Composable
private fun ViewfinderBrackets(landscape: Boolean, recording: Boolean) {
    val color by animateColorAsState(
        if (recording) Alert.copy(alpha = 0.9f) else Color.White.copy(alpha = 0.4f),
        label = "bracket"
    )
    Canvas(Modifier.fillMaxSize()) {
        val w = size.width
        val h = size.height
        val left = if (landscape) w * 0.06f else w * 0.08f
        val right = if (landscape) w * 0.58f else w * 0.92f
        val top = if (landscape) h * 0.22f else h * 0.17f
        val bottom = if (landscape) h * 0.78f else h * 0.48f
        val len = 26.dp.toPx()
        val sw = 3.dp.toPx()

        fun corner(x: Float, y: Float, dx: Float, dy: Float) {
            drawLine(color, Offset(x, y), Offset(x + dx * len, y), sw, StrokeCap.Round)
            drawLine(color, Offset(x, y), Offset(x, y + dy * len), sw, StrokeCap.Round)
        }
        corner(left, top, 1f, 1f)
        corner(right, top, -1f, 1f)
        corner(left, bottom, 1f, -1f)
        corner(right, bottom, -1f, -1f)
    }
}

@Composable
private fun RecordingFrame() {
    val transition = rememberInfiniteTransition(label = "frame")
    val a by transition.animateFloat(
        initialValue = 0.15f,
        targetValue = 0.6f,
        animationSpec = infiniteRepeatable(tween(900), RepeatMode.Reverse),
        label = "frameAlpha"
    )
    Box(Modifier.fillMaxSize().border(BorderStroke(3.dp, Alert.copy(alpha = a))))
}

// ================================================================
// TOP BAR
// ================================================================

@Composable
private fun RecBadge(recording: Boolean, elapsedSeconds: Long) {
    val pulse = rememberInfiniteTransition(label = "pulse")
    val alpha by pulse.animateFloat(
        initialValue = 1f,
        targetValue = 0.25f,
        animationSpec = infiniteRepeatable(tween(700), RepeatMode.Reverse),
        label = "alpha"
    )

    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(Panel)
            .border(BorderStroke(1.dp, PanelBorder), RoundedCornerShape(50))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier
                .size(10.dp)
                .alpha(if (recording) alpha else 1f)
                .clip(CircleShape)
                .background(if (recording) Alert else TextMuted)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            if (recording) "REC  ${formatTime(elapsedSeconds)}" else "READY",
            color = TextPrimary,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            fontFamily = FontFamily.Monospace
        )
    }
}

@Composable
private fun NetworkPill(online: Boolean) {
    val color by animateColorAsState(if (online) Accent else Amber, label = "net")
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(Panel)
            .border(BorderStroke(1.dp, PanelBorder), RoundedCornerShape(50))
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Spacer(Modifier.width(6.dp))
        Text(
            if (online) "SERVER" else "OFFLINE",
            color = TextPrimary,
            fontSize = 12.sp,
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
private fun SettingsButton(enabled: Boolean, onClick: () -> Unit) {
    val tint = if (enabled) TextPrimary else TextMuted.copy(alpha = 0.4f)
    Box(
        Modifier
            .size(38.dp)
            .clip(CircleShape)
            .background(Panel)
            .border(BorderStroke(1.dp, PanelBorder), CircleShape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        // Simple "sliders" icon drawn on a canvas (no icon library needed)
        Canvas(Modifier.size(18.dp)) {
            val ys = listOf(0.2f, 0.5f, 0.8f)
            val knobs = listOf(0.68f, 0.3f, 0.6f)
            ys.forEachIndexed { i, y ->
                val py = size.height * y
                drawLine(tint, Offset(0f, py), Offset(size.width, py), 2.dp.toPx(), StrokeCap.Round)
                drawCircle(tint, radius = 3.2.dp.toPx(), center = Offset(size.width * knobs[i], py))
            }
        }
    }
}

// ================================================================
// STATS + SYNC
// ================================================================

@Composable
private fun Stats(frameCount: Int, uploadedCount: Int, pendingCount: Int) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        StatCard("FRAMES", frameCount.toString(), TextPrimary, Modifier.weight(1f))
        StatCard("UPLOADED", uploadedCount.toString(), Accent, Modifier.weight(1f))
        StatCard(
            "PENDING",
            pendingCount.toString(),
            if (pendingCount > 0) Amber else TextMuted,
            Modifier.weight(1f)
        )
    }
}

@Composable
private fun StatCard(label: String, value: String, valueColor: Color, modifier: Modifier) {
    val animated by animateColorAsState(valueColor, label = "statColor")
    Column(
        modifier = modifier
            .clip(RoundedCornerShape(14.dp))
            .background(Panel)
            .border(BorderStroke(1.dp, PanelBorder), RoundedCornerShape(14.dp))
            .padding(horizontal = 14.dp, vertical = 12.dp)
    ) {
        Text(label, color = TextMuted, fontSize = 10.sp, letterSpacing = 1.2.sp)
        Spacer(Modifier.height(2.dp))
        Text(value, color = animated, fontSize = 26.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun SyncStatus(
    frameCount: Int,
    uploadedCount: Int,
    pendingCount: Int,
    serverOnline: Boolean
) {
    if (frameCount == 0 && pendingCount == 0) return

    val target = if (frameCount > 0) (uploadedCount.toFloat() / frameCount).coerceIn(0f, 1f) else 1f
    val progress by animateFloatAsState(target, animationSpec = tween(400), label = "sync")

    val (label, color) = when {
        pendingCount > 0 && !serverOnline -> "Offline · $pendingCount queued on device" to Amber
        pendingCount > 0 -> "Uploading · $pendingCount left" to Accent
        else -> "All frames synced" to Accent
    }

    Column(Modifier.fillMaxWidth().padding(horizontal = 2.dp)) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(label, color = color, fontSize = 12.sp, fontWeight = FontWeight.Medium)
            if (frameCount > 0) {
                Text(
                    "${(progress * 100).toInt()}%",
                    color = TextMuted,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace
                )
            }
        }
        Spacer(Modifier.height(6.dp))
        LinearProgressIndicator(
            progress = { progress },
            modifier = Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(2.dp)),
            color = color,
            trackColor = Color(0x33FFFFFF)
        )
    }
}

// ================================================================
// HASH CHIP
// ================================================================

@Composable
private fun HashChip(hash: String, timestamp: String) {
    val clipboard = LocalClipboardManager.current
    val haptics = LocalHapticFeedback.current
    var copied by remember { mutableStateOf(false) }

    LaunchedEffect(copied) {
        if (copied) {
            delay(1500)
            copied = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(14.dp))
            .background(Panel)
            .border(BorderStroke(1.dp, PanelBorder), RoundedCornerShape(14.dp))
            .clickable(enabled = hash.isNotEmpty(), role = Role.Button) {
                clipboard.setText(AnnotatedString(hash))
                haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                copied = true
            }
            .padding(horizontal = 14.dp, vertical = 10.dp)
    ) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text("LAST SHA-256 FINGERPRINT", color = TextMuted, fontSize = 10.sp, letterSpacing = 1.2.sp)
            if (hash.isNotEmpty()) {
                Text(
                    if (copied) "COPIED ✓" else "tap to copy",
                    color = if (copied) Accent else TextMuted,
                    fontSize = 10.sp,
                    fontWeight = if (copied) FontWeight.Bold else FontWeight.Normal
                )
            }
        }
        Spacer(Modifier.height(4.dp))
        Text(
            if (hash.isEmpty()) "Waiting for first frame…"
            else "${hash.take(16)}…${hash.takeLast(8)}",
            color = if (hash.isEmpty()) TextMuted else Accent,
            fontSize = 13.sp,
            fontFamily = FontFamily.Monospace,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
        if (timestamp.isNotEmpty()) {
            Text(timestamp, color = TextMuted, fontSize = 11.sp, fontFamily = FontFamily.Monospace)
        }
    }
}

// ================================================================
// RECORD BUTTON
// ================================================================

@Composable
private fun RecordButton(recording: Boolean, onStart: () -> Unit, onStop: () -> Unit) {
    val haptics = LocalHapticFeedback.current
    val transition = updateTransition(recording, label = "record")
    val innerSize by transition.animateDp(label = "size") { if (it) 28.dp else 60.dp }
    val corner by transition.animateDp(label = "corner") { if (it) 8.dp else 30.dp }

    val spin = rememberInfiniteTransition(label = "spin")
    val angle by spin.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(2400, easing = LinearEasing)),
        label = "angle"
    )

    Box(
        modifier = Modifier
            .size(88.dp)
            .clip(CircleShape)
            .clickable(role = Role.Button) {
                haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                if (recording) onStop() else onStart()
            },
        contentAlignment = Alignment.Center
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = 4.dp.toPx()
            drawCircle(
                color = Color.White,
                radius = size.minDimension / 2 - stroke / 2,
                style = Stroke(stroke)
            )
            if (recording) {
                drawArc(
                    color = Alert,
                    startAngle = angle,
                    sweepAngle = 80f,
                    useCenter = false,
                    topLeft = Offset(stroke / 2, stroke / 2),
                    size = Size(size.width - stroke, size.height - stroke),
                    style = Stroke(stroke, cap = StrokeCap.Round)
                )
            }
        }
        Box(
            Modifier
                .size(innerSize)
                .clip(RoundedCornerShape(corner))
                .background(Alert)
        )
    }
}

// ================================================================
// SETTINGS DIALOG
// ================================================================

@Composable
private fun ServerDialog(
    current: String,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit
) {
    var text by remember { mutableStateOf(current) }
    val trimmed = text.trim()
    val valid = trimmed.startsWith("http://") || trimmed.startsWith("https://")

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Backend server") },
        text = {
            Column {
                Text(
                    "Address of the FastAPI backend that receives the evidence frames.",
                    color = TextMuted,
                    fontSize = 13.sp
                )
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = text,
                    onValueChange = { text = it },
                    singleLine = true,
                    isError = !valid,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
                    supportingText = { if (!valid) Text("Must start with http:// or https://") },
                    label = { Text("Server URL") }
                )
                TextButton(onClick = { text = ApiClient.DEFAULT_URL }) {
                    Text("Reset to default")
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onSave(trimmed) }, enabled = valid) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

private fun formatTime(totalSeconds: Long): String {
    val h = totalSeconds / 3600
    val m = (totalSeconds % 3600) / 60
    val s = totalSeconds % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%02d:%02d".format(m, s)
}