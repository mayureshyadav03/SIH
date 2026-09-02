"""
detection.py
------------
Phase 4 — Iceberg & Sea-Ice Detection (main pipeline)

Implements the full Phase 4 workflow from the Roadmap/SRD:

    Processed MODIS Image
        -> Image Enhancement
        -> Noise Reduction
        -> Image Segmentation
        -> Computer-Vision Ice Detection
        -> AI/ML Detection Model
        -> Detection Evaluation
        -> Iceberg/Sea-Ice Regions
        -> Boundary Extraction
        -> Position Extraction
        -> Phase 4 Detection Output  (consumed by Phase 5 Feature Extraction)

This module is intentionally limited to detection. It does not implement
trajectory prediction, risk assessment, or navigation decision logic
(Phases 5+ in the Roadmap).

Input contract (from Phase 3 — Satellite Data Processing):
    A `ProcessedMODISData` object providing:
        - image: 2D NumPy array (single-band, cropped/reprojected Antarctic
          MODIS imagery, as produced by Phase 3 using GDAL/Rasterio).
        - geotransform: 6-tuple (origin_x, pixel_width, rotation_x,
          origin_y, rotation_y, pixel_height), in the standard GDAL
          geotransform convention, used to convert pixel (row, col)
          coordinates to geographic (lat, lon).
        - timestamp: optional observation timestamp (passed through only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import numpy as np

from image_processing import (
    enhance_image,
    reduce_noise,
    segment_image,
    detect_ice_regions_cv,
    extract_boundaries,
)
from ai_detection import IceDetectionModel, evaluate_detection


# ---------------------------------------------------------------------------
# 1. INPUT
# ---------------------------------------------------------------------------

@dataclass
class ProcessedMODISData:
    """
    Represents the output of Phase 3 (Satellite Data Processing) that
    Phase 4 consumes as input.

    Attributes:
        image: 2D NumPy array, single-band processed MODIS imagery.
        geotransform: 6-tuple GDAL-style geotransform
            (origin_x, pixel_width, rotation_x, origin_y, rotation_y, pixel_height)
            used to map pixel coordinates to (lon, lat).
        timestamp: Optional ISO-format observation timestamp, passed through
            to the output for use by later phases. Not used for detection.
    """
    image: np.ndarray
    geotransform: tuple
    timestamp: Optional[str] = None

    def validate(self) -> None:
        if not isinstance(self.image, np.ndarray):
            raise TypeError("ProcessedMODISData.image must be a NumPy ndarray.")
        if self.image.ndim != 2:
            raise ValueError(
                f"ProcessedMODISData.image must be single-band (2D), got shape {self.image.shape}."
            )
        if self.image.size == 0:
            raise ValueError("ProcessedMODISData.image is empty.")
        if not isinstance(self.geotransform, (tuple, list)) or len(self.geotransform) != 6:
            raise ValueError(
                "ProcessedMODISData.geotransform must be a 6-element tuple "
                "(origin_x, pixel_width, rotation_x, origin_y, rotation_y, pixel_height)."
            )


def load_processed_modis_data(
    image: np.ndarray,
    geotransform: tuple,
    timestamp: Optional[str] = None,
) -> ProcessedMODISData:
    """
    Load and validate Phase 3 output for use by the Phase 4 pipeline.

    Args:
        image: 2D NumPy array, single-band processed MODIS image.
        geotransform: 6-tuple GDAL-style geotransform.
        timestamp: Optional observation timestamp string.

    Returns:
        Validated ProcessedMODISData instance.
    """
    data = ProcessedMODISData(image=image, geotransform=tuple(geotransform), timestamp=timestamp)
    data.validate()
    return data


# ---------------------------------------------------------------------------
# 9. POSITION EXTRACTION
# ---------------------------------------------------------------------------

def pixel_to_geo(row: float, col: float, geotransform: tuple) -> tuple:
    """
    Convert a pixel (row, col) coordinate to geographic (lat, lon) using
    the standard GDAL geotransform convention:

        lon = origin_x + col * pixel_width  + row * rotation_x
        lat = origin_y + col * rotation_y   + row * pixel_height

    Args:
        row: Pixel row (y).
        col: Pixel column (x).
        geotransform: 6-tuple (origin_x, pixel_width, rotation_x,
            origin_y, rotation_y, pixel_height).

    Returns:
        (latitude, longitude) tuple.
    """
    origin_x, pixel_width, rotation_x, origin_y, rotation_y, pixel_height = geotransform
    lon = origin_x + col * pixel_width + row * rotation_x
    lat = origin_y + col * rotation_y + row * pixel_height
    return lat, lon


def extract_positions(boundaries: List[np.ndarray], geotransform: tuple) -> List[Dict[str, float]]:
    """
    Extract a representative (lat, lon) position for each detected
    iceberg/sea-ice region boundary, using the region's pixel centroid.

    Args:
        boundaries: List of (row, col) boundary point arrays, as returned
            by image_processing.extract_boundaries.
        geotransform: 6-tuple GDAL-style geotransform from Phase 3.

    Returns:
        List of dicts, one per region:
            {"latitude": float, "longitude": float,
             "centroid_row": float, "centroid_col": float}
    """
    positions = []
    for boundary in boundaries:
        centroid_row = float(np.mean(boundary[:, 0]))
        centroid_col = float(np.mean(boundary[:, 1]))
        lat, lon = pixel_to_geo(centroid_row, centroid_col, geotransform)
        positions.append(
            {
                "latitude": lat,
                "longitude": lon,
                "centroid_row": centroid_row,
                "centroid_col": centroid_col,
            }
        )
    return positions


# ---------------------------------------------------------------------------
# 10. OUTPUT
# ---------------------------------------------------------------------------

@dataclass
class Phase4DetectionOutput:
    """
    Final Phase 4 output, ready to be consumed by Phase 5 (Feature Extraction).

    Attributes:
        timestamp: Observation timestamp passed through from Phase 3 input.
        detection_mask: Final binary mask (2D NumPy array, {0, 255}) marking
            detected sea-ice/iceberg pixels.
        boundaries: List of (row, col) boundary point arrays, one per
            detected region.
        positions: List of dicts with latitude/longitude per detected region
            (same order as `boundaries`).
        model_confidence: AI/ML model confidence score for this detection run.
        evaluation: Optional dict of detection evaluation metrics (only
            populated when ground-truth data is supplied).
    """
    timestamp: Optional[str]
    detection_mask: np.ndarray
    boundaries: List[np.ndarray]
    positions: List[Dict[str, float]]
    model_confidence: float
    evaluation: Optional[Dict[str, float]] = field(default=None)

    def region_count(self) -> int:
        return len(self.boundaries)

    def summary(self) -> Dict[str, Any]:
        """Compact, Phase-5-friendly summary of this detection output."""
        return {
            "timestamp": self.timestamp,
            "num_regions_detected": self.region_count(),
            "model_confidence": self.model_confidence,
            "positions": self.positions,
            "evaluation": self.evaluation,
        }


# ---------------------------------------------------------------------------
# PIPELINE ORCHESTRATION
# ---------------------------------------------------------------------------

def run_phase4_pipeline(
    processed_data: ProcessedMODISData,
    min_area_px: int = 15,
    ground_truth_mask: Optional[np.ndarray] = None,
) -> Phase4DetectionOutput:
    """
    Run the full Phase 4 iceberg & sea-ice detection pipeline on a single
    processed MODIS observation.

    Steps:
        1. Validate input.
        2. Enhance image (CLAHE).
        3. Reduce noise (bilateral filter).
        4. Segment image (Otsu thresholding + morphology).
        5. Computer-vision ice-region filtering.
        6. AI/ML detection model (KMeans-based pixel classification).
        7. Combine CV + AI/ML masks into a final detection mask.
        8. Evaluate detection (only if ground truth is provided).
        9. Extract boundaries (contours).
        10. Extract lat/lon positions for each detected region.

    Args:
        processed_data: Validated ProcessedMODISData (Phase 3 output).
        min_area_px: Minimum region size (pixels) to keep as valid detection.
        ground_truth_mask: Optional binary mask for evaluation purposes only.

    Returns:
        Phase4DetectionOutput ready for Phase 5 Feature Extraction.
    """
    processed_data.validate()
    image = processed_data.image

    # Image Enhancement
    enhanced = enhance_image(image)

    # Noise Reduction
    denoised = reduce_noise(enhanced)

    # Image Segmentation
    segmented_mask = segment_image(denoised)

    # Computer-Vision Ice Detection (region-size filtering)
    cv_mask = detect_ice_regions_cv(segmented_mask, min_area_px=min_area_px)

    # AI/ML Detection Model
    model = IceDetectionModel()
    ai_result = model.fit_predict(denoised)

    # Combine CV-filtered mask and AI/ML mask (logical AND) for a more
    # robust final detection than either method alone.
    combined_mask = cv2_and(cv_mask, ai_result.mask)
    final_mask = detect_ice_regions_cv(combined_mask, min_area_px=min_area_px)

    # Detection Evaluation (only if ground truth supplied)
    evaluation = None
    if ground_truth_mask is not None:
        evaluation = evaluate_detection(final_mask, ground_truth_mask)

    # Boundary Extraction
    boundaries = extract_boundaries(final_mask, min_area_px=min_area_px)

    # Position Extraction
    positions = extract_positions(boundaries, processed_data.geotransform)

    return Phase4DetectionOutput(
        timestamp=processed_data.timestamp,
        detection_mask=final_mask,
        boundaries=boundaries,
        positions=positions,
        model_confidence=ai_result.model_confidence,
        evaluation=evaluation,
    )


def cv2_and(mask_a: np.ndarray, mask_b: np.ndarray) -> np.ndarray:
    """Small helper to combine two binary masks with logical AND."""
    import cv2
    return cv2.bitwise_and(mask_a, mask_b)


# ---------------------------------------------------------------------------
# SYNTHETIC TEST DATA (clearly separated from the real processing pipeline)
# ---------------------------------------------------------------------------

def create_synthetic_test_image(size: int = 128, seed: int = 0) -> ProcessedMODISData:
    """
    Create a MINIMAL SYNTHETIC test image for exercising the pipeline
    when no real Phase 3 MODIS output is available.

    THIS IS NOT REAL SATELLITE DATA. It is a simple synthetic array with
    a bright circular "iceberg" region on a darker "ocean" background,
    used only to demonstrate that the pipeline runs end-to-end.

    Args:
        size: Width/height of the synthetic square image, in pixels.
        seed: Random seed for reproducible synthetic noise.

    Returns:
        ProcessedMODISData wrapping the synthetic image and a placeholder
        geotransform anchored near the Antarctic coast.
    """
    rng = np.random.default_rng(seed)

    # Dark "ocean" background with mild sensor noise.
    image = rng.normal(loc=60, scale=5, size=(size, size))

    # Bright "iceberg" region (circular blob).
    yy, xx = np.meshgrid(np.arange(size), np.arange(size), indexing="ij")
    center_r, center_c, radius = size * 0.35, size * 0.6, size * 0.12
    iceberg_mask = (yy - center_r) ** 2 + (xx - center_c) ** 2 <= radius ** 2
    image[iceberg_mask] = rng.normal(loc=220, scale=8, size=int(iceberg_mask.sum()))

    # Second smaller ice floe.
    center_r2, center_c2, radius2 = size * 0.7, size * 0.25, size * 0.06
    floe_mask = (yy - center_r2) ** 2 + (xx - center_c2) ** 2 <= radius2 ** 2
    image[floe_mask] = rng.normal(loc=200, scale=8, size=int(floe_mask.sum()))

    image = np.clip(image, 0, 255)

    # Placeholder geotransform: roughly anchored off the Antarctic coast,
    # ~500 m pixel size (0.005 deg approx), for demonstration only.
    placeholder_geotransform = (-60.0, 0.005, 0.0, -65.0, 0.0, -0.005)

    return load_processed_modis_data(
        image=image,
        geotransform=placeholder_geotransform,
        timestamp="synthetic-test-observation",
    )


# ---------------------------------------------------------------------------
# DEMO ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("PHASE 4 — Iceberg & Sea-Ice Detection")
    print("Running on MINIMAL SYNTHETIC TEST DATA (not real MODIS imagery).")
    print("=" * 70)

    test_data = create_synthetic_test_image()
    output = run_phase4_pipeline(test_data)

    print(f"Timestamp:            {output.timestamp}")
    print(f"Regions detected:     {output.region_count()}")
    print(f"Model confidence:     {output.model_confidence:.3f}")
    print("Detected positions (lat, lon):")
    for i, pos in enumerate(output.positions, start=1):
        print(f"  Region {i}: lat={pos['latitude']:.5f}, lon={pos['longitude']:.5f}")

    print()
    print("Phase 4 output summary (ready for Phase 5 Feature Extraction):")
    print(output.summary())
