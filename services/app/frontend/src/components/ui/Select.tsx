import type { ReactNode } from 'react';

import { Dropdown, type DropdownLayoutProps } from './Dropdown';
import { Listbox, type ListboxOption } from './Listbox';

interface SelectProps<T extends string> extends DropdownLayoutProps {
  /** What is being chosen ("Sort by"). Names the list, and prefixes the button for screen readers. */
  label: string;
  icon: ReactNode;
  value: T;
  options: readonly ListboxOption<T>[];
  onChange: (value: T) => void;
}

/** Choose one of several: a button showing the current choice that opens a list. Chosen
 *  options apply at once and close the menu. (A native select was tried: browsers draw its
 *  popup themselves, and phone emulators draw it detached from the control.) */
export function Select<T extends string>({
  label,
  icon,
  value,
  options,
  onChange,
  ...layout
}: SelectProps<T>) {
  const current = options.find((option) => option.value === value)?.label ?? '';
  return (
    <Dropdown
      icon={icon}
      label={
        <>
          <span className="visually-hidden">{label}</span> {current}
        </>
      }
      {...layout}
    >
      {({ close }) => (
        <Listbox
          label={label}
          options={options}
          value={value}
          onChoose={(next) => {
            onChange(next);
            close();
          }}
        />
      )}
    </Dropdown>
  );
}
