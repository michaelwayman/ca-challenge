import { useCallback, useRef } from 'react';

import type { Industry } from '../../api';
import { serializeState } from '../../urlState';
import { useListState } from '../../useListState';
import { CardSkeleton } from '../ui/CardSkeleton';
import { Notice } from '../ui/Notice';
import { Pagination } from '../ui/Pagination';
import { TagList } from '../ui/TagList';
import { useFocusAfterChange } from '../ui/useFocusAfterChange';
import { BrandCard } from './BrandCard';
import { IndustryFilter } from './IndustryFilter';
import { resultsStatus } from './resultsStatus';
import { SortControl } from './SortControl';
import { useBrands } from './useBrands';

interface BrandListProps {
  industries: Industry[];
  apiUrl?: string;
  pageSize?: number;
}

/** Needs a TanStack `QueryClientProvider` above it (see mount.tsx). */
export function BrandList({ industries, apiUrl = '/api/brands/', pageSize = 12 }: BrandListProps) {
  const [state, setState] = useListState();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tagsRef = useRef<HTMLUListElement>(null);
  const focusAfterUpdate = useFocusAfterChange(state.industries);

  const goToFirstPage = useCallback(() => setState({ page: 1 }, { replace: true }), [setState]);
  const { data, isError, isPending, isPlaceholderData, outOfRange, refetch } = useBrands(state, {
    apiUrl,
    pageSize,
    goToFirstPage,
  });
  const loading = isPending || outOfRange;
  const retry = { label: 'Try again', onClick: () => void refetch() };

  const goToPage = (page: number) => {
    setState({ page });
    // Keyboard and screen reader users should land on the new results, not the old link.
    headingRef.current?.focus();
    headingRef.current?.scrollIntoView?.({ block: 'start' });
  };
  const clearFilters = () => {
    focusAfterUpdate(() => triggerRef.current);
    setState({ industries: [] });
  };
  const removeIndustry = (slug: string) => {
    const index = state.industries.indexOf(slug);
    const remaining = state.industries.filter((s) => s !== slug);
    focusAfterUpdate(() =>
      remaining.length === 0
        ? triggerRef.current
        : tagsRef.current?.querySelectorAll<HTMLButtonElement>('button')[
            Math.min(index, remaining.length - 1)
          ],
    );
    setState({ industries: remaining });
  };

  // A slug in the URL that is not in the list (a stale bookmark) still gets a tag to remove.
  const tags = state.industries.map((slug) => ({
    key: slug,
    label: industries.find((i) => i.slug === slug)?.name ?? slug,
  }));
  const total = data?.count;
  const status = resultsStatus({
    loading,
    updating: isPlaceholderData,
    page: state.page,
    pageSize,
    total,
    shown: data?.results.length ?? 0,
  });

  let body;
  if (loading) {
    body = <CardSkeleton />;
  } else if (isError && !data) {
    body = (
      <Notice tone="error" action={retry}>
        We couldn&rsquo;t load the brands. Check your connection and try again.
      </Notice>
    );
  } else if (data && data.count === 0) {
    body = (
      <Notice
        action={
          state.industries.length > 0
            ? { label: 'Clear filters', onClick: clearFilters }
            : undefined
        }
      >
        No brands match these filters.
      </Notice>
    );
  } else if (data) {
    body = (
      <div className={`results${isPlaceholderData ? ' stale' : ''}`} aria-busy={isPlaceholderData}>
        <div className="grid">
          {data.results.map((brand) => (
            <BrandCard key={brand.slug} brand={brand} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="brand-list">
      <div className="toolbar">
        <div className="controls">
          <IndustryFilter
            industries={industries}
            selected={state.industries}
            onChange={(slugs) => setState({ industries: slugs })}
            triggerRef={triggerRef}
          />
          <SortControl value={state.ordering} onChange={(ordering) => setState({ ordering })} />
        </div>
        <p className="status" role="status">
          {status}
        </p>
      </div>
      {tags.length > 0 && (
        <TagList
          tags={tags}
          label="Active industry filters"
          removeLabel={(tag) => `Remove ${tag.label} filter`}
          onRemove={removeIndustry}
          onClear={clearFilters}
          listRef={tagsRef}
        />
      )}
      <h2 className="visually-hidden" tabIndex={-1} ref={headingRef}>
        Brand results
      </h2>
      {isError && data && (
        <Notice tone="error" action={retry}>
          We couldn&rsquo;t refresh these results.
        </Notice>
      )}
      {body}
      {data && (
        <Pagination
          page={state.page}
          totalPages={Math.ceil((total ?? 0) / pageSize)}
          hrefFor={(page) => `${window.location.pathname}${serializeState({ ...state, page })}`}
          onPage={goToPage}
        />
      )}
    </div>
  );
}
