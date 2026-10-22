import { useCallback, useMemo, useSyncExternalStore } from 'react';

import { applyPatch, type ListState, parseState, serializeState } from './urlState';

// pushState does not fire popstate, so changes we make ourselves notify subscribers
// through this set; back/forward still arrive as real popstate events.
const listeners = new Set<() => void>();

function subscribe(callback: () => void) {
  listeners.add(callback);
  window.addEventListener('popstate', callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener('popstate', callback);
  };
}

const getSearch = () => window.location.search;

interface NavigateOptions {
  /** Replace the history entry instead of adding one (for corrections, not choices). */
  replace?: boolean;
}

export function updateListState(patch: Partial<ListState>, { replace = false } = {}) {
  const next = applyPatch(parseState(window.location.search), patch);
  const url = `${window.location.pathname}${serializeState(next)}${window.location.hash}`;
  if (url === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;
  if (replace) window.history.replaceState(null, '', url);
  else window.history.pushState(null, '', url);
  listeners.forEach((listener) => listener());
}

export function useListState() {
  const search = useSyncExternalStore(subscribe, getSearch);
  const state = useMemo(() => parseState(search), [search]);
  const setState = useCallback(
    (patch: Partial<ListState>, options?: NavigateOptions) => updateListState(patch, options),
    [],
  );
  return [state, setState] as const;
}
