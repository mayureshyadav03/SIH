"""
Configuration objects and error types for Phase 3 - Satellite Data Processing.
"""

from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


class Phase3Error(Exception):
    """Base error for all Phase 3 processing failures."""


class InputError(Phase3Error):
    """Missing input file, unreadable raster, or invalid raster."""


class ValidationError(Phase3Error):
    """Raster failed validation (missing CRS, bands, or metadata)."""


class RegionError(Phase3Error):
    """Invalid or non-overlapping Antarctic bounding box."""


class BandSelectionError(Phase3Error):
    """Requested band selection is invalid for this raster."""


class GeoprocessingError(Phase3Error):
    """Reprojection or resampling failed."""


class OutputError(Phase3Error):
    """Writing the processed dataset failed."""


@dataclass
class Phase3Config:
    """
    Input configuration for a single Phase 3 run.

    Attributes:
        input_path: Path to the already-downloaded, validated MODIS Aqua
            raster on local disk (Phase 2 output).
        bbox: Antarctic geographic bounding box as
            (min_lon, min_lat, max_lon, max_lat) in EPSG:4326.
        bands: 1-based band indices to keep. If None, all bands are kept.
        target_crs: Optional target CRS (e.g. "EPSG:3031" - Antarctic Polar
            Stereographic). If None or equal to the source CRS, no
            reprojection is performed.
        target_resolution: Optional (x_res, y_res) in target CRS units.
            If None, no resampling is performed.
        output_dir: D2 - Processed Data Storage directory.
        dataset_name: Base name used for the output files. Defaults to the
            input file's stem if not provided.
    """

    input_path: str
    bbox: Tuple[float, float, float, float]
    bands: Optional[Sequence[int]] = None
    target_crs: Optional[str] = None
    target_resolution: Optional[Tuple[float, float]] = None
    output_dir: str = "data/processed"
    dataset_name: Optional[str] = None
    nodata: Optional[float] = field(default=None)
