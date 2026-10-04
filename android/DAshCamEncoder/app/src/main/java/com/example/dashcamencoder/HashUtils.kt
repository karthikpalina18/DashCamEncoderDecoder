package com.example.dashcamencoder

import java.io.File
import java.security.MessageDigest

object HashUtils {

    fun sha256(file: File): String {

        val digest =
            MessageDigest.getInstance("SHA-256")

        file.inputStream().use { input ->

            val buffer = ByteArray(8192)

            while (true) {

                val bytesRead =
                    input.read(buffer)

                if (bytesRead == -1) {
                    break
                }

                digest.update(
                    buffer,
                    0,
                    bytesRead
                )
            }
        }

        return digest
            .digest()
            .joinToString("") { byte ->

                "%02x".format(byte)
            }
    }
}