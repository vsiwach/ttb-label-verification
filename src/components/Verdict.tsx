import type { ReactNode } from 'react';
import type { FieldStatus } from '../api/types';
import { IconCheck, IconFlag, IconWarn } from './icons';

export interface VerdictProps {
  status: FieldStatus;
  title: ReactNode;
  sub?: ReactNode;
}

const ICON: Record<FieldStatus, typeof IconCheck> = {
  match: IconCheck, likely: IconWarn, flag: IconFlag,
};

export default function Verdict({ status, title, sub }: VerdictProps) {
  const Icon = ICON[status];
  return (
    <div className={`verdict verdict--${status}`} role="status" aria-live="polite">
      <span className="verdict__icon" aria-hidden="true">
        <Icon size={20} strokeWidth={2.5} />
      </span>
      <div>
        <p className="verdict__title">{title}</p>
        {sub && <p className="verdict__sub">{sub}</p>}
      </div>
    </div>
  );
}
