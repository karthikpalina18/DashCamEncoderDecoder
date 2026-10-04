package com.example.dashcamencoder

import android.Manifest
import android.content.ContentValues
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.MediaStore
import android.view.Surface
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.MediaStoreOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import androidx.activity.enableEdgeToEdge
import com.example.dashcamencoder.ui.DashCamScreen
import com.example.dashcamencoder.ui.theme.DashCamEncoderTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {

    private lateinit var cameraExecutor: ExecutorService

    private var previewView: PreviewView? = null

    private var imageCapture: ImageCapture? = null

    private var videoCapture: VideoCapture<Recorder>? = null

    private var activeRecording: Recording? = null

    private var recording by mutableStateOf(false)

    private var frameCount by mutableIntStateOf(0)

    private var uploadedCount by mutableIntStateOf(0)

    private var pendingCount by mutableIntStateOf(0)

    private var lastHash by mutableStateOf("")

    private var lastTimestamp by mutableStateOf("")

    private var serverOnline by mutableStateOf(false)

    private var serverUrl by mutableStateOf(ApiClient.DEFAULT_URL)

    private var evidenceLabel by mutableStateOf("")

    private var evidenceId =
        "DASH-${UUID.randomUUID().toString().take(8)}"


    private val cameraPermissionLauncher =
        registerForActivityResult(
            ActivityResultContracts.RequestPermission()
        ) { granted ->

            if (granted) {

                previewView?.let {
                    startCamera(it)
                }
            }
        }


    override fun onCreate(
        savedInstanceState: Bundle?
    ) {

        super.onCreate(savedInstanceState)

        enableEdgeToEdge()

        ApiClient.load(this)
        serverUrl = ApiClient.baseUrl

        cameraExecutor =
            Executors.newSingleThreadExecutor()

        setContent {

            DashCamEncoderTheme {

                DashCamScreen(
                    recording = recording,
                    frameCount = frameCount,
                    uploadedCount = uploadedCount,
                    pendingCount = pendingCount,
                    lastHash = lastHash,
                    lastTimestamp = lastTimestamp,
                    serverOnline = serverOnline,
                    serverUrl = serverUrl,
                    evidenceId = evidenceLabel,

                    onPreviewReady = { view ->
                        previewView = view
                        checkPermission(view)
                    },

                    onStart = { startRecording() },

                    onStop = { stopRecording() },

                    onSaveServerUrl = { url ->
                        ApiClient.saveUrl(this@MainActivity, url)
                        serverUrl = ApiClient.baseUrl
                        serverOnline = false
                    }
                )
            }

            // Queue + upload progress (kept in sync every second)
            LaunchedEffect(Unit) {
                while (true) {
                    pendingCount = QueueManager.pendingCount(this@MainActivity)
                    val sessionPending = QueueManager.pendingCount(
                        this@MainActivity, evidenceId
                    )
                    uploadedCount = (frameCount - sessionPending).coerceAtLeast(0)
                    delay(1000)
                }
            }

            // Real connectivity check against the backend
            LaunchedEffect(serverUrl) {
                while (true) {
                    serverOnline = withContext(Dispatchers.IO) {
                        ApiClient.isServerReachable()
                    }
                    if (serverOnline && QueueManager.pendingCount(this@MainActivity) > 0) {
                        QueueManager.scheduleUpload(this@MainActivity)
                    }
                    delay(5000)
                }
            }
        }
    }


    private fun checkPermission(
        view: PreviewView
    ) {

        if (
            ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.CAMERA
            ) == PackageManager.PERMISSION_GRANTED
        ) {

            startCamera(view)

        } else {

            cameraPermissionLauncher.launch(
                Manifest.permission.CAMERA
            )
        }
    }


    private fun startCamera(
        view: PreviewView
    ) {

        val providerFuture =
            ProcessCameraProvider
                .getInstance(this)

        providerFuture.addListener({

            try {

                val provider =
                    providerFuture.get()

                val preview =
                    Preview.Builder()
                        .setTargetRotation(
                            view.display?.rotation
                                ?: Surface.ROTATION_0
                        )
                        .build()

                preview.surfaceProvider =
                    view.surfaceProvider


                // -----------------------------------------
                // Image capture
                // -----------------------------------------

                imageCapture =
                    ImageCapture.Builder()
                        .setCaptureMode(
                            ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY
                        )
                        .setTargetRotation(
                            view.display?.rotation
                                ?: Surface.ROTATION_0
                        )
                        .build()


                // -----------------------------------------
                // Video capture
                // -----------------------------------------

                val recorder =
                    Recorder.Builder()
                        .setQualitySelector(
                            QualitySelector.from(
                                Quality.HD
                            )
                        )
                        .build()

                videoCapture =
                    VideoCapture.withOutput(
                        recorder
                    )


                val selector =
                    CameraSelector.DEFAULT_BACK_CAMERA


                provider.unbindAll()


                provider.bindToLifecycle(

                    this,

                    selector,

                    preview,

                    imageCapture,

                    videoCapture
                )

            } catch (exception: Exception) {

                exception.printStackTrace()
            }

        }, ContextCompat.getMainExecutor(this))
    }


    // =========================================================
    // START RECORDING
    // =========================================================

    private fun startRecording() {

        val videoCapture =
            videoCapture ?: return

        val timestamp =
            SimpleDateFormat(
                "yyyyMMdd_HHmmss",
                Locale.US
            ).format(Date())

        evidenceId =
            "DASH-$timestamp"

        evidenceLabel = evidenceId


        frameCount = 0

        uploadedCount = 0

        pendingCount =
            QueueManager.pendingCount(this)

        lastHash = ""

        lastTimestamp = ""

        recording = true


        // -----------------------------------------------------
        // Create video output
        // -----------------------------------------------------

        val contentValues =
            ContentValues().apply {

                put(
                    MediaStore.Video.Media.DISPLAY_NAME,
                    "$evidenceId.mp4"
                )

                put(
                    MediaStore.Video.Media.MIME_TYPE,
                    "video/mp4"
                )

                put(
                    MediaStore.Video.Media.RELATIVE_PATH,
                    "Movies/DashCam"
                )
            }


        val outputOptions =
            MediaStoreOutputOptions
                .Builder(
                    contentResolver,
                    MediaStore.Video.Media.EXTERNAL_CONTENT_URI
                )
                .setContentValues(
                    contentValues
                )
                .build()


        val pendingRecording =
            videoCapture.output
                .prepareRecording(
                    this,
                    outputOptions
                )


        activeRecording =
            pendingRecording.start(

                ContextCompat.getMainExecutor(this)

            ) { event ->

                when (event) {

                    is VideoRecordEvent.Start -> {

                        recording = true
                    }

                    is VideoRecordEvent.Finalize -> {

                        recording = false

                        if (
                            event.error !=
                            VideoRecordEvent.Finalize.ERROR_NONE
                        ) {

                            event.cause
                                ?.printStackTrace()
                        }
                    }
                }
            }


        // Start periodic frame acquisition

        startFrameCapture()
    }


    // =========================================================
    // CAPTURE FINGERPRINT FRAMES
    // =========================================================

    private fun startFrameCapture() {

        Thread {

            while (recording) {

                captureFingerprintFrame()

                Thread.sleep(1000)
            }

        }.start()
    }


    // =========================================================
    // CAPTURE JPEG
    // =========================================================

    private fun captureFingerprintFrame() {

        val capture =
            imageCapture ?: return

        val directory =
            File(
                filesDir,
                "frames"
            )

        if (!directory.exists()) {
            directory.mkdirs()
        }


        val file =
            File(
                directory,
                "${evidenceId}_${frameCount + 1}.jpg"
            )


        val options =
            ImageCapture.OutputFileOptions
                .Builder(file)
                .build()


        capture.takePicture(

            options,

            cameraExecutor,

            object :
                ImageCapture.OnImageSavedCallback {

                override fun onImageSaved(
                    outputFileResults:
                    ImageCapture.OutputFileResults
                ) {

                    processCapturedFrame(file)
                }


                override fun onError(
                    exception: ImageCaptureException
                ) {

                    exception.printStackTrace()
                }
            }
        )
    }


    // =========================================================
    // PROCESS FRAME
    // =========================================================

    private fun processCapturedFrame(
        file: File
    ) {

        try {

            val hash =
                HashUtils.sha256(file)

            val timestamp =
                SimpleDateFormat(
                    "yyyy-MM-dd HH:mm:ss.SSS",
                    Locale.US
                ).format(Date())


            val frame =
                FrameData(

                    evidenceId =
                        evidenceId,

                    frameIndex =
                        frameCount + 1,

                    timestamp =
                        timestamp,

                    hashAlgorithm =
                        "SHA-256",

                    hash =
                        hash,

                    filePath =
                        file.absolutePath
                )


            runOnUiThread {

                frameCount++

                lastHash =
                    hash

                lastTimestamp =
                    timestamp
            }


            // -------------------------------------------------
            // Save locally first.
            // This guarantees that the frame exists even
            // when the network is unavailable.
            // -------------------------------------------------

            QueueManager.saveFrame(
                this,
                frame
            )


            pendingCount =
                QueueManager.pendingCount(this)


        } catch (exception: Exception) {

            exception.printStackTrace()
        }
    }


    // =========================================================
    // STOP RECORDING
    // =========================================================

    private fun stopRecording() {

        activeRecording?.stop()

        activeRecording = null

        recording = false

        QueueManager.scheduleUpload(this)
    }


    // =========================================================
    // CLEANUP
    // =========================================================

    override fun onDestroy() {

        activeRecording?.close()

        cameraExecutor.shutdown()


        super.onDestroy()
    }
}
