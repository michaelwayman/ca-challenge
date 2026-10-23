import type { ReactNode } from 'react';

interface NoticeProps {
  /** An error is announced to screen readers as soon as it appears. */
  tone?: 'neutral' | 'error';
  /** A button under the message: Try again, Clear filters. */
  action?: { label: string; onClick: () => void };
  children: ReactNode;
}

/** A message in place of content: nothing found, or something went wrong. */
export function Notice({ tone = 'neutral', action, children }: NoticeProps) {
  return (
    <div
      className={`notice${tone === 'error' ? ' error' : ''}`}
      role={tone === 'error' ? 'alert' : undefined}
    >
      <p className="message">{children}</p>
      {action && (
        <button type="button" className="button" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}
