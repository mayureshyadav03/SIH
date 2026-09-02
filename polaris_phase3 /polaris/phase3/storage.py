"""
Saving the clean processed Antarctic dataset to D2 - Processed Data
Storage (Phase 3, steps 9-10).

Only the processed (cropped/reprojected/resampled) bands and their
metadata are persisted - not the raw satellite imagery - per the SRD's
storage-efficiency requirement (section 11).
"""

import json
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np
import rasterio

from .config import OutputError


def save_processed_dataset(
    processed_array: np.ndarray,
    transform: Any,
    crs: Any,
    metadata: Dict[str, Any],
    output_dir: str,
    dataset_name: str,
    nodata: Optional[float] = None,
) -> Tuple[str, str]:
    """
    Write the processed raster (GeoTIFF) and its metadata (JSON) into
    D2 - Processed Data Storage.

    Returns:
        (raster_output_path, metadata_output_path)

    Raises:
        OutputError: if writing either file fails.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"Could not create output directory '{output_dir}': {exc}") from exc

    raster_path = os.path.join(output_dir, f"{dataset_name}_processed.tif")
    metadata_path = os.path.join(output_dir, f"{dataset_name}_metadata.json")

    count, height, width = processed_array.shape

    try:
        with rasterio.open(
            raster_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=count,
            dtype=str(processed_array.dtype),
            crs=crs,
            transform=transform,
            nodata=nodata,
            compress="deflate",
        ) as dst:
            dst.write(processed_array)
    except Exception as exc:
        raise OutputError(f"Failed to write processed raster to '{raster_path}': {exc}") from exc

    try:
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2, default=str)
    except OSError as exc:
        raise OutputError(f"Failed to write metadata to '{metadata_path}': {exc}") from exc

    return raster_path, metadata_path
