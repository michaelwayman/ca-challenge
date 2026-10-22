import { type ReactNode, type RefObject, useId, useRef } from 'react';

import { ChevronDownIcon } from './icons';
import { useDisclosure } from './useDisclosure';

/** How a dropdown sits in its page, shared by the components built on it. */
export interface DropdownLayoutProps {
  /** Which edge of the button the menu lines up with. */
  align?: 'start' | 'end';
  /** A narrower menu, for short labels. */
  compact?: boolean;
  /** On a phone the menu spans the nearest positioned ancestor (a toolbar), not the button. */
  sheet?: boolean;
  className?: string;
}

interface DropdownProps extends DropdownLayoutProps {
  icon: ReactNode;
  label: ReactNode;
  /** A short count inside the button, such as how many options are chosen. */
  badge?: ReactNode;
  /** Highlights the button: something is chosen. */
  active?: boolean;
  /** Names the menu, which is exposed as a group of controls. */
  menuLabel: string;
  /** Owned by the parent when it needs to return focus to the button. */
  triggerRef?: RefObject<HTMLButtonElement | null>;
  /** The menu's contents. `close` shuts the menu and puts focus back on the button. */
  children: (menu: { close: () => void }) => ReactNode;
}

/** A button that opens a floating menu. It owns opening and closing (a click or focus outside
 *  closes it, Escape closes it and returns focus to the button); what is inside the menu, and
 *  what choosing does, is up to the caller. See MultiSelect. */
export function Dropdown({
  icon,
  label,
  badge,
  active = false,
  align = 'start',
  compact = false,
  sheet = false,
  className,
  menuLabel,
  triggerRef,
  children,
}: DropdownProps) {
  const ownRef = useRef<HTMLButtonElement>(null);
  const buttonRef = triggerRef ?? ownRef;
  const { open, setOpen, rootRef, close } = useDisclosure(buttonRef);
  const menuId = useId();

  const rootClass = ['dropdown', sheet && 'dropdown--sheet', className].filter(Boolean).join(' ');
  const menuClass = [
    'dropdown__menu',
    align === 'end' && 'dropdown__menu--end',
    compact && 'dropdown__menu--compact',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={rootClass} ref={rootRef}>
      <button
        type="button"
        ref={buttonRef}
        className={`dropdown__trigger${active ? ' dropdown__trigger--active' : ''}`}
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen(!open)}
      >
        {icon}
        {label}
        {badge !== undefined && (
          <>
            {/* Explicit space, so the name reads "Industry 2 selected" however it is computed. */}{' '}
            <span className="dropdown__badge">{badge}</span>
          </>
        )}
        <ChevronDownIcon className="dropdown__chevron" />
      </button>
      {open && (
        <div className={menuClass} id={menuId} role="group" aria-label={menuLabel}>
          {children({ close })}
        </div>
      )}
    </div>
  );
}
