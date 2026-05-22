import type { ReactNode, SVGProps } from 'react';

export type IconProps = SVGProps<SVGSVGElement> & {
  size?: number;
  strokeWidth?: number;
};

function Icon({ size = 20, strokeWidth = 2, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconCheck     = (p: IconProps) => <Icon {...p}><path d="M4 12.6 9.2 18 20 7" /></Icon>;
export const IconWarn      = (p: IconProps) => <Icon {...p}><path d="M12 4 2.5 20h19L12 4z" /><path d="M12 10v4" /><path d="M12 17.5h.01" /></Icon>;
export const IconFlag      = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5" /><path d="M12 16.5h.01" /></Icon>;
export const IconUpload    = (p: IconProps) => <Icon {...p}><path d="M12 17V5" /><path d="M6 11l6-6 6 6" /><path d="M4 19h16" /></Icon>;
export const IconImage     = (p: IconProps) => <Icon {...p}><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="2" /><path d="m21 17-5-5-9 9" /></Icon>;
export const IconFolder    = (p: IconProps) => <Icon {...p}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" /></Icon>;
export const IconArrowR    = (p: IconProps) => <Icon {...p}><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></Icon>;
export const IconArrowL    = (p: IconProps) => <Icon {...p}><path d="M19 12H5" /><path d="m11 18-6-6 6-6" /></Icon>;
export const IconChevronR  = (p: IconProps) => <Icon {...p}><path d="m9 6 6 6-6 6" /></Icon>;
export const IconPlay      = (p: IconProps) => <Icon {...p}><path d="M7 5v14l12-7L7 5z" fill="currentColor" stroke="none" /></Icon>;
export const IconClose     = (p: IconProps) => <Icon {...p}><path d="M6 6l12 12" /><path d="M18 6 6 18" /></Icon>;
export const IconInfo      = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v6" /><path d="M12 7.5h.01" /></Icon>;
export const IconLightning = (p: IconProps) => <Icon {...p}><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" /></Icon>;
export const IconClock     = (p: IconProps) => <Icon {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>;
export const IconShield    = (p: IconProps) => <Icon {...p}><path d="M12 3 4 6v6c0 5 3.5 8.5 8 9 4.5-.5 8-4 8-9V6l-8-3z" /></Icon>;
