package com.example.dashcamencoder

import android.content.Context
import okhttp3.ConnectionPool
import okhttp3.Dispatcher
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.util.concurrent.TimeUnit

object ApiClient {

    // ============================================================
    // SETTINGS
    // ============================================================

    private const val PREFS = "dashcam_settings"
    private const val KEY_URL = "server_url"

    // Current laptop IP + FastAPI port
    const val DEFAULT_URL = "http://10.178.204.88:8000"

    /**
     * Current backend URL.
     * Can be changed from the application's settings.
     */
    @Volatile
    var baseUrl: String = DEFAULT_URL
        private set


    // ============================================================
    // LOAD SAVED SERVER URL
    // ============================================================

    fun load(context: Context) {

        baseUrl = context
            .getSharedPreferences(
                PREFS,
                Context.MODE_PRIVATE
            )
            .getString(
                KEY_URL,
                DEFAULT_URL
            )
            ?.trim()
            ?.trimEnd('/')
            ?: DEFAULT_URL

        println(
            "SERVER URL | $baseUrl"
        )
    }


    // ============================================================
    // SAVE SERVER URL
    // ============================================================

    fun saveUrl(
        context: Context,
        url: String
    ) {

        val cleanUrl =
            url
                .trim()
                .trimEnd('/')

        baseUrl = cleanUrl

        context
            .getSharedPreferences(
                PREFS,
                Context.MODE_PRIVATE
            )
            .edit()
            .putString(
                KEY_URL,
                cleanUrl
            )
            .apply()

        println(
            "SERVER URL SAVED | $baseUrl"
        )
    }


    // ============================================================
    // MAIN HTTP CLIENT
    // ============================================================

    private val client =
        OkHttpClient.Builder()

            // Connection establishment
            .connectTimeout(
                10,
                TimeUnit.SECONDS
            )

            // Server response
            .readTimeout(
                60,
                TimeUnit.SECONDS
            )

            // JPEG upload
            .writeTimeout(
                60,
                TimeUnit.SECONDS
            )

            // WorkManager handles retries
            .retryOnConnectionFailure(
                false
            )

            // Reuse TCP connections
            .connectionPool(
                ConnectionPool(
                    5,
                    5,
                    TimeUnit.MINUTES
                )
            )

            // Limit simultaneous uploads
            .dispatcher(
                Dispatcher().apply {

                    maxRequests = 6

                    maxRequestsPerHost = 3
                }
            )

            .build()


    // ============================================================
    // HEALTH CHECK CLIENT
    // ============================================================

    private val pingClient =
        client
            .newBuilder()

            .connectTimeout(
                3,
                TimeUnit.SECONDS
            )

            .readTimeout(
                3,
                TimeUnit.SECONDS
            )

            .build()


    // ============================================================
    // SERVER HEALTH CHECK
    // ============================================================

    fun isServerReachable(): Boolean {

        return try {

            val request =
                Request.Builder()
                    .url(
                        "$baseUrl/api/v1/health"
                    )
                    .get()
                    .build()

            pingClient
                .newCall(request)
                .execute()
                .use { response ->

                    println(
                        "HEALTH CHECK | " +
                                "HTTP=${response.code}"
                    )

                    response.isSuccessful
                }

        } catch (e: Exception) {

            println(
                "HEALTH CHECK ERROR | " +
                        "${e.javaClass.simpleName}: " +
                        "${e.message}"
            )

            false
        }
    }


    // ============================================================
    // UPLOAD FRAME
    // ============================================================

    fun uploadFrame(
        frame: FrameData
    ): Boolean {

        // --------------------------------------------------------
        // CHECK FILE
        // --------------------------------------------------------

        val file =
            File(frame.filePath)

        if (!file.exists()) {

            println(
                "UPLOAD ERROR | File not found | " +
                        "${file.absolutePath}"
            )

            return false
        }

        if (!file.isFile) {

            println(
                "UPLOAD ERROR | Not a file | " +
                        "${file.absolutePath}"
            )

            return false
        }

        if (file.length() <= 0) {

            println(
                "UPLOAD ERROR | Empty file | " +
                        "${file.absolutePath}"
            )

            return false
        }


        // --------------------------------------------------------
        // LOG UPLOAD
        // --------------------------------------------------------

        println(
            "UPLOAD START | " +
                    "evidence=${frame.evidenceId} | " +
                    "frame=${frame.frameIndex} | " +
                    "size=${file.length()} bytes"
        )


        // --------------------------------------------------------
        // MULTIPART FORM
        // --------------------------------------------------------

        val multipart =
            MultipartBody.Builder()

                .setType(
                    MultipartBody.FORM
                )

                // Evidence ID
                .addFormDataPart(
                    "evidence_id",
                    frame.evidenceId
                )

                // Frame index
                .addFormDataPart(
                    "frame_index",
                    frame.frameIndex.toString()
                )

                // Capture timestamp
                .addFormDataPart(
                    "timestamp",
                    frame.timestamp
                )

                // Hash algorithm
                .addFormDataPart(
                    "hash_algorithm",
                    frame.hashAlgorithm
                )

                // SHA-256 hash
                .addFormDataPart(
                    "hash",
                    frame.hash
                )

                // JPEG frame
                .addFormDataPart(
                    "frame",
                    file.name,
                    file.asRequestBody(
                        "image/jpeg".toMediaType()
                    )
                )

                .build()


        // --------------------------------------------------------
        // HTTP REQUEST
        // --------------------------------------------------------

        val request =
            Request.Builder()
                .url(
                    "$baseUrl/api/v1/frames"
                )
                .post(
                    multipart
                )
                .build()


        // --------------------------------------------------------
        // SEND REQUEST
        // --------------------------------------------------------

        return try {

            client
                .newCall(request)
                .execute()
                .use { response ->

                    val responseBody =
                        response.body
                            ?.string()
                            ?: ""

                    if (response.isSuccessful) {

                        println(
                            "SERVER SUCCESS | " +
                                    "evidence=${frame.evidenceId} | " +
                                    "frame=${frame.frameIndex} | " +
                                    "HTTP=${response.code} | " +
                                    "body=$responseBody"
                        )

                        true

                    } else {

                        println(
                            "SERVER ERROR | " +
                                    "evidence=${frame.evidenceId} | " +
                                    "frame=${frame.frameIndex} | " +
                                    "HTTP=${response.code} | " +
                                    "body=$responseBody"
                        )

                        false
                    }
                }

        } catch (e: Exception) {

            println(
                "NETWORK ERROR | " +
                        "evidence=${frame.evidenceId} | " +
                        "frame=${frame.frameIndex} | " +
                        "${e.javaClass.simpleName}: " +
                        "${e.message}"
            )

            e.printStackTrace()

            false
        }
    }
}