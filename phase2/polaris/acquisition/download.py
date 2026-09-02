"""Granule download from LAADS DAAC / NASA data pools.

Downloads MODIS granules plus their metadata (mirrored as JSON) into the
temporary raw store defined by `StorageLayout.raw_tmp`. Downloads are
streamed with `requests` so multi-hundred-MB granules never live fully in
memory, and any interrupted transfer cleans up its partial file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable

import requests

from polaris.acquisition.earthdata import anonymized_href, session
from polaris.acquisition.search import Granule
from polaris.config import MODISProduct, Region, pipeline, storage

CHUNK = 1 << 20  # 1 MiB


@dataclass
class DownloadManifest:
    """Result of a download run; also persisted as a JSON manifest."""

    product: str
    region: str
    date: str
    files: list[Path] = field(default_factory=list)
    metadata: list[Path] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "product": self.product,
            "region": self.region,
            "date": self.date,
            "files": [str(f) for f in self.files],
            "metadata": [str(f) for f in self.metadata],
            "failed": self.failed,
        }


def _granule_dir(product: MODISProduct, day: date) -> Path:
    return storage.raw_tmp / product.earthdata_slug / day.isoformat()


def _suggest_local_name(granule: Granule, product: MODISProduct, day: date) -> str:
    stem = granule.title or granule.id.split("/")[-1]
    if not stem.lower().endswith((".hdf", ".nc", ".h5")):
        stem += ".hdf"
    return stem


def download_granules(
    granules: Iterable[Granule],
    product: MODISProduct,
    region: Region,
    day: date,
    *,
    http: requests.Session | None = None,
) -> DownloadManifest:
    """Stream-download each granule and its metadata into the raw store.

    Returns a manifest; individual failures are recorded in `manifest.failed`
    and do not abort the remaining granules.
    """
    target = _granule_dir(product, day)
    target.mkdir(parents=True, exist_ok=True)

    manifest = DownloadManifest(product.earthdata_slug, region.name, day.isoformat())
    s = http or session()

    for granule in granules:
        local = target / _suggest_local_name(granule, product, day)
        try:
            _stream_to(s, granule.data_url, local)
            manifest.files.append(local)
            meta_path = target / f"{local.stem}.meta.json"
            _save_metadata(meta_path, granule, local)
            manifest.metadata.append(meta_path)
        except (requests.RequestException, OSError) as exc:
            manifest.failed.append(f"{granule.title}: {exc}")
        except Exception as exc:  # defensive: never kill the batch
            manifest.failed.append(f"{granule.title}: unexpected {exc!r}")

    manifest_path = target / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))
    return manifest


def _stream_to(s: requests.Session, url: str, local: Path) -> None:
    if not url:
        raise requests.RequestException("granule has no data URL (missing auth link?)")
    with s.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        tmp = local.with_suffix(local.suffix + ".part")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(CHUNK):
                    if chunk:
                        fh.write(chunk)
            tmp.replace(local)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)


def _save_metadata(meta_path: Path, granule: Granule, local: Path) -> None:
    meta = {
        **granule.__dict__,
        "local_path": str(local),
        "href_clean": anonymized_href(granule.data_url),
        "size_bytes_local": local.stat().st_size,
    }
    meta_path.write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":  # pragma: no cover - manual tester
    from polaris.acquisition.search import search_granules
    from polaris.config import MODIS_PRODUCTS, pipeline

    product = MODIS_PRODUCTS["MOD021KM"]
    region = pipeline.region
    day = date.today()
    hits = search_granules(product, region.bounds, day, page_limit=1)
    m = download_granules(hits, product, region, day)
    print(json.dumps(m.to_dict(), indent=2))