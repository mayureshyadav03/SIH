"""
POLARIS - Phase 5: Feature Extraction
======================================

Consumes the processed/georeferenced MODIS data (Phase 3 output) and the
detected iceberg/sea-ice regions (Phase 4 output) and produces one feature
record per detected iceberg observation.

Scope (per Phase-5 workflow / SRD / Roadmap):
    Processed MODIS Data
        -> Extract Latitude / Longitude
        -> Extract Iceberg Boundary
        -> Calculate Ice-Covered Area
        -> Calculate Distance from Ship
        -> Extract Reflectance / Brightness
        -> Extract Spectral Information
        -> Extract SST
        -> Extract Cloud Information
        -> Add Observation Timestamp / Metadata
        -> Add Historical Movement Information
        -> Create Feature Vector
        -> Output to Phase 6

This module does NOT perform data acquisition, detection, tracking,
trajectory prediction, risk assessment, navigation, or any UI/DB work.
Those belong to other phases.

Technology used: Python, NumPy, OpenCV (boundary extraction), Rasterio-style
affine transforms (for pixel -> geographic coordinate conversion and pixel
area, consistent with GDAL/Rasterio georeferencing used in Phase 3).
"""

import math
from datetime import datetime, timezone

import numpy as np
import cv2

try:
    # rasterio's geotransform type (also available standalone as `affine`)
    from affine import Affine
except ImportError:
    # Minimal fallback with the same interface used here (a, b, c, d, e, f
    # coefficients and `transform * (col, row)` -> (x, y)), so this module
    # works unmodified with a real rasterio.Affine / affine.Affine instance
    # wherever the `affine` package (a rasterio dependency) is installed.
    class Affine:
        def __init__(self, a, b, c, d, e, f):
            self.a, self.b, self.c, self.d, self.e, self.f = a, b, c, d, e, f

        def __mul__(self, pixel):
            col, row = pixel
            x = self.a * col + self.b * row + self.c
            y = self.d * col + self.e * row + self.f
            return x, y


# ---------------------------------------------------------------------------
# INPUT DATA CONTRACTS (documented, minimal structures — see rule 19)
# ---------------------------------------------------------------------------
#
# modis_data (from Phase 3, per MYD02/MYD03/MYD35/MYD28 + QA):
#   {
#       "transform": affine.Affine,       # pixel -> geo coordinate mapping
#       "crs": str,                       # e.g. "EPSG:3031" (projected) or
#                                          # "EPSG:4326" (geographic)
#       "radiance_bands": {                # from MYD02 (Level-1B radiance)
#           "<band_name>": np.ndarray(2D), ...
#       },
#       "band_scales": {"<band_name>": float, ...},   # optional, MYD02 attrs
#       "band_offsets": {"<band_name>": float, ...},  # optional, MYD02 attrs
#       "sst_kelvin": np.ndarray(2D) or None,          # from MYD28
#       "cloud_mask": np.ndarray(2D) or None,          # from MYD35
#       "qa": np.ndarray(2D) or None,                  # QA data
#       "timestamp": datetime,                          # observation time
#       "metadata": {...}                                # any MYD03/QA metadata
#   }
#
# iceberg_detection (from Phase 4, one entry per detected iceberg):
#   {
#       "iceberg_id": str,
#       "mask": np.ndarray(2D, bool),   # True where this iceberg's pixels are
#   }
#
# ship_position:
#   {"latitude": float, "longitude": float}
#
# historical_positions (optional, from prior stored observations for the
# SAME iceberg_id; Phase 5 only reads/stores this, it does not build it):
#   [{"timestamp": datetime, "latitude": float, "longitude": float}, ...]
#   (assumed sorted oldest -> newest; may be empty for a first observation)
#
# ---------------------------------------------------------------------------


def _validate_modis_data(modis_data):
    """Basic presence/type checks for required MODIS inputs."""
    if not isinstance(modis_data.get("transform"), Affine):
        raise ValueError("modis_data['transform'] must be an affine.Affine geotransform")
    if not modis_data.get("radiance_bands"):
        raise ValueError("modis_data['radiance_bands'] (MYD02) is required")
    if modis_data.get("timestamp") is None:
        raise ValueError("modis_data['timestamp'] is required")


def _validate_iceberg_detection(iceberg_detection):
    mask = iceberg_detection.get("mask")
    if mask is None or not isinstance(mask, np.ndarray) or mask.dtype != bool:
        raise ValueError("iceberg_detection['mask'] must be a boolean numpy array")
    if not mask.any():
        raise ValueError("iceberg_detection['mask'] contains no iceberg pixels")


# ---------------------------------------------------------------------------
# 1. LATITUDE / LONGITUDE  (uses MYD03-style geolocation via geotransform)
# ---------------------------------------------------------------------------

def extract_lat_lon(mask, transform):
    """
    Determine the geographic coordinate of a detected iceberg from its
    pixel mask and the MODIS geolocation (affine geotransform, MYD03).

    Position is reported as the centroid of the iceberg's pixels.

    Returns: (latitude, longitude)
    """
    rows, cols = np.where(mask)
    if rows.size == 0:
        raise ValueError("Empty iceberg mask; cannot compute position")

    centroid_row = float(np.mean(rows))
    centroid_col = float(np.mean(cols))

    # Affine geotransform: pixel (col, row) -> geographic (x, y)
    x, y = transform * (centroid_col + 0.5, centroid_row + 0.5)

    # Convention: x = longitude, y = latitude for geographic CRS output
    # (Phase 3 is expected to have reprojected/geolocated data accordingly).
    longitude, latitude = x, y
    return latitude, longitude


# ---------------------------------------------------------------------------
# 2. ICEBERG BOUNDARY  (OpenCV contour extraction)
# ---------------------------------------------------------------------------

def extract_iceberg_boundary(mask, transform=None):
    """
    Extract the contour/polygon boundary of the detected iceberg.

    If a geotransform is supplied, boundary points are converted to
    geographic coordinates; otherwise pixel (col, row) coordinates are
    returned.

    Returns: list of (x, y) boundary points (outer contour).
    """
    mask_uint8 = mask.astype(np.uint8) * 255
    contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return []

    # Use the largest contour (the iceberg region may produce one primary
    # contour; smaller artifacts are ignored).
    largest = max(contours, key=cv2.contourArea)
    points = largest.reshape(-1, 2)  # (col, row) pairs

    if transform is None:
        return [(float(c), float(r)) for c, r in points]

    boundary = []
    for col, row in points:
        x, y = transform * (float(col) + 0.5, float(row) + 0.5)
        boundary.append((x, y))
    return boundary


# ---------------------------------------------------------------------------
# 3. ICE-COVERED AREA
# ---------------------------------------------------------------------------

def compute_pixel_area_km2(transform):
    """
    Compute the ground area represented by a single pixel, in km^2, from
    the geotransform produced by Phase 3 (GDAL/Rasterio reprojection).

    Assumes a projected CRS with linear (metre) units, as expected after
    Phase 3 reprojects/crops the Antarctic region.
    """
    pixel_width_m = abs(transform.a)
    pixel_height_m = abs(transform.e)
    pixel_area_m2 = pixel_width_m * pixel_height_m
    return pixel_area_m2 / 1_000_000.0


def calculate_ice_area(mask, transform):
    """
    Calculate the detected iceberg's ice-covered area in km^2.
    """
    pixel_area_km2 = compute_pixel_area_km2(transform)
    return float(np.count_nonzero(mask)) * pixel_area_km2


# ---------------------------------------------------------------------------
# 4. DISTANCE FROM SHIP
# ---------------------------------------------------------------------------

def calculate_distance_from_ship(iceberg_lat, iceberg_lon, ship_position):
    """
    Great-circle (haversine) distance between the iceberg and the ship's
    current position.

    Returns: dict with distance in kilometres and nautical miles.
    """
    lat1, lon1 = ship_position["latitude"], ship_position["longitude"]
    lat2, lon2 = iceberg_lat, iceberg_lon

    R_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_km = R_km * c
    distance_nm = distance_km / 1.852

    return {"distance_km": distance_km, "distance_nm": distance_nm}


# ---------------------------------------------------------------------------
# 5. REFLECTANCE AND BRIGHTNESS
# ---------------------------------------------------------------------------

def extract_reflectance_brightness(radiance_bands, mask, band_scales=None, band_offsets=None):
    """
    Extract reflectance (where scale/offset calibration is available from
    MYD02 metadata) and brightness (mean raw band value) for the iceberg
    region, per band.

    band_scales / band_offsets: optional dicts of MYD02 per-band
    reflectance_scales / reflectance_offsets. If not supplied for a band,
    only brightness (raw radiance statistics) is reported for that band.
    """
    band_scales = band_scales or {}
    band_offsets = band_offsets or {}

    reflectance = {}
    brightness = {}

    for band_name, band_array in radiance_bands.items():
        valid = _masked_valid_values(band_array, mask)
        if valid.size == 0:
            continue

        brightness[band_name] = {
            "mean": float(np.mean(valid)),
            "min": float(np.min(valid)),
            "max": float(np.max(valid)),
        }

        if band_name in band_scales and band_name in band_offsets:
            refl_values = band_scales[band_name] * (valid - band_offsets[band_name])
            reflectance[band_name] = {
                "mean": float(np.mean(refl_values)),
                "min": float(np.min(refl_values)),
                "max": float(np.max(refl_values)),
            }

    return reflectance, brightness


def _masked_valid_values(array, mask, fill_value=None):
    """
    Return the values of `array` within `mask`, excluding invalid/fill
    pixels (NaN, or the product's documented fill value if supplied).
    """
    values = array[mask]
    valid = values[~np.isnan(values.astype(float))] if np.issubdtype(values.dtype, np.floating) else values
    if fill_value is not None:
        valid = valid[valid != fill_value]
    return valid


# ---------------------------------------------------------------------------
# 6. SPECTRAL INFORMATION
# ---------------------------------------------------------------------------

def extract_spectral_information(radiance_bands, mask):
    """
    Extract the mean spectral value for each available MODIS band within
    the iceberg region (the iceberg's spectral signature).
    """
    spectral_info = {}
    for band_name, band_array in radiance_bands.items():
        valid = _masked_valid_values(band_array, mask)
        if valid.size == 0:
            continue
        spectral_info[band_name] = float(np.mean(valid))
    return spectral_info


# ---------------------------------------------------------------------------
# 7. SEA-SURFACE TEMPERATURE (MYD28)
# ---------------------------------------------------------------------------

def extract_sst(sst_kelvin, mask, fill_value=None):
    """
    Extract mean sea-surface temperature for the iceberg region from
    MYD28, converted to degrees Celsius.

    Returns None if no SST data is available for this observation.
    """
    if sst_kelvin is None:
        return None

    valid = _masked_valid_values(sst_kelvin, mask, fill_value=fill_value)
    if valid.size == 0:
        return None

    mean_kelvin = float(np.mean(valid))
    return mean_kelvin - 273.15


# ---------------------------------------------------------------------------
# 8. CLOUD INFORMATION (MYD35)
# ---------------------------------------------------------------------------

def extract_cloud_information(cloud_mask, mask):
    """
    Extract cloud coverage/information for the iceberg region from the
    MYD35 cloud mask.

    Returns None if no cloud mask is available. Otherwise returns the
    fraction of the region covered by each cloud-mask category value
    present, plus the overall cloud-covered fraction (values indicating
    cloudy/uncertain per the MYD35 product, i.e. all values other than
    "confident clear").
    """
    if cloud_mask is None:
        return None

    region_values = cloud_mask[mask]
    if region_values.size == 0:
        return None

    total = region_values.size
    categories = {}
    for value in np.unique(region_values):
        count = int(np.count_nonzero(region_values == value))
        categories[int(value)] = count / total

    # MYD35 convention: 3 = confident clear. Anything else counts toward
    # cloud coverage for this simple feature-extraction purpose.
    CONFIDENT_CLEAR = 3
    cloud_fraction = 1.0 - categories.get(CONFIDENT_CLEAR, 0.0)

    return {"category_fractions": categories, "cloud_fraction": cloud_fraction}


# ---------------------------------------------------------------------------
# 9. TEMPORAL INFORMATION
# ---------------------------------------------------------------------------

def extract_temporal_information(timestamp, metadata=None):
    """
    Store the observation timestamp and any relevant MODIS metadata
    required downstream (Phase 5 does not interpret metadata further).
    """
    if isinstance(timestamp, datetime):
        ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        ts_str = ts.isoformat()
    else:
        ts_str = str(timestamp)

    return {"observation_timestamp": ts_str, "metadata": metadata or {}}


# ---------------------------------------------------------------------------
# 10. HISTORICAL MOVEMENT INFORMATION
# ---------------------------------------------------------------------------

def extract_historical_movement(current_position, historical_positions):
    """
    Store previous position, current position, and basic historical
    movement information using previously available iceberg observations.

    Does NOT perform trajectory prediction or full tracking (Phase 6/7).

    current_position: {"latitude": float, "longitude": float}
    historical_positions: list of prior observations for this same
        iceberg, sorted oldest -> newest (may be empty).
    """
    previous_position = None
    historical_movement = None

    if historical_positions:
        previous = historical_positions[-1]
        previous_position = {
            "latitude": previous["latitude"],
            "longitude": previous["longitude"],
            "timestamp": str(previous.get("timestamp")),
        }

        displacement = calculate_distance_from_ship(
            previous["latitude"], previous["longitude"], current_position
        )
        historical_movement = {
            "previous_observations_count": len(historical_positions),
            "displacement_from_previous_km": displacement["distance_km"],
            "displacement_from_previous_nm": displacement["distance_nm"],
        }

    return previous_position, historical_movement


# ---------------------------------------------------------------------------
# FEATURE VECTOR CONSTRUCTION
# ---------------------------------------------------------------------------

def build_feature_vector(
    iceberg_id,
    latitude,
    longitude,
    iceberg_boundary,
    ice_covered_area_km2,
    distance_from_ship,
    reflectance,
    brightness,
    spectral_information,
    sea_surface_temperature_c,
    cloud_information,
    temporal_information,
    previous_iceberg_position,
    current_iceberg_position,
    historical_movement,
):
    """
    Assemble the Phase-5 feature record for one detected iceberg
    observation, matching the record structure required by the SRD/roadmap.
    """
    return {
        "iceberg_id": iceberg_id,
        "latitude": latitude,
        "longitude": longitude,
        "iceberg_position": {"latitude": latitude, "longitude": longitude},
        "iceberg_boundary": iceberg_boundary,
        "ice_covered_area_km2": ice_covered_area_km2,
        "distance_from_ship": distance_from_ship,
        "reflectance": reflectance,
        "brightness": brightness,
        "spectral_information": spectral_information,
        "sea_surface_temperature_c": sea_surface_temperature_c,
        "cloud_information": cloud_information,
        "observation_timestamp": temporal_information["observation_timestamp"],
        "observation_metadata": temporal_information["metadata"],
        "previous_iceberg_position": previous_iceberg_position,
        "current_iceberg_position": current_iceberg_position,
        "historical_movement": historical_movement,
    }


# ---------------------------------------------------------------------------
# TOP-LEVEL PHASE 5 ORCHESTRATION
# ---------------------------------------------------------------------------

def process_iceberg_observation(
    modis_data,
    iceberg_detection,
    ship_position,
    historical_positions=None,
):
    """
    Run the full Phase-5 feature-extraction workflow for a single detected
    iceberg and return its feature record.
    """
    _validate_modis_data(modis_data)
    _validate_iceberg_detection(iceberg_detection)

    mask = iceberg_detection["mask"]
    transform = modis_data["transform"]

    latitude, longitude = extract_lat_lon(mask, transform)
    boundary = extract_iceberg_boundary(mask, transform)
    area_km2 = calculate_ice_area(mask, transform)
    distance = calculate_distance_from_ship(latitude, longitude, ship_position)

    reflectance, brightness = extract_reflectance_brightness(
        modis_data["radiance_bands"],
        mask,
        band_scales=modis_data.get("band_scales"),
        band_offsets=modis_data.get("band_offsets"),
    )
    spectral_info = extract_spectral_information(modis_data["radiance_bands"], mask)
    sst_c = extract_sst(modis_data.get("sst_kelvin"), mask)
    cloud_info = extract_cloud_information(modis_data.get("cloud_mask"), mask)
    temporal_info = extract_temporal_information(
        modis_data["timestamp"], modis_data.get("metadata")
    )

    current_position = {"latitude": latitude, "longitude": longitude}
    previous_position, historical_movement = extract_historical_movement(
        current_position, historical_positions or []
    )

    return build_feature_vector(
        iceberg_id=iceberg_detection.get("iceberg_id"),
        latitude=latitude,
        longitude=longitude,
        iceberg_boundary=boundary,
        ice_covered_area_km2=area_km2,
        distance_from_ship=distance,
        reflectance=reflectance,
        brightness=brightness,
        spectral_information=spectral_info,
        sea_surface_temperature_c=sst_c,
        cloud_information=cloud_info,
        temporal_information=temporal_info,
        previous_iceberg_position=previous_position,
        current_iceberg_position=current_position,
        historical_movement=historical_movement,
    )


def process_all_icebergs(
    modis_data,
    iceberg_detections,
    ship_position,
    historical_positions_by_id=None,
):
    """
    Run Phase 5 for every detected iceberg in a single MODIS observation.

    iceberg_detections: list of iceberg_detection dicts (see contract above)
    historical_positions_by_id: optional dict {iceberg_id: [prior obs...]}

    Returns: list of feature records (the Phase-5 output feature dataset),
    ready to be passed to Phase 6.
    """
    historical_positions_by_id = historical_positions_by_id or {}
    feature_dataset = []

    for detection in iceberg_detections:
        history = historical_positions_by_id.get(detection.get("iceberg_id"), [])
        record = process_iceberg_observation(
            modis_data, detection, ship_position, historical_positions=history
        )
        feature_dataset.append(record)

    return feature_dataset


# ---------------------------------------------------------------------------
# MINIMAL EXAMPLE
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Synthetic minimal example showing how Phase 5 is called.
    # In the real system, these inputs come from Phase 3 (modis_data) and
    # Phase 4 (iceberg_detections).

    example_transform = Affine(
        30.0, 0.0, 400000.0,   # pixel width (m), rotation, x origin
        0.0, -30.0, -2500000.0  # rotation, pixel height (m, negative), y origin
    )

    height, width = 100, 100
    example_mask = np.zeros((height, width), dtype=bool)
    example_mask[40:60, 40:70] = True  # a synthetic detected iceberg region

    rng = np.random.default_rng(0)
    example_modis_data = {
        "transform": example_transform,
        "crs": "EPSG:3031",
        "radiance_bands": {
            "band1": rng.uniform(0, 400, size=(height, width)),
            "band2": rng.uniform(0, 400, size=(height, width)),
        },
        "band_scales": {"band1": 0.001, "band2": 0.001},
        "band_offsets": {"band1": 0.0, "band2": 0.0},
        "sst_kelvin": rng.uniform(271.0, 275.0, size=(height, width)),
        "cloud_mask": rng.integers(0, 4, size=(height, width)),
        "qa": None,
        "timestamp": datetime(2026, 1, 15, 6, 30, tzinfo=timezone.utc),
        "metadata": {"product": "MYD02/MYD03/MYD35/MYD28", "granule": "example"},
    }

    example_detections = [{"iceberg_id": "ICE-001", "mask": example_mask}]
    example_ship_position = {"latitude": -66.5, "longitude": 90.2}
    example_history = {
        "ICE-001": [
            {"timestamp": "2026-01-14T06:30:00+00:00", "latitude": -66.42, "longitude": 90.15}
        ]
    }

    feature_dataset = process_all_icebergs(
        example_modis_data,
        example_detections,
        example_ship_position,
        historical_positions_by_id=example_history,
    )

    import json
    print(json.dumps(feature_dataset, indent=2, default=str))
