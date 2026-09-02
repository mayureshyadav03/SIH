"""
Phase 3 pipeline orchestrator.

Wires the individual steps together in the exact order defined by the
POLARIS roadmap / SRD:

Validated MODIS Aqua Dataset -> Read Raster Data -> Validate Input ->
Crop Antarctic Region -> Reproject if required -> Resample if required ->
Extract Required Bands -> Extract Required Metadata -> NumPy Processing ->
Generate Clean Processed Dataset -> D2 - Processed Data Storage
"""

import os
from typing import Any, Dict

from .bands import extract_bands
from .config import Phase3Config
from .geoprocessing import crop_to_antarctica, reproject_raster, resample_raster
from .metadata import extract_metadata
from .numpy_ops import process_with_numpy
from .raster_io import close_raster, read_raster, validate_raster
from .storage import save_processed_dataset


def run_phase3_pipeline(config: Phase3Config) -> Dict[str, Any]:
    """
    Run the full Phase 3 workflow for a single MODIS raster.

    Returns:
        A summary dict with the output file paths and the metadata that
        was written to D2, so the caller (or Phase 4) can pick it up
        without re-reading the raster.
    """
    raster_stages = []  # every RasterInfo we open, so we can close them all

    try:
        raw_info = read_raster(config.input_path)
        raster_stages.append(raw_info)
        validate_raster(raw_info)

        cropped_info = crop_to_antarctica(raw_info, config.bbox)
        raster_stages.append(cropped_info)

        reprojected_info = reproject_raster(cropped_info, config.target_crs)
        if reprojected_info is not cropped_info:
            raster_stages.append(reprojected_info)

        resampled_info = resample_raster(reprojected_info, config.target_resolution)
        if resampled_info is not reprojected_info:
            raster_stages.append(resampled_info)

        band_indexes = list(config.bands) if config.bands else list(
            range(1, resampled_info.count + 1)
        )
        band_array = extract_bands(resampled_info, band_indexes)

        metadata = extract_metadata(resampled_info, band_indexes)

        processed_array = process_with_numpy(band_array, nodata=config.nodata)

        dataset_name = config.dataset_name or os.path.splitext(
            os.path.basename(config.input_path)
        )[0]

        raster_path, metadata_path = save_processed_dataset(
            processed_array,
            resampled_info.transform,
            resampled_info.crs,
            metadata,
            config.output_dir,
            dataset_name,
            nodata=config.nodata,
        )

        return {
            "processed_raster_path": raster_path,
            "processed_metadata_path": metadata_path,
            "bands_extracted": band_indexes,
            "metadata": metadata,
        }

    finally:
        for info in raster_stages:
            close_raster(info)
