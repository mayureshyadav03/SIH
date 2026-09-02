"""
Basic verification test for POLARIS Phase 3.

Builds a small synthetic GeoTIFF covering part of Antarctica (so no real
MODIS download is required to verify the pipeline), runs the Phase 3
pipeline end-to-end, and checks the outputs.
"""

import json
import os
import shutil
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from polaris.phase3.config import Phase3Config, RegionError
from polaris.phase3.pipeline import run_phase3_pipeline


def _make_synthetic_modis_raster(path: str) -> None:
    """Create a tiny 3-band raster over part of the Antarctic coast."""
    width, height = 100, 100
    # ~0.01 degree pixels, upper-left near the Antarctic Peninsula
    transform = from_origin(-70.0, -60.0, 0.01, 0.01)

    data = np.random.randint(0, 10000, size=(3, height, width)).astype("uint16")

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=3,
        dtype="uint16",
        crs="EPSG:4326",
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(data)
        dst.update_tags(SATELLITE="Aqua", INSTRUMENT="MODIS")


def test_phase3_pipeline_end_to_end():
    tmp_dir = tempfile.mkdtemp()
    try:
        raw_path = os.path.join(tmp_dir, "synthetic_modis.tif")
        output_dir = os.path.join(tmp_dir, "processed")
        _make_synthetic_modis_raster(raw_path)

        config = Phase3Config(
            input_path=raw_path,
            bbox=(-70.5, -60.5, -69.5, -59.5),
            bands=[1, 2],
            target_crs=None,
            target_resolution=None,
            output_dir=output_dir,
            dataset_name="test_run",
            nodata=0,
        )

        result = run_phase3_pipeline(config)

        assert os.path.isfile(result["processed_raster_path"])
        assert os.path.isfile(result["processed_metadata_path"])
        assert result["bands_extracted"] == [1, 2]

        with rasterio.open(result["processed_raster_path"]) as ds:
            assert ds.count == 2
            assert ds.crs is not None
            arr = ds.read()
            assert arr.shape[0] == 2
            assert np.nanmax(arr) <= 1.0  # normalized

        with open(result["processed_metadata_path"]) as f:
            metadata = json.load(f)
        assert metadata["raster_info"]["bands_extracted"] == [1, 2]
        assert metadata["spatial_info"]["crs"] is not None
        assert metadata["satellite_product_info"].get("SATELLITE") == "Aqua"

        print("Phase 3 pipeline test passed.")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_phase3_rejects_out_of_range_bbox():
    tmp_dir = tempfile.mkdtemp()
    try:
        raw_path = os.path.join(tmp_dir, "synthetic_modis.tif")
        _make_synthetic_modis_raster(raw_path)

        # Bounding box nowhere near the raster's actual coverage.
        config = Phase3Config(
            input_path=raw_path,
            bbox=(100.0, 50.0, 101.0, 51.0),
            output_dir=os.path.join(tmp_dir, "processed"),
        )

        try:
            run_phase3_pipeline(config)
            assert False, "Expected RegionError for non-overlapping bbox"
        except RegionError:
            pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_phase3_pipeline_end_to_end()
    test_phase3_rejects_out_of_range_bbox()
    print("All Phase 3 tests passed.")
