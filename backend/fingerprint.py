"""Perceptual fingerprinting helpers for robust video matching.

SHA-256 remains the authoritative byte-level integrity mechanism.  This module
adds a transformation-tolerant visual fingerprint used only to locate the
corresponding video segment.
"""
from __future__ import annotations

import cv2
import numpy as np


def phash(image: np.ndarray, hash_size: int = 8, highfreq_factor: int = 4) -> np.ndarray:
    """Return a binary perceptual hash using a DCT, as a 64-bit vector."""
    if image is None or image.size == 0:
        raise ValueError("empty image")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    size = hash_size * highfreq_factor
    gray = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)
    dct = cv2.dct(gray)
    low = dct[:hash_size, :hash_size]
    values = low.flatten()
    median = np.median(values[1:])
    return (values > median).astype(np.uint8)


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    return int(np.count_nonzero(a != b))


def phash_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return 1.0 - hamming(a, b) / float(len(a))


def orb_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Approximate local-feature similarity, useful for moderate crops/overlays."""
    try:
        orb = cv2.ORB_create(nfeatures=600)
        ka, da = orb.detectAndCompute(a, None)
        kb, db = orb.detectAndCompute(b, None)
        if da is None or db is None or len(ka) < 8 or len(kb) < 8:
            return 0.0
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = matcher.match(da, db)
        if not matches:
            return 0.0
        good = [m for m in matches if m.distance <= 55]
        return min(1.0, len(good) / max(12.0, min(len(ka), len(kb)) * 0.25))
    except cv2.error:
        return 0.0


def combined_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Combine global perceptual similarity and local-feature evidence."""
    p = phash_similarity(phash(a), phash(b))
    o = orb_similarity(a, b)
    return 0.80 * p + 0.20 * o
