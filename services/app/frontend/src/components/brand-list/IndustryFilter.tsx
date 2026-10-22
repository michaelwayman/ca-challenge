import type { RefObject } from 'react';

import type { Industry } from '../../api';
import { FilterIcon } from '../ui/icons';
import { MultiSelect } from '../ui/MultiSelect';

interface IndustryFilterProps {
  industries: Industry[];
  selected: string[];
  onChange: (slugs: string[]) => void;
  triggerRef: RefObject<HTMLButtonElement | null>;
}

/** Filter the brands by industry: any number can be chosen. */
export function IndustryFilter({
  industries,
  selected,
  onChange,
  triggerRef,
}: IndustryFilterProps) {
  return (
    <MultiSelect
      label="Industry"
      icon={<FilterIcon />}
      options={industries.map((i) => ({ value: i.slug, label: i.name, count: i.brand_count }))}
      selected={selected}
      onChange={onChange}
      triggerRef={triggerRef}
      countNoun="brands"
      sheet
    />
  );
}
