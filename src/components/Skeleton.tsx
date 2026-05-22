import type { CSSProperties } from 'react';

interface SkelProps {
  width?: number | string;
  height?: number;
  style?: CSSProperties;
}

export function SkeletonLine({ width = '100%', height, style }: SkelProps) {
  return <span className="skel skel--line" aria-hidden="true" style={{ width, height, ...style }} />;
}

export function SkeletonBlock({ width = '100%', height = 120, style }: SkelProps) {
  return <span className="skel skel--block" aria-hidden="true" style={{ width, height, ...style }} />;
}
