interface StatusInput {
  /** Nothing has loaded yet (or the page is being corrected). */
  loading: boolean;
  /** Showing the previous results while the next ones load. */
  updating: boolean;
  page: number;
  pageSize: number;
  /** Total matches and how many are on this page; undefined until something has loaded. */
  total: number | undefined;
  shown: number;
}

/** The line read out to screen readers as results change ("Showing 1–12 of 40 brands"). */
export function resultsStatus({
  loading,
  updating,
  page,
  pageSize,
  total,
  shown,
}: StatusInput): string {
  if (loading) return 'Loading brands…';
  if (updating) return 'Updating results…';
  if (total === undefined) return '';
  if (total === 0) return 'No brands found.';
  const first = (page - 1) * pageSize + 1;
  return `Showing ${first}–${first + shown - 1} of ${total} brand${total === 1 ? '' : 's'}`;
}
