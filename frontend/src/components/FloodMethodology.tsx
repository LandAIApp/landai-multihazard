import { useI18n } from '../i18n/LanguageContext';

const ITEMS = ['s1', 'ratio', 'otsu', 'clean', 's2', 'notDepth'] as const;

export default function FloodMethodology() {
  const { t } = useI18n();
  return (
    <details className="card methodology">
      <summary>{t('flood.methodology.title')}</summary>
      <p>{t('flood.methodology.intro')}</p>
      <ul>
        {ITEMS.map((id) => <li key={id}>{t(`flood.methodology.${id}` as 'flood.methodology.s1')}</li>)}
      </ul>
    </details>
  );
}
