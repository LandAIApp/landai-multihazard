"""REAL Overpass smoke test: per-category resilience (facilities -> roads -> buildings).

    python scripts/smoke_overpass.py                       # 2 km square near Ibagué
    python scripts/smoke_overpass.py --lon -74.08 --lat 4.65 --side-m 6000

Prints, per category: status, cells done/total, elements, seconds, mirror that answered and error code.
Exit code 0 when at least one category succeeded (a partial answer is the designed degraded mode).
"""
from __future__ import annotations

import argparse
import sys

from _common import Timer, settings, square_footprint, verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--lon', type=float, default=-75.2322)
    ap.add_argument('--lat', type=float, default=4.4389)
    ap.add_argument('--side-m', type=float, default=2000)
    a = ap.parse_args()
    from app.core.errors import ExternalSourceError
    from app.services import osm
    st = settings()
    _g, _crs, wgs = square_footprint(a.lon, a.lat, a.side_m)
    print(f'Endpoint {st.overpass_endpoint}  fallbacks={st.overpass_fallback_endpoints}')
    print(f'Cells: facilities {st.overpass_facility_cell_km} km · roads {st.overpass_cell_km} km · buildings '
          f'{st.overpass_building_cell_km} km · budget {st.overpass_total_budget_s}s · max cells/category {st.overpass_max_cells}')
    osm.clear_cache()
    with Timer() as t:
        try:
            data = osm.fetch(wgs.bounds, st, on_progress=lambda d, n: print(f'  progress {d}/{n}'))
        except ExternalSourceError as exc:
            print(f'ALL CATEGORIES FAILED: {exc.code} {exc.message}')
            print('details:', exc.details)
            return verdict(False, 'Overpass')
    print(f'\noverall status: {data.status}   total {t.seconds:.1f}s   elements {data.element_count}')
    for name, info in data.categories.items():
        err = (info.get('error') or {}).get('code')
        print(f"  {name:<10} {info['status']:<8} cells {info.get('cells_done')}/{info.get('cells')}  "
              f"elements {info.get('elements')}  {info.get('seconds')}s  endpoint={info.get('endpoint')}  error={err}")
    print(f'buildings={len(data.buildings)} roads={len(data.roads)} health={len(data.health)} education={len(data.education)}')
    return verdict(any(c['status'] == 'success' for c in data.categories.values()), 'Overpass (at least one category)')


if __name__ == '__main__':
    sys.exit(main())
