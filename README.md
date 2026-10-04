
# 🚗 Edge-to-Cloud DashCam Video Integrity Verification

**Academic Cloud Computing Project — Palina Karthik**

A distributed **Edge-to-Cloud video evidence verification platform** designed to capture dashcam evidence on a mobile device, generate cryptographic fingerprints, store evidence metadata in the Cloud, and validate submitted video using frame-level integrity verification and video sequence matching.

---

## 📌 Project Overview

This project connects three major components:

```text
📱 Android DashCam
        │
        │ Evidence Frames + SHA-256
        ▼
☁️ FastAPI Cloud Backend
        │
        ├── PostgreSQL / Supabase
        ├── Evidence Storage
        └── Fingerprint Records
        │
        ▼
🖥️ Evidence Validation Application
        │
        ├── Integrity Verification
        ├── Individual Frame Verification
        └── Video Matching

The system is designed around the idea that a dashcam recording should not simply be stored as a video file. Evidence frames are fingerprinted so that the recorded evidence can later be checked for modification.
🎯 Objectives
The main objectives of the project are:
- Capture dashcam video using an Android device.
- Generate evidence frames during recording.
- Calculate SHA-256 fingerprints for captured frames.
- Upload evidence metadata to a Cloud backend.
- Store fingerprints and evidence information.
- Recalculate fingerprints during verification.
- Detect modified or missing evidence frames.
- Match submitted videos against previously recorded evidence.
- Detect temporal inconsistencies.
- Demonstrate network failure and recovery scenarios.
- Evaluate the system as an Edge-to-Cloud distributed application.
🏗️ System Architecture
                    EDGE DEVICE
                ┌─────────────────┐
                │ Android DashCam │
                │                 │
                │ CameraX         │
                │ MP4 Recording   │
                │ Frame Capture   │
                │ SHA-256         │
                │ Local Queue     │
                └────────┬────────┘
                         │
                         │ REST API
                         ▼
                ┌─────────────────┐
                │ FastAPI Backend │
                │                 │
                │ Evidence API    │
                │ Verification    │
                │ Video Matching  │
                └────────┬────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
       ┌──────────────┐      ┌──────────────┐
       │ Supabase /   │      │ Evidence     │
       │ PostgreSQL   │      │ Storage      │
       └──────────────┘      └──────────────┘
                         │
                         ▼
                ┌─────────────────┐
                │ Decoder /       │
                │ Validation App  │
                │                 │
                │ Integrity Check │
                │ Frame Check     │
                │ Video Match     │
                └─────────────────┘

📱 Android DashCam
The Android application acts as the Edge component of the system.
Main responsibilities
- Camera preview
- MP4 video recording
- Periodic evidence-frame capture
- SHA-256 fingerprint generation
- Evidence ID generation
- Uploading frame metadata
- Handling temporary network failures
The application uses CameraX for camera functionality.
During an evidence session, the application creates an evidence identifier such as:
DASH-20261004_001951

Captured evidence frames contain information such as:
Evidence ID
Frame index
Timestamp
Hash algorithm
SHA-256 fingerprint
Local file path

🔐 SHA-256 Evidence Fingerprinting
Each evidence frame is processed using:
SHA-256

Conceptually:
JPEG Frame
     │
     ▼
   SHA-256
     │
     ▼
Fingerprint

During verification, the stored frame is hashed again:
Stored Frame
     │
     ▼
   SHA-256
     │
     ▼
New Fingerprint
     │
     ▼
Compare with Recorded Fingerprint

If the fingerprints are identical:
VALID

If they differ:
ALTERED

This provides exact byte-level integrity verification for the stored evidence frames.
☁️ Cloud Backend
The backend provides REST APIs for communication between the Android application and the validation system.
The backend is responsible for:
- Receiving evidence metadata
- Storing fingerprint information
- Retrieving recordings
- Recalculating frame fingerprints
- Performing individual frame verification
- Performing video matching
- Returning verification results
Technologies
FastAPI
Python
REST API
Supabase / PostgreSQL

🖥️ Evidence Decoder
The decoder provides an interface for examining recorded evidence.
1. Integrity Check
Recalculates SHA-256 fingerprints for stored frames.
Recorded fingerprint
        │
        ├── Compare ──► VALID
        │
        └─────────────► ALTERED

2. Individual Frame Verification
A specific frame can be selected and independently verified.
The decoder can display:
- Recorded SHA-256
- Recalculated SHA-256
- Frame status
- Storage information
3. Video Match
A submitted video can be compared against recorded evidence.
The system can provide:
- Match percentage
- Similarity score
- Confidence score
- Corresponding recording
- Matched segment
- Reference frame range
- Temporal anomalies
🎥 Video Matching
Video matching is different from exact SHA-256 verification.
SHA-256
Used for:
Exact frame integrity verification

Video Matching
Used for:
Finding corresponding video content

This allows the system to identify whether a submitted video appears to correspond to an existing recorded sequence even when the submitted video is not byte-for-byte identical.
The matching process can analyse:
- Sampled frames
- Similarity
- Frame correspondence
- Temporal order
- Missing reference frames
- Unmatched sections
⚠️ Network Failure Handling
The project also considers distributed-system failures.
Example:
Android
   │
   │ Upload
   ▼
Network ❌
   │
   ▼
Local evidence retained
   │
   │ Connection restored
   ▼
Retry upload
   │
   ▼
Cloud Backend

This demonstrates concepts such as:
- Fault tolerance
- Retry
- Recovery
- Local buffering
- Network failure
- Distributed communication
🧪 Testing
The project includes testing for different video and system conditions.
Examples include:
- Original video
- Trimmed video
- Temporal shift
- Missing frames
- Duplicate frames
- Reordered frames
- Resolution changes
- FPS changes
- Re-encoding
- Compression changes
- Noise
- Blur
- Overlay/modification
- Partial modification
- Different recording
- Network failure
The purpose is to evaluate how the verification system behaves under different transformations and failure conditions.
📊 Evidence Workflow
1. Start Android DashCam
          ↓
2. Create Evidence ID
          ↓
3. Record MP4
          ↓
4. Capture evidence frame
          ↓
5. Generate SHA-256
          ↓
6. Upload fingerprint
          ↓
7. Store in Cloud
          ↓
8. Submit video for verification
          ↓
9. Recalculate / compare
          ↓
10. Generate verification result

🛡️ Security & Integrity
The project demonstrates several security-related concepts:
- Cryptographic hashing
- Data integrity
- Evidence validation
- API-based communication
- Cloud storage
- Separation of recorded and recalculated fingerprints
- Detection of modified evidence
SHA-256 is used as the cryptographic fingerprinting mechanism.
☁️ Cloud Computing Concepts Demonstrated
Edge Computing
Part of the processing occurs on the smartphone before data is sent to the Cloud.
Distributed Systems
The Android application and Cloud backend operate as separate components communicating over a network.
Fault Tolerance
The application must handle temporary network failures.
Cloud Storage
Evidence metadata and fingerprints are stored using Cloud services.
Scalability
The architecture can be considered for multiple vehicles and concurrent evidence sessions.
Performance
The project can evaluate:
- Frame processing time
- Upload latency
- Database latency
- Video matching time
- Storage requirements
- Network behaviour
🧰 Technologies
Component	Technology
Mobile	Android / Kotlin
Camera	CameraX
Video	MP4 / H.264
Fingerprint	SHA-256
Backend	FastAPI
Database	PostgreSQL / Supabase
API	REST
Decoder	Streamlit
Processing	Python
Cloud	Supabase
Version Control	Git / GitHub


📂 Repository Structure
DashCam-Video-Integrity/
│
├── android/
│   ├── app/
│   ├── src/
│   ├── build.gradle
│   └── settings.gradle
│
├── backend/
│   ├── FastAPI application
│   ├── API endpoints
│   ├── fingerprint verification
│   └── video matching
│
├── decoder/
│   ├── app.py
│   └── validation interface
│
├── tests/
│   ├── integrity tests
│   ├── video matching tests
│   └── network failure tests
│
├── documentation/
│   ├── reports
│   ├── test scenarios
│   └── screenshots
│
└── README.md

🚀 Running the Project
Android
Open the Android project in Android Studio.
Connect an Android device or start an emulator.
Grant camera permission and run the application.
Backend
Install the required Python dependencies:
pip install -r requirements.txt

Start the FastAPI server using the project's configured startup command.
The backend should expose the required REST endpoints for evidence upload and verification.
Decoder
Install the required Streamlit dependencies and start:
streamlit run app.py

Configure the backend server address in the decoder interface.
📋 Project Outcome
The project demonstrates an end-to-end Edge-to-Cloud evidence verification workflow:
Capture
   ↓
Fingerprint
   ↓
Upload
   ↓
Cloud Storage
   ↓
Verification
   ↓
Video Matching
   ↓
Integrity / Anomaly Result

The main contribution is the integration of:
- Mobile Edge processing
- Cloud services
- Cryptographic fingerprinting
- Video matching
- Distributed-system communication
- Network failure handling
- Evidence integrity verification
into one practical academic project.
👨‍💻 Author
Palina Karthik
Master's Student — ESIGELEC, France
B.Tech — Computer Science Engineering, Parul University
Academic Project
Edge-to-Cloud DashCam Video Integrity Verification Platform
📜 Academic Project
This repository contains software, experiments, test cases and documentation developed as part of an academic Cloud Computing / Distributed Systems project.
