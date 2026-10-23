import type { RefObject } from 'react';

import { CloseIcon } from './icons';

export interface Tag {
  key: string;
  label: string;
}

interface TagListProps {
  tags: readonly Tag[];
  /** Names the list for screen readers ("Active industry filters"). */
  label: string;
  onRemove: (key: string) => void;
  onClear?: () => void;
  /** The remove button's accessible name; defaults to "Remove <label>". */
  removeLabel?: (tag: Tag) => string;
  /** For moving focus to a remove button after one is gone. */
  listRef?: RefObject<HTMLUListElement | null>;
  className?: string;
}

/** Removable tags, with an optional Clear all link. */
export function TagList({
  tags,
  label,
  onRemove,
  onClear,
  removeLabel = (tag) => `Remove ${tag.label}`,
  listRef,
  className,
}: TagListProps) {
  return (
    <div className={['tags', className].filter(Boolean).join(' ')}>
      <ul aria-label={label} ref={listRef}>
        {tags.map((tag) => (
          <li key={tag.key} className="tag">
            {tag.label}
            <button
              type="button"
              className="remove"
              aria-label={removeLabel(tag)}
              onClick={() => onRemove(tag.key)}
            >
              <CloseIcon />
            </button>
          </li>
        ))}
      </ul>
      {onClear && (
        <button type="button" className="button link" onClick={onClear}>
          Clear all
        </button>
      )}
    </div>
  );
}
