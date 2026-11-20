import { useI18n } from '../i18n/LanguageContext';
import type { HazardId, HazardInfo } from '../types/api';
import { HazardIcon } from './icons';

interface Props {
  hazards: HazardInfo[];
  current: HazardId | null;
  onSelect: (id: HazardId) => void;
}

/** Compact hazard switcher shown in the header. Switching never starts an analysis. */
export default function HazardSelector({ hazards, current, onSelect }: Props) {
  const { t } = useI18n();
  return (
    <nav className="hazard-selector" role="tablist" aria-label={t('selector.label')}>
      {hazards.map((h) => (
        <button key={h.id} type="button" role="tab" aria-selected={current === h.id} data-testid={`hazard-tab-${h.id}`}
                className={`hazard-tab${current === h.id ? ' active' : ''}`}
                onClick={() => onSelect(h.id)}>
          <HazardIcon hazard={h.id} size={15} />
          <span>{t(`hazard.${h.id}.name` as 'hazard.flood.name')}</span>
        </button>
      ))}
    </nav>
  );
}
