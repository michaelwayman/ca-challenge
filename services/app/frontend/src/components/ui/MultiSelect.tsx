import { type ReactNode, type RefObject, useId } from 'react';

import { Dropdown, type DropdownLayoutProps } from './Dropdown';

export interface MultiSelectOption {
  value: string;
  label: string;
  /** Shown at the end of the row (and read out) when present. */
  count?: number;
}

interface MultiSelectProps extends DropdownLayoutProps {
  label: string;
  icon: ReactNode;
  options: readonly MultiSelectOption[];
  selected: readonly string[];
  onChange: (selected: string[]) => void;
  /** Owned by the parent so it can return focus here after a tag is removed. */
  triggerRef?: RefObject<HTMLButtonElement | null>;
  /** What the count means, for the screen reader ("brands"); singular is derived by dropping a trailing "s". */
  countNoun?: string;
}

/** Choose any number: a button that opens a menu of real checkboxes. Choices apply as you make
 *  them (there is nothing to submit); Done only closes the menu. The list scrolls, so it can
 *  grow with the data behind it. */
export function MultiSelect({
  label,
  icon,
  options,
  selected,
  onChange,
  triggerRef,
  countNoun = 'items',
  ...layout
}: MultiSelectProps) {
  const countId = useId();
  const singular = countNoun.replace(/s$/, '');
  const toggle = (value: string, checked: boolean) =>
    onChange(checked ? [...selected, value] : selected.filter((v) => v !== value));

  return (
    <Dropdown
      icon={icon}
      label={label}
      badge={
        selected.length > 0 ? (
          <>
            {selected.length} <span className="visually-hidden">selected</span>
          </>
        ) : undefined
      }
      active={selected.length > 0}
      menuLabel={label}
      triggerRef={triggerRef}
      {...layout}
    >
      {({ close }) => (
        <>
          <ul className="options">
            {options.map((option) => {
              const { count } = option;
              const describedBy = `${countId}-${option.value}`;
              return (
                <li key={option.value}>
                  <label className="option">
                    <input
                      type="checkbox"
                      className="checkbox"
                      checked={selected.includes(option.value)}
                      aria-describedby={count === undefined ? undefined : describedBy}
                      onChange={(event) => toggle(option.value, event.target.checked)}
                    />
                    {option.label}
                    {count !== undefined && (
                      <span className="count" aria-hidden="true">
                        {count}
                      </span>
                    )}
                  </label>
                  {count !== undefined && (
                    <span id={describedBy} className="visually-hidden">
                      {count} {count === 1 ? singular : countNoun}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
          <div className="footer">
            {selected.length > 0 ? (
              <button type="button" className="button link" onClick={() => onChange([])}>
                Clear
              </button>
            ) : (
              <span />
            )}
            <button type="button" className="button small" onClick={close}>
              Done
            </button>
          </div>
        </>
      )}
    </Dropdown>
  );
}
