"""Exposure status model: success | partial | failed, per-category OSM degradation, partial WorldPop (all fakes)."""
import pytest

from app.core.errors import ExternalSourceError
from app.services import exposure, worldpop
from app.services.osm import OsmData

from test_exposure_service import S, osm_data, pop, req, run


def osm_partial(failed=('buildings',)):
    """OSM answered for some categories only (as osm.fetch now returns it)."""
    d = osm_data()
    d.categories = {
        'facilities': {'status': 'success', 'cells': 1, 'cells_done': 1, 'elements': 1, 'seconds': 1.0, 'error': None},
        'roads': {'status': 'success', 'cells': 1, 'cells_done': 1, 'elements': 1, 'seconds': 2.0, 'error': None},
        'buildings': {'status': 'success', 'cells': 4, 'cells_done': 4, 'elements': 2, 'seconds': 9.0, 'error': None}}
    for name in failed:
        d.categories[name].update(status='failed', cells_done=1, elements=0,
                                  error={'code': 'osm_timeout', 'message': 'OpenStreetMap (Overpass) timed out.'})
        for key in {'buildings': ('buildings',), 'roads': ('roads',), 'facilities': ('health', 'education')}[name]:
            setattr(d, key, [])
    return d


def osm_partial_cells(key='buildings', pct=40.0):
    d = osm_partial(())
    d.categories[key].update(status='partial', cells_done=2, coverage_pct=pct,
                             error={'code': 'osm_budget_exhausted', 'message': 'The OpenStreetMap time budget for this category was used up.'})
    return d


def pop_partial(*_a, **_k):
    return worldpop.PopulationResult(
        estimate=250.0, year=2020, resolution='100m', dataset='WorldPop', api_version='v3', task_id=None,
        analysis_area_ha=123.0, simplification={'applied': True, 'vertices_before': 90000, 'vertices_after': 18000,
                                                'tolerance_m': 5, 'area_change_pct': -0.4, 'parts': 300},
        partial=True, chunks=10, chunks_failed=1, parts=300, coverage_pct=91.0,
        failures=[{'code': 'worldpop_http_error', 'message': 'x', 'parts': 30, 'http_status': 422}])


def boom(code='osm_unavailable'):
    def fail(*_a, **_k):
        raise ExternalSourceError('down', code=code)
    return fail


def test_buildings_timeout_returns_partial_osm_with_roads_and_health():
    r = run(osm_fetch=lambda b, s: osm_partial(('buildings',)))
    m = r['metrics']
    assert r['status'] == 'partial'
    assert r['sources']['openstreetmap']['status'] == 'partial'
    cats = r['sources']['openstreetmap']['details']['categories']
    assert cats['buildings']['status'] == 'failed' and cats['buildings']['error']['code'] == 'osm_timeout'
    assert cats['roads']['status'] == 'success' and cats['facilities']['status'] == 'success'
    assert m['buildings_intersecting']['value'] is None and m['buildings_intersecting']['coverage'] == 'unavailable'
    assert m['buildings_within_buffer']['coverage'] == 'unavailable'                    # unknown, NOT zero
    assert m['roads_km_intersecting']['value'] == pytest.approx(1.1, rel=0.1) and m['roads_km_intersecting']['coverage'] == 'mapped'
    assert m['health_intersecting']['value'] == 1
    assert m['population']['value'] == 321.0                                           # WorldPop unaffected
    assert any(w['code'] == 'osm_category_unavailable' for w in r['warnings'])
    assert not any(w['code'] == 'osm_no_data' and w['params'].get('category') == 'buildings' for w in r['warnings'])


def test_roads_unavailable_does_not_hide_buildings():
    r = run(osm_fetch=lambda b, s: osm_partial(('roads',)))
    m = r['metrics']
    assert m['roads_km_intersecting']['coverage'] == 'unavailable' and m['roads_km_intersecting']['value'] is None
    assert m['buildings_intersecting']['value'] == 1 and r['status'] == 'partial'


def test_facilities_unavailable_marks_health_and_education():
    r = run(osm_fetch=lambda b, s: osm_partial(('facilities',)))
    for key in ('health_intersecting', 'education_intersecting', 'health_within_buffer'):
        assert r['metrics'][key]['coverage'] == 'unavailable' and r['metrics'][key]['value'] is None
    assert r['metrics']['buildings_intersecting']['value'] == 1


def test_worldpop_partial_is_labelled_and_carries_geometry_metadata():
    r = run(pop_fn=pop_partial)
    p = r['metrics']['population']
    assert r['status'] == 'partial' and p['status'] == 'partial' and p['value'] == 250.0
    assert p['chunks'] == 10 and p['chunks_failed'] == 1 and p['coverage_pct'] == 91.0
    src = r['sources']['worldpop']
    assert src['status'] == 'partial' and src['details']['chunks'] == 10 and src['details']['simplification_applied'] is True
    assert src['details']['vertices_before'] == 90000 and src['details']['vertices_after'] == 18000
    assert src['details']['area_change_pct'] == -0.4 and src['details']['failures'][0]['http_status'] == 422
    assert any(w['code'] == 'worldpop_partial' for w in r['warnings'])


def test_worldpop_unavailable_with_osm_ok_is_partial_never_zero():
    r = run(pop_fn=boom('worldpop_payload_too_large'))
    assert r['status'] == 'partial' and r['metrics']['population']['value'] is None
    assert r['metrics']['population']['status'] == 'unavailable' and r['metrics']['buildings_intersecting']['value'] == 1


def test_osm_failed_with_worldpop_ok_is_partial():
    r = run(osm_fetch=boom())
    assert r['status'] == 'partial' and r['metrics']['population']['value'] == 321.0


def test_both_sources_unavailable_is_failed_but_still_returns_the_footprint():
    r = run(osm_fetch=boom(), pop_fn=boom('worldpop_http_error'))
    assert r['status'] == 'failed'
    assert r['metrics']['population']['value'] is None and r['metrics']['buildings_intersecting']['value'] is None
    assert r['metrics']['affected_area_ha'] > 0 and r['layers']['footprint']['features']          # EO result kept


def test_osm_failed_and_population_skipped_is_failed():
    r = run(osm_fetch=boom(), request=req(include_population=False), pop_fn=lambda *a, **k: pytest.fail('called'))
    assert r['status'] == 'failed'


def test_everything_ok_is_success_with_per_category_details():
    r = run(osm_fetch=lambda b, s: osm_partial(()))
    assert r['status'] == 'success' and r['sources']['openstreetmap']['status'] == 'success'


def test_non_success_results_are_never_cached():
    check = exposure._cacheable(S)
    assert not check({'status': 'partial'}) and not check({'status': 'failed'}) and check({'status': 'success'})


def test_response_model_accepts_failed_and_partial_source_states():
    from app.schemas.exposure import ExposureResponse
    r = run(osm_fetch=boom(), pop_fn=boom())
    assert ExposureResponse(**r).status == 'failed'
    r = run(pop_fn=pop_partial, osm_fetch=lambda b, s: osm_partial(('buildings',)))
    assert ExposureResponse(**r).sources['worldpop'].status == 'partial'


def test_category_partial_is_a_labelled_lower_bound_not_unavailable_and_not_zero():
    r = run(osm_fetch=lambda b, s: osm_partial_cells('buildings', 40.0))
    m = r['metrics']['buildings_intersecting']
    assert m['coverage'] == 'partial' and m['coverage_pct'] == 40.0 and m['value'] == 1
    assert r['status'] == 'partial' and r['sources']['openstreetmap']['status'] == 'partial'
    w = [x for x in r['warnings'] if x['code'] == 'osm_category_partial']
    assert w and w[0]['params']['key'] == 'buildings' and w[0]['params']['coverage'] == 40.0
    assert w[0]['params']['error_code'] == 'osm_budget_exhausted'
    assert not any(x['code'] == 'osm_category_unavailable' for x in r['warnings'])


def test_partial_with_nothing_found_stays_a_lower_bound_of_zero_not_no_data():
    d = osm_partial_cells('roads', 25.0)
    d.roads = []
    r = run(osm_fetch=lambda b, s: d)
    m = r['metrics']['roads_km_intersecting']
    assert m['coverage'] == 'partial' and m['value'] == 0.0
    assert not any(x['code'] == 'osm_no_data' and x['params'].get('category') == 'roads' for x in r['warnings'])


def test_csv_marks_partial_lower_bounds():
    r = run(osm_fetch=lambda b, s: osm_partial_cells('buildings', 40.0), pop_fn=pop_partial)
    rows = {row.split(',')[0]: row for row in r['exports']['csv'].splitlines()}
    assert ',partial,' in rows['buildings_intersecting'] and 'lower bound' in rows['buildings_intersecting']
    assert ',partial,' in rows['population_estimate']
