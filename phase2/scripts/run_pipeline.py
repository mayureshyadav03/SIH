#!/usr/bin/env python3
"""POLARIS end-to-end pipeline runner.

Orchestrates the full chain per the roadmap:
  acquisition -> processing -> detection -> features -> tracking
  -> prediction -> risk -> navigation -> output.

Accepts the Antarctic observation region either as a named preset
(--region) or as an explicit geographic bounding box (--bbox),
per SRD section 4 input: "Geographic coordinates/bounding box".

The acquisition stage is implemented (Phase 2): it authenticates to
NASA Earthdata, searches CMR for MODIS granules intersecting the region,
downloads them and validates the datasets. Remaining stages are traced
until their phases are implemented.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from typing import Any, Callable

from polaris.acquisition.client import AcquisitionClient
from polaris.config import ANTARCTIC_REGIONS, MODIS_PRODUCTS, Region, pipeline


def _parse_bbox(raw: list[str] | None) -> Region | None:
    if raw is None:
        return None
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in raw)
    lat_ok = -90 <= min_lat <= max_lat <= -60
    lon_ok = -180 <= min_lon <= max_lon <= 180
    if not (lat_ok and lon_ok):
        return None
    return Region(
        name=f"custom_{min_lon}_{min_lat}_{max_lon}_{max_lat}",
        min_lon=min_lon,
        min_lat=min_lat,
        max_lon=max_lon,
        max_lat=max_lat,
    )


def _parse_date(raw: str | None) -> date:
    if not raw or raw in ("latest", "today"):
        return date.today()
    if raw == "yesterday":
        return date.today() - timedelta(days=1)
    return date.fromisoformat(raw)


def _trace(stage: str, fn: Callable[[dict[str, Any]], None], ctx: dict[str, Any]) -> None:
    print(f"[pipeline] {stage} ...")
    fn(ctx)
    print(f"[pipeline] {stage} done")


def _stage_acquisition(ctx: dict[str, Any]) -> None:
    day: date = ctx["date"]
    client = AcquisitionClient(product=ctx["product"], region=ctx["region"])
    result = client.acquire(day)
    ctx["acquisition"] = result
    print(f"  granules found : {len(result.granules)}")
    if result.manifest:
        print(f"  downloaded     : {len(result.manifest.files)} file(s)")
        print(f"  failed         : {len(result.manifest.failed)}")
    if result.validation:
        print(f"  validation     : {result.validation.summary}")
    if not result.ok:
        print("  WARNING: acquisition incomplete", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="POLARIS pipeline runner")
    parser.add_argument("--product", default=pipeline.product, choices=sorted(MODIS_PRODUCTS))
    parser.add_argument("--region", default=pipeline.region_name)
    parser.add_argument(
        "--bbox",
        nargs=4,
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        default=None,
        type=float,
        help="Explicit geographic bounding box: overrides --region, "
        "format: <min_lon> <min_lat> <max_lon> <max_lat>",
    )
    parser.add_argument(
        "--date",
        "-d",
        default=None,
        help="Observation date YYYY-MM-DD, 'today' or 'yesterday'",
    )
    args = parser.parse_args()

    if args.bbox is not None:
        region = _parse_bbox([str(v) for v in args.bbox])
        if region is None:
            parser.error(
                "invalid --bbox: require min_lon <= max_lon and "
                "latitude within [-90, -60] (min_lat <= max_lat)"
            )
    else:
        region = ANTARCTIC_REGIONS[args.region]

    ctx: dict[str, Any] = {
        "product": MODIS_PRODUCTS[args.product],
        "region": region,
        "bounds": region.bounds,
        "date": _parse_date(args.date),
        "satellite": pipeline.satellite,
    }

    print(
        f"POLARIS pipeline: product={args.product} region={region.name} "
        f"bounds={region.bounds} date={ctx['date'].isoformat()}"
    )

    _trace("acquisition", _stage_acquisition, ctx)

    remaining = {
        "processing": "polaris.processing",
        "detection": "polaris.detection",
        "features": "polaris.features",
        "tracking": "polaris.tracking",
        "prediction": "polaris.prediction",
        "risk": "polaris.risk",
        "navigation": "polaris.navigation",
    }
    for stage, module in remaining.items():
        __import__(module)
        _trace(stage, lambda _ctx: None, ctx)


if __name__ == "__main__":
    main()