package com.example.dashcamencoder

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONObject
import java.io.File

class UploadWorker(
    context: Context,
    workerParams: WorkerParameters
) : Worker(context, workerParams) {

    override fun doWork(): Result {
        val pendingDirectory = File(applicationContext.filesDir, "pending")

        if (!pendingDirectory.exists()) {
            return Result.success()
        }

        val imageFiles = pendingDirectory.listFiles()?.filter {
            it.extension.lowercase() == "jpg"
        } ?: emptyList()

        if (imageFiles.isEmpty()) {
            return Result.success()
        }

        var allSuccessful = true

        for (imageFile in imageFiles) {
            val jsonFile = File(pendingDirectory, "${imageFile.nameWithoutExtension}.json")

            if (!jsonFile.exists()) {
                continue
            }

            try {
                val jsonContent = jsonFile.readText()
                val jsonObject = JSONObject(jsonContent)

                val frame = FrameData(
                    evidenceId = jsonObject.optString("evidenceId", ""),
                    frameIndex = jsonObject.optInt("frameIndex", 0),
                    timestamp = jsonObject.optString("timestamp", ""),
                    hashAlgorithm = jsonObject.optString("hashAlgorithm", ""),
                    hash = jsonObject.optString("hash", ""),
                    filePath = imageFile.absolutePath
                )

                val success = ApiClient.uploadFrame(frame)

                if (success) {
                    imageFile.delete()
                    jsonFile.delete()
                } else {
                    allSuccessful = false
                }
            } catch (e: Exception) {
                e.printStackTrace()
                allSuccessful = false
            }
        }

        return if (allSuccessful) {
            Result.success()
        } else {
            Result.retry()
        }
    }
}
