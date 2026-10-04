package com.example.dashcamencoder

data class FrameData(

    val evidenceId: String,

    val frameIndex: Int,

    val timestamp: String,

    val hashAlgorithm: String,

    val hash: String,

    val filePath: String

)