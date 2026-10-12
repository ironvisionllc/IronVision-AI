// Single swap point for brand assets. All files are generated from original/Logo-01.webp by scripts/build_brand_assets.py.
// When the official vector arrives, point these exports at it (e.g. an .svg needs no srcset) – every usage follows.
import mark1 from "./logo-mark-40.png";
import mark2 from "./logo-mark-80.png";
import markDark1 from "./logo-mark-dark-40.png";
import markDark2 from "./logo-mark-dark-80.png";
import markMono1 from "./logo-mark-mono-40.png";
import markMono2 from "./logo-mark-mono-80.png";
import markLg from "./logo-mark.png";
import lockup1 from "./logo-lockup-288.png";
import lockup2 from "./logo-lockup-576.png";
import lockupDark1 from "./logo-lockup-dark-288.png";
import lockupDark2 from "./logo-lockup-dark-576.png";

export interface BrandImage { src: string; srcSet: string }
const img = (a: string, b: string, c?: string): BrandImage => ({ src: a, srcSet: `${a} 1x, ${b} 2x${c ? `, ${c} 4x` : ""}` });

export const mark = img(mark1, mark2, markLg);
export const markDark = img(markDark1, markDark2);
export const markMono = img(markMono1, markMono2);
export const lockup = img(lockup1, lockup2);
export const lockupDark = img(lockupDark1, lockupDark2);
