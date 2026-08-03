interface BrandMarkProps {
  size?: number
}

/** Inline redraw of the PlagCheck magnifier mark — ring/glyph in
 * `currentColor` so it inherits `--text` in both themes, check badge in
 * `--accent`. Replaces the raster logo in the top bar (see BrandMark.tsx
 * plan notes for why); the original PNG assets stay put for the favicon. */
export function BrandMark({ size = 22 }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      aria-hidden="true"
      className="brand-mark"
    >
      <circle cx="13.5" cy="13.5" r="9.5" stroke="currentColor" strokeWidth="2.4" />
      <line x1="16" y1="7.5" x2="16" y2="19.5" stroke="var(--accent)" strokeWidth="1.6" />
      <line x1="10.2" y1="10.6" x2="13" y2="13.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <line x1="13" y1="10.6" x2="10.2" y2="13.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <line x1="18.4" y1="9.8" x2="21.6" y2="9.8" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
      <line x1="18.4" y1="12.6" x2="21.6" y2="12.6" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
      <line x1="18.4" y1="15.4" x2="21.6" y2="15.4" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
      <line x1="20.5" y1="26.5" x2="27" y2="20" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      <circle cx="23.5" cy="23.5" r="5" fill="var(--accent)" />
      <path
        d="M21 23.5l1.7 1.7L26 21.8"
        stroke="var(--accent-ink)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  )
}
