import { useI18n } from '../i18n/LanguageContext';
import { formatNumber } from '../services/format';
import type { PublicConfig } from '../types/api';

/** Short usage limits, so people know them before running anything. */
export default function LimitsNotice({ config, drawnMax, hectares }: { config: PublicConfig; drawnMax?: number; hectares?: number | null }) {
  const { t, lang } = useI18n();
  const n = (v: number) => formatNumber(v, lang);
  return (
    <div className="notice-info limits-notice" data-testid="limits-notice">
      <strong>{t('limits.title')}</strong>
      <ul>
        <li>{t('limits.area', { municipality: n(config.aoi.municipality.max_hectares), drawn: n(drawnMax ?? config.aoi.custom.max_hectares) })}</li>
        <li>{t('limits.exposure', { max: n(config.exposure.max_aoi_hectares) })}</li>
        <li>{t('limits.osm')}</li>
      </ul>
      {hectares != null && hectares > config.exposure.max_aoi_hectares && (
        <p className="limits-warn" data-testid="limits-exposure-warn">{t('limits.tooBigForExposure', { max: n(config.exposure.max_aoi_hectares) })}</p>
      )}
    </div>
  );
}
