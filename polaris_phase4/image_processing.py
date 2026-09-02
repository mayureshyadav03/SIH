"""
image_processing.py
--------------------
Phase 4 — Iceberg & Sea-Ice Detection
Sub-steps implemented here (per SRD Section 7 / Roadmap Phase 4):
    - Image Enhancement (OpenCV / NumPy)
    - Noise Reduction (OpenCV)
    - Image Segmentation (thresholding)
    - Boundary Extraction (OpenCV contours)

This module performs classic computer-vision processing only. It does not
perform AI/ML detection (see ai_detection.py) and does not perform
trajectory prediction, risk assessment, or navigation logic.

Input convention:
    All functions expect a single-band (grayscale) processed MODIS image
    as a 2D NumPy array. Phase 3 is responsible for producing this
    cropped / reprojected / band-extracted array.
"""

from __future__ import annotations

import numpy as np
import cv2


def _validate_grayscale_image(image: np.ndarray) -> np.ndarray:
    """
    Validate that the input is usable as a single-band image and
    return an 8-bit normalized copy suitable for OpenCV processing.

    Raises:
        TypeError: if input is not a NumPy array.
        ValueError: if input is empty, not 2D, or contains no valid data.
    """
    if not isinstance(image, np.ndarray):
        raise TypeError("Expected a NumPy ndarray as input image.")

    if image.ndim != 2:
        raise ValueError(
            f"Expected a single-band (2D) image, got array with shape {image.shape}."
        )

    if image.size == 0:
        raise ValueError("Input image is empty.")

    if not np.isfinite(image).any():
        raise ValueError("Input image contains no finite pixel values.")

    # Replace non-finite values (e.g. NaN from masked satellite pixels) with 0
    clean = np.nan_to_num(image, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float64)

    # Normalize to 0-255 8-bit range for OpenCV compatibility.
    min_val, max_val = clean.min(), clean.max()
    if max_val - min_val < 1e-9:
        # Flat image (no variation) — return as mid-gray to avoid divide-by-zero.
        return np.full(clean.shape, 128, dtype=np.uint8)

    normalized = (clean - min_val) / (max_val - min_val) * 255.0
    return normalized.astype(np.uint8)


def enhance_image(image: np.ndarray) -> np.ndarray:
    """
    Enhance contrast of processed MODIS imagery to make ice/sea-ice
    regions more distinguishable from open water.

    Uses CLAHE (Contrast Limited Adaptive Histogram Equalization), which
    is well suited to satellite imagery with uneven illumination/reflectance.

    Args:
        image: 2D NumPy array (single-band processed MODIS image).

    Returns:
        8-bit contrast-enhanced image (2D NumPy array).
    """
    img8 = _validate_grayscale_image(image)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(img8)
    return enhanced


def reduce_noise(image: np.ndarray) -> np.ndarray:
    """
    Apply noise reduction to enhanced imagery while preserving ice-edge
    detail (important for later boundary extraction).

    Uses a bilateral filter, which smooths noise but preserves edges
    better than a simple Gaussian/median blur.

    Args:
        image: 8-bit 2D NumPy array (typically output of enhance_image).

    Returns:
        8-bit denoised image (2D NumPy array).
    """
    img8 = _validate_grayscale_image(image)
    denoised = cv2.bilateralFilter(img8, d=7, sigmaColor=50, sigmaSpace=50)
    return denoised


def segment_image(image: np.ndarray) -> np.ndarray:
    """
    Segment the denoised image into candidate ice / non-ice regions
    using Otsu's automatic thresholding, followed by a light morphological
    cleanup to remove speckle noise and close small gaps.

    Args:
        image: 8-bit 2D NumPy array (typically output of reduce_noise).

    Returns:
        Binary mask (2D NumPy array, dtype=uint8, values {0, 255}) where
        255 marks candidate ice/iceberg pixels.
    """
    img8 = _validate_grayscale_image(image)

    # Otsu's method automatically selects a threshold; ice/snow typically
    # has high reflectance relative to open water in MODIS visible/NIR bands.
    _, mask = cv2.threshold(img8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Morphological cleanup: remove small noise specks, close small holes.
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    return mask


def detect_ice_regions_cv(mask: np.ndarray, min_area_px: int = 15) -> np.ndarray:
    """
    Computer-vision-based ice/iceberg region identification.

    Filters the segmented binary mask to remove regions smaller than a
    minimum pixel-area threshold (removes noise/artifacts that are too
    small to plausibly be sea-ice or an iceberg at MODIS resolution).

    Args:
        mask: Binary mask (output of segment_image).
        min_area_px: Minimum contour area (in pixels) to keep as a valid
            ice/iceberg region.

    Returns:
        Cleaned binary mask (2D NumPy array, dtype=uint8, values {0, 255}).
    """
    if mask is None or mask.size == 0:
        raise ValueError("Input mask is empty.")

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cleaned = np.zeros_like(mask)

    for cnt in contours:
        if cv2.contourArea(cnt) >= min_area_px:
            cv2.drawContours(cleaned, [cnt], -1, 255, thickness=cv2.FILLED)

    return cleaned


def extract_boundaries(mask: np.ndarray, min_area_px: int = 15) -> list:
    """
    Extract iceberg/sea-ice region boundaries (contours) from a binary mask.

    Args:
        mask: Binary mask (2D NumPy array, values {0, 255}).
        min_area_px: Minimum contour area (in pixels) to be considered a
            valid detected region.

    Returns:
        List of boundaries. Each boundary is a NumPy array of shape (N, 2)
        with (row, col) pixel coordinates outlining one detected region,
        ordered from largest to smallest area.
    """
    if mask is None or mask.size == 0:
        raise ValueError("Input mask is empty.")

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boundaries = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area_px:
            continue
        # cv2 contours are (x, y) i.e. (col, row); convert to (row, col)
        pts = cnt.reshape(-1, 2)
        row_col_pts = np.stack([pts[:, 1], pts[:, 0]], axis=1)
        boundaries.append(row_col_pts)

    boundaries.sort(key=lambda b: cv2.contourArea(b[:, ::-1].astype(np.int32)), reverse=True)
    return boundaries
