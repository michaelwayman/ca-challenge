interface CardSkeletonProps {
  /** How many placeholder cards. */
  count?: number;
}

/** Cards with the real layout but no content, so the page does not jump on load. */
export function CardSkeleton({ count = 6 }: CardSkeletonProps) {
  return (
    <div className="grid" aria-hidden="true" data-testid="card-skeleton">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="card">
          <span className="skeleton skeleton--badge" />
          <span className="skeleton skeleton--title" />
          <span className="skeleton skeleton--line" />
          <span className="skeleton skeleton--line" />
          <span className="skeleton skeleton--block" />
        </div>
      ))}
    </div>
  );
}
