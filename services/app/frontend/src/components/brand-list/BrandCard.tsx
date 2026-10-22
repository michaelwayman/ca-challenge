import type { Brand, TopReview } from '../../api';
import { Stars } from '../ui/Stars';

/** The brand's best review, quoted. */
function ReviewQuote({ review }: { review: TopReview }) {
  return (
    <blockquote className="card__quote">
      <p className="card__snippet">{review.snippet}</p>
      <footer className="card__attribution">
        {review.reviewer ?? 'Anonymous'} &middot; <Stars rating={review.rating} /> &middot;{' '}
        <a href={review.url}>{review.title}</a>
      </footer>
    </blockquote>
  );
}

export function BrandCard({ brand }: { brand: Brand }) {
  return (
    <article className="card">
      {brand.industries.length > 0 && (
        <ul className="card__badges">
          {brand.industries.map((industry) => (
            <li key={industry.slug} className="badge">
              {industry.name}
            </li>
          ))}
        </ul>
      )}
      <h3 className="card__title">
        <a className="card__link" href={brand.url}>
          {brand.name}
        </a>
      </h3>
      <p className="card__rating">
        <Stars rating={brand.average_rating} showValue />{' '}
        <span className="card__count">({brand.review_count})</span>
      </p>
      <p className="card__excerpt">{brand.excerpt}</p>
      {brand.top_review && <ReviewQuote review={brand.top_review} />}
    </article>
  );
}
