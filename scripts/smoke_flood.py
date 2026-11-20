"""Flood smoke test against a RUNNING backend with real Earth Engine (and optionally the exposure step).

    python scripts/smoke_flood.py --pre-start 2026-01-01 --pre-end 2026-01-26 --post-start 2026-02-02 --post-end 2026-02-15 \
        [--department Cordoba] [--municipality Monteria] [--base http://localhost:8001] [--exposure]

Pick dates around a REAL, known flood: the module is experimental and has no accuracy metrics. The ratio domain is
'linear' (default); pass --ratio reference only to compare (it inverts the signal).
"""
from __future__ import annotations

import argparse
import sys

from _common import Timer, http, verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:8001')
    ap.add_argument('--department', default='Cordoba')
    ap.add_argument('--municipality', default='Monteria')
    ap.add_argument('--pre-start', required=True)
    ap.add_argument('--pre-end', required=True)
    ap.add_argument('--post-start', required=True)
    ap.add_argument('--post-end', required=True)
    ap.add_argument('--ratio', choices=['linear', 'reference'], default='linear')
    ap.add_argument('--exposure', action='store_true')
    a = ap.parse_args()
    body = {'hazard': 'flood', 'department': a.department, 'municipality': a.municipality,
            'params': {'pre_start': a.pre_start, 'pre_end': a.pre_end, 'post_start': a.post_start,
                       'post_end': a.post_end, 'ratio_domain': a.ratio}}
    code, out = http('GET', f'{a.base}/health?check_ee=true')
    print('health      ', code, out)
    if out.get('status') != 'ok':
        return verdict(False, 'Earth Engine not initialised')
    code, out = http('POST', f'{a.base}/api/v1/analysis/preflight', body)
    print('preflight   ', code, {k: out.get(k) for k in ('valid', 'status', 'aoi_hectares', 'counts')})
    if code != 200 or not out.get('valid'):
        return verdict(False, f"preflight blocked: {out.get('blocking_errors')}")
    with Timer() as t:
        code, out = http('POST', f'{a.base}/api/v1/analysis/run', body)
    print(f'run          {code} in {t.seconds:.0f}s')
    if code != 200:
        return verdict(False, f'run failed: {out}')
    stats = out.get('statistics', {})
    print('validation  ', out.get('validation_status'), '| method', (out.get('methodology') or {}).get('version'))
    print('statistics  ', {k: stats.get(k) for k in ('flood_area_ha', 'flood_pct_of_aoi', 'otsu_threshold', 'ratio_domain')})
    print('layers      ', [layer.get('id') for layer in out.get('layers', [])])
    print('warnings    ', [w.get('code') for w in out.get('warnings', [])])
    ok = True
    if a.exposure:
        ref = out.get('footprint_reference')
        with Timer() as t2:
            code, ex = http('POST', f'{a.base}/api/v1/exposure/analyze', {'analysis_ref': ref})
        print(f'exposure     {code} in {t2.seconds:.0f}s  status={ex.get("status")}')
        ok = code == 200 and ex.get('status') in ('success', 'partial')
    return verdict(ok, 'Flood')


if __name__ == '__main__':
    sys.exit(main())
