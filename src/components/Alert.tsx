import type { ReactNode } from 'react';
import { IconCheck, IconFlag, IconInfo, IconWarn, IconClose } from './icons';

type Variant = 'info' | 'success' | 'warning' | 'error';

export interface AlertProps {
  variant?: Variant;
  title?: ReactNode;
  onDismiss?: () => void;
  children?: ReactNode;
}

const ICON: Record<Variant, typeof IconInfo> = {
  info: IconInfo, success: IconCheck, warning: IconWarn, error: IconFlag,
};

export default function Alert({ variant = 'info', title, children, onDismiss }: AlertProps) {
  const I = ICON[variant];
  const role = variant === 'error' || variant === 'warning' ? 'alert' : 'status';
  return (
    <div className={`alert alert--${variant}`} role={role}>
      <span className="alert__icon"><I size={20} strokeWidth={2.5} aria-hidden="true" /></span>
      <div className="alert__body">
        {title && <p className="alert__title">{title}</p>}
        {typeof children === 'string' ? <p>{children}</p> : children}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          style={{
            appearance: 'none', border: 0, background: 'transparent', cursor: 'pointer',
            color: 'currentColor', padding: 4, borderRadius: 4,
          }}
        >
          <IconClose size={18} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
