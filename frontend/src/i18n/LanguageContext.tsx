import {
  createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode,
} from 'react';
import type { HazardId } from '../types/api';
import {
  localeOf, persistLanguage, resolveInitialLanguage, translate, translateOptional,
  type Language, type MessageKey, type Params,
} from './index';

interface I18nValue {
  lang: Language;
  locale: string;
  setLang: (lang: Language) => void;
  t: (key: MessageKey, params?: Params) => string;
  tOptional: (key: string, params?: Params) => string | undefined;
}

const LanguageContext = createContext<I18nValue | null>(null);

function browserStorage(): Storage | null {
  try { return typeof window === 'undefined' ? null : window.localStorage; } catch { return null; }
}

export function LanguageProvider({ children, initial }: { children: ReactNode; initial?: Language }) {
  const [lang, setLang] = useState<Language>(() => initial ?? resolveInitialLanguage(browserStorage()));

  useEffect(() => {
    document.documentElement.lang = lang;
    persistLanguage(lang, browserStorage());
  }, [lang]);

  const t = useCallback((key: MessageKey, params?: Params) => translate(lang, key, params), [lang]);
  const tOptional = useCallback((key: string, params?: Params) => translateOptional(lang, key, params), [lang]);
  const value = useMemo<I18nValue>(
    () => ({ lang, locale: localeOf(lang), setLang, t, tOptional }),
    [lang, t, tOptional],
  );
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useI18n must be used inside <LanguageProvider>');
  return ctx;
}


// ---------------------------------------------------------------------------------------------------------------
// Hazard-scoped wording
// ---------------------------------------------------------------------------------------------------------------
const HazardContext = createContext<HazardId>('wildfire');

/** The hazard whose workspace is open (wildfire when no scope is mounted). */
export function useHazard(): HazardId {
  return useContext(HazardContext);
}

/**
 * Inside this scope every translation first looks for a hazard-specific text under ``<key>.<hazard>`` and falls back to
 * the base key. That is how the shared components (results, exposure dashboard, layer panel...) say "detected
 * inundation extent" for a flood and keep every wildfire text exactly as it was, without touching those components.
 */
export function HazardTextScope({ hazard, children }: { hazard: HazardId; children: ReactNode }) {
  const parent = useI18n();
  const value = useMemo<I18nValue>(() => ({
    ...parent,
    t: (key, params) => translateOptional(parent.lang, `${key}.${hazard}`, params) ?? parent.t(key, params),
    tOptional: (key, params) =>
      translateOptional(parent.lang, `${key}.${hazard}`, params) ?? parent.tOptional(key, params),
  }), [parent, hazard]);
  return (
    <HazardContext.Provider value={hazard}>
      <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
    </HazardContext.Provider>
  );
}
