import { useId } from 'react';

import { type Ordering, ORDERINGS } from '../../urlState';
import { ChevronDownIcon, SortIcon } from '../ui/icons';

const LABELS: Record<Ordering, string> = {
  name: 'Name (A–Z)',
  '-average_rating': 'Highest rated',
  average_rating: 'Lowest rated',
  '-review_count': 'Most reviews',
  review_count: 'Fewest reviews',
};

const isOrdering = (value: string): value is Ordering => ORDERINGS.includes(value as Ordering);

interface SortControlProps {
  value: Ordering;
  onChange: (ordering: Ordering) => void;
}

/** Choose the order the brands are listed in. A native select: the browser and the platform
 *  supply the keyboard, screen reader and touch behaviour, and a phone shows its own picker. */
export function SortControl({ value, onChange }: SortControlProps) {
  const id = useId();
  return (
    <div className="sort-select">
      <label htmlFor={id}>Sort by</label>
      <div className="field">
        <SortIcon className="icon" />
        <select
          id={id}
          value={value}
          onChange={(event) => {
            if (isOrdering(event.target.value)) onChange(event.target.value);
          }}
        >
          {ORDERINGS.map((ordering) => (
            <option key={ordering} value={ordering}>
              {LABELS[ordering]}
            </option>
          ))}
        </select>
        <ChevronDownIcon className="chevron" />
      </div>
    </div>
  );
}
