import { useRef, useState } from 'react';
import type { ComponentType } from 'react';
import Button from './Button';
import { IconImage, IconUpload, IconWarn, type IconProps } from './icons';

export interface FileDropzoneProps {
  accept?: string;
  multiple?: boolean;
  onFiles?: (files: File[]) => void;
  label?: string;
  hint?: string;
  buttonLabel?: string;
  icon?: ComponentType<IconProps>;
  /** When set, the primary button calls this instead of opening the file
   *  picker. Drag-and-drop still uploads files directly; a small text
   *  link below the dropzone exposes the file-picker fallback. Used by
   *  /upload and /batch to send the user to the sample gallery. */
  onBrowse?: () => void;
  /** Label for the file-picker fallback link, shown only when onBrowse
   *  is set. Defaults to "Or pick a file from your computer". */
  pickerFallbackLabel?: string;
}

export default function FileDropzone({
  accept = 'image/jpeg,image/png',
  multiple = false,
  onFiles,
  label = 'Drag a label image here',
  hint = 'JPEG or PNG, up to 20 MB.',
  buttonLabel = 'Choose a file…',
  icon: IconComp = IconUpload,
  onBrowse,
  pickerFallbackLabel = 'Or pick a file from your computer',
}: FileDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError]       = useState<string | null>(null);

  const acceptList = accept.split(',').map(s => s.trim());
  const isAllowed = (file: File) => {
    if (!acceptList.length) return true;
    return acceptList.some(a => {
      if (a.endsWith('/*')) return file.type.startsWith(a.slice(0, -1));
      return file.type === a;
    });
  };

  function handle(list: FileList | null) {
    const files = Array.from(list || []);
    if (!files.length) return;
    const bad = files.find(f => !isAllowed(f));
    if (bad) {
      setError(`"${bad.name}" is not a supported file type. Please use ${acceptList.join(' or ')}.`);
      return;
    }
    setError(null);
    onFiles?.(multiple ? files : [files[0]]);
  }

  return (
    <div>
      <div
        className={`dropzone ${dragging ? 'dropzone--active' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragEnter={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={(e) => {
          if (e.currentTarget.contains(e.relatedTarget as Node)) return;
          setDragging(false);
        }}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files); }}
        role="region"
        aria-label={label}
        aria-describedby="dz-hint dz-state"
        style={error ? { borderColor: 'var(--status-flag-fg)' } : undefined}
      >
        <span className="dropzone__icon" aria-hidden="true">
          <IconComp size={28} strokeWidth={2} />
        </span>
        <div>
          <p style={{ fontSize: 'var(--fs-20)', fontWeight: 600, color: 'var(--color-ink)', margin: 0 }}>
            {dragging ? 'Release to upload' : label}
          </p>
          <p id="dz-hint" style={{ fontSize: 'var(--fs-16)', color: 'var(--color-ink-muted)', margin: '4px 0 0' }}>
            {hint} <span className="kbd">⌘V</span> to paste also works.
          </p>
        </div>
        <Button
          size="lg"
          icon={IconImage}
          onClick={() => (onBrowse ? onBrowse() : inputRef.current?.click())}
        >
          {buttonLabel}
        </Button>
        <p id="dz-state" className="sr-only" aria-live="polite">
          {dragging ? 'File over drop zone. Release to upload.' : ''}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={multiple}
          hidden
          onChange={(e) => handle(e.target.files)}
        />
      </div>
      {onBrowse && (
        <p style={{ margin: '8px 0 0', textAlign: 'center', fontSize: 13 }}>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            style={{
              background: 'none', border: 'none', padding: 0,
              color: 'var(--color-primary)', fontWeight: 600,
              cursor: 'pointer', textDecoration: 'underline',
            }}
          >{pickerFallbackLabel}</button>
        </p>
      )}
      {error && (
        <div role="alert" className="field__error" style={{ marginTop: 12 }}>
          <IconWarn size={16} aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
