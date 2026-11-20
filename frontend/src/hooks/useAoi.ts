import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { DrawTool } from '../components/MapView';
import { api } from '../services/api';
import { areaLevel, closeRing, hasSelfIntersection, rectangleRing, ringAreaHectares } from '../services/geometry';
import type { LngLat, PublicConfig, Ring } from '../types/api';

export type AreaMode = 'municipality' | 'draw';
export const DEFAULT_AREA = { department: 'Tolima', municipality: 'San Luis' } as const;
const round6 = (p: LngLat): LngLat => [Math.round(p[0] * 1e6) / 1e6, Math.round(p[1] * 1e6) / 1e6];

interface Options {
  config: PublicConfig;
  /** Hectares reported by the last preflight (municipality mode). */
  preflightHectares: number | null;
  /** Called on every USER change of the area (the page clears its stale results). */
  onChange: () => void;
  onError: (e: unknown) => void;
  /** Hazard-specific drawn-area limits (hectares) overriding the shared ones. */
  customLimits?: { max: number; warn: number };
}

/**
 * Study-area state shared by every hazard workspace: municipality / drawn polygon, catalogues, measurement against the
 * backend limits. Nothing is remembered: each hazard workspace starts clean.
 */
export function useAoi({ config, preflightHectares, onChange, onError, customLimits }: Options) {
  const [mode, setModeState] = useState<AreaMode>('municipality');
  const [drawTool, setDrawTool] = useState<DrawTool | null>(null);
  const [draft, setDraft] = useState<LngLat[]>([]);
  const [ring, setRingState] = useState<Ring | null>(null);
  const [departments, setDepartments] = useState<string[]>([]);
  const [municipalities, setMunicipalities] = useState<string[]>([]);
  const [department, setDepartmentState] = useState('');
  const [municipality, setMunicipalityState] = useState('');
  const [catalogLoading, setCatalogLoading] = useState(false);
  const wantedMunicipality = useRef('');

  useEffect(() => {
    setCatalogLoading(true);
    api.departments()
      .then(({ departments: ds }) => {
        setDepartments(ds);
      })
      .catch(onError)
      .finally(() => setCatalogLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!department) { setMunicipalities([]); setMunicipalityState(''); return; }
    let cancelled = false;
    setCatalogLoading(true);
    api.municipalities(department)
      .then(({ municipalities: ms }) => {
        if (cancelled) return;
        setMunicipalities(ms);
        const wanted = wantedMunicipality.current;
        setMunicipalityState(ms.includes(wanted) ? wanted : '');   // never auto-pick: the user chooses
        wantedMunicipality.current = '';
      })
      .catch((e) => !cancelled && onError(e))
      .finally(() => !cancelled && setCatalogLoading(false));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [department]);

  const custom = config.aoi.custom;
  const limits = mode === 'draw'
    ? { max: customLimits?.max ?? custom.max_hectares, warn: customLimits?.warn ?? custom.warn_hectares, min: custom.min_hectares, maxVertices: custom.max_vertices }
    : { max: config.aoi.municipality.max_hectares, warn: config.aoi.municipality.warn_hectares, min: 0, maxVertices: custom.max_vertices };
  const drawnPoints = ring ?? (draft.length >= 3 ? draft : null);
  const hectares = mode === 'draw' ? (drawnPoints ? ringAreaHectares(drawnPoints) : null) : preflightHectares;
  const level = areaLevel(hectares, limits, mode === 'draw');
  const vertexCount = ring ? ring.length - 1 : draft.length;
  const selfIntersects = mode === 'draw' && !!ring && hasSelfIntersection(ring);
  const tooManyVertices = mode === 'draw' && vertexCount > custom.max_vertices;
  const areaReady = mode === 'municipality'
    ? !!department && !!municipality
    : !!ring && (level === 'ok' || level === 'warn') && !selfIntersects && !tooManyVertices;

  /** Area part of a request body (municipality or drawn polygon). */
  const selection = useMemo(() => (mode === 'municipality'
    ? { department, municipality }
    : { geometry: { type: 'Polygon' as const, coordinates: [(ring ?? []).map(round6)] } }),
  [mode, department, municipality, ring]);

  const stopDrawing = useCallback(() => { setDrawTool(null); setDraft([]); }, []);
  const setMode = (m: AreaMode) => { onChange(); stopDrawing(); setModeState(m); };
  const setDepartment = (v: string) => { setDepartmentState(v); onChange(); };
  const setMunicipality = (v: string) => { setMunicipalityState(v); onChange(); };
  const setRing = (r: Ring | null) => { setRingState(r); onChange(); };
  const onTool = (tool: DrawTool) => {
    onChange(); setRingState(null); setDraft([]); setDrawTool(tool);
    if (window.innerWidth <= 820) {
      window.setTimeout(() => document.getElementById('map-section')?.scrollIntoView({ behavior: 'smooth' }), 50);
    }
  };
  const onPoint = (p: LngLat) => {
    if (drawTool === 'polygon') {
      setDraft((d) => (d.length && d[d.length - 1][0] === p[0] && d[d.length - 1][1] === p[1] ? d : [...d, p]));
    } else if (drawTool === 'rectangle') {
      if (draft.length === 0) { setDraft([p]); return; }
      if (draft[0][0] === p[0] || draft[0][1] === p[1]) return;
      setRingState(rectangleRing(draft[0], p));
      stopDrawing();
    }
  };
  const onFinish = () => {
    if (drawTool !== 'polygon' || draft.length < 3) return;
    setRingState(closeRing(draft));
    stopDrawing();
  };
  const onUndo = () => setDraft((d) => d.slice(0, -1));
  const onClear = () => { onChange(); setRingState(null); stopDrawing(); };
  /** Loads a ready-made polygon (example buttons): draw mode, finished ring. */
  const loadRing = (r: Ring) => { onChange(); stopDrawing(); setModeState('draw'); setRingState(r); };
  /** Selects a municipality directly (used by the "load example" buttons). */
  const selectMunicipality = (dep: string, mun: string) => {
    onChange(); stopDrawing(); setModeState('municipality');
    wantedMunicipality.current = mun;
    if (dep === department) setMunicipalityState(mun); else setDepartmentState(dep);
  };

  return {
    mode, setMode, drawTool, draft, ring, setRing, departments, municipalities, department, municipality,
    setDepartment, setMunicipality, selectMunicipality, loadRing, catalogLoading, limits, hectares, level, vertexCount,
    selfIntersects, tooManyVertices, areaReady, selection, custom, stopDrawing, onTool, onPoint, onFinish, onUndo, onClear,
  };
}
