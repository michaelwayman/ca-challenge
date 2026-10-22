// The URL query string is the single source of truth for what the list shows.
// Parameter names match the API (industry, ordering, page) so a URL reads the same
// in the address bar and in the request.

export const ORDERINGS = [
  'name',
  '-average_rating',
  'average_rating',
  '-review_count',
  'review_count',
] as const;
export type Ordering = (typeof ORDERINGS)[number];
export const DEFAULT_ORDERING: Ordering = 'name';

export interface ListState {
  industries: string[];
  ordering: Ordering;
  page: number;
}

export const DEFAULT_STATE: ListState = { industries: [], ordering: DEFAULT_ORDERING, page: 1 };

const isOrdering = (value: string | null): value is Ordering =>
  ORDERINGS.includes(value as Ordering);

/** Tolerant: anything unrecognised falls back to the default instead of throwing. */
export function parseState(search: string): ListState {
  const params = new URLSearchParams(search);
  const ordering = params.get('ordering');
  const page = Number.parseInt(params.get('page') ?? '', 10);
  return {
    industries: [...new Set(params.getAll('industry').filter(Boolean))].sort(),
    ordering: isOrdering(ordering) ? ordering : DEFAULT_ORDERING,
    page: Number.isInteger(page) && page >= 1 ? page : 1,
  };
}

/** Canonical query string: defaults omitted and industries sorted, so equal states
 *  always produce equal URLs (and equal cache keys). */
export function serializeState(state: ListState): string {
  const params = new URLSearchParams();
  [...state.industries].sort().forEach((slug) => params.append('industry', slug));
  if (state.ordering !== DEFAULT_ORDERING) params.set('ordering', state.ordering);
  if (state.page > 1) params.set('page', String(state.page));
  const query = params.toString();
  return query ? `?${query}` : '';
}

/** Changing what is listed returns to page 1; changing only the page does not. */
export function applyPatch(state: ListState, patch: Partial<ListState>): ListState {
  const next = { ...state, ...patch };
  const listingChanged = patch.industries !== undefined || patch.ordering !== undefined;
  return listingChanged && patch.page === undefined ? { ...next, page: 1 } : next;
}
