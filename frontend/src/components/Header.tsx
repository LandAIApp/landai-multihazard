import type { ReactNode } from 'react';
import { useHazard, useI18n } from '../i18n/LanguageContext';
import type { HazardId } from '../types/api';
import { HazardIcon } from './icons';
import LanguageSwitch from './LanguageSwitch';

// Light variant for the dark UI. The original-colour logo is in the same folder:
// assets/brand/logo-landai-transparent.png (it has low contrast on #071110).
const LOGO_SRC = `${import.meta.env.BASE_URL}assets/brand/logo-landai-light.png`;

interface Props {
  /** The open workspace; `null` on the landing page. Defaults to the hazard of the surrounding scope. */
  hazard?: HazardId | null;
  /** Hazard selector (rendered by the app shell). */
  selector?: ReactNode;
}

export default function Header({ hazard, selector }: Props) {
  const { t } = useI18n();
  const scoped = useHazard();
  const shown = hazard === undefined ? scoped : hazard;
  return (
    <header className="header">
      <div className="brand">
        <img className="brand-logo" src={LOGO_SRC} alt={t('header.logoAlt')} />
        <span className="brand-divider" aria-hidden />
        <div className="brand-product">
          <div className="brand-product-name">
            <HazardIcon hazard={shown} size={18} />
            <span>{t('header.product')}</span>
          </div>
          <div className="brand-labs">{t('header.labs')}</div>
        </div>
      </div>
      {selector}
      <div className="header-right">
        <span className="header-note">{t('header.subtitle')}</span>
        <LanguageSwitch />
      </div>
    </header>
  );
}
