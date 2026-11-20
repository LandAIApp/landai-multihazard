import { useI18n } from '../i18n/LanguageContext';
import type { HazardId, HazardInfo } from '../types/api';
import { HazardIcon } from './icons';

export function StatusBadges({ info }: { info: HazardInfo }) {
  const { t } = useI18n();
  return (
    <div className="badges">
      <span className={`badge status-${info.module_status}`}>{t(`module.status.${info.module_status}` as 'module.status.operational')}</span>
      <span className={`badge validation-${info.validation_status}`}>
        {t(`validation.${info.validation_status}` as 'validation.experimental')}
      </span>
    </div>
  );
}

/** Landing state: nothing is selected, nothing runs. Each card states the module's real status. */
export default function HazardLanding({ hazards, onSelect }: { hazards: HazardInfo[]; onSelect: (id: HazardId) => void }) {
  const { t } = useI18n();
  return (
    <main className="landing" data-testid="landing">
      <h1>{t('landing.title')}</h1>
      <p className="landing-sub">{t('landing.subtitle')}</p>
      <h2 className="landing-choose">{t('landing.choose')}</h2>
      <div className="hazard-cards">
        {hazards.map((h) => (
          <article key={h.id} className={`hazard-card ${h.module_status}`} data-testid={`hazard-card-${h.id}`}>
            <div className="hazard-card-icon"><HazardIcon hazard={h.id} size={28} /></div>
            <h3>{t(`hazard.${h.id}.name` as 'hazard.flood.name')}</h3>
            <StatusBadges info={h} />
            <p>{t(`hazard.${h.id}.tagline` as 'hazard.flood.tagline')}</p>
            <ul className="card-facts">
              <li>{t(`product.${h.product_types[0]}` as 'product.anomaly')}</li>
              {h.resolution_m !== null && <li>{t('module.resolution', { m: h.resolution_m })}</li>}
              <li>{t(h.exposure_available ? 'module.exposure.yes' : 'module.exposure.no')}</li>
            </ul>
            <button type="button" className={`btn primary full`}
                    onClick={() => onSelect(h.id)}>
              {t('landing.open')}
            </button>
          </article>
        ))}
      </div>
      <p className="muted small landing-note">{t('landing.note')}</p>
    </main>
  );
}
