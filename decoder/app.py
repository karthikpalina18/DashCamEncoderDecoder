import json
import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="DashCam Evidence Decoder",
    page_icon="🛡️",
    layout="wide",
)

DEFAULT_API_URL = os.getenv("DASHCAM_API_URL", "http://10.178.204.88:8000")

for key in ("verification", "frame_verification", "video_match", "selected_evidence"):
    st.session_state.setdefault(key, None)


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
    <style>
    .block-container { padding-top: 1.6rem; max-width: 1200px; }

    .hero {
        padding: 22px 26px; border-radius: 16px; margin-bottom: 18px;
        background: linear-gradient(135deg, #0f1b2b 0%, #10261f 100%);
        border: 1px solid #1f2f3f;
    }
    .hero h1 { margin: 0; font-size: 30px; color: #f2f5f9; }
    .hero p  { margin: 4px 0 0; color: #9aa7b8; font-size: 15px; }

    .verdict {
        padding: 22px; border-radius: 14px; text-align: center;
        font-size: 24px; font-weight: 700; margin: 6px 0 14px;
    }
    .verdict small { display:block; font-size: 14px; font-weight: 400; opacity:.85; margin-top:4px; }
    .verdict.ok   { background:#0f3a28; border:1px solid #27c97d; color:#6ff0ae; }
    .verdict.bad  { background:#41191d; border:1px solid #ff5252; color:#ff8a8a; }

    .chip {
        display:inline-block; padding:2px 10px; border-radius:999px;
        font-size:12px; font-weight:600; letter-spacing:.4px;
    }
    .chip.ok  { background:#123d2a; color:#6ff0ae; }
    .chip.bad { background:#421c1c; color:#ff8a8a; }

    div[data-testid="stMetric"] {
        background:#111821; border:1px solid #1f2b38; border-radius:12px; padding:12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>🛡️ DashCam Evidence Decoder</h1>
      <p>Independent integrity verification of dashcam footage — every frame is re-hashed from storage and compared with its recorded SHA-256 fingerprint.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Backend")
    api_url = st.text_input("FastAPI server", value=DEFAULT_API_URL).rstrip("/")

    if st.button("Test connection", use_container_width=True):
        try:
            r = requests.get(f"{api_url}/api/v1/health", timeout=5)
            (st.success if r.ok else st.error)(
                "Backend connected" if r.ok else f"HTTP {r.status_code}"
            )
        except Exception as error:
            st.error(str(error))

    if st.button("↻ Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("Hash algorithm")
    st.code("SHA-256")
    st.caption("Role")
    st.code("INSURER / DECODER")


# ============================================================
# API
# ============================================================

@st.cache_data(ttl=15, show_spinner=False)
def api_get(url, timeout=30):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=300, show_spinner=False)
def fetch_image(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.content


def verify_evidence(evidence_id):
    # Never cached: verification must always re-hash the stored bytes.
    r = requests.get(f"{api_url}/api/v1/verify/evidence/{evidence_id}", timeout=180)
    r.raise_for_status()
    return r.json()


def verify_single_frame(evidence_id, frame_index):
    r = requests.get(f"{api_url}/api/v1/verify/{evidence_id}/{frame_index}", timeout=60)
    r.raise_for_status()
    return r.json()


# ============================================================
# LOAD EVIDENCE LIST
# ============================================================

try:
    evidence_list = api_get(f"{api_url}/api/v1/evidence", 10).get("evidence", [])
except Exception as error:
    st.error("Unable to connect to the FastAPI backend.")
    st.code(str(error))
    st.stop()

if not evidence_list:
    st.info("No evidence has been uploaded yet. Start a recording in the DashCam app.")
    st.stop()

selected = st.selectbox(
    "Evidence recording",
    evidence_list,
    index=len(evidence_list) - 1,  # newest last (IDs are timestamped)
)

if st.session_state.selected_evidence != selected:
    st.session_state.selected_evidence = selected
    st.session_state.verification = None
    st.session_state.frame_verification = None
    st.session_state.video_match = None

try:
    evidence = api_get(f"{api_url}/api/v1/evidence/{selected}")
except Exception as error:
    st.error("Unable to load evidence.")
    st.code(str(error))
    st.stop()

frames = evidence.get("frames", [])
df = pd.DataFrame(frames)

if not df.empty and "captured_at" in df.columns:
    df["captured_at"] = pd.to_datetime(df["captured_at"], errors="coerce")
    first, last = df["captured_at"].min(), df["captured_at"].max()
    duration = (last - first).total_seconds() if pd.notna(first) and pd.notna(last) else 0
    indexes = sorted(df["frame_index"].tolist())
    missing = sorted(set(range(indexes[0], indexes[-1] + 1)) - set(indexes))
else:
    first = last = None
    duration, missing = 0, []


# ============================================================
# SUMMARY
# ============================================================

c1, c2, c3, c4 = st.columns(4)
c1.metric("Frames stored", len(frames))
c2.metric("Duration", f"{int(duration // 60)}m {int(duration % 60)}s")
c3.metric("Started", first.strftime("%d %b %H:%M:%S") if pd.notna(first) else "—")
c4.metric("Missing frames", len(missing), help="Gaps in the frame sequence")

if missing:
    st.warning(
        f"Sequence gap detected: frame(s) {', '.join(map(str, missing[:15]))}"
        f"{' …' if len(missing) > 15 else ''} were never received."
    )

tab_verify, tab_video, tab_gallery, tab_frames, tab_about = st.tabs(
    ["🔐 Verification", "🎬 Video Match", "🖼️ Gallery", "📋 Frame log", "ℹ️ How it works"]
)


# ============================================================
# TAB: VERIFICATION
# ============================================================

with tab_verify:
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Complete evidence")
        if st.button("Verify all frames", type="primary", use_container_width=True):
            with st.spinner(f"Re-hashing {len(frames)} frames from storage…"):
                try:
                    st.session_state.verification = verify_evidence(selected)
                except Exception as error:
                    st.session_state.verification = None
                    st.error("Verification failed.")
                    st.code(str(error))

    with right:
        st.subheader("Single frame")
        if frames:
            frame_choice = st.selectbox(
                "Frame", [f["frame_index"] for f in frames], key="frame_selector"
            )
            if st.button("Verify frame", use_container_width=True):
                with st.spinner("Verifying…"):
                    try:
                        st.session_state.frame_verification = verify_single_frame(
                            selected, frame_choice
                        )
                    except Exception as error:
                        st.session_state.frame_verification = None
                        st.error("Frame verification failed.")
                        st.code(str(error))

    result = st.session_state.verification
    if result:
        st.divider()
        ok = result.get("verified", False)
        total, valid, invalid = (
            result.get("total_frames", 0),
            result.get("valid_frames", 0),
            result.get("invalid_frames", 0),
        )

        if ok:
            st.markdown(
                '<div class="verdict ok">✓ INTEGRITY VALID'
                "<small>All recorded frames match their original fingerprint.</small></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="verdict bad">✗ INTEGRITY FAILED'
                f"<small>{invalid} of {total} frame(s) are modified, missing or unreadable.</small></div>",
                unsafe_allow_html=True,
            )

        m1, m2, m3 = st.columns(3)
        m1.metric("Total", total)
        m2.metric("Valid", valid)
        m3.metric("Invalid", invalid)
        st.progress(valid / total if total else 0.0)

        vdf = pd.DataFrame(result.get("frames", []))
        if not vdf.empty:
            only_bad = st.toggle("Show only problem frames", value=not ok)
            shown = vdf[vdf["integrity"] != "VALID"] if only_bad else vdf
            cols = [c for c in ["frame_index", "integrity", "stored_hash", "calculated_hash", "error"]
                    if c in shown.columns]

            def colour(v):
                return "color:#6ff0ae" if v == "VALID" else "color:#ff8a8a;font-weight:600"

            st.dataframe(
                shown[cols].style.map(colour, subset=["integrity"]),
                use_container_width=True,
                hide_index=True,
            )

        report = {
            "evidence_id": selected,
            "verified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "algorithm": "SHA-256",
            **result,
        }
        d1, d2 = st.columns(2)
        d1.download_button(
            "⬇ Download report (JSON)",
            json.dumps(report, indent=2),
            file_name=f"{selected}_verification.json",
            mime="application/json",
            use_container_width=True,
        )
        if not vdf.empty:
            d2.download_button(
                "⬇ Download report (CSV)",
                vdf.to_csv(index=False),
                file_name=f"{selected}_verification.csv",
                mime="text/csv",
                use_container_width=True,
            )

    fr = st.session_state.frame_verification
    if fr and fr.get("evidence_id") == selected:
        st.divider()
        st.subheader(f"Frame {fr.get('frame_index')}")
        good = fr.get("verified", False)
        st.markdown(
            f'<span class="chip {"ok" if good else "bad"}">'
            f'{"VALID" if good else "TAMPERED"}</span>',
            unsafe_allow_html=True,
        )

        img_col, hash_col = st.columns([1, 2])
        with img_col:
            try:
                st.image(
                    fetch_image(f"{api_url}/api/v1/evidence/{selected}/{fr['frame_index']}/image"),
                    use_container_width=True,
                )
            except Exception:
                st.caption("Preview unavailable")
        with hash_col:
            st.caption("Stored SHA-256")
            st.code(fr.get("stored_hash", "N/A"))
            st.caption("Calculated SHA-256")
            st.code(fr.get("calculated_hash", "N/A"))
            st.caption("Storage path")
            st.code(fr.get("storage_path", "N/A"))


# ============================================================
# TAB: VIDEO MATCH
# ============================================================

with tab_video:
    st.subheader("Submitted video matching")
    st.caption("Perceptual matching locates the corresponding recorded segment. SHA-256 remains the exact byte-level integrity check above.")
    submitted = st.file_uploader("Upload a submitted video", type=["mp4", "mov", "mkv", "avi"], key="submitted_video")
    vc1, vc2 = st.columns(2)
    with vc1:
        threshold = st.slider("Perceptual similarity threshold", 0.50, 1.00, 0.70, 0.01)
    with vc2:
        sample_every = st.number_input(
            "Sample every Nth video frame (0 = automatic)", 0, 120, 0,
            help="Automatic mode samples at the fingerprint cadence used by the Android dashcam, so different submitted FPS values are handled correctly."
        )
    if submitted and st.button("Run video integrity / synchronization test", type="primary", use_container_width=True):
        try:
            files = {"video": (submitted.name, submitted.getvalue(), submitted.type or "video/mp4")}
            data = {"evidence_id": selected, "threshold": str(threshold), "sample_every": str(sample_every)}
            with st.spinner("Matching submitted video against stored fingerprints…"):
                r = requests.post(f"{api_url}/api/v1/match/video", data=data, files=files, timeout=600)
                r.raise_for_status()
                result = r.json()
            st.session_state.video_match = result
        except Exception as error:
            st.error("Video matching failed.")
            st.code(str(error))

    result = st.session_state.get("video_match")
    if result and result.get("evidence_id") == selected:
        st.divider()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Classification", result.get("classification", "—"))
        c2.metric("Alignment", f"{result.get('alignment_coverage_percentage', result.get('match_percentage', 0)):.2f}%")
        c3.metric("Confidence", f"{result.get('confidence_score', 0):.3f}")
        c4.metric("Processing", f"{result.get('processing_time_seconds', 0):.2f}s")
        seg = result.get("matched_segment")
        if seg:
            st.info(f"Matched trip: {result.get('corresponding_trip')} · submitted {seg.get('submitted_start_seconds', 0):.2f}s–{seg.get('submitted_end_seconds', 0):.2f}s · reference frames {seg.get('reference_start_frame')}–{seg.get('reference_end_frame')}")
        anomalies = result.get("anomalies", [])
        if anomalies:
            st.warning("Anomalies: " + "; ".join(anomalies))
        else:
            st.success("No temporal anomalies detected in the matched sequence.")
        vframes = pd.DataFrame(result.get("frames", []))
        if not vframes.empty:
            st.dataframe(vframes, use_container_width=True, hide_index=True)
        st.download_button("⬇ Download video-match report", json.dumps(result, indent=2), file_name=f"{selected}_video_match.json", mime="application/json", use_container_width=True)


# ============================================================
# TAB: GALLERY
# ============================================================

with tab_gallery:
    if not frames:
        st.info("No frames found.")
    else:
        per_page = 12
        pages = max(1, -(-len(frames) // per_page))
        page = st.number_input("Page", 1, pages, 1, help=f"{len(frames)} frames, {per_page} per page")
        subset = frames[(page - 1) * per_page: page * per_page]

        cols = st.columns(4)
        for i, f in enumerate(subset):
            with cols[i % 4]:
                try:
                    st.image(
                        fetch_image(f"{api_url}/api/v1/evidence/{selected}/{f['frame_index']}/image"),
                        use_container_width=True,
                    )
                except Exception:
                    st.caption("Preview unavailable")
                st.caption(f"**#{f['frame_index']}** · `{str(f['frame_hash'])[:12]}…`")


# ============================================================
# TAB: FRAME LOG
# ============================================================

with tab_frames:
    if df.empty:
        st.info("No frames found.")
    else:
        query = st.text_input("Filter by hash or frame number", placeholder="e.g. a3f9 or 42")
        table = df.copy()
        if query:
            q = query.lower()
            mask = (
                table["frame_hash"].astype(str).str.lower().str.contains(q)
                | table["frame_index"].astype(str).eq(q)
            )
            table = table[mask]

        cols = [c for c in ["frame_index", "captured_at", "hash_algorithm", "frame_hash", "storage_path"]
                if c in table.columns]
        st.dataframe(table[cols], use_container_width=True, hide_index=True)
        st.download_button(
            "⬇ Export frame log (CSV)",
            table[cols].to_csv(index=False),
            file_name=f"{selected}_frames.csv",
            mime="text/csv",
        )


# ============================================================
# TAB: ABOUT
# ============================================================

with tab_about:
    st.markdown(
        """
        1. The **DashCam app** hashes every captured JPEG with SHA-256 on the phone, then uploads frame + hash.
        2. The **backend** recomputes the hash on receipt and rejects any mismatch, then stores the image in private Supabase Storage and the fingerprint in PostgreSQL.
        3. This **decoder** never touches Supabase directly. On verification the backend downloads each stored JPEG, re-hashes the real bytes, and compares against the stored fingerprint.
        """
    )
    st.code(
        """Phone JPEG ─► SHA-256 ─► stored fingerprint ─┐
                                                COMPARE ─► VALID / TAMPERED
Stored JPEG ─► SHA-256 ─► calculated hash ──┘""",
        language=None,
    )
