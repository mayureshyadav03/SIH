"""NASA Earthdata authentication and HTTP session handling.

NASA data access (Earthdata Search, CMR, LAADS DAAC) is authenticated via
Earthdata Login (urs.earthdata.nasa.gov). Credentials are read from
environment variables (EARTHDATA_USERNAME / EARTHDATA_PASSWORD in .env) and
written to the standard ~/.netrc so `requests`/curl-based clients
authenticate transparently.

The exported `session()` follows the OAuth redirect chain that Earthdata
servers use: anonymous LAADS links -> urs login -> authorized content.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import requests

from polaris.config import pipeline

URS_HOST = "urs.earthdata.nasa.gov"
NETRC_PATH = Path.home() / ".netrc"


class EarthdataAuthError(RuntimeError):
    """Raised when Earthdata credentials are missing or rejected."""


def ensure_netrc(username: Optional[str] = None, password: Optional[str] = None) -> None:
    """Write u/p for urs.earthdata.nasa.gov into ~/.netrc (0600).

    Explicit args win; otherwise values are read from env/.env config.
    """
    username = username or pipeline.earthdata_username
    password = password or pipeline.earthdata_password
    if not username or not password:
        raise EarthdataAuthError(
            "Earthdata credentials not configured. "
            "Set EARTHDATA_USERNAME / EARTHDATA_PASSWORD in .env "
            "(register free at https://urs.earthdata.nasa.gov)."
        )

    netrc_entry = f"machine {URS_HOST} login {username} password {password}\n"
    lines: list[str] = []
    if NETRC_PATH.exists():
        lines = [
            line
            for line in NETRC_PATH.read_text().splitlines()
            if f"machine {URS_HOST}" not in line
        ]
    lines.append(netrc_entry.rstrip("\n"))
    NETRC_PATH.write_text("\n".join(lines) + "\n")
    NETRC_PATH.chmod(0o600)


def netrc_available() -> bool:
    if not NETRC_PATH.exists():
        return False
    for line in NETRC_PATH.read_text().splitlines():
        if f"machine {URS_HOST}" in line:
            return True
    return False


def session() -> requests.Session:
    """Build an authenticated requests.Session for NASA data services."""
    if not netrc_available():
        ensure_netrc()

    s = requests.Session()
    s.params.update({"dl": "1"})
    # requests consults ~/.netrc for basic auth against urs.earthdata.nasa.gov
    s.trust_env = True
    return s


def anonymized_href(href: str) -> str:
    """Strip credentials that may be embedded in a signed download URL."""
    return href.split("?")[0] if href else href


def auth_status() -> dict[str, object]:
    if netrc_available():
        return {"authenticated": True, "host": URS_HOST, "netrc": str(NETRC_PATH)}
    return {
        "authenticated": False,
        "hint": "run ensure_netrc() with EARTHDATA_USERNAME/PASSWORD set",
    }