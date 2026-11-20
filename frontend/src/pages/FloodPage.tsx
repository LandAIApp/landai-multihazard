import LimitsNotice from '../components/LimitsNotice';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AreaPanel from '../components/AreaPanel';
import type { Busy, Status, StatusKind } from '../components/ControlPanel';
import DrawBar from '../components/DrawBar';
import ExposurePanel from '../components/ExposurePanel';
import FloodControls, { type FloodDates } from '../components/FloodControls';
import FloodExposureAction from '../components/FloodExposureAction';
import FloodMethodology from '../components/FloodMethodology';
import FloodResults from '../components/FloodResults';
import LayerPanel, { type ExposureLayerEntry } from '../components/LayerPanel';
import MapView, { type ExposureFocus } from '../components/MapView';
import { useAoi } from '../hooks/useAoi';
import { FALLBACK_HAZARDS } from '../hazards/registry';
import { HazardTextScope, useI18n } from '../i18n/LanguageContext';
import type { MessageKey, Params } from '../i18n';
import { api, API_BASE } from '../services/api';
import { DEFAULT_CONFIG, mergeConfig } from '../services/config';
import { DEFAULT_EXPOSURE_VISIBLE, EXPOSURE_LAYERS } from '../services/exposure';
import { formatNumber } from '../services/format';
import { describeError } from '../services/issues';
import { FLOOD_EXAMPLE_DATES, FLOOD_EXAMPLE_RING } from '../services/floodExample';
import { FLOOD_MAIN_LAYER_IDS } from '../services/layers';
import { newProgressId, useProgress } from '../services/progress';
import type {
  ExposureLayerName, ExposureResponse, HazardInfo, HazardPreflight, HazardRequest, HazardResult, PublicConfig, Ring,
} from '../types/api';

const ringBounds = (r: Ring): [[number, number], [number, number]] => {
  const xs = r.map((p) => p[0]); const ys = r.map((p) => p[1]);
  return [[Math.min(...ys), Math.min(...xs)], [Math.max(...ys), Math.max(...xs)]];
};
const customLimits = (f?: { max_custom_hectares?: number; warn_custom_hectares?: number }) =>
  (f?.max_custom_hectares && f.warn_custom_hectares ? { max: f.max_custom_hectares, warn: f.warn_custom_hectares } : undefined);
const todayIso = () => new Date().toISOString().slice(0, 10);
type Tab = 'results' | 'exposure';
const EMPTY_DATES: FloodDates = { preStart: '', preEnd: '', postStart: '', postEnd: '' };

interface StatusState { kind: StatusKind; key?: MessageKey; params?: Params; error?: unknown }

/**
 * Flood workspace. Nothing runs when it opens or when a parameter changes: preflight, analysis and exposure are three
 * explicit user actions. The detection is the Sentinel-1 reference method (see docs/flood/methodology.md).
 */
export default function FloodPage({ info = FALLBACK_HAZARDS[1] }: { info?: HazardInfo }) {
  const { lang, t } = useI18n();
  const [config, setConfig] = useState<PublicConfig>(DEFAULT_CONFIG);
  const [dates, setDates] = useState<FloodDates>(EMPTY_DATES);
  const [viewBounds, setViewBounds] = useState<[[number, number], [number, number]] | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [elapsed, setElapsed] = useState(0);
  const [statusState, setStatusState] = useState<StatusState>({ kind: 'idle', key: 'flood.status.idle' });
  const [preflight, setPreflight] = useState<HazardPreflight | null>(null);
  const [result, setResult] = useState<HazardResult | null>(null);
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [opacity, setOpacity] = useState<Record<string, number>>({});
  const [tab, setTab] = useState<Tab>('results');
  const [bufferM, setBufferM] = useState<number>(DEFAULT_CONFIG.exposure.default_buffer_m);
  const [exposure, setExposure] = useState<ExposureResponse | null>(null);
  const [exposureLoading, setExposureLoading] = useState(false);
  const [exposureError, setExposureError] = useState<unknown>(null);
  const [exposureVisible, setExposureVisible] = useState<Record<ExposureLayerName, boolean>>(DEFAULT_EXPOSURE_VISIBLE);
  const [analysisPid, setAnalysisPid] = useState<string | null>(null);
  const [exposurePid, setExposurePid] = useState<string | null>(null);
  const [focus, setFocus] = useState<ExposureFocus | null>(null);
  const analysisInFlight = useRef(false);
  const exposureInFlight = useRef(false);
  const timer = useRef<number | null>(null);
  const analysisProgress = useProgress(analysisPid, busy === 'analysis');
  const exposureProgress = useProgress(exposurePid, exposureLoading);

  const fail = (error: unknown) => setStatusState({ kind: 'error', error });
  const status = useMemo<Status>(() => ({
    kind: statusState.kind,
    text: statusState.error !== undefined
      ? describeError(lang, statusState.error, API_BASE)
      : t(statusState.key ?? 'flood.status.idle', statusState.params),
  }), [statusState, lang, t]);

  useEffect(() => {
    api.config().then((c) => {
      const merged = mergeConfig(c);
      setConfig(merged);
      setBufferM(merged.exposure.default_buffer_m);
    }).catch(() => { /* keep defaults */ });
  }, []);

  useEffect(() => {
    if (busy === 'analysis') {
      setElapsed(0);
      timer.current = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    }
    return () => { if (timer.current) { window.clearInterval(timer.current); timer.current = null; } };
  }, [busy]);

  const invalidate = useCallback(() => {
    setPreflight(null); setResult(null); setExposure(null); setExposureError(null);
    setTab('results'); setVisible({});
    setStatusState({ kind: 'idle', key: 'flood.status.inputsChanged' });
  }, []);

  const aoi = useAoi({ config, customLimits: customLimits(config.hazards?.flood), preflightHectares: preflight?.aoi_hectares ?? null, onChange: invalidate, onError: fail });
  const effectiveBusy: Busy = busy ?? (aoi.catalogLoading ? 'catalog' : null);
  const limits = config.hazards?.flood;

  const body = useMemo<HazardRequest>(() => ({
    hazard: 'flood', ...aoi.selection,
    params: {
      pre_start: dates.preStart, pre_end: dates.preEnd, post_start: dates.postStart, post_end: dates.postEnd,
    },
  }), [aoi.selection, dates]);

  const onDates = (d: FloodDates) => { setDates(d); invalidate(); };
  /** Reference-script example: its study-area polygon and its PRE/POST windows. Runs nothing. */
  const onExample = () => {
    invalidate();
    setDates({ ...FLOOD_EXAMPLE_DATES });
    aoi.loadRing(FLOOD_EXAMPLE_RING);
    setViewBounds(ringBounds(FLOOD_EXAMPLE_RING));
    setStatusState({ kind: 'info', key: 'flood.status.exampleLoaded' });
    scrollToMap();
  };

  const scrollToMap = () => {
    if (window.innerWidth <= 820) {
      window.setTimeout(() => document.getElementById('map-section')?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  };

  const onCheck = async () => {
    setBusy('preflight'); setResult(null);
    setStatusState({ kind: 'info', key: 'flood.status.checking' });
    try {
      const pf = await api.hazardPreflight(body);
      setPreflight(pf);
      setStatusState(pf.valid ? { kind: 'success', key: 'flood.status.preflightOk' }
        : { kind: 'error', key: 'flood.status.preflightBlocked' });
    } catch (e) { setPreflight(null); fail(e); } finally { setBusy(null); }
  };

  const onAnalyze = async () => {
    if (analysisInFlight.current) return;            // a second click while one request is running is ignored
    analysisInFlight.current = true;
    const pid = newProgressId();
    setAnalysisPid(pid); setBusy('analysis'); setResult(null); setExposure(null);
    setStatusState({ kind: 'info', key: 'flood.status.analyzing' });
    try {
      const res = await api.hazardRun({ ...body, progress_id: pid });
      setResult(res); setPreflight(null);
      const v: Record<string, boolean> = {}; const o: Record<string, number> = {};
      res.layers.forEach((l) => { v[l.id] = l.visible_by_default; o[l.id] = 0.8; });
      setVisible(v); setOpacity(o);
      setStatusState(res.warnings.length ? { kind: 'warning', key: 'flood.status.doneWarnings' }
        : { kind: 'success', key: 'flood.status.done' });
      scrollToMap();
    } catch (e) { fail(e); } finally { analysisInFlight.current = false; setBusy(null); }
  };

  const onExposure = async () => {
    if (!result?.footprint_reference || exposureInFlight.current) return;
    exposureInFlight.current = true;
    const pid = newProgressId();
    setExposurePid(pid); setExposureLoading(true); setExposureError(null); setExposure(null); setTab('exposure');
    try {
      const res = await api.exposure({
        analysis_ref: result.footprint_reference, threshold: config.exposure.default_threshold, buffer_m: bufferM,
        progress_id: pid,
      });
      setExposure(res); setExposureVisible(DEFAULT_EXPOSURE_VISIBLE);
    } catch (e) { setExposureError(e); } finally { exposureInFlight.current = false; setExposureLoading(false); }
  };

  const onFocus = (target: { osm?: string; layer?: ExposureLayerName }) => {
    setFocus((f) => ({ ...target, seq: (f?.seq ?? 0) + 1 }));
    document.getElementById('map-section')?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
  };

  const exposureEntries: ExposureLayerEntry[] = exposure
    ? EXPOSURE_LAYERS.flatMap((name) => {
      const fc = exposure.layers[name];
      return fc && fc.features.length ? [{ name, total: fc.metadata?.total ?? fc.features.length, shown: fc.features.length }] : [];
    })
    : [];
  const showTabs = !!result || !!exposure || exposureLoading;
  const mode = aoi.mode;

  const areaPanel = (
    <AreaPanel
      mode={mode} drawTool={aoi.drawTool} draftCount={aoi.draft.length} hasRing={!!aoi.ring} vertexCount={aoi.vertexCount}
      hectares={aoi.hectares} level={aoi.level} limits={aoi.limits} selfIntersects={aoi.selfIntersects}
      tooManyVertices={aoi.tooManyVertices} disabled={effectiveBusy !== null}
      onTool={aoi.onTool} onFinish={aoi.onFinish} onUndo={aoi.onUndo} onClear={aoi.onClear}
    />
  );

  return (
    <HazardTextScope hazard="flood">
      <div className="body" data-testid="flood-page">
        <aside className="sidebar">
          <FloodControls
            mode={mode} onMode={aoi.setMode} areaSlot={areaPanel} areaReady={aoi.areaReady} maxHectares={aoi.limits.max}
            departments={aoi.departments} municipalities={aoi.municipalities}
            department={aoi.department} municipality={aoi.municipality}
            onDepartment={aoi.setDepartment} onMunicipality={aoi.setMunicipality}
            dates={dates} onDates={onDates} minDate={limits?.min_date ?? '2015-01-01'} maxDate={todayIso()}
            maxWindowDays={limits?.max_window_days ?? 90}
            busy={effectiveBusy} elapsed={elapsed} status={status} preflight={preflight} progress={analysisProgress}
            paused={config.service?.analysis_enabled === false}
            onExample={onExample} onCheck={onCheck} onAnalyze={onAnalyze}
          />
          {showTabs && (
            <div className="tabs" role="tablist" aria-label={t('tabs.results')}>
              {(['results', 'exposure'] as const).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} data-testid={`tab-${k}`}
                        className={tab === k ? 'active' : ''} onClick={() => setTab(k)}>
                  {t(`tabs.${k}` as 'tabs.results')}
                </button>
              ))}
            </div>
          )}
          {tab === 'results' && (
            <>
              <FloodResults result={result} info={info} />
              {result && (
                <FloodExposureAction
                  result={result} config={config} running={exposureLoading} disabled={effectiveBusy !== null}
                  paused={config.service?.exposure_enabled === false} bufferM={bufferM} onBuffer={setBufferM}
                  onRun={onExposure}
                />
              )}
              <FloodMethodology />
            </>
          )}
          {tab === 'exposure' && (
            <ExposurePanel
              exposure={exposure} loading={exposureLoading} error={exposureError} apiBase={API_BASE}
              progress={exposureProgress} demoRecordedAt={null} canLoadDemo={false} onLoadDemo={() => undefined}
              onFocus={onFocus}
            />
          )}
          <LimitsNotice config={config} hectares={aoi.hectares} drawnMax={config.hazards?.flood?.max_custom_hectares} />
        </aside>
        <main className="map-wrap" id="map-section">
          <MapView
            layers={result?.layers ?? []} visible={visible} opacity={opacity}
            boundary={result?.boundary ?? null} bounds={result?.bounds ?? viewBounds}
            drawTool={mode === 'draw' ? aoi.drawTool : null} draft={aoi.draft} ring={mode === 'draw' ? aoi.ring : null}
            level={aoi.level}
            limitChip={mode === 'draw' ? t('map.limitChip', { max: formatNumber(aoi.limits.max, lang) }) : undefined}
            onPoint={aoi.onPoint} onFinish={aoi.onFinish} onRingChange={aoi.setRing}
            exposure={exposure?.layers ?? null} exposureVisible={exposureVisible} focus={focus}
          />
          {mode === 'draw' && !result && (
            <DrawBar
              hectares={aoi.hectares} level={aoi.level} maxHectares={aoi.limits.max}
              drawing={aoi.drawTool !== null} isPolygon={aoi.drawTool === 'polygon'} draftCount={aoi.draft.length}
              hasRing={!!aoi.ring} onFinish={aoi.onFinish} onUndo={aoi.onUndo} onClear={aoi.onClear}
            />
          )}
          <LayerPanel layers={result?.layers ?? []} visible={visible} opacity={opacity} mainIds={FLOOD_MAIN_LAYER_IDS}
                      onToggle={(id) => setVisible((v) => ({ ...v, [id]: !v[id] }))}
                      onOpacity={(id, val) => setOpacity((o) => ({ ...o, [id]: val }))}
                      exposureLayers={exposureEntries} exposureVisible={exposureVisible}
                      onExposureToggle={(name) => setExposureVisible((v) => ({ ...v, [name]: !v[name] }))} />
        </main>
      </div>
    </HazardTextScope>
  );
}
