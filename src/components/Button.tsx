import type { ButtonHTMLAttributes, ComponentType, ReactNode } from 'react';
import type { IconProps } from './icons';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
type Size = 'md' | 'lg';

export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'type'> {
  variant?: Variant;
  size?: Size;
  icon?: ComponentType<IconProps>;
  trailingIcon?: ComponentType<IconProps>;
  type?: 'button' | 'submit' | 'reset';
  children?: ReactNode;
}

export default function Button({
  variant = 'primary',
  size = 'md',
  icon: LeadingIcon,
  trailingIcon: TrailingIcon,
  disabled,
  type = 'button',
  children,
  className,
  onClick,
  ...rest
}: ButtonProps) {
  const cls = [
    'btn',
    variant === 'secondary' && 'btn--secondary',
    variant === 'danger'    && 'btn--danger',
    variant === 'ghost'     && 'btn--ghost',
    size === 'lg' && 'btn--lg',
    className,
  ].filter(Boolean).join(' ');
  const iconSize = size === 'lg' ? 20 : 18;
  return (
    <button
      type={type}
      className={cls}
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      aria-disabled={disabled || undefined}
      {...rest}
    >
      {LeadingIcon && <LeadingIcon size={iconSize} aria-hidden="true" />}
      {children !== undefined && <span>{children}</span>}
      {TrailingIcon && <TrailingIcon size={iconSize} aria-hidden="true" />}
    </button>
  );
}
