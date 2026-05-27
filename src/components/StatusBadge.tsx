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
  /** When provided, the badge renders as a button and invokes this on
   *  click — useful in review surfaces where a Flag pill should jump
   *  the agent into the per-item reject dialog with the relevant
   *  reasons pre-checked. Without onClick the badge stays a passive
   *  status indicator (default behaviour). */
  onClick?: () => void;
  /** Optional aria-label override / tooltip for the button form. */
  actionLabel?: string;
}

export default function StatusBadge({ status, size = 'md', onClick, actionLabel }: StatusBadgeProps) {
  const { label, aria, Icon } = MAP[status];
  const content = (
    <>
      <span className="status__icon" aria-hidden="true">
        <Icon size={size === 'sm' ? 10 : 12} strokeWidth={3} />
      </span>
      <span>{label}</span>
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={`status status--${status}`}
        data-size={size}
        aria-label={actionLabel || aria}
        title={actionLabel}
        style={{ cursor: 'pointer', border: 'none', font: 'inherit' }}
      >
        {content}
      </button>
    );
  }

  return (
    <span className={`status status--${status}`} role="status" aria-label={aria} data-size={size}>
      {content}
    </span>
  );
}
