import { type RefObject, useEffect, useRef, useState } from 'react';

/** Open/close state for a button that reveals a panel. While open, a click or keyboard focus
 *  landing outside `rootRef` closes it, and Escape closes it and returns focus to the button. */
export function useDisclosure(triggerRef: RefObject<HTMLButtonElement | null>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const closeIfOutside = (event: Event) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener('pointerdown', closeIfOutside);
    document.addEventListener('focusin', closeIfOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeIfOutside);
      document.removeEventListener('focusin', closeIfOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [open, triggerRef]);

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  return { open, setOpen, rootRef, close };
}
