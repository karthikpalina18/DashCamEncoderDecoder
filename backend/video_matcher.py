"""Robust temporal/perceptual video correspondence matcher.

The Android reference JPEG and MP4 VideoCapture are independent capture paths,
so byte identity and single-frame pHash equality are not expected. This module
uses multi-feature visual similarity plus ordered sequence alignment, and then
an independent integrity analysis of the submitted video (continuity, timing,
local modification) because sparse 1-fps references cannot see frame-level edits.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fingerprint import phash


# --------------------------------------------------------------------------
# Feature similarity
# --------------------------------------------------------------------------
def _prep(image, size=(96, 54)):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, size, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    gray = (gray - gray.mean()) / (gray.std() + 1e-6)

    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [18, 8], [0, 180, 0, 256])
    hist = cv2.normalize(hist, None).flatten()

    edges = cv2.Canny((gray * 255).astype(np.uint8), 60, 140)
    eh, _ = np.histogram(edges.ravel(), bins=[0, 1, 256])
    edge_density = float(eh[1]) / max(1, edges.size)
    return gray, hist.astype(np.float32), edge_density


def _feature_similarity(a, b):
    pa = phash(a)
    pb = phash(b)
    p = 1.0 - np.count_nonzero(pa != pb) / float(len(pa))

    ga, ha, ea = _prep(a)
    gb, hb, eb = _prep(b)

    g = float(np.mean(ga * gb))
    g = float(np.clip((g + 1.0) / 2.0, 0.0, 1.0))

    h = float(np.minimum(ha, hb).sum() / max(ha.sum(), hb.sum(), 1e-8))
    h = float(np.clip(h, 0.0, 1.0))

    e = float(np.exp(-abs(ea - eb) / 0.035))
    e = float(np.clip(e, 0.0, 1.0))

    return float(0.48 * p + 0.30 * g + 0.14 * h + 0.08 * e)


def _read_candidates(video_path, target_fps=5.0):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("Unable to decode submitted video")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    step = max(1, int(round(fps / target_fps)))
    out = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            out.append({
                "frame_no": i + 1,
                "time": i / fps if fps > 0 else 0.0,
                "image": frame,
                "hash": phash(frame),
            })
        i += 1
    cap.release()
    return fps, total, step, out


# --------------------------------------------------------------------------
# Integrity analysis helpers
# --------------------------------------------------------------------------
def _group(idx, gap=2):
    """Collapse runs of nearby indices into event start indices."""
    out, prev = [], None
    for k in idx:
        if prev is None or k - prev > gap:
            out.append(int(k))
        prev = k
    return out


def _is_periodic(starts, tol=0.25):
    """Regular spacing => codec GOP pulses / fps conversion, not tampering."""
    if len(starts) < 4:
        return False
    gaps = np.diff(starts).astype(np.float64)
    return float(gaps.std() / max(gaps.mean(), 1e-6)) < tol


def _rolling_median(x, w=15):
    n, h = len(x), w // 2
    return np.array([np.median(x[max(0, i - h):min(n, i + h + 1)]) for i in range(n)],
                    dtype=np.float32)


def _temporal_continuity(video_path, fps):
    """Dense (every frame) scan of the submitted video for edits that the
    sparse reference alignment cannot see: duplicated runs, jump spikes
    (deleted content) and out-of-place frames (reordering)."""
    cap = cv2.VideoCapture(str(video_path))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        frames.append(cv2.resize(g, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32))
    cap.release()

    info = {
        "frames_analyzed": len(frames),
        "duplicate_events": 0,
        "discontinuity_events": 0,
        "reorder_events": 0,
        "duplicate_times": [],
        "discontinuity_times": [],
        "reorder_times": [],
        "median_frame_diff": 0.0,
    }
    if len(frames) < 12:
        return info

    F = np.stack(frames)
    d1 = np.abs(F[1:] - F[:-1]).mean(axis=(1, 2))          # frame t -> t+1
    d2 = np.abs(F[2:] - F[:-2]).mean(axis=(1, 2))          # frame t -> t+2
    med = float(np.median(d1))
    info["median_frame_diff"] = round(med, 4)
    base = np.maximum(_rolling_median(d1), 0.5)
    to_t = lambda k: round(float(k) / fps, 3) if fps else 0.0

    # 1) Duplicated frames: near-zero motion runs inside moving footage.
    # Exact duplicate-frame detector (independent of sparse references).
    fh=[]
    for g in frames:
        sm=cv2.resize(g.astype(np.uint8),(32,18),interpolation=cv2.INTER_AREA)
        fh.append(phash(cv2.cvtColor(sm,cv2.COLOR_GRAY2BGR)))
    hd=np.array([np.count_nonzero(fh[k]!=fh[k+1]) for k in range(len(fh)-1)],dtype=np.float32)
    ex=np.where(hd<=2)[0]
    exs=_group(ex,gap=3)
    if exs:
        info["duplicate_events"]=len(exs)
        info["duplicate_times"]=[to_t(s) for s in exs[:20]]
    if med >= 1.0:
        dup_idx = np.where(d1 < 0.2 * med)[0]
        starts = _group(dup_idx)
        frac = len(dup_idx) / float(len(d1))
        if starts and frac < 0.4 and not _is_periodic(starts):
            info["duplicate_events"] = len(starts)
            info["duplicate_times"] = [to_t(s) for s in starts[:20]]

    # 2) Discontinuities: abrupt jump relative to local motion (deleted frames).
    spike_idx = np.where((d1 / base > 2.2) & (d1 - base > 1.0))[0]
    starts = _group(spike_idx)
    if starts and not _is_periodic(starts):
        info["discontinuity_events"] = len(starts)
        info["discontinuity_times"] = [to_t(s) for s in starts[:20]]

    # 3) Out-of-place frames: a frame farther from both neighbours than the
    #    neighbours are from each other (swap / reorder signature).
    dmax = np.maximum(d1[:-1], d1[1:])
    oop = np.where((d2 < 0.7 * dmax) & (dmax > 1.6 * base[:-1]))[0] + 1
    starts = _group(oop)
    if starts and not _is_periodic(starts):
        info["reorder_events"] = len(starts)
        info["reorder_times"] = [to_t(s) for s in starts[:20]]

    return info


def _block_corrs(a, b, grid=(8, 6)):
    ga = cv2.resize(cv2.cvtColor(a, cv2.COLOR_BGR2GRAY), (96, 54),
                    interpolation=cv2.INTER_AREA).astype(np.float32)
    gb = cv2.resize(cv2.cvtColor(b, cv2.COLOR_BGR2GRAY), (96, 54),
                    interpolation=cv2.INTER_AREA).astype(np.float32)
    gx, gy = grid
    bw, bh = 96 // gx, 54 // gy
    out = np.full(gx * gy, np.nan, dtype=np.float32)
    for r in range(gy):
        for c in range(gx):
            pa = ga[r * bh:(r + 1) * bh, c * bw:(c + 1) * bw].ravel()
            pb = gb[r * bh:(r + 1) * bh, c * bw:(c + 1) * bw].ravel()
            sa, sb = pa.std(), pb.std()
            if sa < 2.0 or sb < 2.0:
                continue
            out[r * gx + c] = float(np.mean((pa - pa.mean()) * (pb - pb.mean())) / (sa * sb))
    return out


def _local_modification(aligned, query, ref_images):
    """Flag aligned pairs that deviate from the video's own typical behaviour.
    A per-block baseline absorbs uniform effects (watermark, crop, noise,
    brightness); only time-localised edits stand out."""
    if len(aligned) < 5:
        return []
    C = np.stack([_block_corrs(query[i]["image"], ref_images[j]) for i, j, _ in aligned])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        base = np.nanmedian(C, axis=0)
    dev = base[None, :] - C
    dev = np.where(np.isnan(dev), 0.0, dev)
    block_flag = (dev > 0.35).sum(axis=1)

    s = np.array([p[2] for p in aligned], dtype=np.float64)
    med = float(np.median(s))
    mad = 1.4826 * float(np.median(np.abs(s - med)))
    sim_out = s < med - max(0.06, 5.0 * mad)

    flagged = np.where((block_flag >= 2) | sim_out)[0]
    if len(flagged) == 0 or len(flagged) > 0.6 * len(aligned):
        return []   # nothing, or so widespread it is the baseline (global edit)
    return [round(float(query[aligned[k][0]]["time"]), 3) for k in flagged]


def _internal_unmatched_gap(aligned, query):
    if len(aligned) < 8:
        return []
    qidx=[p[0] for p in aligned]
    out=[]
    for a,b in zip(qidx,qidx[1:]):
        if b>a+1:
            gap=float(query[b]["time"]-query[a]["time"])
            if gap>=1.0:
                out.append({"start_seconds":round(float(query[a]["time"]),3),
                            "end_seconds":round(float(query[b]["time"]),3),
                            "gap_seconds":round(gap,3)})
    return out

def _timing_gaps(aligned, query, reference_interval):
    """Compare submitted-time gaps with reference-time gaps between consecutive
    aligned pairs. Deleted/stretched content shows up as a local deviation from
    the video's overall playback speed."""
    if len(aligned) < 4:
        return []
    ts = np.array([query[p[0]]["time"] for p in aligned], dtype=np.float64)
    js = np.array([p[1] for p in aligned], dtype=np.float64)
    dt_sub = np.diff(ts)
    dt_ref = np.diff(js) * float(reference_interval)
    ok = dt_ref > 0
    if ok.sum() < 3:
        return []
    rm = float(np.median(dt_sub[ok] / dt_ref[ok]))
    if rm <= 0:
        return []
    gaps = []
    for k in np.where(ok)[0]:
        expected = rm * dt_ref[k]
        tol = max(0.7, 0.35 * expected)
        if abs(dt_sub[k] - expected) > tol:
            gaps.append({
                "at_submitted_seconds": round(float(ts[k]), 3),
                "deviation_seconds": round(float(dt_sub[k] - expected), 3),
            })
    return gaps


# --------------------------------------------------------------------------
# Main alignment
# --------------------------------------------------------------------------
def align_video(refs, video_path, threshold=0.70, reference_interval=1.0, sample_every=0):
    started = perf_counter()
    if sample_every and sample_every > 0:
        cap_probe = cv2.VideoCapture(str(video_path))
        probe_fps = float(cap_probe.get(cv2.CAP_PROP_FPS) or 30.0)
        cap_probe.release()
        target_fps = max(0.5, probe_fps / float(sample_every))
    else:
        target_fps = 5.0
    fps, total_frames, sample_step, query = _read_candidates(video_path, target_fps)

    if not refs or not query:
        return {
            "match_detected": False,
            "classification": "NO_MATCH",
            "matched_fingerprints": 0,
            "submitted_fingerprints": len(query),
        }

    reference_indexes = [r[0]["frame_index"] for r in refs]
    ref_images = [r[1] for r in refs]
    n, m = len(query), len(refs)

    sim = np.zeros((n, m), dtype=np.float32)
    for i, q in enumerate(query):
        for j, rimg in enumerate(ref_images):
            sim[i, j] = _feature_similarity(q["image"], rimg)

    floor = max(0.54, min(0.68, threshold - 0.10))
    q_gap = 0.010
    r_gap = 0.065

    dp = np.full((n + 1, m + 1), -1e9, dtype=np.float32)
    trace = np.zeros((n + 1, m + 1), dtype=np.int8)
    dp[:, 0] = 0.0
    for j in range(1, m + 1):
        dp[0, j] = dp[0, j - 1] - r_gap

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            candidates = (
                (dp[i - 1, j] - q_gap, 2),
                (dp[i, j - 1] - r_gap, 3),
            )
            s = float(sim[i - 1, j - 1])
            if s >= floor:
                candidates = candidates + ((dp[i - 1, j - 1] + s - floor, 1),)
            best, tr = max(candidates, key=lambda x: x[0])
            dp[i, j] = best
            trace[i, j] = tr

    best_pos = np.unravel_index(int(np.argmax(dp)), dp.shape)
    i, j = best_pos
    pairs = []
    while i > 0 and j > 0:
        tr = int(trace[i, j])
        if tr == 1:
            pairs.append((i - 1, j - 1, float(sim[i - 1, j - 1])))
            i -= 1
            j -= 1
        elif tr == 2:
            i -= 1
        elif tr == 3:
            j -= 1
        else:
            break
    pairs.reverse()

    aligned = [p for p in pairs if p[2] >= floor]
    if aligned:
        runs, current = [], [aligned[0]]
        for p in aligned[1:]:
            prev = current[-1]
            if p[0] > prev[0] and p[1] > prev[1]:
                current.append(p)
            else:
                runs.append(current)
                current = [p]
        runs.append(current)
        aligned = max(runs, key=len)

    ref_seq = [p[1] for p in aligned]
    order_violations = sum(1 for a, b in zip(ref_seq, ref_seq[1:]) if b <= a)
    duplicates = sum(1 for a, b in zip(ref_seq, ref_seq[1:]) if b == a)

    unique = sorted(set(ref_seq))
    used = set(unique)
    missing = (
        [reference_indexes[k] for k in range(unique[0], unique[-1] + 1) if k not in used]
        if unique else []
    )
    span_len = (unique[-1] - unique[0] + 1) if unique else 0
    span_coverage = 100.0 * len(unique) / span_len if span_len else 0.0

    coverage = 100.0 * len(unique) / m
    strong = [p for p in aligned if p[2] >= threshold]
    strong_pct = 100.0 * len(strong) / len(aligned) if aligned else 0.0
    confidence = float(np.mean([p[2] for p in aligned])) if aligned else 0.0
    median = float(np.median([p[2] for p in aligned])) if aligned else 0.0

    # Whole-timeline compression check (large deletions)
    reference_span_seconds = max(0.0, (m - 1) * float(reference_interval))
    submitted_duration_seconds = float(total_frames) / float(fps) if fps else 0.0
    temporal_compression_ratio = (
        submitted_duration_seconds / reference_span_seconds if reference_span_seconds > 0 else 1.0
    )
    severe_temporal_gap = (
        coverage >= 95.0
        and reference_span_seconds >= 10.0
        and submitted_duration_seconds < reference_span_seconds * 0.70
    )
    estimated_missing_seconds = (
        max(0.0, reference_span_seconds - submitted_duration_seconds) if severe_temporal_gap else 0.0
    )

    # ---- Integrity analysis (only meaningful if the video matched at all) ----
    detected = (
        coverage >= 55.0 and confidence >= floor and median >= floor and order_violations == 0
    )

    continuity = {"duplicate_events": 0, "discontinuity_events": 0, "reorder_events": 0}
    timing_gaps, modified_times, internal_gaps = [], [], []
    if detected:
        continuity = _temporal_continuity(video_path, fps)
        timing_gaps = _timing_gaps(aligned, query, reference_interval)
        modified_times = _local_modification(aligned, query, ref_images)
        internal_gaps = _internal_unmatched_gap(aligned, query)

    tamper_evidence = bool(
        duplicates
        or severe_temporal_gap
        or continuity["duplicate_events"]
        or continuity["discontinuity_events"]
        or continuity["reorder_events"]
        or timing_gaps
        or modified_times
        or internal_gaps
    )

    # TRUE_MATCH: strong match, no tamper evidence, and either near-complete
    # coverage or a clean contiguous clip (trim / extracted segment).
    contiguous_clip = coverage >= 55.0 and span_coverage >= 85.0
    full = (
        detected
        and not tamper_evidence
        and (coverage >= 93.0 or contiguous_clip)
        and confidence >= 0.68
        and median >= 0.66
    )

    classification = "PARTIAL_MATCH_OR_MODIFIED" if (detected and tamper_evidence) else ("TRUE_MATCH" if full else (
        "PARTIAL_MATCH_OR_MODIFIED" if detected else "NO_MATCH"))

    # ---- Output rows ----
    by_q = {p[0]: p for p in aligned}
    rows = []
    for qi, q in enumerate(query):
        p = by_q.get(qi)
        if p is None:
            rows.append({
                "submitted_frame": q["frame_no"],
                "submitted_time": round(q["time"], 4),
                "reference_frame": None,
                "similarity": round(float(np.max(sim[qi])), 4),
                "matched": False,
            })
        else:
            _, ri, score = p
            rows.append({
                "submitted_frame": q["frame_no"],
                "submitted_time": round(q["time"], 4),
                "reference_frame": reference_indexes[ri],
                "similarity": round(score, 4),
                "matched": bool(score >= threshold),
                "aligned": True,
            })

    matched_rows = [r for r in rows if r.get("reference_frame") is not None]
    first_match = min(matched_rows, key=lambda x: x["submitted_frame"]) if matched_rows else None
    last_match = max(matched_rows, key=lambda x: x["submitted_frame"]) if matched_rows else None
    segment = None
    if first_match and last_match:
        segment = {
            "submitted_start_seconds": first_match["submitted_time"],
            "submitted_end_seconds": last_match["submitted_time"],
            "reference_start_frame": first_match["reference_frame"],
            "reference_end_frame": last_match["reference_frame"],
        }

    anomalies = []
    if order_violations:
        anomalies.append(f"{order_violations} reference-order violation(s)")
    if duplicates:
        anomalies.append(f"{duplicates} duplicated reference-frame match(es)")
    if missing and (tamper_evidence or span_coverage < 85.0):
        anomalies.append(f"{len(missing)} missing reference frame(s) inside matched span")
    if severe_temporal_gap:
        anomalies.append(
            "temporal span is abnormally compressed; "
            f"estimated missing/deleted content ~{estimated_missing_seconds:.2f}s"
        )
    if continuity["duplicate_events"]:
        anomalies.append(
            f"{continuity['duplicate_events']} duplicated-frame run(s) near t="
            f"{continuity.get('duplicate_times', [])[:5]}s"
        )
    if continuity["discontinuity_events"]:
        anomalies.append(
            f"{continuity['discontinuity_events']} temporal discontinuity(ies) "
            f"(possible deleted frames) near t={continuity.get('discontinuity_times', [])[:5]}s"
        )
    if continuity["reorder_events"]:
        anomalies.append(
            f"{continuity['reorder_events']} out-of-order frame event(s) near t="
            f"{continuity.get('reorder_times', [])[:5]}s"
        )
    if timing_gaps:
        anomalies.append(f"{len(timing_gaps)} timeline gap/stretch(es) vs. reference timing")
    if internal_gaps:
        anomalies.append(f"{len(internal_gaps)} internal unmatched section(s) between matched regions")
    if modified_times:
        anomalies.append(
            f"{len(modified_times)} aligned frame(s) locally inconsistent with reference "
            f"(possible content modification) near t={modified_times[:5]}s"
        )
    if coverage < 95 and not (contiguous_clip and not tamper_evidence):
        anomalies.append("unmatched submitted/reference section(s)")
    if strong_pct < 50 and aligned:
        anomalies.append("many aligned frames are below the requested per-frame threshold")

    return {
        "match_detected": detected,
        "classification": classification,
        "matched_segment": segment,
        "confidence_score": round(confidence, 4),
        "median_similarity": round(median, 4),
        "alignment_coverage_percentage": round(coverage, 2),
        "span_coverage_percentage": round(span_coverage, 2),
        "strong_threshold_percentage": round(strong_pct, 2),
        "match_percentage": round(coverage, 2),
        "matched_fingerprints": len(unique),
        "submitted_fingerprints": len(query),
        "reference_frames": m,
        "missing_reference_frames": missing[:100],
        "anomalies": anomalies,
        "processing_time_seconds": round(perf_counter() - started, 4),
        "video_fps": fps,
        "video_frame_count": total_frames,
        "video_duration_seconds": round(total_frames / fps, 3) if fps else 0.0,
        "reference_sampling_interval_seconds": round(reference_interval, 4),
        "effective_sample_every": sample_step,
        "temporal_order_violations": order_violations,
        "temporal_compression_ratio": round(temporal_compression_ratio, 4),
        "estimated_missing_seconds": round(estimated_missing_seconds, 4),
        "duplicate_reference_matches": duplicates,
        "integrity": {
            "tamper_evidence": tamper_evidence,
            "continuity": continuity,
            "timing_gaps": timing_gaps[:20],
            "internal_unmatched_gaps": internal_gaps[:20],
            "locally_modified_times": modified_times[:20],
        },
        "frames": rows,
    }