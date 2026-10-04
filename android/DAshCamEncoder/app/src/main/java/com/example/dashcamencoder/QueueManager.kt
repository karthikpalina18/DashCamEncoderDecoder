package com.example.dashcamencoder

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import org.json.JSONObject
import java.io.File

object QueueManager {

    fun saveFrame(
        context: Context,
        frame: FrameData
    ) {

        val pendingDirectory =
            File(
                context.filesDir,
                "pending"
            )

        if (!pendingDirectory.exists()) {

            pendingDirectory.mkdirs()
        }

        val source =
            File(frame.filePath)

        val destination =
            File(
                pendingDirectory,
                source.name
            )

        source.copyTo(
            destination,
            overwrite = true
        )

        val metadata =
            JSONObject()

        metadata.put(
            "evidenceId",
            frame.evidenceId
        )

        metadata.put(
            "frameIndex",
            frame.frameIndex
        )

        metadata.put(
            "timestamp",
            frame.timestamp
        )

        metadata.put(
            "hashAlgorithm",
            frame.hashAlgorithm
        )

        metadata.put(
            "hash",
            frame.hash
        )

        File(
            pendingDirectory,
            "${source.nameWithoutExtension}.json"
        ).writeText(
            metadata.toString()
        )

        scheduleUpload(context)
    }


    fun scheduleUpload(
        context: Context
    ) {

        val constraints =
            Constraints.Builder()
                .setRequiredNetworkType(
                    NetworkType.CONNECTED
                )
                .build()

        val request =
            OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(constraints)
                .build()

        WorkManager
            .getInstance(context)
            .enqueueUniqueWork(

                "dashcam-upload",

                ExistingWorkPolicy.APPEND_OR_REPLACE,

                request
            )
    }


    fun pendingCount(
        context: Context
    ): Int {

        val directory =
            File(
                context.filesDir,
                "pending"
            )

        return directory
            .listFiles()
            ?.count {
                it.extension.lowercase() == "jpg"
            }
            ?: 0
    }

    /** Pending frames that belong to one recording session. */
    fun pendingCount(
        context: Context,
        evidenceId: String
    ): Int {

        val directory = File(context.filesDir, "pending")

        return directory
            .listFiles()
            ?.count {
                it.extension.lowercase() == "jpg" &&
                    it.name.startsWith(evidenceId)
            }
            ?: 0
    }
}
