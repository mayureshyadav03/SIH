"""
Reading and validating the local MODIS Aqua raster (Phase 3, steps 1-2).

Downloading and NASA authentication are Phase 2 concerns and are NOT
implemented here - this module only opens a raster that already exists
on local disk.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from .config import InputError, ValidationError


@dataclass
class RasterInfo:
    """Lightweight handle bundling an open dataset with its key facts."""

    path: str
    dataset: Any  # rasterio.io.DatasetReader
    width: int
    height: int
    count: int
    crs: Any
    transform: Any
    dtypes: List[str]
    nodata: Any
    tags: Dict[str, str] = field(default_factory=dict)


def read_raster(path: str) -> RasterInfo:
    """
    Open the MODIS raster with Rasterio (GDAL-backed) and read its core
    dimensions, band count, CRS and metadata.

    Raises:
        InputError: if the file does not exist or cannot be opened.
    """
    if not os.path.isfile(path):
        raise InputError(f"MODIS raster not found: {path}")

    try:
        dataset = rasterio.open(path)
    except rasterio.errors.RasterioIOError as exc:
        raise InputError(f"Unable to open raster '{path}': {exc}") from exc

    try:
        info = RasterInfo(
            path=path,
            dataset=dataset,
            width=dataset.width,
            height=dataset.height,
            count=dataset.count,
            crs=dataset.crs,
            transform=dataset.transform,
            dtypes=list(dataset.dtypes),
            nodata=dataset.nodata,
            tags=dataset.tags(),
        )
    except Exception as exc:  # narrow: any read failure means an invalid raster
        dataset.close()
        raise InputError(f"Unable to read raster metadata from '{path}': {exc}") from exc

    return info


def validate_raster(info: RasterInfo) -> None:
    """
    Verify the raster was opened correctly and carries the minimum
    information Phase 3 needs to proceed.

    Raises:
        ValidationError: if any required piece of information is missing.
    """
    if info.dataset is None or info.dataset.closed:
        raise ValidationError(f"Raster '{info.path}' is not open/readable.")

    if info.count < 1:
        raise ValidationError(f"Raster '{info.path}' contains no bands.")

    if info.width <= 0 or info.height <= 0:
        raise ValidationError(f"Raster '{info.path}' has invalid dimensions.")

    if info.crs is None:
        raise ValidationError(
            f"Raster '{info.path}' has no CRS/spatial reference - cannot be "
            f"cropped or reprojected."
        )

    if info.transform is None or info.transform.is_identity:
        raise ValidationError(
            f"Raster '{info.path}' has no valid geotransform."
        )


def to_memory_dataset(
    array: np.ndarray,
    transform: Any,
    crs: Any,
    dtype: str,
    nodata: Optional[float] = None,
    tags: Optional[Dict[str, str]] = None,
) -> RasterInfo:
    """
    Wrap an in-memory array (produced by crop/reproject/resample) as an
    open rasterio dataset so downstream steps can keep working with a
    single, consistent RasterInfo interface.

    The backing MemoryFile is kept alive on the returned RasterInfo via
    the `_memfile` attribute so it isn't garbage-collected; call
    `close_raster()` when done with it.
    """
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    count, height, width = array.shape

    memfile = MemoryFile()
    with memfile.open(
        driver="GTiff",
        height=height,
        width=width,
        count=count,
        dtype=dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(array)
        if tags:
            dst.update_tags(**tags)

    dataset = memfile.open()
    info = RasterInfo(
        path="<in-memory>",
        dataset=dataset,
        width=dataset.width,
        height=dataset.height,
        count=dataset.count,
        crs=dataset.crs,
        transform=dataset.transform,
        dtypes=list(dataset.dtypes),
        nodata=dataset.nodata,
        tags=dataset.tags(),
    )
    info._memfile = memfile  # type: ignore[attr-defined]
    return info


def close_raster(info: RasterInfo) -> None:
    """Close a RasterInfo's dataset and, if present, its backing MemoryFile."""
    try:
        if info.dataset is not None and not info.dataset.closed:
            info.dataset.close()
    finally:
        memfile = getattr(info, "_memfile", None)
        if memfile is not None:
            memfile.close()
