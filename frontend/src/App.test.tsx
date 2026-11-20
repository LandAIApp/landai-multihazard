// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ANALYSIS, CONFIG, EXPOSURE } from './test/fixtures';
import type { HazardResult } from './types/api';

vi.mock('./components/MapView', () => ({
  default: (props: Record<string, unknown> & { onPoint: (p: [number, number]) => void; onFinish: () => void }) => (
    <div data-testid="map-mock">
      <button onClick={() => props.onPoint([-75, 4])}>pt1</button>
      <button onClick={() => props.onPoint([-74.9, 4])}>pt2</button>
      <button onClick={() => props.onPoint([-74.9, 4.1])}>pt3</button>
      <button onClick={() => props.onPoint([-75, 4.1])}>pt4</button>
      <button onClick={() => props.onFinish()}>finish-map</button>
    </div>
  ),
}));

const api = vi.hoisted(() => ({
  config: vi.fn(), departments: vi.fn(), municipalities: vi.fn(), preflight: vi.fn(), analyze: vi.fn(),
  exposure: vi.fn(), recordedDemo: vi.fn(), progress: vi.fn(), hazards: vi.fn(), hazardPreflight: vi.fn(), hazardRun: vi.fn(),
}));
vi.mock('./services/api', () => ({ API_BASE: 'http://test', api }));

import App from './App';
import { LanguageProvider } from './i18n/LanguageContext';

const FLOOD: HazardResult = {
  analysis_id: 'abc', hazard_type: 'flood', product_type: 'potential_detection',
  product_label: { en: 'Detected inundation extent', es: 'Extensión de inundación detectada' }, status: 'ok',
  aoi: { kind: 'municipality', hectares: 28000, department: 'Tolima', municipality: 'San Luis' },
  analysis_period: { windows: { pre: { start: '2026-05-01', end: '2026-05-30' }, post: { start: '2026-06-01', end: '2026-06-30' } } },
  methodology: { name: 'Sentinel-1 SAR VV/VH change detection (log-ratio + Otsu)', version: 'reference-script-1' },
  data_sources: [], resolution: { spatial_m: 10 }, validation_status: 'under_validation',
  statistics: { flood_hectares: 1234.5, flood_raw_hectares: 1500, flood_pct_of_aoi: 4.4, otsu_threshold: -0.31,
    ratio_domain: 'linear', scene_counts: { s1_pre: 6, s1_post: 5, s2_pre: 3, s2_post: 2 } },
  layers: [{ id: 'flood_extent', label: 'x', group: 'results', description: '', tile_url: 'https://t/{z}/{x}/{y}',
    visible_by_default: true, legend: null }],
  boundary: { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } },
  bounds: [[0, 0], [1, 1]], footprint_reference: 'tok123',
  warnings: [{ code: 'flood_extent_very_large', message: 'm' }],
  limitations: [{ code: 'flood_no_slope_mask', message: 'm' }, { code: 'flood_extent_only', message: 'm' }],
  generated_at: '2026-10-01T12:00:00Z', exposure_ready: true, details: {},
};

const HAZARDS = [
  { id: 'wildfire', module_status: 'operational', analysis_available: true, exposure_available: true, product_types: ['observed_footprint'],
    product_label: { en: '', es: '' }, validation_status: 'operational_preliminary', methodology: null, resolution_m: 20, disclaimer: { en: '', es: '' } },
  { id: 'flood', module_status: 'experimental', analysis_available: true, exposure_available: true, product_types: ['potential_detection'],
    product_label: { en: '', es: '' }, validation_status: 'under_validation', methodology: null, resolution_m: 10, disclaimer: { en: '', es: '' } },
];

function renderApp(lang: 'es' | 'en' = 'es') {
  return render(<LanguageProvider initial={lang}><App /></LanguageProvider>);
}
const click = (name: RegExp | string) => fireEvent.click(screen.getByRole('button', { name }));
const setDates = () => {
  for (const [id, v] of [['pre-start', '2026-05-01'], ['pre-end', '2026-05-30'], ['post-start', '2026-06-01'], ['post-end', '2026-06-30']]) {
    fireEvent.change(document.getElementById(id) as HTMLInputElement, { target: { value: v } });
  }
};
const noComputation = () => {
  for (const f of [api.analyze, api.hazardRun, api.hazardPreflight, api.preflight, api.exposure]) expect(f).not.toHaveBeenCalled();
};

beforeEach(() => {
  api.config.mockResolvedValue({ ...CONFIG, hazards: { flood: { min_date: '2015-01-01', max_window_days: 90, exposure_max_pixels: 6_000_000, resolution_m: 10, max_custom_hectares: 500_000, warn_custom_hectares: 100_000 } } });
  api.hazards.mockResolvedValue(HAZARDS);
  api.departments.mockResolvedValue({ departments: ['Tolima'] });
  api.municipalities.mockResolvedValue({ municipalities: ['San Luis'] });
  api.analyze.mockResolvedValue(ANALYSIS);
  api.exposure.mockResolvedValue({ ...EXPOSURE, hazard_type: 'flood', mode: 'flood_analysis' });
  api.recordedDemo.mockResolvedValue(null);
  api.progress.mockRejectedValue(new Error('unknown'));
  api.hazardPreflight.mockResolvedValue({ hazard_type: 'flood', status: 'ok', valid: true, aoi_hectares: 28000, aoi_kind: 'municipality',
    counts: { s1_pre: 6, s1_post: 5, s2_pre: 3, s2_post: 2 }, date_windows: {}, warnings: [], blocking_errors: [] });
  api.hazardRun.mockResolvedValue(FLOOD);
});
afterEach(() => { cleanup(); localStorage.clear(); vi.clearAllMocks(); });

describe('landing state', () => {
  it('shows the two modules with their real status and runs nothing', async () => {
    renderApp();
    expect(screen.getByTestId('landing')).toBeTruthy();
    expect(screen.getByTestId('hazard-card-wildfire').textContent).toContain('Operativo');
    expect(screen.getByTestId('hazard-card-flood').textContent).toContain('Experimental');
    expect(screen.getByTestId('hazard-card-flood').textContent).toContain('En validación');
    expect(screen.queryByTestId('hazard-card-landslide')).toBeNull();
    expect(document.body.textContent).not.toMatch(/landslide|deslizamiento/i);
    await waitFor(() => expect(api.hazards).toHaveBeenCalled());
    noComputation();
  });

  it('is in English when the language is English', () => {
    renderApp('en');
    expect(screen.getByText('Choose a hazard to begin')).toBeTruthy();
    expect(screen.getByTestId('hazard-card-flood').textContent).toContain('Under validation');
  });

  it('keeps working when the backend is an older, wildfire-only release', async () => {
    api.hazards.mockRejectedValue(new Error('404'));
    renderApp();
    expect(screen.getByTestId('hazard-card-flood')).toBeTruthy();
    await waitFor(() => expect(api.hazards).toHaveBeenCalled());
  });
});

describe('hazard selector', () => {
  it('opens the wildfire workspace without running anything', async () => {
    renderApp('en');
    fireEvent.click(screen.getByTestId('hazard-tab-wildfire'));
    expect(await screen.findByRole('button', { name: 'Analyze Wildfire' })).toBeTruthy();
    noComputation();
  });

  it('switching hazards never triggers an analysis', async () => {
    renderApp('en');
    for (const h of ['wildfire', 'flood', 'wildfire', 'flood', 'wildfire']) fireEvent.click(screen.getByTestId(`hazard-tab-${h}`));
    await waitFor(() => expect(api.departments).toHaveBeenCalled());
    noComputation();
  });

  it('fully resets the study area when switching from wildfire to flood', async () => {
    renderApp('en');
    fireEvent.click(screen.getByTestId('hazard-tab-wildfire'));
    fireEvent.click(await screen.findByRole('tab', { name: 'Draw area' }));
    click('Polygon');
    for (const p of ['pt1', 'pt2', 'pt3', 'pt4']) click(p);
    click('finish-map');
    await screen.findAllByRole('button', { name: 'Clear' });
    fireEvent.click(screen.getByTestId('hazard-tab-flood'));
    const municipality = await screen.findByRole('tab', { name: 'By municipality' });
    expect(municipality.getAttribute('aria-selected')).toBe('true');
    expect(screen.queryAllByRole('button', { name: 'Clear' }).length).toBe(0);   // the ring is gone
    noComputation();
  });
});

describe('flood workspace', () => {
  async function openFlood() {
    renderApp('en');
    fireEvent.click(screen.getByTestId('hazard-tab-flood'));
    await screen.findByTestId('flood-page');
    fireEvent.change(await screen.findByLabelText('Department'), { target: { value: 'Tolima' } });
    await waitFor(() => expect((screen.getByLabelText('Municipality') as HTMLSelectElement).options.length).toBeGreaterThan(1));
    fireEvent.change(screen.getByLabelText('Municipality'), { target: { value: 'San Luis' } });
  }

  it('opens without running anything and needs the four dates before enabling the buttons', async () => {
    await openFlood();
    expect((screen.getByRole('button', { name: 'Detect flood' }) as HTMLButtonElement).disabled).toBe(true);
    setDates();
    expect((screen.getByRole('button', { name: 'Detect flood' }) as HTMLButtonElement).disabled).toBe(false);
    noComputation();
  });

  it('rejects windows in the wrong order', async () => {
    await openFlood();
    setDates();
    fireEvent.change(document.getElementById('post-start') as HTMLInputElement, { target: { value: '2026-05-10' } });
    expect((screen.getByRole('button', { name: 'Detect flood' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/POST cannot start before PRE ends/)).toBeTruthy();
  });

  it('checks availability with the common endpoint and the flood params', async () => {
    await openFlood();
    setDates();
    click('Check availability');
    await waitFor(() => expect(api.hazardPreflight).toHaveBeenCalled());
    const body = api.hazardPreflight.mock.calls[0][0];
    expect(body).toMatchObject({ hazard: 'flood', department: 'Tolima', municipality: 'San Luis' });
    expect(body.params).toEqual({ pre_start: '2026-05-01', pre_end: '2026-05-30', post_start: '2026-06-01', post_end: '2026-06-30' });
    expect(api.hazardRun).not.toHaveBeenCalled();
    expect(await screen.findByText('Enough images are available. You can run the analysis.')).toBeTruthy();
  });

  it('runs the analysis, shows the result and its limitations, and does NOT start exposure by itself', async () => {
    await openFlood();
    setDates();
    click('Detect flood');
    await waitFor(() => expect(api.hazardRun).toHaveBeenCalledTimes(1));
    expect(api.hazardRun.mock.calls[0][0].progress_id).toBeTruthy();
    const results = screen.getByTestId('flood-results');
    await waitFor(() => expect(results.textContent).toContain('1,235 ha'));
    expect(results.textContent).toContain('Under validation');
    expect(results.textContent).toContain('slope mask');            // honest limitation, translated
    expect(screen.getByText(/exceeds 40 %/)).toBeTruthy();         // very-large-extent warning
    expect(screen.getByTestId('exposure-action')).toBeTruthy();
    expect(api.exposure).not.toHaveBeenCalled();
    expect(api.analyze).not.toHaveBeenCalled();                     // the wildfire route is never used for flood
  });

  it('shows a short limits notice with the flood drawn-area limit', async () => {
    await openFlood();
    const n = screen.getByTestId('limits-notice').textContent ?? '';
    expect(n).toMatch(/500,000 ha/);
    expect(n).toMatch(/50,000 ha/);
    expect(n).toMatch(/several minutes/);
    expect(screen.queryByTestId('limits-exposure-warn')).toBeNull();      // no area yet
    click('Load example');                                                // 417,450 ha > exposure limit
    expect(screen.getByTestId('limits-exposure-warn').textContent).toMatch(/exceeds 50,000 ha/);
  });

  it('has no ratio-domain option (linear power is the only mode)', async () => {
    await openFlood();
    expect(document.getElementById('ratio-domain')).toBeNull();
    expect(screen.queryByRole('button', { name: /Advanced options/ })).toBeNull();
  });

  it('loads the reference-script polygon and dates with "Load example" and runs nothing', async () => {
    await openFlood();
    click('Load example');
    expect((document.getElementById('pre-start') as HTMLInputElement).value).toBe('2026-01-01');
    expect((document.getElementById('pre-end') as HTMLInputElement).value).toBe('2026-01-26');
    expect((document.getElementById('post-start') as HTMLInputElement).value).toBe('2026-02-02');
    expect((document.getElementById('post-end') as HTMLInputElement).value).toBe('2026-02-15');
    expect(screen.getByRole('tab', { name: 'Draw area' }).getAttribute('aria-selected')).toBe('true');
    click('Check availability');
    await waitFor(() => expect(api.hazardPreflight).toHaveBeenCalled());
    const body = api.hazardPreflight.mock.calls[0][0];
    expect(body.geometry.type).toBe('Polygon');
    expect(body.geometry.coordinates[0].length).toBeGreaterThan(100);
    expect(body.params).toEqual({ pre_start: '2026-01-01', pre_end: '2026-01-26', post_start: '2026-02-02', post_end: '2026-02-15' });
    expect(api.hazardRun).not.toHaveBeenCalled();
  });

  it('switching hazard resets the previous hazard result, dates and exposure but and the area, and runs nothing', async () => {
    await openFlood();
    setDates();
    click('Detect flood');
    await waitFor(() => expect(screen.getByTestId('flood-results').textContent).toContain('1,235 ha'));
    fireEvent.click(screen.getByTestId('hazard-tab-wildfire'));
    expect(screen.queryByTestId('flood-results')).toBeNull();
    expect(api.analyze).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('hazard-tab-flood'));
    await screen.findByTestId('flood-page');
    expect(screen.getByTestId('flood-results').textContent).not.toContain('1,235 ha');
    expect(screen.queryByTestId('exposure-action')).toBeNull();
    expect((document.getElementById('post-start') as HTMLInputElement).value).toBe('');
    await screen.findByLabelText('Department');
    expect((screen.getByLabelText('Department') as HTMLSelectElement).value).toBe('');           // nothing preselected
    expect((screen.getByLabelText('Municipality') as HTMLSelectElement).value).toBe('');
    expect(api.hazardRun).toHaveBeenCalledTimes(1);               // only the click above
    expect(api.exposure).not.toHaveBeenCalled();
  });

  it('exposure is an explicit second step that sends the flood footprint reference', async () => {
    await openFlood();
    setDates();
    click('Detect flood');
    await screen.findByTestId('exposure-action');
    click('Analyze Exposure');
    await waitFor(() => expect(api.exposure).toHaveBeenCalledTimes(1));
    expect(api.exposure.mock.calls[0][0].analysis_ref).toBe('tok123');
  });

  it('uses the flood wording in shared components, and any parameter change clears the stale result', async () => {
    await openFlood();
    setDates();
    click('Detect flood');
    await screen.findByTestId('exposure-action');
    expect(screen.getByText(/Overlays the detected inundation extent/)).toBeTruthy();
    expect(screen.queryByText(/burn/i)).toBeNull();
    fireEvent.change(document.getElementById('post-end') as HTMLInputElement, { target: { value: '2026-06-20' } });
    await waitFor(() => expect(screen.queryByTestId('exposure-action')).toBeNull());
    expect(api.hazardRun).toHaveBeenCalledTimes(1);
  });

  it('shows a translated error when the backend answers 501 methodology_unavailable', async () => {
    api.hazardRun.mockRejectedValue({ code: 'methodology_unavailable', message: 'x' });
    await openFlood();
    setDates();
    click('Detect flood');
    expect(await screen.findByText('The methodology of this module is not available yet. No analysis is run.')).toBeTruthy();
  });
});
