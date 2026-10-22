import { type KeyboardEvent, useId, useRef } from 'react';

export interface ListboxOption<T extends string> {
  value: T;
  label: string;
}

interface ListboxProps<T extends string> {
  label: string;
  options: readonly ListboxOption<T>[];
  value: T;
  onChoose: (value: T) => void;
}

/** A single-choice list. Each option is a tab stop, as checkboxes are: Tab and Shift+Tab walk
 *  them without choosing, Enter or Space chooses. The arrow keys, Home, End and typing a letter
 *  move between the options too. Meant to sit in a Dropdown menu. */
export function Listbox<T extends string>({ label, options, value, onChoose }: ListboxProps<T>) {
  const optionRefs = useRef<(HTMLLIElement | null)[]>([]);
  const menuId = useId();
  const last = options.length - 1;

  const focusOption = (index: number) => optionRefs.current[index]?.focus();

  const onKeyDown = (event: KeyboardEvent<HTMLLIElement>, index: number, current: T) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        focusOption(Math.min(index + 1, last));
        return;
      case 'ArrowUp':
        event.preventDefault();
        focusOption(Math.max(index - 1, 0));
        return;
      case 'Home':
        event.preventDefault();
        focusOption(0);
        return;
      case 'End':
        event.preventDefault();
        focusOption(last);
        return;
      case 'Enter':
      case ' ':
        event.preventDefault();
        onChoose(current);
        return;
    }
    if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const letter = event.key.toLowerCase();
      // Search from the option after this one and wrap, so repeating a letter cycles.
      for (let step = 1; step <= options.length; step++) {
        const candidate = (index + step) % options.length;
        if (options[candidate]?.label.toLowerCase().startsWith(letter)) {
          focusOption(candidate);
          return;
        }
      }
    }
  };

  return (
    <ul className="dropdown__options" role="listbox" id={menuId} aria-label={label}>
      {options.map((option, index) => {
        const selected = option.value === value;
        return (
          <li
            key={option.value}
            ref={(element) => {
              optionRefs.current[index] = element;
            }}
            role="option"
            aria-selected={selected}
            tabIndex={0}
            className={`dropdown__option${selected ? ' dropdown__option--selected' : ''}`}
            onClick={() => onChoose(option.value)}
            onKeyDown={(event) => onKeyDown(event, index, option.value)}
          >
            <span className={`radio${selected ? ' radio--checked' : ''}`} aria-hidden="true" />
            {option.label}
          </li>
        );
      })}
    </ul>
  );
}
