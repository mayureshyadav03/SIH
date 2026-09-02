"""Central POLARIS configuration and data-format definitions.

Single source of truth for the architecture: product selection,
Antarctic region, storage layout, and standard feature/file-format
definitions consumed by pipeline modules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - optional until env is installed
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Region:
    """Antarctic geographic region selection (MOD-FR-02)."""

    name: str
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.min_lon, self.min_lat, self.max_lon, self.max_lat)


ANTARCTIC_REGIONS = {
    "antarctic_wide": Region(
        name="antarctic_wide",
        min_lon=-180.0,
        min_lat=-80.0,
        max_lon=180.0,
        max_lat=-60.0,
    ),
    "weddell_sea": Region(
        name="weddell_sea",
        min_lon=-60.0,
        min_lat=-75.0,
        max_lon=-20.0,
        max_lat=-60.0,
    ),
    "ross_sea": Region(
        name="ross_sea",
        min_lon=150.0,
        min_lat=-78.0,
        max_lon=-150.0,
        max_lat=-60.0,
    ),
}


@dataclass(frozen=True)
class MODISProduct:
    """A MODIS Aqua data product definition."""

    label: str
    level: str          # L1B | L2 | L3
    earthdata_slug: str
    bands: tuple[str, ...] = ()
    resolution_m: int = 0


MODIS_PRODUCTS = {
    "MOD03": MODISProduct("MOD03", "L1B", "MOD03", ("EV_1KM_RefSB",)),
    "MOD021KM": MODISProduct("MOD021KM", "L1B", "MOD021KM", ()),
    "MOD02QKM": MODISProduct("MOD02QKM", "L1B", "MOD02QKM", ()),
    "MOD06_L2": MODISProduct("MOD06_L2", "L2", "MOD06_L2", ("Cloud_Mask_1km",)),
    "MOD28": MODISProduct("MOD28", "L2", "MOD28", ("SST",)),
    "MOD11_L2": MODISProduct("MOD11_L2", "L2", "MOD11_L2", ("LST",)),
    "MOD09GA": MODISProduct("MOD09GA", "L2", "MOD09GA", ()),
    "MOD10A1": MODISProduct("MOD10A1", "L3", "MOD10A1", ("NDSI_Snow_Cover",)),
    "MOD13Q1": MODISProduct("MOD13Q1", "L3", "MOD13Q1", ("NDVI",)),
}


@dataclass(frozen=True)
class StorageLayout:
    """Storage-efficiency strategy (SRD section 11).

    Raw acquisitions are treated as temporary working files; the system
    persists processed observations, extracted features, iceberg tracks,
    prediction results and metadata instead of raw imagery.
    """

    root: Path = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
    raw_tmp: Path = field(init=False)
    processed: Path = field(init=False)
    features: Path = field(init=False)
    predictions: Path = field(init=False)
    metadata: Path = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_tmp", self.root / "raw")
        object.__setattr__(self, "processed", self.root / "processed")
        object.__setattr__(self, "features", self.root / "features")
        object.__setattr__(self, "predictions", self.root / "predictions")
        object.__setattr__(self, "metadata", self.root / "metadata")
        for path in (
            self.raw_tmp,
            self.processed,
            self.features,
            self.predictions,
            self.metadata,
        ):
            path.mkdir(parents=True, exist_ok=True)


storage = StorageLayout()


@dataclass(frozen=True)
class DataFormats:
    """Canonical file formats used across the pipeline."""

    raster: str = "GEOTIFF"                  # processed band images (GeoTIFF)
    vector_icebergs: str = "GEOJSON"         # iceberg boundaries / positions
    features: str = "CSV"                    # extracted feature tables
    tracks: str = "GEOJSON"                  # historical iceberg trajectories
    predictions: str = "GEOJSON"             # predicted trajectories
    risk_output: str = "GEOJSON"             # risk assessment output
    route: str = "GEOJSON"                   # safer-route recommendations
    metadata: str = "JSON"                   # observation metadata


formats = DataFormats()


@dataclass(frozen=True)
class PipelineConfig:
    """Runtime defaults for the data-source/observation layer."""

    satellite: str = os.getenv("SATELLITE", "Aqua")
    instrument: str = "MODIS"
    product: str = os.getenv("MODIS_PRODUCT", "MOD021KM")
    region_name: str = os.getenv("POLARIS_REGION", "antarctic_wide")
    temporal_resolution_h: int = 12          # ~2 passes/day near poles
    crs_target: str = "EPSG:3031"            # Antarctic Polar Stereographic
    earthdata_username: str = os.getenv("EARTHDATA_USERNAME", "")
    earthdata_password: str = os.getenv("EARTHDATA_PASSWORD", "")

    @property
    def region(self) -> Region:
        return ANTARCTIC_REGIONS[self.region_name]


pipeline = PipelineConfig()