import os
import hashlib
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

STORAGE_BUCKET = "dashcam-evidence"


if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing from .env")

if not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_SECRET_KEY is missing from .env"
    )


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="DashCam Evidence Authentication API",
    description=(
        "Backend server for DashCam Encoder and Decoder"
    ),
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# ROOT
# ============================================================

@app.get("/")
def root():

    return {
        "project":
            "DashCam Evidence Authentication System",

        "status":
            "running",

        "version":
            "1.0.0"
    }


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/v1/health")
def health():

    return {
        "status": "healthy",
        "service": "DashCam Backend",
        "version": "1.0.0"
    }


@app.get("/api/v1/health/database")
def database_health():

    try:

        response = (
            supabase
            .table("dashcam_frames")
            .select("id")
            .limit(1)
            .execute()
        )

        return {
            "status": "connected",
            "database": "Supabase PostgreSQL",
            "rows_checked": len(response.data)
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


@app.get("/api/v1/health/storage")
def storage_health():

    try:

        buckets = (
            supabase
            .storage
            .list_buckets()
        )

        found = any(
            bucket.name == STORAGE_BUCKET
            for bucket in buckets
        )

        if not found:

            raise HTTPException(
                status_code=404,
                detail=(
                    f"Bucket '{STORAGE_BUCKET}' "
                    f"was not found"
                )
            )

        return {
            "status": "connected",
            "bucket": STORAGE_BUCKET,
            "private": True
        }

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# UPLOAD FRAME
# ============================================================

@app.post("/api/v1/frames")
async def upload_frame(

    evidence_id: str = Form(...),

    frame_index: int = Form(...),

    timestamp: str = Form(...),

    hash_algorithm: str = Form(...),

    hash: str = Form(...),

    frame: UploadFile = File(...)

):

    evidence_id = evidence_id.strip()
    client_hash = hash.strip().lower()

    # --------------------------------------------------------
    # Validate evidence ID
    # --------------------------------------------------------

    if not evidence_id:

        raise HTTPException(
            status_code=400,
            detail="evidence_id cannot be empty"
        )


    # --------------------------------------------------------
    # Validate frame index
    # --------------------------------------------------------

    if frame_index < 1:

        raise HTTPException(
            status_code=400,
            detail="frame_index must be >= 1"
        )


    # --------------------------------------------------------
    # Validate algorithm
    # --------------------------------------------------------

    if hash_algorithm.upper() != "SHA-256":

        raise HTTPException(
            status_code=400,
            detail="Only SHA-256 is supported"
        )


    # --------------------------------------------------------
    # Validate hash
    # --------------------------------------------------------

    if len(client_hash) != 64:

        raise HTTPException(
            status_code=400,
            detail="Invalid SHA-256 hash length"
        )

    try:

        int(client_hash, 16)

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid SHA-256 hash"
        )


    # --------------------------------------------------------
    # Validate image
    # --------------------------------------------------------

    if frame.content_type not in [
        "image/jpeg",
        "image/jpg"
    ]:

        raise HTTPException(
            status_code=400,
            detail="Only JPEG files are supported"
        )


    # --------------------------------------------------------
    # Read image
    # --------------------------------------------------------

    file_bytes = await frame.read()

    if not file_bytes:

        raise HTTPException(
            status_code=400,
            detail="Empty frame received"
        )


    # --------------------------------------------------------
    # Server-side SHA-256
    # --------------------------------------------------------

    server_hash = hashlib.sha256(
        file_bytes
    ).hexdigest()


    # --------------------------------------------------------
    # Verify client hash
    # --------------------------------------------------------

    if server_hash.lower() != client_hash:

        raise HTTPException(
            status_code=400,
            detail={
                "message":
                    "Hash verification failed",

                "client_hash":
                    client_hash,

                "server_hash":
                    server_hash,

                "integrity":
                    "INVALID"
            }
        )


    # --------------------------------------------------------
    # Storage path
    # --------------------------------------------------------

    storage_path = (
        f"{evidence_id}/"
        f"frame_{frame_index:06d}.jpg"
    )


    try:

        # ----------------------------------------------------
        # Check duplicate
        # ----------------------------------------------------

        existing = (
            supabase
            .table("dashcam_frames")
            .select("id")
            .eq(
                "evidence_id",
                evidence_id
            )
            .eq(
                "frame_index",
                frame_index
            )
            .execute()
        )

        if existing.data:

            return {
                "success": True,
                "message": "Frame already exists",
                "evidence_id": evidence_id,
                "frame_index": frame_index,
                "hash": server_hash,
                "integrity": "VALID",
                "duplicate": True
            }


        # ----------------------------------------------------
        # Upload JPEG
        # ----------------------------------------------------

        (
            supabase
            .storage
            .from_(STORAGE_BUCKET)
            .upload(
                path=storage_path,
                file=file_bytes,
                file_options={
                    "content-type": "image/jpeg",
                    "upsert": False
                }
            )
        )


        # ----------------------------------------------------
        # Insert metadata
        # ----------------------------------------------------

        database_data = {

            "evidence_id":
                evidence_id,

            "frame_index":
                frame_index,

            "captured_at":
                timestamp,

            "hash_algorithm":
                "SHA-256",

            "frame_hash":
                server_hash,

            "storage_path":
                storage_path
        }


        (
            supabase
            .table("dashcam_frames")
            .insert(database_data)
            .execute()
        )


        return {

            "success": True,

            "message":
                "Frame received and verified",

            "evidence_id":
                evidence_id,

            "frame_index":
                frame_index,

            "timestamp":
                timestamp,

            "hash_algorithm":
                "SHA-256",

            "client_hash":
                client_hash,

            "server_hash":
                server_hash,

            "integrity":
                "VALID",

            "storage_path":
                storage_path
        }


    except Exception as error:

        # Attempt storage cleanup if database insertion failed
        try:

            (
                supabase
                .storage
                .from_(STORAGE_BUCKET)
                .remove([storage_path])
            )

        except Exception:
            pass

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# GET ALL EVIDENCE
# ============================================================

@app.get("/api/v1/evidence")
def get_all_evidence():

    try:

        response = (
            supabase
            .table("dashcam_frames")
            .select("evidence_id")
            .execute()
        )

        evidence_ids = sorted(
            list(
                set(
                    row["evidence_id"]
                    for row in response.data
                )
            )
        )

        return {
            "count": len(evidence_ids),
            "evidence": evidence_ids
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# GET COMPLETE EVIDENCE
# ============================================================

@app.get("/api/v1/evidence/{evidence_id}")
def get_evidence(evidence_id: str):

    try:

        response = (
            supabase
            .table("dashcam_frames")
            .select("*")
            .eq(
                "evidence_id",
                evidence_id
            )
            .order(
                "frame_index"
            )
            .execute()
        )

        return {
            "evidence_id": evidence_id,
            "frame_count": len(response.data),
            "frames": response.data
        }

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# GET SINGLE FRAME METADATA
# ============================================================

@app.get(
    "/api/v1/evidence/"
    "{evidence_id}/{frame_index}"
)
def get_frame(
    evidence_id: str,
    frame_index: int
):

    try:

        response = (
            supabase
            .table("dashcam_frames")
            .select("*")
            .eq(
                "evidence_id",
                evidence_id
            )
            .eq(
                "frame_index",
                frame_index
            )
            .single()
            .execute()
        )

        if not response.data:

            raise HTTPException(
                status_code=404,
                detail="Frame not found"
            )

        return response.data

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# VERIFY COMPLETE EVIDENCE
#
# IMPORTANT:
# This route MUST appear BEFORE
# /verify/{evidence_id}/{frame_index}
# ============================================================

@app.get(
    "/api/v1/verify/evidence/{evidence_id}"
)
def verify_complete_evidence(
    evidence_id: str
):

    try:

        response = (
            supabase
            .table("dashcam_frames")
            .select("*")
            .eq(
                "evidence_id",
                evidence_id
            )
            .order(
                "frame_index"
            )
            .execute()
        )

        frames = response.data

        if not frames:

            raise HTTPException(
                status_code=404,
                detail="Evidence not found"
            )


        results = []

        valid_count = 0
        invalid_count = 0


        for record in frames:

            frame_index = record["frame_index"]

            stored_hash = record["frame_hash"]

            storage_path = record["storage_path"]


            try:

                frame_bytes = (
                    supabase
                    .storage
                    .from_(STORAGE_BUCKET)
                    .download(storage_path)
                )


                calculated_hash = (
                    hashlib
                    .sha256(frame_bytes)
                    .hexdigest()
                )


                verified = (
                    stored_hash.lower()
                    ==
                    calculated_hash.lower()
                )


                if verified:

                    valid_count += 1

                else:

                    invalid_count += 1


                results.append({

                    "frame_index":
                        frame_index,

                    "stored_hash":
                        stored_hash,

                    "calculated_hash":
                        calculated_hash,

                    "verified":
                        verified,

                    "integrity":
                        (
                            "VALID"
                            if verified
                            else
                            "TAMPERED"
                        )
                })


            except Exception as frame_error:

                invalid_count += 1

                results.append({

                    "frame_index":
                        frame_index,

                    "stored_hash":
                        stored_hash,

                    "calculated_hash":
                        None,

                    "verified":
                        False,

                    "integrity":
                        "ERROR",

                    "error":
                        str(frame_error)
                })


        overall_valid = (
            len(frames) > 0
            and
            invalid_count == 0
            and
            valid_count == len(frames)
        )


        return {

            "evidence_id":
                evidence_id,

            "total_frames":
                len(frames),

            "valid_frames":
                valid_count,

            "invalid_frames":
                invalid_count,

            "integrity":
                (
                    "VALID"
                    if overall_valid
                    else
                    "TAMPERED"
                ),

            "verified":
                overall_valid,

            "frames":
                results
        }


    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail={
                "message":
                    "Evidence verification failed",

                "error":
                    str(error)
            }
        )


# ============================================================
# VERIFY SINGLE FRAME
#
# IMPORTANT:
# This route comes AFTER the complete-evidence route.
# ============================================================

@app.get(
    "/api/v1/verify/"
    "{evidence_id}/{frame_index}"
)
def verify_frame(
    evidence_id: str,
    frame_index: int
):

    try:

        response = (
            supabase
            .table("dashcam_frames")
            .select("*")
            .eq(
                "evidence_id",
                evidence_id
            )
            .eq(
                "frame_index",
                frame_index
            )
            .single()
            .execute()
        )


        if not response.data:

            raise HTTPException(
                status_code=404,
                detail="Frame not found"
            )


        record = response.data

        stored_hash = record["frame_hash"]

        storage_path = record["storage_path"]


        # Download actual JPEG
        frame_bytes = (
            supabase
            .storage
            .from_(STORAGE_BUCKET)
            .download(storage_path)
        )


        if not frame_bytes:

            raise HTTPException(
                status_code=404,
                detail="Frame could not be downloaded"
            )


        # Recalculate SHA-256
        calculated_hash = (
            hashlib
            .sha256(frame_bytes)
            .hexdigest()
        )


        # Compare
        verified = (
            stored_hash.lower()
            ==
            calculated_hash.lower()
        )


        return {

            "evidence_id":
                evidence_id,

            "frame_index":
                frame_index,

            "algorithm":
                "SHA-256",

            "stored_hash":
                stored_hash,

            "calculated_hash":
                calculated_hash,

            "integrity":
                (
                    "VALID"
                    if verified
                    else
                    "TAMPERED"
                ),

            "verified":
                verified,

            "storage_path":
                storage_path,

            "message":
                (
                    "Frame integrity verified successfully"
                    if verified
                    else
                    "Frame integrity verification failed"
                )
        }


    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail={
                "message":
                    "Frame verification failed",

                "error":
                    str(error)
            }
        )


# ============================================================
# DELETE EVIDENCE
# ============================================================

@app.delete(
    "/api/v1/evidence/{evidence_id}"
)
def delete_evidence(
    evidence_id: str
):

    try:

        response = (
            supabase
            .table("dashcam_frames")
            .select("storage_path")
            .eq(
                "evidence_id",
                evidence_id
            )
            .execute()
        )

        records = response.data

        if not records:

            raise HTTPException(
                status_code=404,
                detail="Evidence not found"
            )


        paths = [
            record["storage_path"]
            for record in records
        ]


        if paths:

            (
                supabase
                .storage
                .from_(STORAGE_BUCKET)
                .remove(paths)
            )


        (
            supabase
            .table("dashcam_frames")
            .delete()
            .eq(
                "evidence_id",
                evidence_id
            )
            .execute()
        )


        return {

            "success":
                True,

            "evidence_id":
                evidence_id,

            "deleted_frames":
                len(records)
        }


    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# RETENTION CLEANUP
# ============================================================

@app.delete(
    "/api/v1/maintenance/cleanup"
)
def cleanup_old_evidence(
    retention_days: int = 30
):

    if retention_days < 1:

        raise HTTPException(
            status_code=400,
            detail="retention_days must be >= 1"
        )


    try:

        cutoff = (
            datetime.now(timezone.utc)
            -
            timedelta(
                days=retention_days
            )
        )


        response = (
            supabase
            .table("dashcam_frames")
            .select(
                "evidence_id,storage_path"
            )
            .lt(
                "created_at",
                cutoff.isoformat()
            )
            .execute()
        )


        records = response.data


        if not records:

            return {

                "success":
                    True,

                "deleted_evidence":
                    0,

                "deleted_frames":
                    0,

                "message":
                    "No expired evidence found"
            }


        evidence_ids = sorted(
            list(
                set(
                    record["evidence_id"]
                    for record in records
                )
            )
        )


        paths = [
            record["storage_path"]
            for record in records
        ]


        if paths:

            (
                supabase
                .storage
                .from_(STORAGE_BUCKET)
                .remove(paths)
            )


        for evidence_id in evidence_ids:

            (
                supabase
                .table("dashcam_frames")
                .delete()
                .eq(
                    "evidence_id",
                    evidence_id
                )
                .lt(
                    "created_at",
                    cutoff.isoformat()
                )
                .execute()
            )


        return {

            "success":
                True,

            "retention_days":
                retention_days,

            "deleted_evidence":
                len(evidence_ids),

            "deleted_frames":
                len(records),

            "cutoff":
                cutoff.isoformat()
        }


    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )
# ============================================================
# ROBUST VIDEO MATCHING / TEST EVALUATION
# ============================================================
from tempfile import NamedTemporaryFile
from time import perf_counter
import cv2
import numpy as np
from fingerprint import phash
from video_matcher import align_video

@app.get("/api/v1/evidence/{evidence_id}/{frame_index}/image")
def get_frame_image(evidence_id: str, frame_index: int):
    """Return a stored JPEG for the Streamlit gallery/verification UI."""
    from fastapi.responses import Response
    try:
        record = (
            supabase.table("dashcam_frames").select("storage_path")
            .eq("evidence_id", evidence_id).eq("frame_index", frame_index)
            .single().execute().data
        )
        if not record:
            raise HTTPException(status_code=404, detail="Frame not found")
        data = supabase.storage.from_(STORAGE_BUCKET).download(record["storage_path"])
        return Response(content=data, media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=404, detail=str(error))


def _load_reference_frames(evidence_id: str):
    records = (supabase.table("dashcam_frames").select("*")
               .eq("evidence_id", evidence_id).order("frame_index").execute().data)
    if not records:
        raise HTTPException(status_code=404, detail="Evidence not found")
    refs = []
    for record in records:
        data = supabase.storage.from_(STORAGE_BUCKET).download(record["storage_path"])
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is not None:
            refs.append((record, image, phash(image)))
    return refs


@app.post("/api/v1/match/video")
async def match_submitted_video(
    evidence_id: str = Form(...),
    video: UploadFile = File(...),
    threshold: float = Form(0.70),
    sample_every: int = Form(0),
):
    """Match a submitted video against the sparse recorded evidence stream.

    The endpoint keeps SHA-256 verification separate from perceptual
    correspondence. The matcher uses dense temporal sampling and multi-feature
    ordered alignment so small capture-timing differences do not cause genuine
    videos to be rejected.
    """
    if not 0.50 <= threshold <= 1.0:
        raise HTTPException(status_code=400, detail="threshold must be between 0.50 and 1.0")
    if sample_every < 0:
        raise HTTPException(status_code=400, detail="sample_every must be >= 0 (0 = automatic)")
    if not video.filename:
        raise HTTPException(status_code=400, detail="video filename is required")

    started = perf_counter()
    refs = _load_reference_frames(evidence_id)
    if not refs:
        raise HTTPException(status_code=404, detail="No reference fingerprints found")

    reference_interval = 1.0
    ref_times_abs = []
    for record, _image, _hash in refs:
        raw_ts = record.get("captured_at") or record.get("timestamp")
        try:
            text_ts = str(raw_ts).replace("Z", "+00:00")
            ref_times_abs.append(datetime.fromisoformat(text_ts))
        except (TypeError, ValueError):
            ref_times_abs.append(None)
    intervals = []
    for a, b in zip(ref_times_abs, ref_times_abs[1:]):
        if a is not None and b is not None:
            delta = (b - a).total_seconds()
            if 0.2 <= delta <= 5.0:
                intervals.append(delta)
    if intervals:
        reference_interval = float(np.median(intervals))

    content = await video.read()
    suffix = os.path.splitext(video.filename)[1] or ".mp4"
    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = align_video(
            refs,
            tmp_path,
            threshold=threshold,
            reference_interval=reference_interval,
            sample_every=sample_every,
        )

        result.update({
            "evidence_id": evidence_id,
            "submitted_video": video.filename,
        })
        result["processing_time_seconds"] = round(perf_counter() - started, 4)
        if result.get("match_detected"):
            result["corresponding_trip"] = evidence_id
        else:
            result["corresponding_trip"] = None
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
