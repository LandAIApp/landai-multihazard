"""Multi-Hazard platform: registry, common contract, wildfire adapter, flood engine, shared exposure.

Earth Engine, Overpass and WorldPop are always replaced by fakes: nothing here touches the network.
"""
import json
from datetime import date
from unittest.mock import MagicMock, patch

import ee
import numpy as np
import pytest
from ee import apitestcase
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shapely.geometry import box

from app.core.config import Settings
from app.core.errors import InvalidRequestError, MethodologyUnavailableError
from app.hazards import all_engines, get_engine
from app.hazards.flood import engine as flood_engine
from app.hazards.flood import params as flood_params
from app.hazards.flood import s1
from app.hazards.flood.otsu import otsu_numpy
from app.main import create_app
from app.schemas.common import AnalysisRequest, AreaSelection, HazardResult
from app.schemas.exposure import ExposureRequest
from app.schemas.wildfire import AnalyzeResponse, DateRange, DateWindows, LayerInfo, TrainingInfo
from app.services import analysis_ref, analysis_registry, exposure, footprint, spatial, study_area, worldpop
from app.services.osm import OsmData

client = TestClient(create_app(), raise_server_exceptions=False)
FLOOD_PARAMS = {'pre_start': '2026-01-01', 'pre_end': '2026-01-26', 'post_start': '2026-02-02', 'post_end': '2026-02-15'}
AREA = {'department': 'Cordoba', 'municipality': 'Monteria'}
S = Settings(_env_file=None)


@pytest.fixture(autouse=True)
def _clean():
    from app.core.rate_limit import limiter
    flood_engine.reset_flights()
    analysis_registry.clear()
    limiter.reset()                      # in-memory limits are process-wide: every test starts with a full allowance
    yield
    limiter.reset()


@pytest.fixture
def ee_offline():
    case = apitestcase.ApiTestCase()
    with patch.object(ee.data, '_install_cloud_api_resource'):
        case.setUp()
        try:
            with patch.object(ee.data, 'computeValue', side_effect=AssertionError('Remote evaluation')):
                yield
        finally:
            case.tearDown()


# ---------------------------------------------------------------------------------------------------------------
# Common schemas and area selection
# ---------------------------------------------------------------------------------------------------------------
def test_area_selection_rules_are_shared_by_every_hazard():
    AreaSelection(department='A', municipality='B')
    with pytest.raises(ValidationError):
        AreaSelection(department='A')                                        # municipality missing
    with pytest.raises(ValidationError):
        AreaSelection()                                                      # nothing
    poly = {'type': 'Polygon', 'coordinates': [[[0, 0], [0, 1], [1, 1], [0, 0]]]}
    with pytest.raises(ValidationError):
        AreaSelection(department='A', municipality='B', geometry=poly)       # both
    assert AreaSelection(geometry=poly).aoi_kind == 'drawn'


def test_analysis_request_validates_hazard_and_progress_id():
    with pytest.raises(ValidationError):
        AnalysisRequest(hazard='tsunami', **AREA)
    with pytest.raises(ValidationError):
        AnalysisRequest(hazard='flood', progress_id='short', **AREA)


# ---------------------------------------------------------------------------------------------------------------
# Hazard registry / selector data
# ---------------------------------------------------------------------------------------------------------------
def test_hazard_endpoint_reports_the_real_module_status():
    r = client.get('/api/v1/hazards')
    assert r.status_code == 200
    by_id = {h['id']: h for h in r.json()}
    assert set(by_id) == {'wildfire', 'flood'}
    assert by_id['wildfire']['module_status'] == 'operational' and by_id['wildfire']['analysis_available']
    assert by_id['flood']['module_status'] == 'experimental' and by_id['flood']['analysis_available']
    assert by_id['flood']['validation_status'] == 'under_validation'            # never implies validation


def test_no_hazard_is_called_a_generic_affected_area():
    for engine in all_engines():
        label = engine.info().product_label
        assert 'affected' not in label.en.lower() and 'afectad' not in label.es.lower()
    assert 'burned' in get_engine('wildfire').info().product_label.en.lower()
    assert 'inundation' in get_engine('flood').info().product_label.en.lower()


def test_landslide_is_not_part_of_this_version():
    from app.core.errors import HazardNotFoundError
    assert client.get('/api/v1/hazards/landslide/metadata').status_code == 404
    assert 'landslide' not in {h['id'] for h in client.get('/api/v1/hazards').json()}
    with pytest.raises(HazardNotFoundError):
        get_engine('landslide')
    r = client.post('/api/v1/analysis/run', json={'hazard': 'landslide', **AREA})
    assert r.status_code == 422                       # not an accepted hazard value


def test_unknown_hazard_is_a_clean_404():
    r = client.get('/api/v1/hazards/tsunami/metadata')
    assert r.status_code == 404 and r.json()['code'] == 'hazard_not_found'


def test_metadata_endpoint_has_methodology_and_limitations():
    flood = client.get('/api/v1/hazards/flood/metadata').json()
    assert flood['methodology']['version'] == 'reference-script-1'
    assert any(n['code'] == 'flood_extent_only' for n in flood['limitations'])
    assert 'water depth' in flood['disclaimer']['en']


# ---------------------------------------------------------------------------------------------------------------
# Wildfire adapter: same services, common contract
# ---------------------------------------------------------------------------------------------------------------
def legacy_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        status='ok', metadata={'model_version': 'FIRE FOREST COLOMBIA V7.6 (Python port)', 'aoi_kind': 'municipality',
                               'generated_at': '2026-10-01T00:00:00+00:00', 'aoi_hectares': 100.0},
        image_counts={'pre': 3, 'post': 2, 'history': 9},
        date_windows=DateWindows(pre=DateRange(start='a', end='b'), post=DateRange(start='c', end='d'),
                                 history=DateRange(start='e', end='f')),
        training=TrainingInfo(positive_samples=100, negative_samples=200, note='n'),
        area_statistics={'wf035': 5.0, 'wf050': 4.0, 'wf060': 3.0, 'wf072': 2.0, 'wf085': 1.0},
        area_hectares=[{'threshold': 0.5, 'key': 'wf050', 'label': 'Probable', 'hectares': 4.0}],
        layers=[LayerInfo(id='post', label='POST', group='Imagery', description='d', tile_url='https://t/{z}/{x}/{y}',
                          visible_by_default=True)],
        boundary={'type': 'Feature', 'properties': {}, 'geometry': None}, bounds=[[0, 0], [1, 1]],
        analysis_ref='ref' * 10, aoi={'kind': 'municipality', 'hectares': 100.0, 'department': 'Tolima',
                                      'municipality': 'San Luis'})


WILDFIRE_BODY = {'hazard': 'wildfire', 'department': 'Tolima', 'municipality': 'San Luis',
                 'params': {'event_date': '2026-08-05', 'analysis_end': '2026-08-15'}}


def test_wildfire_run_uses_the_unchanged_service_and_maps_to_the_common_contract(monkeypatch):
    seen = {}

    def fake(legacy):
        seen['legacy'] = legacy
        return legacy_response()
    monkeypatch.setattr('app.hazards.wildfire.engine.run_analysis', fake)
    r = client.post('/api/v1/analysis/run', json=WILDFIRE_BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    # the legacy request handed to the wildfire service is exactly the original contract
    assert seen['legacy'].fire_date == date(2026, 8, 5) and seen['legacy'].analysis_end == date(2026, 8, 15)
    assert seen['legacy'].department == 'Tolima'
    for field in ('analysis_id', 'hazard_type', 'product_type', 'status', 'aoi', 'analysis_period', 'methodology',
                  'data_sources', 'resolution', 'validation_status', 'statistics', 'layers', 'footprint_reference',
                  'warnings', 'limitations', 'generated_at', 'exposure_ready'):
        assert field in body, field
    assert body['hazard_type'] == 'wildfire' and body['product_type'] == 'potential_detection'
    assert body['validation_status'] == 'operational_preliminary' and body['exposure_ready'] is True
    assert body['statistics']['primary_hectares'] == 4.0 and body['resolution']['spatial_m'] == 20
    assert body['footprint_reference'] == 'ref' * 10
    assert body['product_label']['en'] == 'Potentially burned area'


def test_wildfire_bad_params_are_an_invalid_request():
    r = client.post('/api/v1/analysis/run', json={**WILDFIRE_BODY, 'params': {'event_date': '2026-08-15',
                                                                              'analysis_end': '2026-08-05'}})
    assert r.status_code == 422 and r.json()['code'] == 'invalid_request'


def test_legacy_wildfire_routes_still_exist_and_keep_their_contract(monkeypatch):
    monkeypatch.setattr('app.api.wildfire.run_analysis', lambda r: legacy_response())
    r = client.post('/api/v1/wildfire/analyze', json={'department': 'Tolima', 'municipality': 'San Luis',
                                                      'fire_date': '2026-08-05', 'analysis_end': '2026-08-15'})
    assert r.status_code == 200 and 'area_hectares' in r.json() and 'analysis_ref' in r.json()


def test_analysis_result_can_be_fetched_again_and_unknown_ids_404(monkeypatch):
    monkeypatch.setattr('app.hazards.wildfire.engine.run_analysis', lambda legacy: legacy_response())
    first = client.post('/api/v1/analysis/run', json=WILDFIRE_BODY).json()
    again = client.get(f"/api/v1/analysis/{first['analysis_id']}")
    assert again.status_code == 200 and again.json()['analysis_id'] == first['analysis_id']
    missing = client.get('/api/v1/analysis/doesnotexist')
    assert missing.status_code == 404 and missing.json()['code'] == 'analysis_not_found'


# ---------------------------------------------------------------------------------------------------------------
# Flood parameters
# ---------------------------------------------------------------------------------------------------------------
def test_flood_params_order_rules():
    flood_params.parse_params(FLOOD_PARAMS)
    bad = [{**FLOOD_PARAMS, 'pre_end': '2025-12-31'},                       # pre ends before it starts
           {**FLOOD_PARAMS, 'post_end': '2026-02-01'},                      # post ends before it starts
           {**FLOOD_PARAMS, 'post_start': '2026-01-10'}]                    # post starts before pre ends
    for raw in bad:
        with pytest.raises(InvalidRequestError):
            flood_params.parse_params(raw)
    with pytest.raises(InvalidRequestError):
        flood_params.parse_params({**FLOOD_PARAMS, 'ratio_domain': 'banana'})


def test_flood_date_guards():
    p = flood_params.parse_params(FLOOD_PARAMS)
    assert flood_params.date_issues(p, S, today=date(2026, 3, 1)) == []
    codes = {i.code for i in flood_params.date_issues(p, S, today=date(2026, 2, 1))}
    assert 'flood_future_date' in codes
    old = flood_params.parse_params({**FLOOD_PARAMS, 'pre_start': '2010-01-01', 'pre_end': '2010-01-20',
                                     'post_start': '2010-01-25', 'post_end': '2010-02-10'})
    assert 'flood_date_too_early' in {i.code for i in flood_params.date_issues(old, S, today=date(2026, 3, 1))}
    long = flood_params.parse_params({**FLOOD_PARAMS, 'pre_start': '2025-06-01'})
    assert 'window_too_long' in {i.code for i in flood_params.date_issues(long, S, today=date(2026, 3, 1))}


# ---------------------------------------------------------------------------------------------------------------
# Flood scientific graph: structure of the port (offline) and the arithmetic it relies on
# ---------------------------------------------------------------------------------------------------------------
def _graph_json(obj) -> str:
    return json.dumps(ee.serializer.encode(obj, for_cloud_api=False))


def test_flood_graph_follows_the_reference_script(ee_offline):
    aoi = ee.Geometry.Rectangle([-75.2, 8.1, -75.1, 8.2])
    graph = s1.flood_graph(aoi, '2026-01-01', '2026-01-26', '2026-02-02', '2026-02-15')
    text = _graph_json(graph['final'])
    for needle in ('COPERNICUS/S1_GRD', 'IW', 'DESCENDING', 'transmitterReceiverPolarisation', 'focal_median',
                   'connectedPixelCount', 'selfMask', 'Reducer.histogram', '2026-01-01', '2026-01-26', '2026-02-02',
                   '2026-02-15'):
        assert needle in text, needle
    assert 'ASCENDING' not in text
    # the slope mask of the script is defined but disabled there: it must NOT be in the graph
    assert 'SRTM' not in text and 'USGS/SRTMGL1' not in text and 'slope' not in text.lower()
    # the Sentinel-2 images are display-only in the script: the detection graph never touches them
    assert 'COPERNICUS/S2' not in text


def test_flood_constants_match_the_script():
    assert s1.SPECKLE_RADIUS_M == 30 and s1.OTSU_SCALE_M == 10 and s1.MASK_SCALE_M == 10
    assert s1.MIN_CONN_PIXELS == 20 and s1.CONN_MAX_SIZE == 100
    from app.hazards.flood.otsu import FALLBACK_THRESHOLD, MAX_BUCKETS
    assert FALLBACK_THRESHOLD == -0.3 and MAX_BUCKETS == 256


def test_flood_statistics_graph_is_one_dictionary(ee_offline):
    aoi = ee.Geometry.Rectangle([-75.2, 8.1, -75.1, 8.2])
    graph = s1.flood_graph(aoi, '2026-01-01', '2026-01-26', '2026-02-02', '2026-02-15')
    text = _graph_json(s1.statistics(graph, aoi))
    assert 'otsuThreshold' in text and 'floodHectares' in text and 'floodRawHectares' in text
    assert 'pixelArea' in text and 'tileScale' in text


def test_linear_ratio_domain_is_the_default_everywhere():
    import inspect
    assert flood_params.parse_params(FLOOD_PARAMS).ratio_domain == 'linear'
    assert inspect.signature(s1.log_ratios).parameters['ratio_domain'].default == 'linear'
    assert inspect.signature(s1.flood_graph).parameters['ratio_domain'].default == 'linear'


def test_both_ratio_domains_build(ee_offline):
    aoi = ee.Geometry.Rectangle([-75.2, 8.1, -75.1, 8.2])
    ref = _graph_json(s1.flood_graph(aoi, '2026-01-01', '2026-01-26', '2026-02-02', '2026-02-15', 'reference')['final'])
    lin = _graph_json(s1.flood_graph(aoi, '2026-01-01', '2026-01-26', '2026-02-02', '2026-02-15', 'linear')['final'])
    assert ref != lin
    assert lin.count('Image.pow') > ref.count('Image.pow')      # only the linear variant converts dB to power first


def test_otsu_recipe_finds_the_valley_between_two_modes():
    rng = np.random.default_rng(1)
    values = np.concatenate([rng.normal(-0.6, 0.08, 4000), rng.normal(0.0, 0.08, 6000)])
    counts, edges = np.histogram(values, bins=256)
    means = (edges[:-1] + edges[1:]) / 2
    thr = otsu_numpy(means, counts)
    assert -0.45 < thr < -0.15
    # an independent brute-force over the same histogram (class-variance maximisation) gives the same cut
    total = counts.sum()
    best = max(range(1, 256), key=lambda i: (counts[:i].sum() / total) * (counts[i:].sum() / total)
               * ((means[:i] * counts[:i]).sum() / max(counts[:i].sum(), 1)
                  - (means[i:] * counts[i:]).sum() / max(counts[i:].sum(), 1)) ** 2)
    assert thr == pytest.approx(float(means[best]))


def test_ratio_domain_semantics_are_documented_by_numbers():
    """A flooded pixel: backscatter falls from -12 dB (PRE) to -22 dB (POST).

    * linear alternative  : log10(post_lin / pre_lin) = (post_dB - pre_dB) / 10 = -1.0   -> negative = flood
    * script's active code: log10(post_dB / pre_dB) = log10(-22 / -12)       = +0.263   -> POSITIVE for a flood
    The mask is ``lrCombined <= threshold`` ("strong negative change"), so the two domains select opposite sides.
    """
    pre, post = -12.0, -22.0
    assert (post - pre) / 10 == pytest.approx(-1.0)
    assert np.log10(post / pre) == pytest.approx(0.263, abs=0.001)
    # and a pixel whose backscatter ROSE (-22 -> -12 dB) is the one that goes negative under the active code
    assert np.log10(-12.0 / -22.0) < 0


# ---------------------------------------------------------------------------------------------------------------
# Flood engine (Earth Engine mocked)
# ---------------------------------------------------------------------------------------------------------------
def flood_request(**kw) -> AnalysisRequest:
    return AnalysisRequest(hazard='flood', params=kw.pop('params', FLOOD_PARAMS), **{**AREA, **kw})


@pytest.fixture
def mock_flood(monkeypatch):
    """Everything that would call Earth Engine, with a 20 000 ha municipality and 3 scenes per window."""
    state = {'evaluate': [], 'counts': {'s1_pre': 3, 's1_post': 2, 's2_pre': 4, 's2_post': 5}}
    area = study_area.StudyArea(kind='municipality', geometry=MagicMock(), hectares=20000.0,
                                boundary={'type': 'Feature', 'properties': {}, 'geometry': None},
                                bounds=[[8.0, -76.0], [9.0, -75.0]], department='Cordoba', municipality='Monteria')
    monkeypatch.setattr(study_area, 'preflight_area', lambda a, s=None: (20000.0, [], [], object()))
    monkeypatch.setattr(study_area, 'build', lambda a, h, handle: area)
    monkeypatch.setattr(flood_engine.s1, 'availability', lambda *a: 'AVAIL')
    monkeypatch.setattr(flood_engine.s1, 'flood_graph', lambda *a, **k: {'final': MagicMock(), 'raw': MagicMock()})
    monkeypatch.setattr(flood_engine.s1, 'statistics', lambda *a, **k: 'STATS')
    monkeypatch.setattr(flood_engine, 'build_layers', lambda images, specs: (
        [LayerInfo(id=spec[0], label=spec[1], group=spec[2], description=spec[3], tile_url='https://t/{z}/{x}/{y}',
                   visible_by_default=spec[6]) for spec in specs], []))
    monkeypatch.setattr(FLOOD_ENGINE_OPTICAL, 's2_context_image', lambda *a: MagicMock())

    def fake_evaluate(obj, what='x'):
        if obj == 'AVAIL':
            return dict(state['counts'])
        return {'otsuThreshold': -0.21, 'floodHectares': 1500.0, 'floodRawHectares': 1800.0}
    monkeypatch.setattr(flood_engine, 'evaluate', fake_evaluate)
    return state


import app.hazards.flood.optical as FLOOD_ENGINE_OPTICAL  # noqa: E402


def test_flood_preflight_reports_scene_counts(mock_flood):
    pf = get_engine('flood').preflight(flood_request())
    assert pf.valid and pf.counts == {'s1_pre': 3, 's1_post': 2, 's2_pre': 4, 's2_post': 5}
    assert pf.date_windows['pre'] == {'start': '2026-01-01', 'end': '2026-01-26'}
    assert pf.warnings == []


def test_flood_preflight_blocks_without_sentinel1_and_never_blames_optical(mock_flood):
    mock_flood['counts'].update(s1_post=0, s2_post=0)
    pf = get_engine('flood').preflight(flood_request())
    assert not pf.valid and [e.code for e in pf.blocking_errors] == ['no_s1_post_images']


def test_flood_preflight_warns_when_only_optical_context_is_missing(mock_flood):
    mock_flood['counts'].update(s2_pre=0)
    pf = get_engine('flood').preflight(flood_request())
    assert pf.valid and [w.code for w in pf.warnings] == ['no_s2_context']


def test_flood_invalid_dates_never_reach_earth_engine(monkeypatch):
    called = []
    monkeypatch.setattr(study_area, 'preflight_area', lambda *a, **k: called.append(1))
    bad = {**FLOOD_PARAMS, 'pre_start': '2005-01-01', 'pre_end': '2005-01-20', 'post_start': '2005-01-25',
           'post_end': '2005-02-10'}
    pf = get_engine('flood').preflight(flood_request(params=bad))
    assert not pf.valid and not called
    assert 'flood_date_too_early' in [e.code for e in pf.blocking_errors]


def test_flood_analysis_returns_the_common_contract(mock_flood):
    result = get_engine('flood').analyze(flood_request())
    assert isinstance(result, HazardResult)
    assert result.hazard_type == 'flood' and result.product_type == 'potential_detection'
    assert result.product_label.en == 'Detected inundation extent'
    assert result.validation_status == 'under_validation' and result.exposure_ready
    assert result.resolution.spatial_m == 10 and result.methodology.version == 'reference-script-1'
    st = result.statistics
    assert st['flood_hectares'] == 1500.0 and st['otsu_threshold'] == -0.21
    assert st['flood_pct_of_aoi'] == pytest.approx(7.5)
    assert any(layer['id'] == 'flood_extent' and layer['visible_by_default'] for layer in result.layers)
    groups = {layer['group'] for layer in result.layers}
    assert groups <= {'context', 'results', 'advanced'}
    codes = {n.code for n in result.limitations}
    assert {'flood_extent_only', 'flood_method_under_validation', 'flood_ratio_domain'} <= codes
    assert 'affected' not in json.dumps(result.model_dump()).lower().replace('affected_', '')


def test_flood_reference_token_carries_what_the_exposure_step_needs(mock_flood):
    result = get_engine('flood').analyze(flood_request())
    payload = analysis_ref.verify(result.footprint_reference)
    assert payload['hazard'] == 'flood' and payload['area_ha'] == {'flood': 1500.0}
    assert payload['params']['post_end'] == '2026-02-15' and payload['params']['ratio_domain'] == 'linear'
    assert payload['municipality'] == 'Monteria'


def test_flood_without_optical_context_drops_only_those_layers(mock_flood):
    mock_flood['counts'].update(s2_pre=0)
    result = get_engine('flood').analyze(flood_request())
    ids = {layer['id'] for layer in result.layers}
    assert 's2_pre' not in ids and 's2_post' not in ids and 'flood_extent' in ids


def test_flood_warns_when_the_detected_share_is_implausibly_large(monkeypatch, mock_flood):
    monkeypatch.setattr(flood_engine, 'evaluate', lambda obj, what='x': (
        dict(mock_flood['counts']) if obj == 'AVAIL'
        else {'otsuThreshold': 0.05, 'floodHectares': 15000.0, 'floodRawHectares': 16000.0}))
    result = get_engine('flood').analyze(flood_request())
    assert 'flood_extent_very_large' in [w.code for w in result.warnings]


def test_flood_zero_detection_is_reported_not_hidden(monkeypatch, mock_flood):
    monkeypatch.setattr(flood_engine, 'evaluate', lambda obj, what='x': (
        dict(mock_flood['counts']) if obj == 'AVAIL'
        else {'otsuThreshold': -0.3, 'floodHectares': 0, 'floodRawHectares': 0}))
    result = get_engine('flood').analyze(flood_request())
    assert result.statistics['flood_hectares'] == 0 and 'no_flood_detected' in [w.code for w in result.warnings]


def test_flood_service_pause_switch(monkeypatch, mock_flood):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'analysis_enabled', False)
    r = client.post('/api/v1/analysis/run', json={'hazard': 'flood', **AREA, 'params': FLOOD_PARAMS})
    assert r.status_code == 503 and r.json()['code'] == 'service_paused'


def test_flood_run_endpoint_end_to_end(mock_flood):
    r = client.post('/api/v1/analysis/run', json={'hazard': 'flood', **AREA, 'params': FLOOD_PARAMS})
    assert r.status_code == 200, r.text
    assert r.json()['hazard_type'] == 'flood'
    fetched = client.get(f"/api/v1/analysis/{r.json()['analysis_id']}")
    assert fetched.status_code == 200


def test_flood_run_with_blocking_preflight_is_a_422(mock_flood):
    mock_flood['counts'].update(s1_pre=0)
    r = client.post('/api/v1/analysis/run', json={'hazard': 'flood', **AREA, 'params': FLOOD_PARAMS})
    assert r.status_code == 422 and r.json()['code'] == 'preflight_failed'


def test_heavy_endpoint_is_rate_limited(mock_flood, monkeypatch):
    from app.core.config import get_settings
    from app.core.rate_limit import limiter
    monkeypatch.setattr(get_settings(), 'rate_limit_analyze', '2/hour')
    limiter.enabled = True
    limiter.reset()
    try:
        codes = [client.post('/api/v1/analysis/run', json={'hazard': 'flood', **AREA, 'params': {
            **FLOOD_PARAMS, 'post_end': f'2026-02-{10 + i}'}}).status_code for i in range(4)]
    finally:
        limiter.reset()
    assert codes[:2] == [200, 200] and codes[2:] == [429, 429]
    assert client.get('/api/v1/hazards').status_code == 200            # light endpoints stay unrestricted


# ---------------------------------------------------------------------------------------------------------------
# Shared exposure engine, driven by a flood footprint
# ---------------------------------------------------------------------------------------------------------------
AOI_WGS = box(-74.03, 4.58, -73.98, 4.63)
HAZ_WGS = box(-74.010, 4.600, -74.000, 4.610)
RING = [list(p) for p in AOI_WGS.exterior.coords]


def flood_ctx(**kw):
    c = {'hazard': 'flood', 'mode': 'flood_analysis', 'kind': 'drawn', 'aoi_hectares': 3000.0, 'fire_date': None,
         'analysis_end': None, 'model_version': 'flood', 'analysis_area_ha': {'flood': 123.0},
         'params': {**FLOOD_PARAMS, 'ratio_domain': 'linear'},
         'date_windows': {'pre': {'start': 'a', 'end': 'b'}, 'post': {'start': 'c', 'end': 'd'}},
         'department': None, 'municipality': None, 'ring': RING}
    c.update(kw)
    return c


def flood_fp():
    crs = spatial.utm_epsg(-74.0, 4.6)
    return footprint.Footprint(crs=crs, pixel_size_m=10, aoi=spatial.to_metric(AOI_WGS, crs),
                               footprints={'flood': spatial.to_metric(HAZ_WGS, crs)}, pixel_counts={'flood': 1})


def _osm():
    from tests.test_exposure_service import osm_data
    return osm_data()


def _pop(*_a, **_k):
    from tests.test_exposure_service import pop
    return pop()


def flood_exposure(osm_fetch=None, pop_fn=_pop):
    return exposure.build_response(ExposureRequest(analysis_ref='x' * 30), flood_ctx(), flood_fp(), S,
                                   osm_fetch=osm_fetch or (lambda b, s: _osm()), pop_estimate=pop_fn)


def test_exposure_engine_is_reused_for_flood_without_wildfire_wording():
    r = flood_exposure()
    assert r['status'] == 'success' and r['hazard_type'] == 'flood' and r['mode'] == 'flood_analysis'
    assert r['analysis']['footprint_label']['en'] == 'Detected inundation extent'
    assert r['analysis']['threshold'] is None and r['sensitivity'] == []           # no wildfire thresholds
    assert r['analysis']['custom_aoi_note'] is None
    assert r['layers']['footprint']['features'][0]['properties']['role'] == 'detected_footprint'
    assert r['metrics']['population']['value'] == 321.0 and r['metrics']['buildings_intersecting']['value'] == 1
    assert 'burn' not in r['sources']['earth_observation']['details']['method']
    assert 'Sentinel-1' in r['sources']['earth_observation']['details']['method']
    assert 'inundation extent' in r['notice']['en'] and 'physical damage' in r['notice']['en']      # exposure != damage
    assert 'extensión de inundación detectada' in r['notice']['es']
    assert 'affected' not in r['notice']['en'].lower()
    product = r['analysis']['product']
    assert product['hazard'] == 'flood' and product['product_type'] == 'potential_detection'
    assert product['validation_status'] == 'under_validation' and product['resolution_m'] == 10
    assert product['methodology']['version'] == 'reference-script-1'
    assert any(n['code'] == 'flood_extent_only' for n in product['limitations'])


def test_flood_exports_carry_the_metadata_and_never_the_wildfire_source():
    import csv
    import io
    r = flood_exposure()
    rows = {x['indicator']: x for x in csv.DictReader(io.StringIO(r['exports']['csv']))}
    assert rows['metadata_hazard']['value'] == 'flood' and rows['metadata_product_type']['value'] == 'potential_detection'
    assert rows['metadata_validation_status']['value'] == 'under_validation'
    assert rows['metadata_resolution_m']['value'] == '10.0'
    assert 'Sentinel-1' in rows['affected_area_ha']['source'] and 'wildfire' not in rows['affected_area_ha']['source']
    report = r['exports']['report']
    assert report['hazard_type'] == 'flood' and report['product']['methodology']['name'].startswith('Sentinel-1')
    assert report['notice'] == r['notice']


def test_flood_exposure_partial_when_worldpop_fails_and_osm_survives():
    from app.core.errors import ExternalSourceError

    def boom(*a, **k):
        raise ExternalSourceError('WorldPop timeout', code='worldpop_timeout', status_code=504)
    r = flood_exposure(pop_fn=boom)
    assert r['status'] == 'partial'
    assert r['metrics']['population']['value'] is None and r['metrics']['population']['status'] == 'unavailable'
    assert r['metrics']['buildings_intersecting']['value'] == 1
    assert r['sources']['worldpop']['status'] == 'error' and r['sources']['openstreetmap']['status'] == 'success'


def test_flood_exposure_partial_when_overpass_fails_and_worldpop_survives():
    from app.core.errors import ExternalSourceError

    def boom(*a, **k):
        raise ExternalSourceError('Overpass down', code='overpass_unavailable')
    r = flood_exposure(osm_fetch=boom)
    assert r['status'] == 'partial' and r['metrics']['population']['value'] == 321.0
    assert r['metrics']['buildings_intersecting']['value'] is None


def test_flood_area_mismatch_between_analysis_and_vector_is_flagged():
    r = exposure.build_response(ExposureRequest(analysis_ref='x' * 30), flood_ctx(analysis_area_ha={'flood': 60.0}),
                                flood_fp(), S, osm_fetch=lambda b, s: _osm(), pop_estimate=_pop)
    assert 'footprint_area_mismatch' in [w['code'] for w in r['warnings']]


def test_empty_flood_footprint_gives_a_clear_error_without_mentioning_thresholds():
    from app.core.errors import NoAffectedAreaError
    fp = flood_fp()
    fp.footprints['flood'] = spatial.to_metric(box(0, 0, 0, 0), fp.crs)
    with pytest.raises(NoAffectedAreaError, match='no area'):
        exposure.build_response(ExposureRequest(analysis_ref='x' * 30), flood_ctx(), fp, S,
                                osm_fetch=lambda b, s: _osm(), pop_estimate=_pop)


def test_exposure_context_from_flood_token_and_cache_identity():
    token = analysis_ref.issue({'hazard': 'flood', 'kind': 'drawn', 'aoi_hectares': 3000.0, 'model_version': 'm',
                                'area_ha': {'flood': 10.0}, 'ring': RING, 'params': {**FLOOD_PARAMS,
                                                                                      'ratio_domain': 'linear'}})
    req = ExposureRequest(analysis_ref=token)
    ctx = exposure._context_from_token(req, S)
    assert ctx['hazard'] == 'flood' and ctx['mode'] == 'flood_analysis' and ctx['ring_bounds']
    other = dict(ctx, params={**ctx['params'], 'ratio_domain': 'reference'})
    assert exposure._identity(ctx) != exposure._identity(other)          # a different method never reuses a cache entry


def test_wildfire_token_without_hazard_field_still_means_wildfire():
    token = analysis_ref.issue({'kind': 'drawn', 'fire_date': '2026-08-05', 'analysis_end': '2026-08-15',
                                'aoi_hectares': 100.0, 'model_version': 'V7.6', 'area_ha': {'wf072': 1.0}, 'ring': RING})
    ctx = exposure._context_from_token(ExposureRequest(analysis_ref=token), S)
    assert ctx['hazard'] == 'wildfire' and ctx['mode'] == 'wildfire_analysis'


def test_landslide_references_are_rejected_by_exposure():
    token = analysis_ref.issue({'hazard': 'landslide', 'kind': 'drawn', 'aoi_hectares': 1.0})
    with pytest.raises(InvalidRequestError):
        exposure._context_from_token(ExposureRequest(analysis_ref=token), S)


def test_flood_exposure_uses_its_own_pixel_budget_at_10_m():
    from app.core.errors import ExposureAreaTooLargeError
    s = Settings(_env_file=None, flood_exposure_max_pixels=1000)
    with pytest.raises(ExposureAreaTooLargeError) as err:
        footprint.extract_masks({'flood': (None, 'Flood')}, None, (-74.1, 4.5, -74.0, 4.6), s, scale=10, margin_px=40,
                                max_pixels=s.flood_exposure_max_pixels, downloader=lambda *a: None)
    assert err.value.details['scale_m'] == 10


def test_tiling_margin_for_the_flood_cleaning_step_covers_the_connected_pixel_rule():
    from app.hazards.flood import footprint as flood_fp_module
    assert flood_fp_module.MARGIN_PX >= 2 * s1.MIN_CONN_PIXELS - 1


def test_public_config_exposes_flood_limits_and_new_version():
    cfg = client.get('/api/v1/config').json()
    assert cfg['version'] == '3.0.0' and cfg['hazards']['flood']['resolution_m'] == 10


def test_flood_accepts_the_reference_script_area_but_wildfire_does_not():
    from app.hazards.flood.engine import _flood_limits
    from app.services import aoi as aoi_service
    st = Settings(_env_file=None)
    ha = 417_450                                          # area of the polygon of the reference script
    assert aoi_service.custom_limit_issues(ha, st)[0]                              # wildfire drawn limit: 100,000 ha
    blocking, warnings = aoi_service.custom_limit_issues(ha, _flood_limits(st))
    assert not blocking and warnings                                              # allowed, with a "large area" warning
    assert aoi_service.custom_limit_issues(600_000, _flood_limits(st))[0]         # still bounded
    assert client.get('/api/v1/config').json()['hazards']['flood']['max_custom_hectares'] == 500_000
