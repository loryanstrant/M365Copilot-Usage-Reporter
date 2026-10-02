// Guess whether an uploaded logo is dark enough to disappear on a dark
// background, so the "white panel" option can be pre-ticked rather than left
// for the admin to discover after their logo vanishes at night.
//
// Draws the file to a small canvas and averages WCAG relative luminance over
// the pixels that are actually painted. Transparent padding is excluded —
// almost every logo is mostly transparent, and including it would drag the
// average towards whatever the browser fills with and make the answer useless.
//
// The result is a convenience, not a security claim: it is sent as a preference
// the admin can override, so a wrong answer costs one click.

const SIZE = 32;
const ALPHA_FLOOR = 16; // ignore near-transparent pixels
const DARK_BELOW = 0.25;

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/**
 * Resolve true when the logo reads as dark, false when it does not, and null
 * when we could not tell (an unreadable file, a browser without canvas). Null
 * leaves the checkbox alone rather than guessing.
 */
export async function looksDark(file: File): Promise<boolean | null> {
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("could not decode"));
      img.src = url;
    });

    const canvas = document.createElement("canvas");
    canvas.width = SIZE;
    canvas.height = SIZE;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return null;
    ctx.drawImage(image, 0, 0, SIZE, SIZE);

    // A blob: URL is same-origin, so the canvas is not tainted and this read
    // is allowed. (It would throw for a cross-origin image.)
    const { data } = ctx.getImageData(0, 0, SIZE, SIZE);

    let total = 0;
    let counted = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < ALPHA_FLOOR) continue;
      total +=
        0.2126 * channel(data[i]) +
        0.7152 * channel(data[i + 1]) +
        0.0722 * channel(data[i + 2]);
      counted += 1;
    }
    if (counted === 0) return null;
    return total / counted < DARK_BELOW;
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}
