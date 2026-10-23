import type { Brand, TopReview } from '../../api';
import { Stars } from '../ui/Stars';

/** The brand's best review, quoted. */
function ReviewQuote({ review }: { review: TopReview }) {
  return (
    <blockquote>
      <p className="snippet">{review.snippet}</p>
      <footer className="attribution">
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
        <ul className="badges">
          {brand.industries.map((industry) => (
            <li key={industry.slug} className="badge">
              {industry.name}
            </li>
          ))}
        </ul>
      )}
      <h3>
        <a href={brand.url}>{brand.name}</a>
      </h3>
      <p className="rating">
        <Stars rating={brand.average_rating} showValue />{' '}
        <span className="count">({brand.review_count})</span>
      </p>
      <p className="excerpt">{brand.excerpt}</p>
      {brand.top_review && <ReviewQuote review={brand.top_review} />}
    </article>
  );
}
