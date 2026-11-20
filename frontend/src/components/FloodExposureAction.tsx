import { useI18n } from '../i18n/LanguageContext';
import { formatNumber } from '../services/format';
import type { HazardResult, PublicConfig } from '../types/api';

interface Props {
  result: HazardResult;
  config: PublicConfig;
  running: boolean;
  disabled: boolean;
  paused?: boolean;
  bufferM: number;
  onBuffer: (v: number) => void;
  onRun: () => void;
}

/** The ONLY place that starts the flood Exposure analysis: an explicit second step, never automatic. */
export default function FloodExposureAction(p: Props) {
  const { lang, t } = useI18n();
  const hectares = p.result.aoi.hectares ?? 0;
  const max = p.config.exposure.max_aoi_hectares;
  const tooLarge = hectares > max;
  const blocked = tooLarge || !p.result.exposure_ready || !p.result.footprint_reference || !!p.paused;
  return (
    <section className="card exposure-action" data-testid="exposure-action">
      <h2>{t('exposure.cta.title')}</h2>
      <p className="muted small">{t('exposure.cta.text')}</p>
      <label htmlFor="exp-buffer">{t('exposure.cta.buffer')}</label>
      <input id="exp-buffer" type="number" min={0} max={p.config.exposure.max_buffer_m} step={50}
             value={p.bufferM} disabled={p.disabled || p.running}
             onChange={(e) => p.onBuffer(Math.max(0, Math.min(p.config.exposure.max_buffer_m, Number(e.target.value) || 0)))} />
      <button className="btn primary full" onClick={p.onRun} disabled={p.disabled || p.running || blocked}>
        {p.running ? t('exposure.cta.running') : t('exposure.cta.button')}
      </button>
      {tooLarge && (
        <div className="alert warning" role="alert">
          {t('exposure.cta.tooLarge', { hectares: formatNumber(hectares, lang), max: formatNumber(max, lang) })}
        </div>
      )}
      {p.paused && <div className="alert warning" role="alert">{t('service.exposurePaused')}</div>}
      <p className="muted small">{t('exposure.cta.limit', { max: formatNumber(max, lang) })}</p>
    </section>
  );
}
