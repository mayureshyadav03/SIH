from polaris import __version__
from polaris.config import (
    ANTARCTIC_REGIONS,
    MODIS_PRODUCTS,
    DataFormats,
    PipelineConfig,
    StorageLayout,
    formats,
    pipeline,
    storage,
)


def test_version():
    assert __version__ == "0.1.0"


def test_region_default():
    region = pipeline.region
    assert region.name == "antarctic_wide"
    assert len(region.bounds) == 4


def test_products_defined():
    assert "MOD021KM" in MODIS_PRODUCTS
    assert MODIS_PRODUCTS["MOD021KM"].level == "L1B"


def test_storage_layout_created():
    assert storage.processed.is_dir()
    assert storage.features.is_dir()
    assert storage.metadata.is_dir()


def test_settings_load():
    assert isinstance(storage, StorageLayout)
    assert isinstance(pipeline, PipelineConfig)
    assert isinstance(formats, DataFormats)
    assert formats.raster == "GEOTIFF"


def test_all_modules_importable():
    import polaris.acquisition  # noqa: F401
    import polaris.processing  # noqa: F401
    import polaris.detection  # noqa: F401
    import polaris.features  # noqa: F401
    import polaris.tracking  # noqa: F401
    import polaris.prediction  # noqa: F401
    import polaris.risk  # noqa: F401
    import polaris.navigation  # noqa: F401
    import polaris.storage  # noqa: F401
    import polaris.dashboard  # noqa: F401


def test_regions_have_antarctic_coverage():
    for region in ANTARCTIC_REGIONS.values():
        assert region.min_lat <= region.max_lat
        assert region.min_lat >= -90.0
        assert region.max_lat <= -60.0