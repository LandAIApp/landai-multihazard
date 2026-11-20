import { useI18n } from '../i18n/LanguageContext';
import { formatDateTime, formatDecimal, formatHectares } from '../services/format';
import { describeIssue } from '../services/issues';
import type { FloodStatistics, HazardResult } from '../types/api';
import { StatusBadges } from './HazardLanding';
import type { HazardInfo } from '../types/api';

/** Common result contract rendered for the flood module (headline, provenance, warnings and honest limitations). */
export default function FloodResults({ result, info }: { result: HazardResult | null; info: HazardInfo }) {
  const { lang, t } = useI18n();
  const st = result?.statistics as unknown as FloodStatistics | undefined;
  const ctx = { aoiHectares: result?.aoi.hectares ?? null };
  const period = (result?.analysis_period as { windows?: { pre?: { start: string; end: string }; post?: { start: string; end: string } } } | undefined)?.windows;

  return (
    <section className="card" data-testid="flood-results">
      <h2>{t('flood.results.title')}</h2>
      <StatusBadges info={result ? { ...info, validation_status: result.validation_status } : info} />
      {!result && <p className="muted">{t('flood.results.empty')}</p>}
      {result && st && (
        <>
          <p className="muted small">
            {result.aoi.kind === 'drawn' ? t('flood.results.drawn') : `${result.aoi.municipality}, ${result.aoi.department}`}
            {period?.pre && period.post && ` · ${t('flood.results.period', { pre: `${period.pre.start} → ${period.pre.end}`, post: `${period.post.start} → ${period.post.end}` })}`}
          </p>
          <div className="headline-results">
            <div><span>{t('flood.results.extent')}</span><strong>{formatHectares(st.flood_hectares, lang)}</strong></div>
            <div><span>{t('flood.results.pct')}</span>
              <strong>{st.flood_pct_of_aoi === null ? '—' : `${formatDecimal(st.flood_pct_of_aoi, lang, 1)} %`}</strong></div>
          </div>
          {st.flood_hectares === 0 && <div className="alert info">{t('flood.results.noDetection')}</div>}
          <div className="result-summary">
            <div><span>{t('flood.results.raw')}</span><strong>{formatHectares(st.flood_raw_hectares, lang)}</strong></div>
            <div><span>{t('flood.results.threshold')}</span>
              <strong>{st.otsu_threshold === null ? '—' : formatDecimal(st.otsu_threshold, lang, 3)}</strong></div>
            <div><span>{t('flood.results.scenes')}</span>
              <strong>{t('flood.results.scenesValue', { s1pre: st.scene_counts.s1_pre, s1post: st.scene_counts.s1_post })}</strong></div>
            <div><span>{t('flood.results.resolution')}</span><strong>{result.resolution.spatial_m} m</strong></div>
            <div><span>{t('flood.results.product')}</span>
              <strong>{t(`product.${result.product_type}` as 'product.anomaly')}</strong></div>
            <div><span>{t('flood.results.generated')}</span><strong>{formatDateTime(result.generated_at, lang)}</strong></div>
          </div>
          <p className="muted small">{t('flood.results.method')}: {result.methodology.name} · {result.methodology.version} · {st.ratio_domain}</p>
          {result.warnings.map((w) => (
            <div key={w.code} className="alert warning">{describeIssue(lang, w, ctx)}</div>
          ))}
          <details className="definitions" open>
            <summary>{t('flood.results.limitations')}</summary>
            <ul>
              {result.limitations.map((n) => <li key={n.code}>{describeIssue(lang, n, ctx)}</li>)}
            </ul>
          </details>
          <p className="muted small">{t('flood.results.nextStep')}</p>
        </>
      )}
      <p className="disclaimer">{t('disclaimer.text')}</p>
    </section>
  );
}
