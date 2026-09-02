"""MODIS granule discovery via the NASA CMR search API.

Queries are composed from a MODIS product (short name), an Antarctic
region (bounding box) and a date/time window. CMR is queried with the
intersection operator (`?/bounding_box`) and the standard `short_name`,
`temporal`, `page_size` and `page_num` parameters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Iterator

import requests

from polaris.acquisition.earthdata import session
from polaris.config import MODISProduct

CMR_SEARCH_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
CMR_PAGE_SIZE = 100


@dataclass(frozen=True)
class Granule:
    """A single MODIS observation granule returned by CMR."""

    id: str
    title: str
    data_url: str
    size_bytes: int
    start_time: str
    end_time: str
    footprint: str  # GeoJSON polygon string of the swath/tile

    @classmethod
    def from_cmr(cls, entry: dict[str, Any]) -> "Granule":
        data_links = [
            link
            for link in entry.get("links", [])
            if link.get("href", "").endswith((".hdf", ".nc", ".h5"))
        ]
        href = data_links[0]["href"] if data_links else ""
        umm = entry.get("umm", {})
        granule = umm.get("DataGranule", {})
        size = int(float(granule.get("Size", 0) or 0))
        temporal = umm.get("TemporalExtent", {}).get("RangeDateTime", {})
        footprint = (
            entry.get("polygons")
            or (umm.get("SpatialExtent", {})
                .get("HorizontalSpatialDomain", {})
                .get("Geometry", {}))
        ) or ""
        return cls(
            id=entry.get("id", ""),
            title=entry.get("title", ""),
            data_url=href,
            size_bytes=size,
            start_time=temporal.get("BeginningDateTime", ""),
            end_time=temporal.get("EndingDateTime", ""),
            footprint=str(footprint),
        )


def _temporal_window(
    start: date | datetime,
    end: date | datetime | None = None,
    duration: timedelta = timedelta(days=1),
) -> str:
    """Build the CMR `temporal` filter string.

    A single date expands to a [start, start+duration) window unless an
    explicit end is supplied.
    """
    if end is None:
        if isinstance(start, datetime):
            end = start + duration
        else:
            end = datetime.combine(start, time.max) + timedelta(seconds=1)
    start = datetime.combine(start, time.min) if isinstance(start, date) else start
    end = datetime.combine(end, time.min) if isinstance(end, date) else end
    return f"{start.isoformat()}Z,{end.isoformat()}Z"


def _cmr_params(
    product: MODISProduct,
    bbox: tuple[float, float, float, float],
    temporal: str,
    page_num: int,
    page_size: int = CMR_PAGE_SIZE,
) -> dict[str, str]:
    """Compose CMR query parameters for a product + region."""
    return {
        "short_name": product.earthdata_slug,
        "bounding_box": ",".join(str(v) for v in bbox),
        "temporal": temporal,
        "page_size": str(page_size),
        "page_num": str(page_num),
    }


def search_granules(
    product: MODISProduct,
    bbox: tuple[float, float, float, float],
    start: date,
    end: date | None = None,
    *,
    page_limit: int = 3,
    page_size: int = CMR_PAGE_SIZE,
) -> list[Granule]:
    """Search CMR for MODIS granules intersecting the Antarctic bbox.

    Returns up to `page_limit * page_size` matching granules, chronologically
    newest last.
    """
    temporal = _temporal_window(start, end)
    found: list[Granule] = []

    with session() as s:
        for page in range(1, page_limit + 1):
            resp = s.get(
                CMR_SEARCH_URL,
                params=_cmr_params(product, bbox, temporal, page, page_size),
                timeout=60,
            )
            resp.raise_for_status()
            body = resp.json()
            entries = body.get("feed", {}).get("entry", [])
            if not entries:
                break
            found.extend(Granule.from_cmr(e) for e in entries)
            if len(entries) < page_size:
                break

    return found


def iter_granules(
    product: MODISProduct,
    bbox: tuple[float, float, float, float],
    start: date,
    end: date | None = None,
    **kwargs: Any,
) -> Iterator[Granule]:
    """Lazy variant of {py:func}`search_granules`."""
    yield from search_granules(product, bbox, start, end, **kwargs)


def dump_query(
    product: MODISProduct, bbox: tuple[float, float, float, float], start: date
) -> str:
    """Render the CMR query as a debuggable URL (used by tests/CLI)."""
    return (
        requests.Request(
            "GET",
            CMR_SEARCH_URL,
            params=_cmr_params(product, bbox, _temporal_window(start), 1),
        )
        .prepare()
        .url
    )


if __name__ == "__main__":  # pragma: no cover - manual smoke tester
    import sys

    from polaris.config import MODIS_PRODUCTS, pipeline

    product = MODIS_PRODUCTS[sys.argv[1] if len(sys.argv) > 1 else "MOD021KM"]
    day = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
    print("query:", dump_query(product, pipeline.region.bounds, day))
    for g in search_granules(product, pipeline.region.bounds, day):
        print(json.dumps(g.__dict__, default=str))