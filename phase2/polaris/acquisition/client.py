"""High-level acquisition client (Phase 2 entry point).

Ties together Earthdata auth, CMR search, download and validation into a
single `acquire()` operation aligned with MOD-FR-01..04:

  * connect/authenticate to Earthdata   (MOD-FR-01)
  * region selection                    (MOD-FR-02)
  * date/time retrieval                 (MOD-FR-03)
  * validate downloaded datasets        (MOD-FR-04)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from polaris.acquisition.download import DownloadManifest, download_granules
from polaris.acquisition.earthdata import ensure_netrc
from polaris.acquisition.search import Granule, search_granules
from polaris.acquisition.validate import ValidationReport, validate_manifest_set
from polaris.config import MODIS_PRODUCTS, MODISProduct, Region, pipeline


@dataclass
class AcquisitionResult:
    """Everything produced by one `AcquisitionClient.acquire()` run."""

    granules: list[Granule] = field(default_factory=list)
    manifest: DownloadManifest | None = None
    validation: ValidationReport | None = None

    @property
    def ok(self) -> bool:
        return bool(
            self.manifest
            and self.manifest.files
            and self.validation
            and self.validation.ok
        )


class AcquisitionClient:
    """Endpoint for the MODIS data-source layer (SRD section 2/4/5)."""

    def __init__(
        self,
        *,
        product: MODISProduct | None = None,
        region: Region | None = None,
        page_limit: int = 3,
    ) -> None:
        self.product = product or MODIS_PRODUCTS[pipeline.product]
        self.region = region or pipeline.region
        self.page_limit = page_limit

    def acquire(
        self,
        day: date,
        *,
        end: date | None = None,
        download: bool = True,
        strict_size: bool = False,
    ) -> AcquisitionResult:
        """Search, download and validate observations for `day` (or a range)."""
        ensure_netrc()  # raises clean error if credentials missing

        granules = search_granules(
            self.product,
            self.region.bounds,
            day,
            end,
            page_limit=self.page_limit,
        )
        result = AcquisitionResult(granules=granules)
        if not granules:
            return result

        if download:
            result.manifest = download_granules(
                granules, self.product, self.region, day
            )
            result.validation = validate_manifest_set(
                result.manifest.files, strict_size=strict_size
            )
        return result


def acquire(
    day: date,
    *,
    product: MODISProduct | None = None,
    region: Region | None = None,
    end: date | None = None,
    download: bool = True,
    strict_size: bool = False,
) -> AcquisitionResult:
    """Module-level convenience: build a client and run `acquire`."""
    client = AcquisitionClient(product=product, region=region)
    return client.acquire(day, end=end, download=download, strict_size=strict_size)


if __name__ == "__main__":  # pragma: no cover - manual tester
    import argparse
    import json
    from datetime import timedelta

    from polaris.config import MODIS_PRODUCTS

    parser = argparse.ArgumentParser(description="POLARIS acquisition tester")
    parser.add_argument("--product", default=pipeline.product)
    parser.add_argument("--region", default=pipeline.region_name)
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument(
        "day", help="observation date YYYY-MM-DD (or 'today'/'yesterday')"
    )
    args = parser.parse_args()

    import polaris.config as cfg

    day = date.today()
    if args.day != "today":
        day = date.fromisoformat(args.day)
    if args.day == "yesterday":
        day = date.today() - timedelta(days=1)

    product = MODIS_PRODUCTS[args.product]
    region = cfg.ANTARCTIC_REGIONS[args.region]
    result = acquire(
        day,
        product=product,
        region=region,
        end=day + timedelta(days=max(0, args.days - 1)),
    )
    print("granules found:", len(result.granules))
    for g in result.granules:
        print(" -", g.title, g.size_bytes)
    if result.manifest:
        print(json.dumps(result.manifest.to_dict(), indent=2))
    if result.validation:
        for f in result.validation.findings:
            print(f"{'OK ' if f.ok else 'BAD'} {f.path.name}: {f.message}")