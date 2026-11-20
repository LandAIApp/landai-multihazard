"""Shared helpers for the manual smoke scripts. These talk to REAL services: run them by hand, once, never in CI.

Secrets are read from the environment / backend/.env by the backend Settings object and are NEVER printed.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def settings():
    """Backend settings (reads backend/.env when present)."""
    from app.core.config import Settings
    env = ROOT / 'backend' / '.env'
    return Settings(_env_file=str(env) if env.exists() else None)


def square_footprint(lon: float, lat: float, side_m: float):
    """Square footprint centred on lon/lat. Returns (geometry in metric CRS, crs, geometry in WGS84)."""
    from shapely.geometry import Point, box
    from app.services import spatial
    crs = spatial.utm_epsg(lon, lat)
    c = spatial.to_metric(Point(lon, lat), crs)
    half = side_m / 2
    g = box(c.x - half, c.y - half, c.x + half, c.y + half)
    return g, crs, spatial.to_wgs84(g, crs)


def http(method: str, url: str, body: dict | None = None, timeout: int = 900):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b'{}')
        except ValueError:
            return e.code, {}


class Timer:
    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        self.seconds = time.time() - self.t0


def verdict(ok: bool, label: str) -> int:
    print(f"\n{'PASS' if ok else 'FAIL'}: {label}")
    return 0 if ok else 1
