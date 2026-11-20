import type { HazardId } from '../types/api';
import FlameIcon from './FlameIcon';

const base = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, className: 'flame-icon' } as const;

/** Waves (Lucide "waves", ISC). */
export function WaveIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} {...base}>
      <path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
      <path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
      <path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
    </svg>
  );
}

/** Layers: the neutral platform mark used on the landing page. */
export function PlatformIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} {...base}>
      <path d="m12 2 10 5-10 5L2 7l10-5z" /><path d="m2 12 10 5 10-5" /><path d="m2 17 10 5 10-5" />
    </svg>
  );
}

export function HazardIcon({ hazard, size = 18 }: { hazard: HazardId | null; size?: number }) {
  if (hazard === 'wildfire') return <FlameIcon size={size} />;
  if (hazard === 'flood') return <WaveIcon size={size} />;
  return <PlatformIcon size={size} />;
}
