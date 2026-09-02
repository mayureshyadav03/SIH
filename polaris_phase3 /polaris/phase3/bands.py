"""
Band extraction for Phase 3 - Satellite Data Processing (step 6).

Only the bands actually required downstream are read out; selection is
fully configurable via Phase3Config.bands.
"""

from typing import Optional, Sequence

import numpy as np

from .config import BandSelectionError
from .raster_io import RasterInfo


def extract_bands(info: RasterInfo, bands: Optional[Sequence[int]] = None) -> np.ndarray:
    """
    Read the requested (1-based) band indices from the raster.

    Args:
        info: Raster to read from.
        bands: 1-based band indices to keep. If None, all bands are read.

    Returns:
        A numpy array of shape (num_bands, height, width).

    Raises:
        BandSelectionError: if any requested band index is out of range.
    """
    if bands is None:
        indexes = list(range(1, info.count + 1))
    else:
        indexes = list(bands)
        invalid = [b for b in indexes if b < 1 or b > info.count]
        if invalid:
            raise BandSelectionError(
                f"Requested band(s) {invalid} are invalid for a raster with "
                f"{info.count} band(s)."
            )
        if not indexes:
            raise BandSelectionError("Band selection must not be empty.")

    return info.dataset.read(indexes)
