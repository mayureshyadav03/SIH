#!/usr/bin/env python3
"""
CLI entry point for POLARIS Phase 3 - Satellite Data Processing.

Example:
    python run_phase3.py \\
        --input data/raw/MYD021KM.A2024001.0000.061.tif \\
        --bbox -180 -90 180 -60 \\
        --bands 1 2 3 \\
        --target-crs EPSG:3031 \\
        --output-dir data/processed
"""

import argparse
import sys

from polaris.phase3.config import Phase3Config, Phase3Error
from polaris.phase3.pipeline import run_phase3_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POLARIS Phase 3 - Satellite Data Processing")
    parser.add_argument("--input", required=True, help="Path to local MODIS Aqua raster")
    parser.add_argument(
        "--bbox", nargs=4, type=float, required=True,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        help="Antarctic bounding box in EPSG:4326",
    )
    parser.add_argument(
        "--bands", nargs="*", type=int, default=None,
        help="1-based band indices to keep (default: all bands)",
    )
    parser.add_argument(
        "--target-crs", default=None,
        help="Optional target CRS, e.g. EPSG:3031 (Antarctic Polar Stereographic)",
    )
    parser.add_argument(
        "--target-resolution", nargs=2, type=float, default=None,
        metavar=("X_RES", "Y_RES"),
        help="Optional target resolution in target CRS units",
    )
    parser.add_argument("--output-dir", default="data/processed", help="D2 storage directory")
    parser.add_argument("--dataset-name", default=None, help="Base name for output files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config = Phase3Config(
        input_path=args.input,
        bbox=tuple(args.bbox),
        bands=args.bands,
        target_crs=args.target_crs,
        target_resolution=tuple(args.target_resolution) if args.target_resolution else None,
        output_dir=args.output_dir,
        dataset_name=args.dataset_name,
    )

    try:
        result = run_phase3_pipeline(config)
    except Phase3Error as exc:
        print(f"Phase 3 failed: {exc}", file=sys.stderr)
        return 1

    print("Phase 3 complete.")
    print(f"  Processed raster:  {result['processed_raster_path']}")
    print(f"  Processed metadata: {result['processed_metadata_path']}")
    print(f"  Bands extracted:   {result['bands_extracted']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
