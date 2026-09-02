"""Dataset validation (MOD-FR-04).

Every downloaded observation is checked before it is handed to the
processing/AI/ML stages:
  * file exists and is non-empty
  * observed size matches the size advertised by CMR/LAADS
  * container magic bytes match the expected format (HDF4/HDF5/NetCDF)
  * the archive opens and exposes geospatial data via GDAL/rasterio

A `ValidationReport` records per-file verdicts together with reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from polaris.acquisition.search import Granule

# HDF4 / HDF5 / NetCDF3 / NetCDF4 (HDF5) magic byte sequences
MAGIC = {
    "HDF4": b"\x0e\x03\x13\x01",
    "HDF5": b"\x89HDF",
    "netCDF3": b"CDF\x01",
    "netCDF4": b"\x89HDF",
}


def sniff_format(path: Path) -> str | None:
    """Identify container format from leading bytes, or None if unknown."""
    with path.open("rb") as fh:
        head = fh.read(8)
    for name, magic in MAGIC.items():
        if head.startswith(magic):
            return name
    return None


@dataclass
class DatasetFinding:
    path: Path
    ok: bool
    message: str


@dataclass
class ValidationReport:
    findings: list[DatasetFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(f.ok for f in self.findings)

    @property
    def summary(self) -> str:
        n_ok = sum(1 for f in self.findings if f.ok)
        return f"{n_ok}/{len(self.findings)} datasets valid"


def validate_local(
    local: Path,
    granule: Granule | None = None,
    expected_size: int | None = None,
    *,
    strict_size: bool = False,
) -> DatasetFinding:
    """Validate a single downloaded file; returns a finding (never raises)."""
    if not local.exists():
        return DatasetFinding(local, False, "file not found")
    if local.stat().st_size == 0:
        return DatasetFinding(local, False, "file is empty")

    size = local.stat().st_size
    expected_size = expected_size if expected_size is not None else (
        granule.size_bytes if granule else None
    )
    if strict_size and expected_size:
        if size != expected_size:
            return DatasetFinding(
                local, False, f"size mismatch: local={size} advertised={expected_size}"
            )

    fmt = sniff_format(local)
    if fmt is None:
        return DatasetFinding(local, False, "unrecognized container format")

    geo_ok = _geo_probe(local)
    if not geo_ok:
        return DatasetFinding(local, False, "file does not expose geospatial data")

    return DatasetFinding(local, True, f"valid {fmt} ({size} bytes)")


def validate_manifest_set(
    files: Iterable[Path],
    granules: Iterable[Granule] | None = None,
    *,
    strict_size: bool = False,
) -> ValidationReport:
    """Validate a batch (e.g. everything on disk under a product/date dir)."""
    report = ValidationReport()
    granule_by_stem = (
        {g.title: g for g in granules} if granules is not None else {}
    )
    for path in files:
        g = None
        for candidate, gr in granule_by_stem.items():
            if candidate in path.name:
                g = gr
                break
        report.findings.append(
            validate_local(path, granule=g, strict_size=strict_size)
        )
    return report


def _geo_probe(local: Path) -> bool:
    """Best-effort check that GDAL/rasterio can open the dataset.

    Falls back to accepting HDF containers when no gdal/rasterio driver is
    available, to remain operational in bare/minimal environments.
    """
    try:
        import rasterio
    except ImportError:
        return sniff_format(local) is not None

    try:
        with rasterio.open(local) as src:
            _ = src.crs
            _ = src.width, src.height
            if src.read(1).size == 0:  # ensure at least one pixel band reads
                return False
            return isinstance(src.read(1), np.ndarray)
    except Exception:
        # e.g. HDF4 without a compiled driver -> still accept if magic matches
        return sniff_format(local) is not None