"""Wildfire smoke test against a RUNNING backend with real Earth Engine (and optionally the exposure step).

    python scripts/smoke_wildfire.py [--base http://localhost:8001] [--department Tolima] [--municipality "San Luis"]
                                     [--fire-date 2026-08-05] [--end-date 2026-08-15] [--exposure]

Exposure is only requested with --exposure (it calls Overpass and WorldPop through the backend). Standard library only.
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse

from _common import Timer, http, verdict


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:8001')
    ap.add_argument('--department', default='Tolima')
    ap.add_argument('--municipality', default='San Luis')
    ap.add_argument('--fire-date', default='2026-08-05')
    ap.add_argument('--end-date', default='2026-08-15')
    ap.add_argument('--exposure', action='store_true')
    a = ap.parse_args()
    body = {'department': a.department, 'municipality': a.municipality, 'fire_date': a.fire_date, 'analysis_end': a.end_date}

    code, out = http('GET', f'{a.base}/health?check_ee=true')
    print('health      ', code, out)
    if out.get('status') != 'ok':
        return verdict(False, 'Earth Engine not initialised (check EE_PROJECT / credentials on the backend)')
    code, out = http('GET', f'{a.base}/api/v1/hazards')
    print('hazards     ', code, [h['id'] for h in out] if isinstance(out, list) else out)
    code, out = http('POST', f'{a.base}/api/v1/wildfire/preflight', body)
    print('preflight   ', code, {k: out.get(k) for k in ('valid', 'pre_count', 'post_count', 'history_count', 'aoi_hectares')})
    if code != 200 or not out.get('valid'):
        return verdict(False, f"preflight blocked: {out.get('blocking_errors')}")
    with Timer() as t:
        code, out = http('POST', f'{a.base}/api/v1/wildfire/analyze', body)
    print(f'analyze      {code} in {t.seconds:.0f}s')
    if code != 200:
        return verdict(False, f'analyze failed: {out}')
    print('model       ', out['metadata'].get('model_version'))
    for row in out['area_hectares']:
        print(f"  >= {row['threshold']:.2f}  {row['hectares']:>12,.1f} ha  ({row['label']})")
    print('layers      ', [layer['id'] for layer in out['layers']])
    ok = True
    if a.exposure:
        ref = out.get('analysis_ref')
        if not ref:
            return verdict(False, 'the analysis returned no exposure reference')
        with Timer() as t2:
            code, ex = http('POST', f'{a.base}/api/v1/exposure/analyze', {'analysis_ref': ref, 'threshold': 0.72})
        print(f'exposure     {code} in {t2.seconds:.0f}s  status={ex.get("status")}')
        for key, src in (ex.get('sources') or {}).items():
            print(f'  source {key:<18} {src.get("status")}  {(src.get("error") or {}).get("code", "")}')
        ok = code == 200 and ex.get('status') in ('success', 'partial')
    return verdict(ok, 'Wildfire')


if __name__ == '__main__':
    sys.exit(main())
