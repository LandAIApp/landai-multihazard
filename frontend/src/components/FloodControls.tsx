import { type ReactNode } from 'react';
import { useI18n } from '../i18n/LanguageContext';
import { describeIssue } from '../services/issues';
import type { HazardPreflight, ProgressSnapshot } from '../types/api';
import type { AreaMode } from '../hooks/useAoi';
import type { Busy, Status } from './ControlPanel';
import ProgressList from './ProgressList';

export interface FloodDates { preStart: string; preEnd: string; postStart: string; postEnd: string }

interface Props {
  mode: AreaMode;
  onMode: (m: AreaMode) => void;
  areaSlot: ReactNode;
  areaReady: boolean;
  maxHectares: number;
  departments: string[];
  municipalities: string[];
  department: string;
  municipality: string;
  onDepartment: (v: string) => void;
  onMunicipality: (v: string) => void;
  dates: FloodDates;
  onDates: (d: FloodDates) => void;
  minDate: string;
  maxDate: string;
  maxWindowDays: number;
  busy: Busy;
  elapsed: number;
  status: Status;
  preflight: HazardPreflight | null;
  progress?: ProgressSnapshot | null;
  paused?: boolean;
  onExample: () => void;
  onCheck: () => void;
  onAnalyze: () => void;
}

/** Window order rule shared with the backend: each window ends after it starts and POST starts after PRE ends. */
export function datesValid(d: FloodDates): boolean {
  const all = Object.values(d).every(Boolean);
  return all && d.preEnd > d.preStart && d.postEnd > d.postStart && d.postStart >= d.preEnd;
}

const fmt = (n: number | null | undefined) => (n === null || n === undefined ? '—' : String(n));

export default function FloodControls(p: Props) {
  const { lang, t } = useI18n();
  const disabled = p.busy !== null;
  const filled = Object.values(p.dates).every(Boolean);
  const ok = datesValid(p.dates);
  const ready = p.areaReady && ok;
  const set = (key: keyof FloodDates) => (v: string) => p.onDates({ ...p.dates, [key]: v });
  const field = (id: string, key: keyof FloodDates, label: string, min?: string) => (
    <div>
      <label htmlFor={id}>{label}</label>
      <input id={id} type="date" value={p.dates[key]} min={min ?? p.minDate} max={p.maxDate} disabled={disabled}
             onChange={(e) => set(key)(e.target.value)} />
    </div>
  );
  const ctx = { department: p.department, municipality: p.municipality, aoiHectares: p.preflight?.aoi_hectares, maxHectares: p.maxHectares };

  return (
    <section className="card" data-testid="flood-controls">
      <div className="card-head">
        <h2>{t('flood.title')}</h2>
        <button type="button" className="btn-link" onClick={p.onExample} disabled={disabled}>{t('flood.example')}</button>
      </div>
      <div className="demo-note">{t('flood.exampleNote')}</div>

      <div className="segmented" role="tablist" aria-label={t('controls.areaTitle')}>
        {(['municipality', 'draw'] as const).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={p.mode === m}
                  className={p.mode === m ? 'active' : ''} disabled={disabled} onClick={() => p.onMode(m)}>
            {t(`controls.mode.${m}` as 'controls.mode.draw')}
          </button>
        ))}
      </div>

      {p.mode === 'municipality' && (
        <>
          <label htmlFor="department">{t('controls.department')}</label>
          <select id="department" value={p.department} disabled={disabled || p.departments.length === 0}
                  onChange={(e) => p.onDepartment(e.target.value)}>
            <option value="">{p.busy === 'catalog' && !p.departments.length ? t('controls.loading') : t('controls.selectDepartment')}</option>
            {p.departments.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <label htmlFor="municipality">{t('controls.municipality')}</label>
          <select id="municipality" value={p.municipality} disabled={disabled || p.municipalities.length === 0}
                  onChange={(e) => p.onMunicipality(e.target.value)}>
            <option value="">{t('controls.selectMunicipality')}</option>
            {p.municipalities.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </>
      )}

      {p.areaSlot}

      <h3 className="window-title">{t('flood.pre')}</h3>
      <div className="field-row">
        {field('pre-start', 'preStart', t('flood.preStart'))}
        {field('pre-end', 'preEnd', t('flood.preEnd'), p.dates.preStart || p.minDate)}
      </div>
      <h3 className="window-title">{t('flood.post')}</h3>
      <div className="field-row">
        {field('post-start', 'postStart', t('flood.postStart'), p.dates.preEnd || p.minDate)}
        {field('post-end', 'postEnd', t('flood.postEnd'), p.dates.postStart || p.minDate)}
      </div>
      <div className="hint muted small">{t('flood.datesHint', { days: p.maxWindowDays })}</div>
      {filled && !ok && <div className="hint error-text">{t('flood.dateOrderError')}</div>}


      <div className="button-row">
        <button className="btn secondary" onClick={p.onCheck} disabled={disabled || !ready}>
          {p.busy === 'preflight' ? t('flood.checking') : t('flood.check')}
        </button>
        <button className="btn primary" onClick={p.onAnalyze} disabled={disabled || !ready || p.paused}>
          {p.busy === 'analysis' ? t('flood.analyzing') : t('flood.analyze')}
        </button>
      </div>

      <div className={`status ${p.status.kind}`} role="status" aria-live="polite">
        {p.busy === 'analysis' && <span className="spinner" aria-hidden />}
        <span>{p.status.text}</span>
        {p.busy === 'analysis' && <span className="elapsed"> ({p.elapsed}s)</span>}
      </div>
      {p.paused && <div className="alert warning" role="alert">{t('flood.paused')}</div>}
      {p.busy === 'analysis' && <ProgressList snapshot={p.progress ?? null} kind="analysis" />}

      <div className="counts four">
        <div><strong>{fmt(p.preflight?.counts.s1_pre)}</strong><span>{t('flood.counts.s1pre')}</span></div>
        <div><strong>{fmt(p.preflight?.counts.s1_post)}</strong><span>{t('flood.counts.s1post')}</span></div>
        <div><strong>{fmt(p.preflight?.counts.s2_pre)}</strong><span>{t('flood.counts.s2pre')}</span></div>
        <div><strong>{fmt(p.preflight?.counts.s2_post)}</strong><span>{t('flood.counts.s2post')}</span></div>
      </div>

      {p.preflight?.blocking_errors.map((e) => (
        <div key={e.code + JSON.stringify(e.params ?? {})} className="alert error">{describeIssue(lang, e, ctx)}</div>
      ))}
      {p.preflight?.warnings.map((w) => (
        <div key={w.code} className="alert warning">{describeIssue(lang, w, ctx)}</div>
      ))}
    </section>
  );
}
