import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';

import { ApiError, fetchBrands, shouldRetry } from '../../api';
import type { ListState } from '../../urlState';

// The listing changes rarely, so a short freshness window avoids refetching on every
// filter toggle back and forth without ever showing data more than 30s old.
const STALE_MS = 30_000;

interface UseBrandsOptions {
  apiUrl: string;
  pageSize: number;
  /** Used to fall back to page 1 when the URL points past the last page. */
  goToFirstPage: () => void;
}

/** The brand listing for the current list state. Keeps the previous results while the next
 *  ones load, and quietly corrects a stale bookmark that points past the last page. */
export function useBrands(state: ListState, { apiUrl, pageSize, goToFirstPage }: UseBrandsOptions) {
  const query = useQuery({
    queryKey: ['brands', apiUrl, pageSize, state],
    queryFn: ({ signal }) => fetchBrands(apiUrl, state, pageSize, signal),
    placeholderData: keepPreviousData,
    staleTime: STALE_MS,
    retry: shouldRetry,
  });

  const outOfRange =
    query.error instanceof ApiError && query.error.status === 404 && state.page > 1;
  useEffect(() => {
    if (outOfRange) goToFirstPage();
  }, [outOfRange, goToFirstPage]);

  return { ...query, outOfRange };
}
