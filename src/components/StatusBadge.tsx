import type { FieldStatus } from '../api/types';
import { IconCheck, IconFlag, IconWarn } from './icons';

const MAP: Record<FieldStatus, { label: string; aria: string; Icon: typeof IconCheck }> = {
  match:  { label: 'Match',                  aria: 'Match',                          Icon: IconCheck },
  likely: { label: 'Likely match — confirm', aria: 'Likely match, confirm needed',   Icon: IconWarn  },
  flag:   { label: 'Flag — review',          aria: 'Flag, needs review',             Icon: IconFlag  },
};

export interface StatusBadgeProps {
  status: FieldStatus;
  size?: 'sm' | 'md';
}

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const { label, aria, Icon } = MAP[status];
  return (
    <span className={`status status--${status}`} role="status" aria-label={aria} data-size={size}>
      <span className="status__icon" aria-hidden="true">
        <Icon size={size === 'sm' ? 10 : 12} strokeWidth={3} />
      </span>
      <span>{label}</span>
    </span>
  );
}
