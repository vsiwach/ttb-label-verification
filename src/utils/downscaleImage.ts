// Client-side image downscale + JPEG re-encode. Runs entirely in the browser
// on a 2D canvas — no upload, no external service.

export interface DownscaleResult {
  blob: Blob;
  dataUrl: string;
  width: number;
  height: number;
  originalSize: number;
  optimizedSize: number;
  originalWidth: number;
  originalHeight: number;
}

export interface DownscaleOptions {
  maxMegapixels?: number;
  quality?: number;
}

export async function downscaleImage(
  file: File | Blob,
  opts: DownscaleOptions = {},
): Promise<DownscaleResult> {
  const maxMegapixels = opts.maxMegapixels ?? 2;
  const quality       = opts.quality       ?? 0.85;

  if (!file || !(file instanceof Blob)) {
    throw new Error('downscaleImage: a File or Blob is required.');
  }
  if (!/^image\//.test(file.type || '')) {
    throw new Error('That file does not look like an image. Please use JPEG or PNG.');
  }

  const originalSize = file.size;
  const objectUrl = URL.createObjectURL(file);

  let img: HTMLImageElement;
  try {
    img = await loadImage(objectUrl);
  } catch {
    URL.revokeObjectURL(objectUrl);
    throw new Error('That image could not be read. It may be corrupt — please pick a different file.');
  }

  const { naturalWidth: oW, naturalHeight: oH } = img;
  if (!oW || !oH) {
    URL.revokeObjectURL(objectUrl);
    throw new Error('That image has no readable dimensions. Please pick a different file.');
  }

  const maxPixels = maxMegapixels * 1_000_000;
  const currentPixels = oW * oH;
  const scale = currentPixels > maxPixels ? Math.sqrt(maxPixels / currentPixels) : 1;
  const w = Math.max(1, Math.round(oW * scale));
  const h = Math.max(1, Math.round(oH * scale));

  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    URL.revokeObjectURL(objectUrl);
    throw new Error("Your browser couldn't optimize the image. Try a different browser.");
  }
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(img, 0, 0, w, h);
  URL.revokeObjectURL(objectUrl);

  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (b) => b ? resolve(b) : reject(new Error("Couldn't compress the image. Please try again.")),
      'image/jpeg',
      quality,
    );
  });
  const dataUrl = canvas.toDataURL('image/jpeg', quality);

  return {
    blob,
    dataUrl,
    width: w,
    height: h,
    originalSize,
    optimizedSize: blob.size,
    originalWidth:  oW,
    originalHeight: oH,
  };
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload  = () => resolve(img);
    img.onerror = () => reject(new Error('image load failed'));
    img.src = src;
  });
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
