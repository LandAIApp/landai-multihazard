"""REAL exposure smoke test: OSM + WorldPop through the shared exposure engine (no Earth Engine needed).

    python scripts/smoke_exposure.py                                  # 1.5 km square footprint near Ibagué
    python scripts/smoke_exposure.py --side-m 4000

Builds the exposure response with the real clients and prints overall status (success|partial|failed), each source's
status/diagnostics and the metrics. 'unavailable' never means zero.
"""
from __future__ import annotations

import argparse
import json
import sys

from _common import Timer, settings, square_footprint, verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--lon', type=float, default=-75.2322)
    ap.add_argument('--lat', type=float, default=4.4389)
    ap.add_argument('--side-m', type=float, default=1500)
    ap.add_argument('--buffer-m', type=float, default=500)
    a = ap.parse_args()
    from app.services import exposure, osm, worldpop
    from app.services import exposure_metrics
    st = settings()
    geom, crs, wgs = square_footprint(a.lon, a.lat, a.side_m)
    osm.clear_cache()
    worldpop.clear_cache()
    out: dict = {'sources': {}}
    ok = True

    with Timer() as t:
        try:
            data = osm.fetch(wgs.bounds, st)
            out['sources']['openstreetmap'] = {'status': data.status, 'categories': {
                k: {kk: vv for kk, vv in v.items() if kk != 'error'} | {'error': (v.get('error') or {}).get('code')}
                for k, v in data.categories.items()}}
            metrics = exposure_metrics.compute(data, geom, crs, buffer_m=a.buffer_m)
            out['metrics'] = {k: v for k, v in metrics.metrics.items()}
        except Exception as exc:  # noqa: BLE001 - diagnostic script
            out['sources']['openstreetmap'] = {'status': 'error', 'error': getattr(exc, 'code', type(exc).__name__)}
            ok = False
        try:
            pop = worldpop.estimate(geom, crs, st)
            out['sources']['worldpop'] = {'status': 'partial' if pop.partial else 'success', 'population': pop.estimate,
                                          'chunks': pop.chunks, 'chunks_failed': pop.chunks_failed,
                                          'coverage_pct': pop.coverage_pct, 'requests': pop.request_count,
                                          'simplification': pop.simplification}
        except Exception as exc:  # noqa: BLE001
            out['sources']['worldpop'] = {'status': 'error', 'error': getattr(exc, 'code', type(exc).__name__)}
            ok = False
    print(json.dumps(out, indent=2, default=str))
    print(f'elapsed {t.seconds:.1f}s   (shared engine module: {exposure.__name__})')
    statuses = {v['status'] for v in out['sources'].values()}
    print('overall:', 'success' if statuses <= {'success'} else ('failed' if statuses == {'error'} else 'partial'))
    return verdict('error' not in statuses or len(statuses) > 1, 'Exposure sources (at least one answered)')


if __name__ == '__main__':
    sys.exit(main())
