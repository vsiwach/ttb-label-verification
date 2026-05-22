import type { FieldStatus } from '../api/types';
import Button from './Button';
import StatusBadge from './StatusBadge';
import { IconArrowR, IconCheck } from './icons';

export interface FieldRowProps {
  fieldName: string;
  declaredValue: string;
  extractedValue: string;
  status: FieldStatus;
  evidenceCropUrl?: string;
  regulationCite?: string;
  onConfirm?: () => void;
}

export default function FieldRow({
  fieldName, declaredValue, extractedValue, status,
  evidenceCropUrl, regulationCite, onConfirm,
}: FieldRowProps) {
  return (
    <div className="fieldrow" role="group" aria-label={`${fieldName}: ${status}`}>
      <div className="fieldrow__evidence" aria-hidden="true">
        {evidenceCropUrl
          ? <img src={evidenceCropUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <span>crop</span>}
      </div>
      <div className="fieldrow__content">
        <div>
          <div className="fieldrow__name">{fieldName}</div>
          <div className="fieldrow__decl">Declared: {declaredValue}</div>
        </div>
        <div>
          <div className="fieldrow__name">Extracted</div>
          <div className="fieldrow__val">{extractedValue}</div>
          {regulationCite && (
            <div style={{ fontSize: 12, color: 'var(--color-ink-subtle)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>
              {regulationCite}
            </div>
          )}
        </div>
        <div className="fieldrow__statusrow">
          <StatusBadge status={status} />
          <div className="fieldrow__actions">
            {status === 'likely' && (
              <Button variant="secondary" icon={IconCheck} onClick={onConfirm}>Confirm</Button>
            )}
            {status === 'flag' && (
              <Button variant="ghost" trailingIcon={IconArrowR}>Review</Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
