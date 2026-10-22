import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';

import type { Brand, BrandPage } from './api';

export const INDUSTRIES = [
  { name: 'Finance', slug: 'finance', brand_count: 4 },
  { name: 'Telecom', slug: 'telecom', brand_count: 1 },
];

export function makeBrand(slug: string, overrides: Partial<Brand> = {}): Brand {
  const name = slug.replace(/^./, (c) => c.toUpperCase());
  return {
    name,
    slug,
    url: `/brand/${slug}/`,
    industries: [{ name: 'Finance', slug: 'finance' }],
    average_rating: 3.9,
    review_count: 12,
    excerpt: `${name} excerpt.`,
    top_review: {
      slug: `${slug}-best`,
      title: `${name} was great`,
      rating: 5,
      snippet: 'Quick and painless from start to finish…',
      reviewer: 'Sarah K.',
      url: `/review/${slug}-best/`,
    },
    ...overrides,
  };
}

export function makePage(results: Brand[], count = results.length): BrandPage {
  return { count, next: null, previous: null, results };
}

export const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

/** A fresh client per test; retryDelay 0 so the retry policy runs without waiting. */
export function renderWithClient(ui: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}
