"""REAL WorldPop V3 smoke test: verifies the API contract this backend assumes.

    python scripts/smoke_worldpop_v3.py                      # 1 km square near Ibagué + a fragmented footprint
    python scripts/smoke_worldpop_v3.py --lon -75.23 --lat 4.44 --side-m 3000 --fragments 150

1. RAW call: POST {base}/v3/population with a plain polygon; prints the status, headers of interest and JSON keys.
2. Backend client call with a fragmented footprint (exercises dissolve / simplify / chunking / 413 splitting).
The API key (WORLDPOP_API_KEY) is used if configured but is never printed. Run once; do not loop.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx

from _common import Timer, settings, square_footprint, verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--lon', type=float, default=-75.2322)
    ap.add_argument('--lat', type=float, default=4.4389)
    ap.add_argument('--side-m', type=float, default=1000)
    ap.add_argument('--fragments', type=int, default=60, help='number of disjoint squares in the fragmented test')
    a = ap.parse_args()
    from shapely.geometry import MultiPolygon, box, mapping
    from app.core.errors import ExternalSourceError
    from app.services import spatial, worldpop
    st = settings()
    print(f'WorldPop base URL : {st.worldpop_base_url}   api_version={st.worldpop_api_version}   year={st.worldpop_year}')
    print(f'API key configured: {bool(st.worldpop_api_key)} (value never printed)')
    ok = True

    geom, crs, wgs = square_footprint(a.lon, a.lat, a.side_m)
    headers = {'X-API-Key': st.worldpop_api_key} if st.worldpop_api_key else {}
    body = {'geojson': {'type': 'Feature', 'properties': {}, 'geometry': mapping(wgs)}, 'year': st.worldpop_year}
    print(f'\n== 1. RAW POST {st.worldpop_base_url}/v3/population  ({geom.area / 10000:.1f} ha)')
    with Timer() as t:
        try:
            r = httpx.post(f'{st.worldpop_base_url}/v3/population', json=body, headers=headers, timeout=st.worldpop_http_timeout_s)
            print(f'HTTP {r.status_code} in {t.seconds if hasattr(t, "seconds") else 0:.1f}s')
            print('content-type:', r.headers.get('content-type'))
            try:
                payload = r.json()
                print('JSON keys   :', sorted(payload) if isinstance(payload, dict) else type(payload).__name__)
                print('total_population:', payload.get('total_population') if isinstance(payload, dict) else None)
                ok &= r.status_code == 200 and isinstance(payload, dict) and 'total_population' in payload
            except ValueError:
                print('Body is not JSON:', r.text[:200])
                ok = False
        except httpx.HTTPError as exc:
            print('Network error:', type(exc).__name__)
            ok = False

    print(f'\n== 2. Backend client, fragmented footprint ({a.fragments} parts)')
    minx, miny, maxx, maxy = geom.bounds
    side = max(int(a.fragments ** 0.5) + 1, 2)
    step = (maxx - minx) / side
    parts = [box(minx + (i % side) * step, miny + (i // side) * step, minx + (i % side) * step + step * 0.6,
                 miny + (i // side) * step + step * 0.6) for i in range(a.fragments)]
    frag = MultiPolygon(parts)
    worldpop.clear_cache()
    with Timer() as t2:
        try:
            res = worldpop.estimate(frag, crs, st)
            print(f'estimate={res.estimate:,.0f} people  partial={res.partial}  chunks={res.chunks} (failed {res.chunks_failed})  '
                  f'requests={res.request_count}  coverage={res.coverage_pct}%  parts={res.parts}')
            print('simplification :', res.simplification)
            print('failures       :', res.failures)
            ok &= res.estimate >= 0
        except ExternalSourceError as exc:
            print(f'FAILED code={exc.code} message={exc.message}  details={json.dumps(exc.details, default=str)[:400]}')
            ok = False
    print(f'elapsed {t2.seconds:.1f}s')
    return verdict(ok, 'WorldPop V3 contract')


if __name__ == '__main__':
    sys.exit(main())
