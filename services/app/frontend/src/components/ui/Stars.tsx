interface StarsProps {
  rating: number | null;
  showValue?: boolean;
}

/** Five stars filled to the nearest whole star; the exact value is in the label.
 *  Same markup and rounding as the Django `stars` template tag. */
export function Stars({ rating, showValue = false }: StarsProps) {
  if (rating === null) return <span className="stars none">No ratings yet</span>;
  const filled = Math.max(0, Math.min(5, Math.round(rating)));
  const value = rating.toFixed(1);
  return (
    <span className="stars" role="img" aria-label={`Rating: ${value} out of 5`}>
      {Array.from({ length: 5 }, (_, index) => (
        <span
          key={index}
          className={`star-${index < filled ? 'full' : 'empty'}`}
          aria-hidden="true"
        >
          {index < filled ? '★' : '☆'}
        </span>
      ))}
      {showValue && (
        <span className="rating-value" aria-hidden="true">
          {value}
        </span>
      )}
    </span>
  );
}
