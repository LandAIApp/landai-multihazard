"""Overpass retrieval/parsing with a mocked HTTP transport (no network): categories degrade INDEPENDENTLY."""
import re
from urllib.parse import unquote_plus

import httpx
import pytest
from shapely.geometry import box

from app.core.config import Settings
from app.core.errors import ExternalSourceError
from app.core.gate import reset_gates
from app.services import osm

BOUNDS = (-74.01, 4.60, -74.00, 4.61)
BIG = (-74.10, 4.50, -74.00, 4.60)           # ~11 km square


def settings(**kw) -> Settings:
    kw.setdefault('overpass_fallback_pause_s', 0)
    kw.setdefault('overpass_cell_pause_s', 0)
    return Settings(_env_file=None, **kw)


def square(lon, lat, d=0.0002):
    pts = [(lon, lat), (lon + d, lat), (lon + d, lat + d), (lon, lat + d), (lon, lat)]
    return [{'lon': x, 'lat': y} for x, y in pts]


BUILDINGS = [
    {'type': 'way', 'id': 1, 'tags': {'building': 'house'}, 'geometry': square(-74.005, 4.605)},
    {'type': 'way', 'id': 1, 'tags': {'building': 'house'}, 'geometry': square(-74.005, 4.605)},  # duplicate
    {'type': 'way', 'id': 4, 'tags': {'amenity': 'school', 'building': 'school'}, 'geometry': square(-74.007, 4.607)},
    {'type': 'relation', 'id': 6, 'tags': {'building': 'yes'}, 'members': []},
]
ROADS = [{'type': 'way', 'id': 2, 'tags': {'highway': 'residential'},
          'geometry': [{'lon': -74.01, 'lat': 4.6}, {'lon': -74.0, 'lat': 4.61}]}]
FACILITIES = [
    {'type': 'node', 'id': 3, 'lat': 4.603, 'lon': -74.004, 'tags': {'amenity': 'hospital', 'name': 'H'}},
    {'type': 'way', 'id': 4, 'tags': {'amenity': 'school', 'building': 'school'}, 'geometry': square(-74.007, 4.607)},
    {'type': 'way', 'id': 5, 'tags': {'barrier': 'fence'}, 'geometry': square(-74.007, 4.607)},
]
BY_CATEGORY = {'facilities': FACILITIES, 'roads': ROADS, 'buildings': BUILDINGS}


def body_of(request: httpx.Request) -> str:
    return unquote_plus(request.content.decode())


def category_of(request: httpx.Request) -> str:
    body = body_of(request)
    if '["building"]' in body:
        return 'buildings'
    if '["highway"' in body:
        return 'roads'
    return 'facilities'


def is_count(request: httpx.Request) -> bool:
    return 'out count' in body_of(request)


def router(overrides=None, calls=None, total='10'):
    """Handler: answers every category with its elements; ``overrides[category]`` may be a status code or a callable."""
    overrides = overrides or {}

    def handler(request: httpx.Request):
        category = category_of(request)
        if calls is not None:
            calls.append((category, 'count' if is_count(request) else 'data', request.url.host))
        override = overrides.get(category)
        if callable(override):
            return override(request)
        if isinstance(override, int):
            return httpx.Response(override)
        if is_count(request):
            return httpx.Response(200, json={'elements': [{'type': 'count', 'tags': {'total': total}}]})
        return httpx.Response(200, json={'elements': BY_CATEGORY[category]})
    return handler


def fresh():
    osm.clear_cache()
    reset_gates()


def run(handler, s=None, bounds=BOUNDS, **kw):
    return osm.fetch(bounds, s or settings(), transport=httpx.MockTransport(handler), sleep=lambda _x: None, **kw)


# ---- parsing --------------------------------------------------------------------------------------------------
def test_parse_dedupes_and_categorises():
    data = osm.parse_elements(BUILDINGS + ROADS + FACILITIES)
    assert len(data.buildings) == 2            # house + school building, duplicate removed
    assert len(data.roads) == 1 and len(data.health) == 1
    assert len(data.education) == 1            # the school is both a building and an education facility
    assert data.skipped_other == 1 and data.skipped_relations == 1


def test_parse_only_keeps_the_requested_category():
    data = osm.parse_elements(FACILITIES, only=('health', 'education'))
    assert len(data.health) == 1 and len(data.education) == 1 and data.buildings == []   # school building NOT a building here


def test_relation_multipolygon_is_assembled():
    outer = [{'lon': 0, 'lat': 0}, {'lon': 0.001, 'lat': 0}, {'lon': 0.001, 'lat': 0.001},
             {'lon': 0, 'lat': 0.001}, {'lon': 0, 'lat': 0}]
    rel = {'type': 'relation', 'id': 9, 'tags': {'building': 'yes', 'type': 'multipolygon'},
           'members': [{'type': 'way', 'role': 'outer', 'geometry': outer}]}
    data = osm.parse_elements([rel])
    assert len(data.buildings) == 1 and data.buildings[0].geom.geom_type == 'Polygon'


# ---- queries are separate per category ---------------------------------------------------------------------------
def test_each_category_has_its_own_bounded_query():
    s = settings()
    facilities = osm.build_queries(BOUNDS, s, 'facilities')[1]
    roads = osm.build_queries(BOUNDS, s, 'roads')[1]
    buildings = osm.build_queries(BOUNDS, s, 'buildings')[1]
    assert 'amenity' in facilities and 'highway' not in facilities and '"building"' not in facilities
    assert 'highway' in roads and 'amenity' not in roads and '"building"' not in roads
    assert '"building"' in buildings and 'highway' not in buildings and 'amenity' not in buildings
    for query in (facilities, roads, buildings):
        assert 'out tags geom' in query and '4.600000,-74.010000,4.610000,-74.000000' in query
        assert f'[timeout:{s.overpass_query_timeout_s}]' in query and 'maxsize' in query
    assert 'out count' in osm.build_queries(BOUNDS, s, 'roads')[0]


# ---- success, cache -------------------------------------------------------------------------------------------------
def test_fetch_ok_requests_categories_separately_in_priority_order_and_caches():
    fresh()
    calls = []
    s = settings()
    first = run(router(calls=calls), s)
    assert [c[0] for c in calls if c[1] == 'data'] == ['facilities', 'roads', 'buildings']      # priority order
    assert first.status == 'success' and not first.from_cache
    assert len(first.buildings) == 2 and len(first.roads) == 1 and len(first.health) == 1 and len(first.education) == 1
    assert set(first.categories) == {'facilities', 'roads', 'buildings'}
    assert all(c['status'] == 'success' for c in first.categories.values())
    n = len(calls)
    second = run(router(calls=calls), s)
    assert second.from_cache and len(calls) == n                                                    # served from cache


def test_requests_are_posts_with_user_agent():
    fresh()
    seen = []

    def handler(request):
        seen.append(request)
        return router()(request)

    run(handler)
    assert all(r.method == 'POST' for r in seen) and 'LandAI' in seen[0].headers['user-agent']


def test_empty_valid_category_is_success_not_failure():
    fresh()
    data = run(router({'buildings': lambda r: httpx.Response(200, json={'elements': [{'type': 'count', 'tags': {'total': '0'}}]})
                       if is_count(r) else httpx.Response(200, json={'elements': []})}))
    assert data.status == 'success' and data.buildings == [] and data.categories['buildings']['elements'] == 0
    assert data.unavailable_keys() == set()


# ---- CATEGORY INDEPENDENCE (the core requirement) -----------------------------------------------------------------
def test_buildings_timeout_still_returns_partial_osm_with_facilities_and_roads():
    fresh()
    data = run(router({'buildings': 504}), settings(overpass_fallback_endpoints=''))
    assert data.status == 'partial'
    assert data.categories['facilities']['status'] == 'success' and data.categories['roads']['status'] == 'success'
    assert data.categories['buildings']['status'] == 'failed'
    assert data.categories['buildings']['error']['code'] == 'osm_timeout'
    assert len(data.roads) == 1 and len(data.health) == 1 and data.buildings == []
    assert data.unavailable_keys() == {'buildings'}                                                  # unknown, NOT zero


def test_roads_failure_keeps_buildings_and_facilities():
    fresh()
    data = run(router({'roads': 503}), settings(overpass_fallback_endpoints=''))
    assert data.status == 'partial' and data.unavailable_keys() == {'roads'}
    assert len(data.buildings) == 2 and len(data.health) == 1


def test_facilities_failure_keeps_roads_and_buildings():
    fresh()
    data = run(router({'facilities': 504}), settings(overpass_fallback_endpoints=''))
    assert data.unavailable_keys() == {'health', 'education'} and len(data.roads) == 1 and len(data.buildings) == 2


def test_every_category_failing_raises_with_per_category_details():
    fresh()
    with pytest.raises(ExternalSourceError) as exc:
        run(lambda r: httpx.Response(504), settings(overpass_fallback_endpoints=''))
    assert exc.value.code == 'osm_timeout'
    assert set(exc.value.details['categories']) == {'facilities', 'roads', 'buildings'}


def test_runtime_remark_marks_only_that_category_incomplete():
    fresh()
    bad = {'buildings': lambda r: httpx.Response(200, json={'elements': [], 'remark': 'runtime error: Query timed out'})}
    data = run(router(bad), settings(overpass_fallback_endpoints=''))
    assert data.categories['buildings']['error']['code'] == 'osm_incomplete' and data.status == 'partial'


# ---- errors, mirrors, rate limits --------------------------------------------------------------------------------
@pytest.mark.parametrize('status,code', [(429, 'osm_rate_limited'), (504, 'osm_timeout'), (503, 'osm_unavailable')])
def test_http_errors_map_to_codes_without_retry_on_a_single_instance(status, code):
    fresh()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    with pytest.raises(ExternalSourceError) as exc:
        run(handler, settings(overpass_fallback_endpoints='', overpass_rate_limit_retries=0))
    assert exc.value.code == code and len(calls) == 3          # one attempt per category, never a retry loop


def test_timeout_exception_maps_to_osm_timeout():
    fresh()

    def handler(request):
        raise httpx.ReadTimeout('slow')

    with pytest.raises(ExternalSourceError) as exc:
        run(handler, settings(overpass_fallback_endpoints=''))
    assert exc.value.code == 'osm_timeout'


def test_fallback_mirror_is_used_and_remembered():
    fresh()
    calls = []

    def handler(request):
        if request.url.host == 'overpass-api.de':
            return httpx.Response(504)
        return router()(request)

    s = settings(overpass_fallback_endpoints='https://mirror.example.org/api/interpreter')
    data = run(lambda r: (calls.append(r.url.host), handler(r))[1], s)
    assert data.status == 'success' and data.endpoint == 'https://mirror.example.org/api/interpreter'
    assert calls.count('overpass-api.de') == 1             # the dead main server is asked once, not once per category


def test_all_instances_failing_tries_each_mirror_once_per_category():
    fresh()
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(504)

    s = settings(overpass_fallback_endpoints='https://m1.example.org/x,https://m2.example.org/x')
    with pytest.raises(ExternalSourceError) as exc:
        run(handler, s)
    assert exc.value.code == 'osm_timeout'
    assert hosts == ['overpass-api.de', 'm1.example.org', 'm2.example.org'] * 3


def test_rate_limit_waits_retry_after_and_asks_the_same_server_again():
    fresh()
    sleeps, hosts = [], []
    state = {'n': 0}

    def handler(request):
        hosts.append(request.url.host)
        state['n'] += 1
        if state['n'] == 1:
            return httpx.Response(429, headers={'Retry-After': '7'})
        return router()(request)

    s = settings(overpass_fallback_endpoints='https://mirror.example.org/x')
    data = osm.fetch(BOUNDS, s, transport=httpx.MockTransport(handler), sleep=lambda sec: sleeps.append(sec))
    assert 7.0 in sleeps and set(hosts) == {'overpass-api.de'} and data.status == 'success'


def test_rate_limit_retries_are_bounded_then_the_mirror_is_used():
    fresh()
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(429) if request.url.host == 'overpass-api.de' else router()(request)

    s = settings(overpass_fallback_endpoints='https://mirror.example.org/x', overpass_rate_limit_retries=2)
    run(handler, s)
    assert hosts.count('overpass-api.de') == 3 and 'mirror.example.org' in hosts           # 1 try + 2 waits, then mirror


def test_size_limit_is_not_retried_on_mirrors_and_only_hits_that_category():
    fresh()
    hosts = []

    def too_many(request):
        hosts.append(request.url.host)
        return httpx.Response(200, json={'elements': [{'type': 'count', 'tags': {'total': '999999999'}}]})

    s = settings(overpass_fallback_endpoints='https://m1.example.org/x', overpass_max_elements=1000)
    data = run(router({'buildings': too_many}), s)
    assert hosts == ['overpass-api.de']                                                      # not retried on the mirror
    assert data.categories['buildings']['error']['code'] == 'osm_too_many_elements' and data.status == 'partial'
    assert data.unavailable_keys() == {'buildings'}


# ---- cells ---------------------------------------------------------------------------------------------------------
def test_plan_cells_small_bbox_is_one_query_and_big_is_split():
    s = settings()
    assert osm.plan_cells(BOUNDS, s) == [BOUNDS]
    cells = osm.plan_cells(BIG, settings(overpass_cell_km=3.0))
    assert len(cells) >= 9 and all(c[0] >= BIG[0] and c[2] <= BIG[2] for c in cells)


def test_plan_cells_drops_cells_outside_the_region():
    s = settings(overpass_cell_km=3.0)
    allc = osm.plan_cells(BIG, s)
    some = osm.plan_cells(BIG, s, region=box(-74.10, 4.50, -74.07, 4.53))
    assert 0 < len(some) < len(allc)


def test_buildings_use_smaller_cells_than_roads_and_facilities():
    s = settings()
    nb, nr, nf = (len(osm.plan_cells(BIG, s, None, osm.category_cell_km(c, s))) for c in ('buildings', 'roads', 'facilities'))
    assert nb > nr >= nf


def _cell_handler(calls=None):
    """One building way per cell + a shared way (same id) returned by every cell."""
    def data_for(request):
        body = body_of(request)
        m = re.search(r'\((-?\d+\.\d+),(-?\d+\.\d+),(-?\d+\.\d+),(-?\d+\.\d+)\)', body)
        s_, w_ = (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)
        return httpx.Response(200, json={'elements': [
            {'type': 'way', 'id': int(abs(s_ * 1000)) * 1000 + int(abs(w_ * 1000)), 'tags': {'building': 'yes'},
             'geometry': [{'lat': s_ + 0.001, 'lon': w_ + 0.001}, {'lat': s_ + 0.001, 'lon': w_ + 0.002},
                          {'lat': s_ + 0.002, 'lon': w_ + 0.002}, {'lat': s_ + 0.001, 'lon': w_ + 0.001}]},
            {'type': 'way', 'id': 777, 'tags': {'building': 'yes'},
             'geometry': [{'lat': 4.55, 'lon': -74.05}, {'lat': 4.55, 'lon': -74.0499},
                          {'lat': 4.5501, 'lon': -74.0499}, {'lat': 4.55, 'lon': -74.05}]}]})

    def handler(request):
        if calls is not None:
            calls.append(category_of(request))
        if category_of(request) != 'buildings':
            return httpx.Response(200, json={'elements': []})
        return data_for(request)
    return handler


def test_fetch_in_cells_merges_dedupes_and_caches_per_category_cell():
    fresh()
    calls = []
    s = settings()
    data = run(_cell_handler(calls), s, BIG)
    plans = [len(osm.plan_cells(BIG, s, None, osm.category_cell_km(c, s))) for c in osm.CATEGORIES]
    expected = sum(plans)
    singles = sum(1 for n in plans if n == 1)                                     # a one-cell category gets a cheap count query first
    assert data.cells == expected and len(calls) == expected + singles
    assert len([f for f in data.buildings if f.key == ('way', 777)]) == 1         # way seen in every cell: counted once
    again = run(_cell_handler(calls), s, BIG)
    assert len(calls) == expected + singles and again.from_cache


def test_too_many_cells_makes_only_that_category_unavailable():
    fresh()
    calls = []
    s = settings(overpass_max_cells=6)               # buildings (3 km cells over ~11 km) exceed it, roads/facilities do not
    data = run(_cell_handler(calls), s, BIG)
    assert data.categories['buildings']['status'] == 'failed'
    assert data.categories['buildings']['error']['code'] == 'osm_too_many_elements'
    assert data.categories['roads']['status'] == 'success' and 'buildings' not in calls     # no request wasted on it
    assert data.status == 'partial'


def test_failed_cell_stops_its_category_and_a_retry_resumes_from_the_cache():
    fresh()
    s = settings(overpass_fallback_endpoints='', overpass_building_cell_km=3.0)
    state = {'building_calls': 0}

    def flaky(request):
        if category_of(request) == 'buildings':
            state['building_calls'] += 1
            if state['building_calls'] >= 3:
                return httpx.Response(504)
        return httpx.Response(200, json={'elements': []})

    data = run(flaky, s, BIG)
    info = data.categories['buildings']
    assert info['status'] == 'partial' and info['cells_done'] == 2 and info['cells'] >= 9     # kept, labelled partial
    assert 0 < info['coverage_pct'] < 100 and data.partial_keys() == {'buildings': info['coverage_pct']}
    assert 'buildings' not in data.unavailable_keys() and data.status == 'partial'
    state['building_calls'] = 0
    resumed = run(lambda r: (state.__setitem__('building_calls', state['building_calls'] + 1) or
                             httpx.Response(200, json={'elements': []})), s, BIG)
    assert resumed.status == 'success' and state['building_calls'] == info['cells'] - 2     # first 2 cells from the cache


def test_time_budget_exhaustion_degrades_the_last_categories_only():
    fresh()
    now = {'t': 0.0}

    def handler(request):
        now['t'] += 100.0                            # every request "takes" 100 s
        return router()(request)

    s = settings(overpass_total_budget_s=350)
    data = osm.fetch(BOUNDS, s, transport=httpx.MockTransport(handler), sleep=lambda _x: None, clock=lambda: now['t'])
    assert data.categories['facilities']['status'] == 'success' and data.categories['roads']['status'] == 'success'
    assert data.categories['buildings']['status'] == 'failed'
    assert data.categories['buildings']['error']['code'] == 'osm_budget_exhausted'


def test_a_slow_category_cannot_starve_the_next_one():
    fresh()
    now = {'t': 0.0}
    calls = []

    def handler(request):
        cat = category_of(request)
        calls.append(cat)
        now['t'] += 100.0 if cat == 'roads' else 1.0           # roads are painfully slow
        return httpx.Response(200, json={'elements': BY_CATEGORY[cat] if not is_count(request) else []})

    s = settings(overpass_road_budget_s=150, overpass_cell_km=3.0, overpass_building_cell_km=20.0,
                 overpass_facility_cell_km=20.0, overpass_total_budget_s=420)
    data = osm.fetch(BIG, s, transport=httpx.MockTransport(handler), sleep=lambda _x: None, clock=lambda: now['t'])
    roads = data.categories['roads']
    assert roads['status'] == 'partial' and roads['cells_done'] == 3 < roads['cells']      # capped (150 s + rolled-over time)
    assert roads['error']['code'] == 'osm_budget_exhausted'
    assert data.categories['buildings']['status'] == 'success'                             # still got its turn
    assert data.categories['facilities']['status'] == 'success'


def test_cells_with_most_affected_area_are_requested_first_and_bbox_is_shrunk():
    fresh()
    boxes = []

    def handler(request):
        m = re.search(r'\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\)', body_of(request))
        boxes.append(tuple(float(v) for v in m.groups()))
        return httpx.Response(200, json={'elements': []})

    s = settings(overpass_building_cell_km=3.0, overpass_cell_km=30.0, overpass_facility_cell_km=30.0)
    region = box(-74.0100, 4.5100, -74.0020, 4.5180)        # a small patch inside the big bbox (south-east corner)
    osm.fetch(BIG, s, transport=httpx.MockTransport(handler), region=region, sleep=lambda _x: None)
    b = [bb for bb in boxes]
    south, west, north, east = b[-1]
    assert all(-74.0101 <= bb[1] and bb[3] <= -74.0019 for bb in b if bb in b)        # nothing outside the region box
    assert (north - south) < 0.03 and (east - west) < 0.03                               # shrunk, not the whole 3 km cell


def test_partial_coverage_is_weighted_by_affected_area():
    fresh()
    s = settings(overpass_fallback_endpoints='', overpass_building_cell_km=5.0, overpass_cell_km=30.0,
                 overpass_facility_cell_km=30.0)
    region = box(-74.10, 4.50, -74.00, 4.60)                          # whole bbox is affected
    state = {'n': 0}

    def handler(request):
        if category_of(request) == 'buildings':
            state['n'] += 1
            if state['n'] > 2:
                return httpx.Response(504)
        return httpx.Response(200, json={'elements': []})

    data = run(handler, s, BIG, region=region)
    info = data.categories['buildings']
    assert info['status'] == 'partial' and info['cells_done'] == 2
    assert info['coverage_pct'] == pytest.approx(100.0 * 2 / info['cells'], abs=2.0)


def test_progress_callback_counts_cells_across_categories():
    fresh()
    seen = []
    s = settings()
    run(_cell_handler(), s, BIG, on_progress=lambda done, total: seen.append((done, total)))
    total = sum(len(osm.plan_cells(BIG, s, None, osm.category_cell_km(c, s))) for c in osm.CATEGORIES)
    assert seen[-1] == (total, total) and [d for d, _t in seen] == sorted(d for d, _t in seen)


def test_overpass_defaults_are_conservative():
    st = Settings(_env_file=None)
    assert st.overpass_building_cell_km < st.overpass_cell_km <= st.overpass_facility_cell_km
    assert (st.overpass_facility_budget_s + st.overpass_road_budget_s + st.overpass_building_budget_s
            <= st.overpass_total_budget_s)
    assert st.overpass_query_timeout_s <= 60 and st.overpass_max_cells <= 40 and st.overpass_total_budget_s > 0
