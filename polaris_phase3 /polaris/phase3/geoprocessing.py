"""
Spatial operations for Phase 3 - Satellite Data Processing:
crop to the Antarctic region, reproject if required, resample if required.

Built on Rasterio (GDAL-backed). Reprojection/resampling are only performed
when actually needed, per the SRD's performance/storage-efficiency
requirements.
"""

from typing import Optional, Tuple

import numpy as np
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.mask import mask as rio_mask
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from shapely.geometry import box, mapping

from .config import GeoprocessingError, RegionError
from .raster_io import RasterInfo, to_memory_dataset


def crop_to_antarctica(
    info: RasterInfo,
    bbox: Tuple[float, float, float, float],
) -> RasterInfo:
    """
    Crop the raster to the given Antarctic geographic bounding box.

    Args:
        info: Open raster (as returned by read_raster / validate_raster).
        bbox: (min_lon, min_lat, max_lon, max_lat) in EPSG:4326.

    Returns:
        A new RasterInfo backed by the cropped, in-memory raster.

    Raises:
        RegionError: if the bbox is malformed or does not overlap the raster.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    if min_lon >= max_lon or min_lat >= max_lat:
        raise RegionError(f"Invalid Antarctic bounding box: {bbox}")

    try:
        region_bounds = transform_bounds("EPSG:4326", info.crs, *bbox)
        geom = [mapping(box(*region_bounds))]
        out_array, out_transform = rio_mask(
            info.dataset, geom, crop=True, all_touched=True
        )
    except ValueError as exc:
        # rasterio.mask raises ValueError when the shapes don't overlap the raster
        raise RegionError(
            f"Antarctic bounding box {bbox} does not overlap raster '{info.path}'."
        ) from exc
    except Exception as exc:
        raise RegionError(f"Failed to crop raster to region {bbox}: {exc}") from exc

    return to_memory_dataset(
        out_array,
        out_transform,
        info.crs,
        dtype=str(out_array.dtype),
        nodata=info.nodata,
        tags=info.tags,
    )


def reproject_raster(
    info: RasterInfo,
    target_crs: Optional[str],
    resampling: Resampling = Resampling.nearest,
) -> RasterInfo:
    """
    Reproject the raster to `target_crs`, only if it differs from the
    raster's current CRS. If `target_crs` is None or already matches,
    the input is returned unchanged.
    """
    if not target_crs:
        return info

    dst_crs = CRS.from_string(target_crs)
    if info.crs == dst_crs:
        return info

    try:
        transform, width, height = calculate_default_transform(
            info.crs, dst_crs, info.width, info.height, *info.dataset.bounds
        )
        dst_array = np.zeros((info.count, height, width), dtype=info.dataset.dtypes[0])

        for band_idx in range(1, info.count + 1):
            reproject(
                source=info.dataset.read(band_idx),
                destination=dst_array[band_idx - 1],
                src_transform=info.transform,
                src_crs=info.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=resampling,
            )
    except Exception as exc:
        raise GeoprocessingError(f"Reprojection to {target_crs} failed: {exc}") from exc

    return to_memory_dataset(
        dst_array,
        transform,
        dst_crs,
        dtype=str(dst_array.dtype),
        nodata=info.nodata,
        tags=info.tags,
    )


def resample_raster(
    info: RasterInfo,
    target_resolution: Optional[Tuple[float, float]],
    resampling: Resampling = Resampling.bilinear,
) -> RasterInfo:
    """
    Resample the raster to `target_resolution` (x_res, y_res), in the
    raster's current CRS units, only if a resolution is given and it
    differs from the current resolution.
    """
    if not target_resolution:
        return info

    current_res = (abs(info.transform.a), abs(info.transform.e))
    if (
        round(current_res[0], 9) == round(target_resolution[0], 9)
        and round(current_res[1], 9) == round(target_resolution[1], 9)
    ):
        return info

    try:
        transform, width, height = calculate_default_transform(
            info.crs,
            info.crs,
            info.width,
            info.height,
            *info.dataset.bounds,
            resolution=target_resolution,
        )
        dst_array = np.zeros((info.count, height, width), dtype=info.dataset.dtypes[0])

        for band_idx in range(1, info.count + 1):
            reproject(
                source=info.dataset.read(band_idx),
                destination=dst_array[band_idx - 1],
                src_transform=info.transform,
                src_crs=info.crs,
                dst_transform=transform,
                dst_crs=info.crs,
                resampling=resampling,
            )
    except Exception as exc:
        raise GeoprocessingError(
            f"Resampling to {target_resolution} failed: {exc}"
        ) from exc

    return to_memory_dataset(
        dst_array,
        transform,
        info.crs,
        dtype=str(dst_array.dtype),
        nodata=info.nodata,
        tags=info.tags,
    )
