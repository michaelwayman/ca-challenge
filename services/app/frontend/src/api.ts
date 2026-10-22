import { DEFAULT_ORDERING, type ListState } from './urlState';

export interface Industry {
  name: string;
  slug: string;
  /** How many brands are in this industry; the page supplies it, a card payload does not. */
  brand_count?: number;
}

export interface TopReview {
  slug: string;
  title: string;
  rating: number;
  snippet: string;
  reviewer: string | null;
  url: string;
}

export interface Brand {
  name: string;
  slug: string;
  url: string;
  industries: Industry[];
  average_rating: number | null;
  review_count: number;
  excerpt: string;
  top_review: TopReview | null;
}

export interface BrandPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: Brand[];
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export function buildQuery(state: ListState, pageSize: number): string {
  const params = new URLSearchParams();
  state.industries.forEach((slug) => params.append('industry', slug));
  if (state.ordering !== DEFAULT_ORDERING) params.set('ordering', state.ordering);
  if (state.page > 1) params.set('page', String(state.page));
  params.set('page_size', String(pageSize));
  return params.toString();
}

export async function fetchBrands(
  apiUrl: string,
  state: ListState,
  pageSize: number,
  signal?: AbortSignal,
): Promise<BrandPage> {
  const response = await fetch(`${apiUrl}?${buildQuery(state, pageSize)}`, {
    signal,
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new ApiError(response.status, `Brand request failed (${response.status})`);
  }
  return (await response.json()) as BrandPage;
}

/** Retry network errors and 5xx twice; a 4xx will not get better by asking again. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false;
  return failureCount < 2;
}
