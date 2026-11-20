import { useEffect, useState } from 'react';
import Header from './components/Header';
import HazardLanding from './components/HazardLanding';
import HazardSelector from './components/HazardSelector';
import { mergeHazards } from './hazards/registry';
import { HazardTextScope } from './i18n/LanguageContext';
import FloodPage from './pages/FloodPage';
import HomePage from './pages/HomePage';
import { api } from './services/api';
import type { HazardId, HazardInfo } from './types/api';

/**
 * Multi-hazard shell: landing -> hazard workspace. Choosing or switching a hazard never starts a computation, and each
 * hazard workspace starts fully reset (area, dates, results, map view).
 */
export default function App({ initialHazard = null }: { initialHazard?: HazardId | null }) {
  const [hazard, setHazard] = useState<HazardId | null>(initialHazard);
  const [hazards, setHazards] = useState<HazardInfo[]>(() => mergeHazards(null));

  // Module status from the backend (an older, wildfire-only backend just keeps the built-in fallback).
  useEffect(() => {
    let cancelled = false;
    api.hazards().then((h) => { if (!cancelled) setHazards(mergeHazards(h)); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const info = hazards.find((h) => h.id === hazard) ?? null;
  const selector = <HazardSelector hazards={hazards} current={hazard} onSelect={setHazard} />;

  return (
      <div className="app">
        <Header hazard={hazard} selector={selector} />
        {hazard === null && <HazardLanding hazards={hazards} onSelect={setHazard} />}
        {hazard === 'wildfire' && <HazardTextScope key="wildfire" hazard="wildfire"><HomePage embedded /></HazardTextScope>}
        {hazard === 'flood' && info && <FloodPage key="flood" info={info} />}
      </div>
  );
}
