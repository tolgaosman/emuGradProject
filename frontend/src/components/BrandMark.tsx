interface BrandMarkProps {
  size?: number
}

/** The PlagCheck mark as inline SVG: magnifier and code glyph in
 * `currentColor` (so it follows the theme), document lines and the check
 * badge in the brand amber. Same geometry as `public/favicon.svg`. */
export function BrandMark({ size = 24 }: BrandMarkProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <circle cx="13.5" cy="13.5" r="9.5" stroke="currentColor" strokeWidth="2.6" />
      <path
        d="M9.6 10.4 7.4 13.5l2.2 3.1M13.6 10.4l-2.1 6.2"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M16.5 7.8v11.4M18.6 10h3M18.6 13h3M18.6 16h2.2"
        stroke="var(--accent)"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path d="m20.6 26.2 6.2-6.2" stroke="currentColor" strokeWidth="2.8" strokeLinecap="round" />
      <circle cx="23.6" cy="23.6" r="5.4" fill="var(--accent)" />
      <path
        d="m21.1 23.7 1.7 1.7 3.3-3.4"
        stroke="var(--accent-ink)"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
