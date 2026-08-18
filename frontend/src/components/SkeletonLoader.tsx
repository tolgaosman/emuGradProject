interface SkeletonLoaderProps {
  label: string
  sublabel?: string
}

export function SkeletonLoader({ label, sublabel }: SkeletonLoaderProps) {
  return (
    <div className="skeleton-loader" role="status" aria-live="polite">
      <div className="skeleton-spinner" aria-hidden="true" />
      <p className="skeleton-label">{label}</p>
      {sublabel && <p className="skeleton-sublabel">{sublabel}</p>}
    </div>
  )
}
