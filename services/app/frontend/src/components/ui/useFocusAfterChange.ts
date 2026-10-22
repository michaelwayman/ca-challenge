import { useCallback, useEffect, useRef } from 'react';

type FindElement = () => HTMLElement | null | undefined;

/** Moves keyboard focus once a change has rendered. The element that had focus (a tag's remove
 *  button) may be gone by then, and without this focus would fall back to the top of the page.
 *  Call the returned function with a lookup just before making the change; it runs after
 *  `dependency` next changes and the new DOM is in place. */
export function useFocusAfterChange(dependency: unknown) {
  const pending = useRef<FindElement | null>(null);

  useEffect(() => {
    const find = pending.current;
    if (!find) return;
    pending.current = null;
    find()?.focus();
  }, [dependency]);

  return useCallback((find: FindElement) => {
    pending.current = find;
  }, []);
}
