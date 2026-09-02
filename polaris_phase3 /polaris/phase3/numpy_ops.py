"""
NumPy-based array processing for Phase 3 - Satellite Data Processing
(step 8).

Limited to Phase 3 data preparation: nodata masking and normalization of
the extracted band array. No detection, segmentation or feature
engineering happens here - that is Phase 4/5.
"""

from typing import Optional

import numpy as np


def process_with_numpy(
    band_array: np.ndarray,
    nodata: Optional[float] = None,
) -> np.ndarray:
    """
    Apply required pixel/array-level preparation:
      - mask nodata pixels
      - normalize each band independently to the [0, 1] float32 range

    Args:
        band_array: Array of shape (bands, height, width).
        nodata: Nodata value to exclude from normalization, if any.

    Returns:
        A float32 array of the same shape, normalized per band.
    """
    if band_array.size == 0:
        raise ValueError("Cannot process an empty band array.")

    array = band_array.astype(np.float32)

    if nodata is not None:
        valid_mask = array != nodata
    else:
        valid_mask = np.isfinite(array)

    normalized = np.zeros_like(array, dtype=np.float32)

    for band_idx in range(array.shape[0]):
        band = array[band_idx]
        mask = valid_mask[band_idx]

        if not np.any(mask):
            # Entire band is nodata; leave as zeros.
            continue

        band_min = band[mask].min()
        band_max = band[mask].max()

        if band_max > band_min:
            normalized[band_idx][mask] = (band[mask] - band_min) / (band_max - band_min)
        else:
            # Constant-valued band: avoid divide-by-zero, keep as zeros.
            normalized[band_idx][mask] = 0.0

        if nodata is not None:
            normalized[band_idx][~mask] = nodata

    return normalized
