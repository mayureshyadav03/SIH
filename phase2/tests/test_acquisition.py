"""Phase 2 tests - acquisition. All offline (mocked HTTP, temp dirs)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from polaris.acquisition.search import (
    CMR_SEARCH_URL,
    Granule,
    _temporal_window,
    dump_query,
    search_granules,
)
from polaris.acquisition.validate import sniff_format, validate_local
from polaris.config import ANTARCTIC_REGIONS, MODIS_PRODUCTS


def test_temporal_window_single_date():
    assert _temporal_window(date(2026, 1, 15)) == (
        "2026-01-15T00:00:00Z,2026-01-16T00:00:00Z"
    )


def test_temporal_window_explicit_range():
    assert _temporal_window(date(2026, 1, 15), date(2026, 1, 17)) == (
        "2026-01-15T00:00:00Z,2026-01-17T00:00:00Z"
    )


def test_dump_query_has_bounds_and_product():
    url = dump_query(
        MODIS_PRODUCTS["MOD021KM"],
        ANTARCTIC_REGIONS["weddell_sea"].bounds,
        date(2026, 1, 15),
    )
    assert url.startswith(CMR_SEARCH_URL)
    assert "short_name=MOD021KM" in url
    assert "bounding_box=-60.0%2C-75.0%2C-20.0%2C-60.0" in url
    assert "temporal=2026-01-15T00%3A00%3A00Z%2C2026-01-16T00%3A00%3A00Z" in url


def test_granule_from_cmr_picks_hdf_link():
    entry = {
        "id": "g1",
        "title": "MOD021KM.A2026015.1200.061.2026015153838.hdf",
        "links": [
            {"href": "https://e4ftl01.cr.usgs.gov/MOD/foo.xml"},
            {"href": "https://data.laads/.../MOD021KM...hdf"},
        ],
        "umm": {
            "DataGranule": {"Size": "123456"},
            "TemporalExtent": {
                "RangeDateTime": {
                    "BeginningDateTime": "2026-01-15T12:00:00Z",
                    "EndingDateTime": "2026-01-15T12:05:00Z",
                }
            },
        },
    }
    g = Granule.from_cmr(entry)
    assert g.data_url.endswith(".hdf")
    assert g.size_bytes == 123456
    assert g.title == entry["title"]


def test_search_granules_paginated_request(monkeypatch):
    """Verify the search path issues one paginated CMR request."""
    import requests

    calls: list[dict] = []

    class FakeResp:
        status_code = 200

        def json(self):
            return {"feed": {"entry": []}}

        def raise_for_status(self):
            pass

    class FakeSession(requests.Session):
        def get(self, url, params=None, timeout=None):
            calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeResp()

    monkeypatch.setattr("polaris.acquisition.search.session", lambda: FakeSession())
    hits = search_granules(
        MODIS_PRODUCTS["MOD06_L2"],
        ANTARCTIC_REGIONS["ross_sea"].bounds,
        date(2026, 1, 15),
        page_limit=1,
    )
    assert hits == []
    assert calls[0]["url"] == CMR_SEARCH_URL
    assert calls[0]["params"]["short_name"] == "MOD06_L2"
    assert calls[0]["params"]["page_num"] == "1"


def test_sniff_hdf4_and_hdf5(tmp_path):
    h4 = tmp_path / "x.hdf"
    h4.write_bytes(b"\x0e\x03\x13\x01rest")
    h5 = tmp_path / "y.h5"
    h5.write_bytes(b"\x89HDF\r\n\x1a\nothers")
    other = tmp_path / "z.bin"
    other.write_bytes(b"\x00\x01\x02\x03")
    assert sniff_format(h4) == "HDF4"
    assert sniff_format(h5) == "HDF5"
    assert sniff_format(other) is None


def test_validate_local_hdf4(monkeypatch, tmp_path):
    monkeypatch.setattr("polaris.acquisition.validate._geo_probe", lambda p: True)
    f = tmp_path / "granule.hdf"
    f.write_bytes(b"\x0e\x03\x13\x01" + b"\x00" * 100)
    finding = validate_local(f)
    assert finding.ok
    assert "HDF4" in finding.message


def test_validate_local_missing_file(tmp_path):
    finding = validate_local(tmp_path / "nope.hdf")
    assert not finding.ok
    assert "not found" in finding.message


def test_validate_local_size_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr("polaris.acquisition.validate._geo_probe", lambda p: True)
    f = tmp_path / "granule.hdf"
    f.write_bytes(b"\x0e\x03\x13\x01" + b"\x00" * 50)
    finding = validate_local(f, expected_size=9999, strict_size=True)
    assert not finding.ok
    assert "size mismatch" in finding.message