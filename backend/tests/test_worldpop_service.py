"""WorldPop V3 client: synchronous contract, geometry preparation, chunking, 413/429/503 handling, partial results."""
import json
import math

import httpx
import pytest
from shapely.geometry import MultiPolygon, Polygon, box

from app.core.config import Settings
from app.core.errors import ExternalSourceError
from app.services import worldpop

CRS = 'EPSG:32618'
HAZARD = box(600000, 500000, 601000, 501000)          # 100 ha


def s(**kw):
    kw.setdefault('worldpop_retry_wait_s', 0.01)
    return Settings(_env_file=None, **kw)


def run(handler, settings=None, geom=HAZARD, **kw):
    worldpop.clear_cache()
    return worldpop.estimate(geom, CRS, settings or s(), transport=httpx.MockTransport(handler),
                             sleep=lambda _x: None, **kw)


def ok(total=123.45, **extra):
    return httpx.Response(200, json={'total_population': total, 'area_km2': 1.0, 'population_density': total,
                                     'data_year': 2020, 'data_source': 'WorldPop 100m',
                                     'processing_time_ms': 120, **extra})


def many_parts(n, size=30.0, gap=60.0):
    """n disjoint squares on a grid (a fragmented footprint)."""
    side = math.ceil(math.sqrt(n))
    parts = []
    for i in range(n):
        x, y = 600000 + (i % side) * gap, 500000 + (i // side) * gap
        parts.append(box(x, y, x + size, y + size))
    return MultiPolygon(parts)


# ---- V3 contract -----------------------------------------------------------------------------------------------
def test_v3_direct_success_posts_real_polygon_synchronously():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        body = json.loads(request.content)
        assert body['year'] == 2020 and 'resolution' not in body
        assert body['geojson']['geometry']['type'] == 'Polygon'
        return ok()

    result = run(handler)
    assert calls == [('POST', '/v3/population')]                      # one POST, no tasks, no polling
    assert result.estimate == pytest.approx(123.45, abs=0.06) and result.api_version == 'v3'
    assert result.year == 2020 and result.resolution == '100m' and result.task_id is None
    assert result.analysis_area_ha == 100.0 and not result.simplification['applied']
    assert result.data_year == 2020 and result.data_source == 'WorldPop 100m' and result.processing_time_ms == 120
    assert not result.partial and result.chunks == 1 and result.coverage_pct == 100.0


def test_default_configuration_is_v3():
    st = Settings(_env_file=None)
    assert st.worldpop_api_version == 'v3' and st.worldpop_base_url == 'https://api.worldpop.org'


def test_polygon_and_multipolygon_inputs():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content)['geojson']['geometry']['type'])
        return ok(10)

    run(handler, geom=HAZARD)
    run(handler, geom=MultiPolygon([box(600000, 500000, 600100, 500100), box(600500, 500500, 600600, 500600)]))
    assert seen == ['Polygon', 'MultiPolygon']


def test_year_comes_from_config_not_event_date():
    assert run(lambda r: ok(5), s(worldpop_year=2018)).year == 2018


def test_obsolete_versions_are_rejected_not_polled():
    with pytest.raises(ExternalSourceError) as exc:
        run(lambda r: ok(), s(worldpop_api_version='v2'))
    assert exc.value.code == 'worldpop_unsupported_version'


def test_malformed_responses_are_errors_not_zero():
    for response in (httpx.Response(200, text='<html>'), httpx.Response(200, json=[1, 2]),
                     httpx.Response(200, json={'status': 'ok'}), httpx.Response(200, json={'total_population': -4})):
        with pytest.raises(ExternalSourceError) as exc:
            run(lambda r, resp=response: resp)
        assert exc.value.code == 'worldpop_bad_response'


def test_api_key_header_only_when_configured():
    seen = {}

    def handler(request):
        seen['key'] = request.headers.get('x-api-key')
        return ok(1)

    run(handler)
    assert seen['key'] is None
    run(handler, s(worldpop_api_key='secret'))
    assert seen['key'] == 'secret'


def test_cache_avoids_second_request_and_is_keyed_by_geometry():
    count = []

    def handler(request):
        count.append(1)
        return ok(7)

    worldpop.clear_cache()
    t = httpx.MockTransport(handler)
    a = worldpop.estimate(HAZARD, CRS, s(), transport=t)
    b = worldpop.estimate(HAZARD, CRS, s(), transport=t)
    assert len(count) == 1 and b.from_cache and a.estimate == b.estimate == 7
    worldpop.estimate(box(600000, 500000, 600500, 500500), CRS, s(), transport=t)
    assert len(count) == 2


# ---- geometry preparation --------------------------------------------------------------------------------------
def test_overlapping_polygons_are_dissolved_never_double_counted():
    a, b = box(0, 0, 100, 100), box(50, 0, 150, 100)
    overlapping = MultiPolygon([a, b])                  # invalid on purpose (overlap)
    prepared = worldpop.prepare(overlapping, s())
    assert prepared.report['dissolved'] and prepared.report['parts'] == 1
    assert prepared.report['area_m2'] == pytest.approx(15000.0)       # union area, not 20000


def test_microscopic_fragments_are_dropped_with_report():
    geom = MultiPolygon([box(0, 0, 100, 100), box(500, 500, 502, 502)])     # 4 m2 sliver
    prepared = worldpop.prepare(geom, s())
    assert prepared.report['parts'] == 1 and prepared.report['parts_dropped'] == 1
    assert prepared.report['dropped_area_m2'] == pytest.approx(4.0)


def test_simplification_only_when_over_limit_and_reported():
    n = 400
    ring = [(600500 + 400 * math.cos(2 * math.pi * i / n) * (1 + 0.002 * (i % 2)),
             500500 + 400 * math.sin(2 * math.pi * i / n) * (1 + 0.002 * (i % 2))) for i in range(n)]
    poly = Polygon(ring)
    report = worldpop.prepare(poly, s(worldpop_max_vertices=100)).report
    assert report['applied'] and report['vertices_after'] <= 100 and report['vertices_before'] > 100
    assert abs(report['area_change_pct']) < 5
    assert not worldpop.prepare(poly, s()).report['applied']


def test_prepare_geometry_returns_wgs84():
    geom, report = worldpop.prepare_geometry(HAZARD, CRS, s())
    minx, miny, maxx, maxy = geom.bounds
    assert -80 < minx < maxx < -70 and 0 < miny < maxy < 10 and report['parts'] == 1


# ---- chunking ----------------------------------------------------------------------------------------------------
def test_fragmented_footprint_is_chunked_into_disjoint_groups_and_summed():
    geom = many_parts(25)
    posted = []

    def handler(request):
        gj = json.loads(request.content)['geojson']['geometry']
        n = len(gj['coordinates']) if gj['type'] == 'MultiPolygon' else 1
        posted.append(n)
        return ok(n * 2.0)

    result = run(handler, s(worldpop_chunk_parts=10), geom=geom)
    assert posted == [10, 10, 5] and result.chunks == 3 and result.request_count == 3
    assert result.estimate == 50.0 and not result.partial and result.parts == 25       # 25 parts x 2


def test_too_many_chunks_is_unavailable_not_zero():
    with pytest.raises(ExternalSourceError) as exc:
        run(lambda r: ok(), s(worldpop_chunk_parts=1, worldpop_max_chunks=5), geom=many_parts(25))
    assert exc.value.code == 'worldpop_geometry_too_complex'


# ---- 413 / 429 / 503 -------------------------------------------------------------------------------------------
def test_413_splits_the_group_and_succeeds():
    geom = many_parts(8)

    def handler(request):
        gj = json.loads(request.content)['geojson']['geometry']
        n = len(gj['coordinates']) if gj['type'] == 'MultiPolygon' else 1
        if n > 2:
            return httpx.Response(413)
        return ok(n)

    result = run(handler, geom=geom)
    assert result.estimate == 8.0 and not result.partial and result.request_count > 1


def test_413_on_a_single_part_is_unavailable_never_zero():
    with pytest.raises(ExternalSourceError) as exc:
        run(lambda r: httpx.Response(413))
    assert exc.value.code == 'worldpop_payload_too_large'


def test_429_retries_once_then_fails():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, headers={'retry-after': '1'})

    with pytest.raises(ExternalSourceError) as exc:
        run(handler)
    assert exc.value.code == 'worldpop_rate_limited' and len(calls) == 2           # one retry, not a hammering loop


def test_429_then_success():
    state = {'n': 0}

    def handler(request):
        state['n'] += 1
        return httpx.Response(429) if state['n'] == 1 else ok(9)

    assert run(handler).estimate == 9.0


def test_503_retries_once_then_fails_and_stops_asking():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)

    with pytest.raises(ExternalSourceError) as exc:
        run(handler, s(worldpop_chunk_parts=1), geom=many_parts(6))
    assert exc.value.code == 'worldpop_http_error' and exc.value.details['http_status'] == 503
    assert len(calls) == 2                                      # the service is down: remaining groups are not attempted


def test_timeout_is_reported():
    def handler(request):
        raise httpx.ReadTimeout('slow')

    with pytest.raises(ExternalSourceError) as exc:
        run(handler)
    assert exc.value.code == 'worldpop_timeout'


# ---- partial results ---------------------------------------------------------------------------------------------
def test_partial_result_when_enough_area_answered_is_labelled():
    geom = many_parts(10)
    state = {'n': 0}

    def handler(request):
        state['n'] += 1
        return httpx.Response(422) if state['n'] == 5 else ok(10)       # one group of 1 part of 10 fails

    result = run(handler, s(worldpop_chunk_parts=1, worldpop_min_partial_coverage_pct=80), geom=geom)
    assert result.partial and result.chunks == 10 and result.chunks_failed == 1
    assert result.estimate == 90.0 and result.coverage_pct == 90.0 and result.failures[0]['http_status'] == 422


def test_partial_below_coverage_threshold_is_unavailable():
    geom = many_parts(10)
    state = {'n': 0}

    def handler(request):
        state['n'] += 1
        return ok(10) if state['n'] <= 3 else httpx.Response(422)

    with pytest.raises(ExternalSourceError) as exc:
        run(handler, s(worldpop_chunk_parts=1, worldpop_min_partial_coverage_pct=80), geom=geom)
    assert exc.value.details['chunks_failed'] == 7 and exc.value.details['coverage_pct'] == 30.0


def test_partial_is_not_cached_but_successful_chunks_are():
    geom = many_parts(4)
    state = {'fail': True, 'posts': 0}

    def handler(request):
        state['posts'] += 1
        gj = json.loads(request.content)['geojson']['geometry']
        first = gj['coordinates'][0][0][0] if gj['type'] == 'Polygon' else None
        if state['fail'] and state['posts'] == 3:
            return httpx.Response(422)
        return ok(5)

    worldpop.clear_cache()
    t = httpx.MockTransport(handler)
    st = s(worldpop_chunk_parts=1, worldpop_min_partial_coverage_pct=50)
    first = worldpop.estimate(geom, CRS, st, transport=t, sleep=lambda _x: None)
    assert first.partial and first.estimate == 15.0
    state['fail'] = False
    before = state['posts']
    second = worldpop.estimate(geom, CRS, st, transport=t, sleep=lambda _x: None)
    assert not second.partial and second.estimate == 20.0
    assert state['posts'] - before == 1                           # only the failed group was asked again
