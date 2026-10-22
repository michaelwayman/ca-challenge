import { type Ordering, ORDERINGS } from '../../urlState';
import { SortIcon } from '../ui/icons';
import { Select } from '../ui/Select';

const LABELS: Record<Ordering, string> = {
  name: 'Name (A–Z)',
  '-average_rating': 'Highest rated',
  average_rating: 'Lowest rated',
  '-review_count': 'Most reviews',
  review_count: 'Fewest reviews',
};

const OPTIONS = ORDERINGS.map((value) => ({ value, label: LABELS[value] }));

interface SortControlProps {
  value: Ordering;
  onChange: (ordering: Ordering) => void;
}

/** Choose the order the brands are listed in. */
export function SortControl({ value, onChange }: SortControlProps) {
  return (
    <Select
      label="Sort by"
      icon={<SortIcon />}
      value={value}
      options={OPTIONS}
      onChange={onChange}
      align="end"
      compact
      sheet
    />
  );
}
