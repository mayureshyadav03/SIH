"""
Metadata extraction for Phase 3 - Satellite Data Processing (step 7).

Retains satellite/product info, observation info, spatial info and raster
info as required by the SRD (section 9 / section 11), so downstream
phases and D2 storage have what they need without carrying the raw file.
"""

from typing import Any, Dict, List

from .config import ValidationError
from .raster_io import RasterInfo

# Tag keys commonly carried by MODIS products that, when present, describe
# the satellite/product and observation - retained if available, never
# invented if absent.
_SATELLITE_TAG_KEYS = (
    "SATELLITE", "PLATFORM", "PLATFORMSHORTNAME", "INSTRUMENT",
    "SHORTNAME", "PRODUCT", "PRODUCTIONDATETIME",
)
_OBSERVATION_TAG_KEYS = (
    "RANGEBEGINNINGDATE", "RANGEBEGINNINGTIME",
    "RANGEENDINGDATE", "RANGEENDINGTIME", "DAYNIGHTFLAG",
)


def extract_metadata(info: RasterInfo, bands: List[int]) -> Dict[str, Any]:
    """
    Build the metadata record to travel with the processed dataset.

    Raises:
        ValidationError: if required raster-level metadata is missing.
    """
    if info.crs is None or info.transform is None:
        raise ValidationError(
            "Cannot extract metadata: raster is missing CRS or transform."
        )

    tags = info.tags or {}

    satellite_info = {k: tags[k] for k in _SATELLITE_TAG_KEYS if k in tags}
    observation_info = {k: tags[k] for k in _OBSERVATION_TAG_KEYS if k in tags}

    metadata = {
        "satellite_product_info": satellite_info,
        "observation_info": observation_info,
        "spatial_info": {
            "crs": info.crs.to_string() if info.crs else None,
            "bounds": list(info.dataset.bounds),
            "transform": list(info.transform)[:6],
            "resolution": [abs(info.transform.a), abs(info.transform.e)],
        },
        "raster_info": {
            "width": info.width,
            "height": info.height,
            "band_count": info.count,
            "bands_extracted": bands,
            "dtype": info.dtypes[0] if info.dtypes else None,
            "nodata": info.nodata,
        },
        "other_tags": {
            k: v
            for k, v in tags.items()
            if k not in _SATELLITE_TAG_KEYS and k not in _OBSERVATION_TAG_KEYS
        },
    }
    return metadata
